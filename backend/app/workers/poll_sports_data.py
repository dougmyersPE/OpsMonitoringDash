"""
SportsDataIO poll worker — runs every 30 seconds via Celery Beat (RedBeat).

Steps:
1. Fetch games for today AND yesterday (avoids missed games spanning midnight)
2. Deduplicate by sdio_game_id, log per-sport counts
3. Load all ProphetX events from DB
4. Run EventMatcher for each ProphetX event against the SDIO game list
5. Upsert event_id_mappings; update Event.real_world_status, status_match, is_flagged
6. Detect mismatches (log WARNING); flag postponed/canceled (SYNC-02 — no write action)
7. Commit and log summary
"""

import asyncio
from datetime import date, datetime, timedelta, timezone

import structlog
from sqlalchemy import select

from app.clients.sportsdataio import SportsDataIOClient
from app.db.redis import get_sync_redis
from app.db.sync_session import SyncSessionLocal
from app.models.event import Event
from app.models.event_id_mapping import EventIDMapping
from app.monitoring.event_matcher import EventMatcher
from app.monitoring.mismatch_detector import is_flag_only, is_mismatch
from app.workers.celery_app import celery_app

log = structlog.get_logger()

# Sports to poll — list reflects confirmed SportsDataIO subscription coverage.
# NFL/NCAAB/NCAAF return 404 (different URL format per RESEARCH.md); excluded here.
# Update this list after validating additional sport endpoints.
SUPPORTED_SPORTS = ["nba", "mlb", "nhl", "soccer"]


@celery_app.task(name="app.workers.poll_sports_data.run", bind=True, max_retries=3)
def run(self):
    """Fetch SDIO games, run EventMatcher, detect mismatches and flag-only events."""
    # ------------------------------------------------------------------ #
    # 1–2. Fetch SportsDataIO games for today AND yesterday               #
    # ------------------------------------------------------------------ #
    try:
        async def _fetch():
            async with SportsDataIOClient() as sdio:
                today = date.today().isoformat()
                yesterday = (date.today() - timedelta(days=1)).isoformat()
                games: list[dict] = []
                sport_counts: dict[str, int] = {}

                for sport in SUPPORTED_SPORTS:
                    count = 0
                    for game_date in [today, yesterday]:
                        try:
                            result = await sdio.get_games_by_date_raw(sport, game_date)
                            if isinstance(result, list):
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
                or game.get("game_id")
                or game.get("id")
                or ""
            )
            if not sdio_game_id:
                continue

            # SportsDataIO uses "HomeTeam"/"AwayTeam" for most sports
            home_team = (
                game.get("HomeTeam")
                or game.get("home_team")
                or game.get("home")
                or ""
            )
            away_team = (
                game.get("AwayTeam")
                or game.get("away_team")
                or game.get("away")
                or ""
            )
            sport = str(game.get("sport") or game.get("League") or "unknown").lower()

            # Parse start time
            start_raw = (
                game.get("DateTime")
                or game.get("DateTimeUTC")
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

            sdio_games_normalized.append({
                "sdio_game_id": sdio_game_id,
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

            # Update real_world_status from matched SDIO game
            if is_confirmed and matched_game:
                px_event.real_world_status = sdio_status

            # Mismatch detection
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
            else:
                px_event.status_match = True

            # Flag-only detection (SYNC-02: no write action for Postponed/Canceled etc.)
            if is_flag_only(sdio_status):
                px_event.is_flagged = True
                log.warning(
                    "event_flag_only_status",
                    event_id=str(px_event.id),
                    prophetx_event_id=str(px_event.prophetx_event_id),
                    sdio_status=sdio_status,
                )
                flagged_count += 1

            px_event.last_real_world_poll = now

        session.commit()

    log.info(
        "poll_sports_data_complete",
        events=events_processed,
        matches=matches_found,
        mismatches=mismatches_found,
        flagged=flagged_count,
    )
