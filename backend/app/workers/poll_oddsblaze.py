"""
OddsBlaze poll worker — runs every 2 minutes via Celery Beat (RedBeat).

Steps:
1. Check ODDSBLAZE_API_KEY is configured and source is enabled
2. Determine which OddsBlaze leagues are relevant based on active sports in DB
3. Fetch schedule for each relevant league
4. Derive status from each event (live/scheduled/final)
5. Fuzzy-match each OddsBlaze event to a ProphetX event by team names + date
6. Update oddsblaze_status and recompute status_match on matched events
7. Publish SSE updates, write heartbeat
"""

import asyncio
import json as _json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher

import redis as _sync_redis
import structlog
from sqlalchemy import select

from app.clients.oddsblaze_api import OddsBlazeClient, LEAGUE_MAP
from app.core.config import settings
from app.db.sync_session import SyncSessionLocal
from app.models.event import Event
from app.monitoring.mismatch_detector import compute_status_match
from app.workers.celery_app import celery_app

log = structlog.get_logger()

FUZZY_THRESHOLD = 0.80  # Both team names must average at or above this to count as a match


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _normalize_sport(sport: str) -> str:
    return sport.strip().lower()


def _derive_status(event: dict, now: datetime) -> str:
    """Derive a canonical status string from an OddsBlaze event dict.

    OddsBlaze provides a `live` boolean:
      - live=True  -> event is in progress
      - live=False -> either scheduled (future) or final (past)
    We use the event `date` field (ISO8601) to distinguish scheduled vs final.
    Events more than 3 hours past their start time are treated as final.
    """
    if event.get("live"):
        return "live"

    date_raw = event.get("date")
    if date_raw:
        try:
            event_dt = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
            if event_dt.tzinfo is None:
                event_dt = event_dt.replace(tzinfo=timezone.utc)
            if now - event_dt > timedelta(hours=3):
                return "final"
        except Exception:
            pass

    return "scheduled"


def _publish_update(entity_id: str) -> None:
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.publish("prophet:updates", _json.dumps({"type": "event_updated", "entity_id": entity_id}))


def _write_heartbeat() -> None:
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.set(
        "worker:heartbeat:poll_oddsblaze",
        "1",
        ex=max(settings.POLL_INTERVAL_ODDSBLAZE * 3, 600),
    )


def _increment_call_counter(worker_name: str) -> None:
    """Atomically increment today's API call counter for this worker.

    Key: api_calls:{worker_name}:{YYYY-MM-DD}
    TTL: 8 days (set only on first write so old keys expire automatically).
    Uses Redis INCR (atomic) -- safe under --concurrency=6.
    """
    today = date.today().isoformat()
    key = f"api_calls:{worker_name}:{today}"
    r = _sync_redis.from_url(settings.REDIS_URL)
    count = r.incr(key)
    if count == 1:
        r.expire(key, 8 * 86400)


