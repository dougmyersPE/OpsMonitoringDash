"""
Sports API poll worker — runs every 30 minutes via Celery Beat (RedBeat).

Steps:
1. For each sport, fetch games for today and yesterday from api-sports.io
2. Build a sport+date index of existing Events in DB
3. Fuzzy-match each game to an Event by team names + date
4. Update sports_api_status and recompute status_match on matched events
5. Enqueue send_alerts and update_event_status when a mismatch is detected
6. Publish SSE updates, write heartbeat
"""

import asyncio
import json as _json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher

import redis as _sync_redis
import structlog
from sqlalchemy import select

from app.clients.sports_api import SportsApiClient, PX_TO_API_SPORTS
from app.core.config import settings
from app.db.sync_session import SyncSessionLocal
from app.models.event import Event
from app.monitoring.mismatch_detector import compute_is_flagged, compute_status_match, get_expected_px_status
from app.workers.celery_app import celery_app
from app.workers.update_event_status import run as update_status_task

log = structlog.get_logger()

FUZZY_THRESHOLD = 0.80

# Common college mascot words to strip when doing fallback matching.
# Sports API often drops the mascot ("Michigan" vs "Michigan Wolverines").
_MASCOT_WORDS = {
    "aggies","aztecs","bearcats","bears","bengals","bobcats","broncos","broncs",
    "bruins","buckeyes","bulldogs","bulls","cardinals","cavaliers","chanticleers",
    "colonels","cougars","crimson tide","cyclones","ducks","eagles","falcons",
    "fighting illini","flyers","gators","golden eagles","golden flashes",
    "golden gophers","hawkeyes","hokies","hoosiers","hornets","hurricanes",
    "huskies","jayhawks","jaspers","longhorns","lumberjacks","mocs","monarchs",
    "mountaineers","mustangs","owls","panthers","peacocks","pioneers","ramblers",
    "razorbacks","red storm","roadrunners","rockets","runnin bulldogs","saints",
    "scarlet knights","seahawks","seminoles","sooners","spartans","tar heels",
    "terrapins","tigers","titans","trojans","volunteers","vulcans","wildcats",
    "wolfpack","wolverines","yellow jackets","zips","gaels","friars","dons",
    "tritons","sycamores","billikens","musketeers","beacons","skyhawks",
    "running bulldogs","blue devils","demon deacons","golden bears","fighting irish",
    "anteaters","banana slugs","blue hens","camels","cardinals","colonials",
    "comets","crusaders","explorers","flyers","friars","greyhounds","hatters",
    "highlanders","lakers","leopards","lions","mavericks","monarchs","patriots",
    "penguins","pilots","quakers","rams","rattlers","red foxes","retrievers",
    "riverhawks","scorpions","seawolves","spiders","statesmen","toreros",
    # Additional mascots confirmed missing from Sports API data
    "boilermakers","bison","braves","catamounts","dolphins","dragons","gamecocks",
    "grizzlies","hilltoppers","jackrabbits","keydets","knights","leathernecks",
    "matadors","miners","phoenix","rainbow warriors","redhawks","roos","texans",
    "tommies","trailblazers","vandals","warriors","warhawks",
}

def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _strip_mascot(name: str) -> str:
    """Return team name with trailing mascot word(s) removed.

    'Michigan Wolverines' -> 'Michigan'
    'Gardner-Webb Runnin Bulldogs' -> 'Gardner-Webb'
    Falls back to original name if no mascot word found.
    """
    lower = name.lower().strip()
    # Try multi-word mascots first (longest match wins)
    for mascot in sorted(_MASCOT_WORDS, key=len, reverse=True):
        if lower.endswith(mascot):
            stripped = name[:-(len(mascot))].strip().rstrip("-").strip()
            if stripped:
                return stripped
    return name


def _best_similarity(db_name: str, api_name: str) -> float:
    """Return highest similarity score across multiple matching strategies.

    Sports API often returns only the school name without the mascot
    (e.g. "Montana" for "Montana Grizzlies", "Western Kentucky" for
    "Western Kentucky Hilltoppers"). Three strategies handle this:

    1. Full name direct similarity
    2. Mascot-stripped DB name vs API name
    3. Prefix: API name is a word-boundary prefix of DB name
    4. Token containment: every word of the API name appears in the DB name
       — naturally prevents same-mascot cross-matching because all tokens
       must match ("Yale Bulldogs" won't match "Bryant Bulldogs" since
       "yale" is absent from {"bryant", "bulldogs"}).

    Sports API appends "W" for women's teams; that suffix is ignored.
    """
    full = _similarity(db_name, api_name)
    if full >= FUZZY_THRESHOLD:
        return full

    best = full

    # Strategy 2: strip known mascot word from DB name then compare
    stripped = _strip_mascot(db_name)
    if stripped != db_name:
        best = max(best, _similarity(stripped, api_name))
        if best >= FUZZY_THRESHOLD:
            return best

    db_lower = db_name.lower().strip()
    api_lower = api_name.lower().strip()

    # Strategy 3: prefix match
    if len(api_lower) >= 4 and db_lower.startswith(api_lower + " "):
        return 1.0

    # Strategy 4: token containment
    # Strip trailing periods and the Sports API women's suffix ("W") before comparing.
    api_tokens = [t.rstrip(".'") for t in api_lower.split() if t not in ("w",)]
    db_tokens = {t.rstrip(".'") for t in db_lower.split()}
    # Require at least one substantial token to avoid single-letter false positives.
    if api_tokens and any(len(t) >= 4 for t in api_tokens):
        if all(t in db_tokens for t in api_tokens):
            return 1.0

    return best


