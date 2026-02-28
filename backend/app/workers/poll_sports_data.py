"""
SportsDataIO poll worker — runs every 30 seconds via Celery Beat (RedBeat).

Steps:
1. Fetch games for today AND yesterday (avoids missed games spanning midnight)
2. Deduplicate by sdio_game_id, log per-sport counts
3. Load all ProphetX events from DB
4. Run EventMatcher for each ProphetX event against the SDIO game list
5. Upsert event_id_mappings; update Event.sdio_status, status_match, is_flagged
6. Detect mismatches (log WARNING); flag postponed/canceled (SYNC-02 — no write action)
7. Commit and log summary
"""

import asyncio
import json as _json
from datetime import date, datetime, timedelta, timezone

import redis as _sync_redis
import structlog
from sqlalchemy import select

from app.clients.sportsdataio import SPORTSDATAIO_SOCCER_BASE_URL, SportsDataIOClient
from app.db.redis import get_sync_redis
from app.db.sync_session import SyncSessionLocal
from app.models.event import Event
from app.models.event_id_mapping import EventIDMapping
from app.monitoring.event_matcher import EventMatcher
from app.monitoring.mismatch_detector import compute_is_flagged, compute_status_match, get_expected_px_status, is_mismatch
from app.workers.celery_app import celery_app
from app.workers.update_event_status import run as update_status_task

log = structlog.get_logger()


def _publish_update(update_type: str, entity_id: str) -> None:
    """Publish a state change to the SSE pub/sub channel."""
    from app.core.config import settings
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.publish("prophet:updates", _json.dumps({
        "type": update_type,
        "entity_id": entity_id,
    }))


def _write_heartbeat(worker_name: str) -> None:
    """Write worker heartbeat key — TTL is 3x poll interval so health check survives slight delays."""
    from app.core.config import settings
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.set(f"worker:heartbeat:{worker_name}", "1", ex=settings.POLL_INTERVAL_SPORTS_DATA * 3)

# Sports to poll — must match the subscription on the configured SPORTSDATAIO_API_KEY.
# URL path mapping (ncaab→cbb etc.) is handled in SportsDataIOClient.
SUPPORTED_SPORTS = ["nba", "nfl", "mlb", "nhl", "ncaab", "ncaaf", "soccer"]

# College/non-pro sports where SDIO returns team abbreviation codes (e.g. "TROY")
# rather than full names — team names are resolved via get_team_names() before matching.
ABBREV_SPORTS: set[str] = {"ncaab", "ncaaf"}

# Map SDIO logical sport names to ProphetX sport field values.
# ProphetX uses broad categories ("Basketball") for both pro and college.
SDIO_TO_PX_SPORT: dict[str, str] = {
    "nba":   "basketball",
    "nfl":   "american football",
    "mlb":   "baseball",
    "nhl":   "ice hockey",
    "ncaab": "basketball",
    "ncaaf": "american football",
    "soccer": "soccer",
}

# Redis key pattern for cached team name lookups.
# Teams don't change mid-season — stored with a 24h TTL so all worker
# processes share one fetch per day instead of fetching every 30 seconds.
_TEAM_NAMES_REDIS_KEY = "sdio:team_names:{sport}"
_TEAM_NAMES_TTL = 86400  # 24 hours

# Redis key for cached SDIO soccer competition data (id + name, 24h TTL).
# Format: [{"id": int, "name": str}, ...]
_SOCCER_COMPETITIONS_REDIS_KEY = "sdio:soccer_competition_data"
_SOCCER_COMPETITIONS_TTL = 86400  # 24 hours