@celery_app.task(name="app.workers.poll_oddsblaze.run", bind=True, max_retries=3)
def run(self):
    """Fetch OddsBlaze schedules and update oddsblaze_status on matched events."""
    if not settings.ODDSBLAZE_API_KEY:
        log.warning("poll_oddsblaze_skipped", reason="ODDSBLAZE_API_KEY not configured")
        return

    from app.workers.source_toggle import is_source_enabled, clear_source_and_recompute
    if not is_source_enabled("oddsblaze"):
        clear_source_and_recompute("oddsblaze")
        _write_heartbeat()
        log.info("poll_oddsblaze_skipped", reason="source disabled")
        return

    now = datetime.now(timezone.utc)

    # ------------------------------------------------------------------ #
    # 1. Determine which leagues to poll based on active sports in DB      #
    # ------------------------------------------------------------------ #
    with SyncSessionLocal() as session:
        active_sports = {
            _normalize_sport(row[0])
            for row in session.execute(
                select(Event.sport).where(Event.sport.isnot(None)).distinct()
            ).all()
        }

    relevant_leagues: list[tuple[str, str]] = []  # (prophetx_sport, league_id)
    for prophetx_sport, league_ids in LEAGUE_MAP.items():
        if prophetx_sport in active_sports:
            for league_id in league_ids:
                relevant_leagues.append((prophetx_sport, league_id))

    if not relevant_leagues:
        log.info("poll_oddsblaze_no_active_sports")
        _write_heartbeat()
        return

    log.info(
        "oddsblaze_leagues_to_fetch",
        count=len(relevant_leagues),
        leagues=[lid for _, lid in relevant_leagues],
    )

    # ------------------------------------------------------------------ #
    # 2. Fetch schedules for relevant leagues                              #
    # ------------------------------------------------------------------ #
    async def _fetch_all() -> list[dict]:
        results: list[dict] = []
        async with OddsBlazeClient() as client:
            for prophetx_sport, league_id in relevant_leagues:
                try:
                    events = await client.get_schedule(league_id)
                    for ev in events:
                        ev["_prophetx_sport"] = prophetx_sport
                    results.extend(events)
                except Exception as exc:
                    log.warning(
                        "oddsblaze_league_fetch_failed",
                        league_id=league_id,
                        error=str(exc),
                    )
        return results

    try:
        all_events = asyncio.run(_fetch_all())
    except Exception as exc:
        log.error("poll_oddsblaze_fetch_failed", error=str(exc), retry=self.request.retries)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    log.info("oddsblaze_events_fetched", total=len(all_events))

    if not all_events:
        _write_heartbeat()
        return

    # ------------------------------------------------------------------ #
    # 3. Load DB events and build sport+date index for matching            #
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

        # Index: (normalized_sport, date) -> list[Event]
        index: dict[tuple[str, date], list[Event]] = defaultdict(list)
        for event in candidates:
            key = (_normalize_sport(event.sport), event.scheduled_start.date())  # type: ignore[union-attr]
            index[key].append(event)

        # ------------------------------------------------------------------ #
        # 4. Match each OddsBlaze event to a ProphetX event                   #
        # ------------------------------------------------------------------ #
        for ob_event in all_events:
            teams = ob_event.get("teams", {})
            home = (teams.get("home") or {}).get("name") or ""
            away = (teams.get("away") or {}).get("name") or ""
            prophetx_sport = ob_event.get("_prophetx_sport", "")
            date_raw = ob_event.get("date")

            if not home or not away or not date_raw:
                continue

            try:
                event_dt = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
                if event_dt.tzinfo is None:
                    event_dt = event_dt.replace(tzinfo=timezone.utc)
                event_date = event_dt.date()
            except Exception:
                continue

            derived_status = _derive_status(ob_event, now)

            # Check same date and ±1 day to absorb timezone differences
            match_candidates = (
                index.get((prophetx_sport, event_date), [])
                + index.get((prophetx_sport, event_date - timedelta(days=1)), [])
                + index.get((prophetx_sport, event_date + timedelta(days=1)), [])
            )

            best_match: Event | None = None
            best_score = 0.0

            for db_event in match_candidates:
                forward = (
                    _similarity(db_event.home_team or "", home)
                    + _similarity(db_event.away_team or "", away)
                ) / 2
                reversed_ = (
                    _similarity(db_event.home_team or "", away)
                    + _similarity(db_event.away_team or "", home)
                ) / 2
                name_score = max(forward, reversed_)

                # Time proximity bonus — prefer closer matches
                time_bonus = 0.0
                if db_event.scheduled_start:
                    delta_hours = abs((db_event.scheduled_start - event_dt).total_seconds()) / 3600
                    if delta_hours <= 1:
                        time_bonus = 0.15
                    elif delta_hours <= 6:
                        time_bonus = 0.10
                    elif delta_hours <= 12:
                        time_bonus = 0.05

                score = name_score + time_bonus
                if score > best_score:
                    best_score = score
                    best_match = db_event

            if best_match and best_score >= FUZZY_THRESHOLD:
                # 12-hour guard — reject cross-day mismatches
                if best_match.scheduled_start:
                    hours_apart = abs((best_match.scheduled_start - event_dt).total_seconds()) / 3600
                    if hours_apart > 12:
                        unmatched += 1
                        log.debug(
                            "oddsblaze_time_too_far",
                            home=home,
                            away=away,
                            event_date=str(event_date),
                            scheduled_start=str(best_match.scheduled_start),
                            hours_apart=round(hours_apart, 1),
                        )
                        continue

                best_match.oddsblaze_status = derived_status
                new_status_match = compute_status_match(
                    best_match.prophetx_status,
                    best_match.odds_api_status,
                    best_match.sdio_status,
                    best_match.espn_status,
                    derived_status,
                )
                best_match.status_match = new_status_match
                best_match.last_real_world_poll = now
                updated += 1
                _publish_update(str(best_match.id))
                log.debug(
                    "oddsblaze_event_matched",
                    event_id=str(best_match.id),
                    home=home,
                    away=away,
                    status=derived_status,
                    match_score=round(best_score, 3),
                )
            else:
                unmatched += 1
                log.debug(
                    "oddsblaze_event_unmatched",
                    home=home,
                    away=away,
                    sport=prophetx_sport,
                    best_score=round(best_score, 3) if best_match else 0.0,
                )

        session.commit()

    # ------------------------------------------------------------------ #
    # 5. Heartbeat + summary                                               #
    # ------------------------------------------------------------------ #
    _write_heartbeat()
    _increment_call_counter("poll_oddsblaze")

    log.info(
        "poll_oddsblaze_complete",
        events_fetched=len(all_events),
        events_updated=updated,
        unmatched=unmatched,
    )