def _normalize_sport(sport: str) -> str:
    return sport.strip().lower()


def _publish_update(entity_id: str) -> None:
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.publish("prophet:updates", _json.dumps({"type": "event_updated", "entity_id": entity_id}))


def _write_heartbeat() -> None:
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.set("worker:heartbeat:poll_sports_api", "1", ex=max(settings.POLL_INTERVAL_SPORTS_API * 3, 600))


def _increment_call_counter(worker_name: str) -> None:
    """Atomically increment today's API call counter for this worker.

    Key: api_calls:{worker_name}:{YYYY-MM-DD}
    TTL: 8 days (set only on first write so old keys expire automatically).
    Uses Redis INCR (atomic) -- safe under --concurrency=6.
    """
    from datetime import date
    today = date.today().isoformat()
    key = f"api_calls:{worker_name}:{today}"
    r = _sync_redis.from_url(settings.REDIS_URL)
    count = r.incr(key)
    if count == 1:
        r.expire(key, 8 * 86400)


@celery_app.task(name="app.workers.poll_sports_api.run", bind=True, max_retries=3)
def run(self):
    """Fetch Sports API scores and update sports_api_status on matched events."""
    if not settings.SPORTS_API_KEY:
        log.warning("poll_sports_api_skipped", reason="SPORTS_API_KEY not configured")
        return

    from app.workers.source_toggle import is_source_enabled, clear_source_and_recompute
    if not is_source_enabled("sports_api"):
        clear_source_and_recompute("sports_api")
        _write_heartbeat()
        log.info("poll_sports_api_skipped", reason="source disabled")
        return

    now = datetime.now(timezone.utc)
    today = now.date()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    # ------------------------------------------------------------------ #
    # 1. Determine which sports to poll based on events in DB             #
    # ------------------------------------------------------------------ #
    with SyncSessionLocal() as session:
        events_in_db = session.execute(
            select(Event).where(
                Event.home_team.isnot(None),
                Event.away_team.isnot(None),
                Event.scheduled_start.isnot(None),
            )
        ).scalars().all()

    if not events_in_db:
        _write_heartbeat()
        return

    # Collect unique normalized sports from DB events that have an API-Sports mapping
    db_sports: set[str] = set()
    for ev in events_in_db:
        normalized = _normalize_sport(ev.sport or "")
        api_sport = PX_TO_API_SPORTS.get(normalized)
        if api_sport:
            db_sports.add(api_sport)

    if not db_sports:
        log.info("poll_sports_api_no_mapped_sports")
        _write_heartbeat()
        return

    # ------------------------------------------------------------------ #
    # 2. Fetch games for each relevant sport                               #
    # ------------------------------------------------------------------ #
    async def _fetch_all() -> list[dict]:
        results: list[dict] = []
        async with SportsApiClient(settings.SPORTS_API_KEY) as client:
            for api_sport in db_sports:
                for game_date in (yesterday, today, tomorrow):
                    games = await client.get_games(api_sport, game_date)
                    results.extend(games)
        return results

    try:
        all_games = asyncio.run(_fetch_all())
    except Exception as exc:
        log.error("poll_sports_api_fetch_failed", error=str(exc), retry=self.request.retries)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    log.info("sports_api_games_fetched", total=len(all_games))

    if not all_games:
        _write_heartbeat()
        return

    # ------------------------------------------------------------------ #
    # 3. Match games to events and update sports_api_status               #
    # ------------------------------------------------------------------ #
    updated = 0
    unmatched = 0

    with SyncSessionLocal() as session:
        candidates = session.execute(
            select(Event).where(
                Event.home_team.isnot(None),
                Event.away_team.isnot(None),
                Event.scheduled_start.isnot(None),
            )
        ).scalars().all()

        # Index by (normalized_sport, date)
        index: dict[tuple[str, date], list[Event]] = defaultdict(list)
        for event in candidates:
            key = (_normalize_sport(event.sport), event.scheduled_start.date())  # type: ignore[union-attr]
            index[key].append(event)

        for game in all_games:
            home = game.get("home_team", "")
            away = game.get("away_team", "")
            api_sport = game.get("sport", "")
            date_str = game.get("date_str", "")
            status_short = game.get("status_short", "")

            if not home or not away or not date_str:
                continue

            try:
                game_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
            except Exception:
                continue

            px_sport = _normalize_sport(api_sport)

            match_candidates = (
                index.get((px_sport, game_date), [])
                + index.get((px_sport, game_date - timedelta(days=1)), [])
                + index.get((px_sport, game_date + timedelta(days=1)), [])
            )

            # Also try common ProphetX sport name variants
            for px_variant, mapped in PX_TO_API_SPORTS.items():
                if mapped == api_sport and px_variant != px_sport:
                    match_candidates += (
                        index.get((_normalize_sport(px_variant), game_date), [])
                        + index.get((_normalize_sport(px_variant), game_date - timedelta(days=1)), [])
                        + index.get((_normalize_sport(px_variant), game_date + timedelta(days=1)), [])
                    )

            best_match: Event | None = None
            best_score = 0.0

            # Parse the game datetime once for time-proximity scoring
            try:
                game_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except Exception:
                game_dt = datetime(game_date.year, game_date.month, game_date.day, 12, 0, tzinfo=timezone.utc)

            for event in match_candidates:
                home_sim = _best_similarity(event.home_team or "", home)
                away_sim = _best_similarity(event.away_team or "", away)
                name_score = (home_sim + away_sim) / 2

                # Time proximity bonus: 0.0–0.15 extra score based on how
                # close the scheduled times are. This breaks ties when the
                # same teams play on consecutive days — the closer game wins.
                time_bonus = 0.0
                if event.scheduled_start and game_dt:
                    delta_hours = abs((event.scheduled_start - game_dt).total_seconds()) / 3600
                    if delta_hours <= 1:
                        time_bonus = 0.15
                    elif delta_hours <= 6:
                        time_bonus = 0.10
                    elif delta_hours <= 12:
                        time_bonus = 0.05

                score = name_score + time_bonus
                if score > best_score:
                    best_score = score
                    best_match = event

            if best_match and best_score >= FUZZY_THRESHOLD:
                # Same-date guard: the Sports API game date must match the ProphetX
                # event's scheduled date. The ±1-day index window exists only to
                # handle UTC/timezone offsets (a game at 11pm ET on Mar 1 is Mar 2
                # UTC), so we allow a ±1 calendar day tolerance but enforce that the
                # actual start times are within 12 hours. Without this, a finished
                # game on day N can fuzzy-match a future event on day N+1 when the
                # same teams play consecutive days (the root cause of false-positive
                # critical alerts).
                if best_match.scheduled_start:
                    hours_apart = abs(
                        (best_match.scheduled_start - game_dt).total_seconds()
                    ) / 3600
                    if hours_apart > 6:
                        unmatched += 1
                        log.debug(
                            "sports_api_time_too_far",
                            home=home, away=away,
                            game_date=str(game_date),
                            scheduled_start=str(best_match.scheduled_start),
                            hours_apart=round(hours_apart, 1),
                        )
                        continue

                best_match.sports_api_status = status_short
                new_status_match = compute_status_match(
                    best_match.prophetx_status,
                    best_match.odds_api_status,
                    status_short,
                    best_match.sdio_status,
                    best_match.espn_status,
                    best_match.oddsblaze_status,
                )
                best_match.status_match = new_status_match
                best_match.last_real_world_poll = now
                # Recompute flag from current source statuses
                was_flagged = best_match.is_flagged
                best_match.is_flagged = compute_is_flagged(
                    best_match.sdio_status,
                    best_match.sports_api_status,
                )
                if best_match.is_flagged and not was_flagged:
                    log.warning(
                        "event_flagged",
                        event_id=str(best_match.id),
                        sports_api_status=status_short,
                    )
                updated += 1
                _publish_update(str(best_match.id))
                if not new_status_match:
                    expected_px_status = get_expected_px_status(status_short)
                    if expected_px_status is not None:
                        update_status_task.delay(
                            event_id=str(best_match.id),
                            target_status=expected_px_status,
                            actor="system",
                        )
                log.debug(
                    "sports_api_event_matched",
                    event_id=str(best_match.id),
                    home=home,
                    away=away,
                    status=status_short,
                    match_score=round(best_score, 3),
                )
            else:
                unmatched += 1
                log.debug(
                    "sports_api_event_unmatched",
                    home=home,
                    away=away,
                    sport=api_sport,
                    best_score=round(best_score, 3) if best_match else 0.0,
                )

        session.commit()

    _write_heartbeat()
    _increment_call_counter("poll_sports_api")

    log.info(
        "poll_sports_api_complete",
        games_fetched=len(all_games),
        events_updated=updated,
        unmatched=unmatched,
    )