@celery_app.task(name="app.workers.poll_sports_data.run", bind=True, max_retries=3)
def run(self):
    """Fetch SDIO games, run EventMatcher, detect mismatches and flag-only events."""
    # Query active ProphetX soccer tournament names so we can filter SDIO
    # competition queries to only competitions that ProphetX currently serves.
    px_soccer_leagues: set[str] = set()
    try:
        with SyncSessionLocal() as pre_session:
            rows = pre_session.execute(
                select(Event.league)
                .where(Event.sport == "Soccer")
                .where(Event.league.isnot(None))
                .distinct()
            ).scalars().all()
            px_soccer_leagues = set(rows)
    except Exception as _e:
        log.warning("sdio_px_soccer_leagues_query_failed", error=str(_e))

    # ------------------------------------------------------------------ #
    # 1–2. Fetch SportsDataIO games for yesterday, today, and tomorrow    #
    # ------------------------------------------------------------------ #
    try:
        async def _fetch():
            from contextlib import AsyncExitStack
            from app.core.config import settings as _settings
            _r = _sync_redis.from_url(_settings.REDIS_URL)

            today = date.today()
            yesterday = (today - timedelta(days=1)).isoformat()
            today = today.isoformat()
            tomorrow = (date.today() + timedelta(days=1)).isoformat()
            games: list[dict] = []
            sport_counts: dict[str, int] = {}

            async with AsyncExitStack() as stack:
                sdio = await stack.enter_async_context(SportsDataIOClient())
                # Soccer competitions list: v3, soccer-specific key
                sdio_soccer = await stack.enter_async_context(
                    SportsDataIOClient(api_key=_settings.SPORTSDATAIO_SOCCER_API_KEY)
                ) if _settings.SPORTSDATAIO_SOCCER_API_KEY else sdio
                # Soccer game data: v4, main key (GamesByDateFinal endpoint)
                sdio_soccer_games = await stack.enter_async_context(
                    SportsDataIOClient(base_url=SPORTSDATAIO_SOCCER_BASE_URL)
                )

                # Resolve team name lookups for college sports (abbreviation → full name).
                # Cached in Redis for 24h — team rosters don't change mid-season, and
                # Redis ensures all fork worker processes share one fetch per day.
                team_name_lookups: dict[str, dict[str, str]] = {}
                for sport in SUPPORTED_SPORTS:
                    if sport in ABBREV_SPORTS:
                        cache_key = _TEAM_NAMES_REDIS_KEY.format(sport=sport)
                        cached_raw = _r.get(cache_key)
                        if cached_raw:
                            team_name_lookups[sport] = _json.loads(cached_raw)
                            log.debug("sdio_team_names_cache_hit", sport=sport, count=len(team_name_lookups[sport]))
                        else:
                            try:
                                fetched = await sdio.get_team_names(sport)
                                _r.set(cache_key, _json.dumps(fetched), ex=_TEAM_NAMES_TTL)
                                team_name_lookups[sport] = fetched
                                log.info("sdio_team_names_loaded", sport=sport, count=len(fetched))
                            except Exception as e:
                                log.warning("sdio_team_names_failed", sport=sport, error=str(e))

                # Load SDIO soccer competition data (id + name, cached 24h), then
                # filter to only competitions matching active ProphetX tournament names.
                # This reduces 32 × 3 = 96 API calls/cycle to ~3 × 3 = 9.
                soccer_competition_ids: list[int] = []
                if "soccer" in SUPPORTED_SPORTS:
                    sdio_comp_data: list[dict] = []  # [{"id": int, "name": str}, ...]
                    cached_comps = _r.get(_SOCCER_COMPETITIONS_REDIS_KEY)
                    if cached_comps:
                        sdio_comp_data = _json.loads(cached_comps)
                        log.debug("sdio_soccer_competitions_cache_hit", count=len(sdio_comp_data))
                    else:
                        try:
                            comps = await sdio_soccer.get_soccer_competitions()
                            sdio_comp_data = [
                                {"id": c["CompetitionId"], "name": c.get("Name", "")}
                                for c in comps
                                if isinstance(c, dict) and c.get("CompetitionId")
                            ]
                            _r.set(_SOCCER_COMPETITIONS_REDIS_KEY, _json.dumps(sdio_comp_data), ex=_SOCCER_COMPETITIONS_TTL)
                            log.info("sdio_soccer_competitions_loaded", count=len(sdio_comp_data))
                        except Exception as e:
                            log.warning("sdio_soccer_competitions_failed", error=str(e))

                    if px_soccer_leagues and sdio_comp_data:
                        # Match ProphetX tournament names to SDIO competition names.
                        # Normalize: lowercase, alphanumeric only — handles spacing
                        # differences like "LaLiga" vs "La Liga".
                        def _norm(s: str) -> str:
                            return "".join(c for c in s.lower() if c.isalnum())

                        norm_px = {_norm(name) for name in px_soccer_leagues}
                        for comp in sdio_comp_data:
                            if _norm(comp["name"]) in norm_px:
                                soccer_competition_ids.append(comp["id"])
                        log.info(
                            "sdio_soccer_competitions_filtered",
                            px_leagues=sorted(px_soccer_leagues),
                            matched_sdio_ids=sorted(soccer_competition_ids),
                            total_available=len(sdio_comp_data),
                        )
                    elif not px_soccer_leagues:
                        log.debug("sdio_soccer_skipped_no_active_px_leagues")

                for sport in SUPPORTED_SPORTS:
                    count = 0
                    if sport == "soccer":
                        # Soccer requires per-competition queries
                        for game_date in [yesterday, today, tomorrow]:
                            for comp_id in soccer_competition_ids:
                                try:
                                    result = await sdio_soccer_games.get_soccer_games_by_date(comp_id, game_date)
                                    for g in result:
                                        if isinstance(g, dict):
                                            g["_sdio_sport"] = "soccer"
                                    games.extend(result)
                                    count += len(result)
                                except Exception as e:
                                    log.debug("sdio_soccer_comp_fetch_failed", comp_id=comp_id, date=game_date, error=str(e))
                    else:
                        client = sdio
                        for game_date in [yesterday, today, tomorrow]:
                            try:
                                result = await client.get_games_by_date_raw(sport, game_date)
                                if isinstance(result, list):
                                    # Tag each game with our logical sport name and, for college
                                    # sports, resolve team abbreviations to full names so
                                    # EventMatcher can fuzzy-match against ProphetX team names.
                                    lookup = team_name_lookups.get(sport, {})
                                    for g in result:
                                        if isinstance(g, dict):
                                            g["_sdio_sport"] = sport
                                            if lookup:
                                                home_abbr = str(g.get("HomeTeam") or "")
                                                away_abbr = str(g.get("AwayTeam") or "")
                                                g["_home_team_full"] = lookup.get(home_abbr, home_abbr)
                                                g["_away_team_full"] = lookup.get(away_abbr, away_abbr)
                                    games.extend(result)
                                    count += len(result)
                            except Exception as e:
                                log.warning(
                                    "sdio_fetch_failed",
                                    sport=sport,
                                    date=game_date,
                                    error=str(e),
                                )
                    sport_counts[sport] = count

            log.info("sdio_games_fetched", sport_counts=sport_counts)
            return games

        raw_games = asyncio.run(_fetch())

    except Exception as exc:
        log.error(
            "poll_sports_data_fetch_failed",
            error=str(exc),
            retry=self.request.retries,
        )
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    # Deduplicate by sdio_game_id
    seen_ids: set[str] = set()
    deduped_games: list[dict] = []
    for game in raw_games:
        if not isinstance(game, dict):
            continue
        gid = str(
            game.get("GameID")
            or game.get("GameId")   # SDIO soccer uses GameId
            or game.get("game_id")
            or game.get("id")
            or ""
        )
        if gid and gid not in seen_ids:
            seen_ids.add(gid)
            deduped_games.append(game)

    log.info("sdio_games_deduplicated", total=len(deduped_games))

    # ------------------------------------------------------------------ #
    # 3. Load ProphetX events from DB                                     #
    # ------------------------------------------------------------------ #
    now = datetime.now(timezone.utc)
    events_processed = 0
    matches_found = 0
    mismatches_found = 0
    flagged_count = 0

    with SyncSessionLocal() as session:
        px_events = session.execute(select(Event)).scalars().all()

        if not px_events:
            log.info("poll_sports_data_no_px_events")
            return

        # 3. Redis client for EventMatcher cache
        redis_client = get_sync_redis()
        matcher = EventMatcher(redis_client)

        # ------------------------------------------------------------------ #
        # 4–6. Match each ProphetX event against SDIO games                  #
        # ------------------------------------------------------------------ #

        # Build SDIO game dicts in EventMatcher format once
        sdio_games_normalized = []
        for game in deduped_games:
            sdio_game_id = str(
                game.get("GameID")
                or game.get("GameId")   # SDIO soccer uses GameId
                or game.get("game_id")
                or game.get("id")
                or ""
            )
            if not sdio_game_id:
                continue

            # For college sports, use full team names resolved from abbreviations.
            # For pro sports, HomeTeam/AwayTeam are already full names.
            home_team = (
                game.get("_home_team_full")
                or game.get("HomeTeam")
                or game.get("HomeTeamName")   # SDIO soccer
                or game.get("home_team")
                or game.get("home")
                or ""
            )
            away_team = (
                game.get("_away_team_full")
                or game.get("AwayTeam")
                or game.get("AwayTeamName")   # SDIO soccer
                or game.get("away_team")
                or game.get("away")
                or ""
            )
            # Use tagged logical sport, then map to ProphetX's sport convention
            # (e.g. "ncaab" → "basketball" to match ProphetX's "Basketball" events).
            sdio_sport = str(
                game.get("_sdio_sport")
                or game.get("sport")
                or game.get("League")
                or "unknown"
            ).lower()
            sport = SDIO_TO_PX_SPORT.get(sdio_sport, sdio_sport)

            # Parse start time — prefer DateTimeUTC (explicit UTC) over DateTime
            # (local time, varies by sport/timezone) to match ProphetX UTC timestamps.
            start_raw = (
                game.get("DateTimeUTC")
                or game.get("DateTimeUtc")    # SDIO soccer
                or game.get("DateTime")
                or game.get("scheduled_start")
                or game.get("start_time")
            )
            scheduled_start = None
            if start_raw:
                try:
                    scheduled_start = datetime.fromisoformat(str(start_raw))
                    if scheduled_start.tzinfo is None:
                        scheduled_start = scheduled_start.replace(tzinfo=timezone.utc)
                except Exception:
                    pass

            # SDIO status field
            sdio_status = str(
                game.get("Status")
                or game.get("status")
                or "Unknown"
            )

            # GlobalGameID (NBA/NFL/MLB/NHL/NCAAB/NCAAF) matches ProphetX event ID directly.
            # Store it so we can skip fuzzy matching when IDs align exactly.
            global_game_id = str(game.get("GlobalGameID") or "")

            sdio_games_normalized.append({
                "sdio_game_id": sdio_game_id,
                "global_game_id": global_game_id,
                "sport": sport,
                "home_team": str(home_team),
                "away_team": str(away_team),
                "scheduled_start": scheduled_start,
                "status": sdio_status,
            })

        for px_event in px_events:
            events_processed += 1

            px_event_dict = {
                "px_event_id": str(px_event.prophetx_event_id),
                "sport": str(px_event.sport or "").lower(),
                "home_team": str(px_event.home_team or ""),
                "away_team": str(px_event.away_team or ""),
                "scheduled_start": px_event.scheduled_start,
            }

            # Direct ID match: SDIO GlobalGameID == ProphetX event ID (NBA/NFL/MLB/NHL etc.)
            # Bypasses fuzzy matching entirely — SDIO abbreviations ("MEM", "DAL") score
            # poorly against ProphetX full names ("Memphis Grizzlies", "Dallas Mavericks").
            px_id = str(px_event.prophetx_event_id)
            direct_game = next(
                (g for g in sdio_games_normalized if g.get("global_game_id") == px_id),
                None,
            )
            if direct_game is not None:
                match = {
                    "sdio_game_id": direct_game["sdio_game_id"],
                    "confidence": 1.0,
                    "is_confirmed": True,
                }
            else:
                match = matcher.find_best_match(px_event_dict, sdio_games_normalized)

            if match is None:
                px_event.last_real_world_poll = now
                continue

            matches_found += 1
            sdio_game_id = match["sdio_game_id"]
            is_confirmed = match.get("is_confirmed", False)
            is_flagged_match = match.get("is_flagged", False)

            # Find matched SDIO game to get its status
            matched_game = next(
                (g for g in sdio_games_normalized if g["sdio_game_id"] == sdio_game_id),
                None,
            )
            sdio_status = matched_game["status"] if matched_game else "Unknown"

            # Upsert into event_id_mappings
            existing_mapping = session.execute(
                select(EventIDMapping).where(
                    EventIDMapping.prophetx_event_id == str(px_event.prophetx_event_id),
                    EventIDMapping.sdio_game_id == sdio_game_id,
                )
            ).scalar_one_or_none()

            if existing_mapping is None:
                mapping = EventIDMapping(
                    prophetx_event_id=str(px_event.prophetx_event_id),
                    sdio_game_id=sdio_game_id,
                    sport=str(px_event.sport or "unknown"),
                    confidence=match["confidence"],
                    is_confirmed=is_confirmed,
                    is_flagged=is_flagged_match,
                )
                session.add(mapping)
            else:
                existing_mapping.confidence = match["confidence"]
                existing_mapping.is_confirmed = is_confirmed
                existing_mapping.is_flagged = is_flagged_match

            # Update sdio_status from matched SDIO game
            if is_confirmed and matched_game:
                px_event.sdio_status = sdio_status

            # Mismatch detection — confirmed matches only.
            # Low-confidence matches (team names match but time is off) can span
            # different game days and must not affect status_match.
            if is_confirmed:
                px_status = str(px_event.prophetx_status or "")
                if is_mismatch(px_status, sdio_status):
                    px_event.status_match = False
                    log.warning(
                        "status_mismatch_detected",
                        event_id=str(px_event.id),
                        prophetx_event_id=str(px_event.prophetx_event_id),
                        px_status=px_status,
                        sdio_status=sdio_status,
                    )
                    mismatches_found += 1
                    _publish_update("mismatch_detected", str(px_event.id))
                    expected_px_status = get_expected_px_status(sdio_status)
                    if expected_px_status is not None:
                        update_status_task.delay(
                            event_id=str(px_event.id),
                            target_status=expected_px_status,
                            actor="system",
                        )
                else:
                    px_event.status_match = compute_status_match(
                        px_event.prophetx_status,
                        px_event.odds_api_status,
                        px_event.sports_api_status,
                        px_event.sdio_status,
                        px_event.espn_status,
                    )

            # Flag detection: derived from current source statuses each cycle.
            # Clears automatically when no source reports a flag-worthy status (SYNC-02).
            was_flagged = px_event.is_flagged
            px_event.is_flagged = compute_is_flagged(
                px_event.sdio_status,
                px_event.sports_api_status,
            )
            if px_event.is_flagged and not was_flagged:
                log.warning(
                    "event_flagged",
                    event_id=str(px_event.id),
                    prophetx_event_id=str(px_event.prophetx_event_id),
                    sdio_status=px_event.sdio_status,
                    sports_api_status=px_event.sports_api_status,
                )
                flagged_count += 1

            px_event.last_real_world_poll = now

        session.commit()

    # Write heartbeat key — read by /health/workers to confirm worker is alive
    _write_heartbeat("poll_sports_data")

    log.info(
        "poll_sports_data_complete",
        events=events_processed,
        matches=matches_found,
        mismatches=mismatches_found,
        flagged=flagged_count,
    )
