"""
ESPN poll worker — runs every 10 minutes via Celery Beat (RedBeat).

Covers all major sports via ESPN's unofficial scoreboard API (no auth required):
  Team sports:   NBA, NFL, MLB, NHL, NCAAB, NCAAF
  Soccer:        MLS, EPL, La Liga, Bundesliga, Serie A, Ligue 1, UCL, UEL
  Individual:    Tennis (ATP/WTA), MMA (UFC), Golf (PGA)

Steps:
1. Identify which ESPN sports are relevant based on events in DB
2. Fetch scoreboards from ESPN unofficial API (no auth required)
3. Match each ESPN record to a ProphetX event:
   - Tennis/MMA: fuzzy match by competitor names + date
   - Golf: fuzzy match by tournament name
4. Update espn_status and recompute status_match on matched events
5. Enqueue send_alerts when a mismatch is detected
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

from app.clients.espn_api import EspnApiClient, PX_TO_ESPN
from app.core.config import settings
from app.db.sync_session import SyncSessionLocal
from app.models.event import Event
from app.monitoring.mismatch_detector import compute_status_match
from app.workers.celery_app import celery_app

log = structlog.get_logger()

FUZZY_THRESHOLD = 0.75  # Slightly lower than Sports API — athlete names vary more


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _normalize_sport(sport: str) -> str:
    return sport.strip().lower()


def _publish_update(entity_id: str) -> None:
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.publish("prophet:updates", _json.dumps({"type": "event_updated", "entity_id": entity_id}))


def _write_heartbeat() -> None:
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.set("worker:heartbeat:poll_espn", "1", ex=max(settings.POLL_INTERVAL_ESPN * 3, 600))


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


@celery_app.task(name="app.workers.poll_espn.run", bind=True, max_retries=3)
def run(self):
    """Fetch ESPN scoreboards and update espn_status on matched events."""
    from app.workers.source_toggle import is_source_enabled, clear_source_and_recompute
    if not is_source_enabled("espn"):
        clear_source_and_recompute("espn")
        _write_heartbeat()
        log.info("poll_espn_skipped", reason="source disabled")
        return

    now = datetime.now(timezone.utc)
    today = now.date()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    # ------------------------------------------------------------------ #
    # 1. Determine which ESPN sports are needed from DB events             #
    # ------------------------------------------------------------------ #
    with SyncSessionLocal() as session:
        events_in_db = session.execute(
            select(Event).where(Event.sport.isnot(None))
        ).scalars().all()

    if not events_in_db:
        _write_heartbeat()
        return

    # Collect ESPN endpoint keys for sports that have events in the DB
    needed_endpoints: set[str] = set()
    for ev in events_in_db:
        normalized = _normalize_sport(ev.sport or "")
        for endpoint_key in PX_TO_ESPN.get(normalized, []):
            needed_endpoints.add(endpoint_key)

    if not needed_endpoints:
        log.info("poll_espn_no_mapped_sports")
        _write_heartbeat()
        return

    # ------------------------------------------------------------------ #
    # 2. Fetch scoreboards from ESPN                                       #
    # ------------------------------------------------------------------ #
    async def _fetch_all() -> list[dict]:
        results: list[dict] = []
        async with EspnApiClient() as client:
            for endpoint_key in needed_endpoints:
                for fetch_date in (yesterday, today, tomorrow):
                    date_str = fetch_date.strftime("%Y%m%d")
                    records = await client.get_scoreboard(endpoint_key, date=date_str)
                    results.extend(records)
        return results

    try:
        all_records = asyncio.run(_fetch_all())
    except Exception as exc:
        log.error("poll_espn_fetch_failed", error=str(exc), retry=self.request.retries)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    log.info("espn_records_fetched", total=len(all_records))

    if not all_records:
        _write_heartbeat()
        return

    # ------------------------------------------------------------------ #
    # 3. Match records to events and update espn_status                   #
    # ------------------------------------------------------------------ #
    updated = 0
    unmatched = 0

    with SyncSessionLocal() as session:
        candidates = session.execute(
            select(Event).where(Event.sport.isnot(None))
        ).scalars().all()

        # Index by (normalized_sport, date) for head-to-head sports
        index: dict[tuple[str, date], list[Event]] = defaultdict(list)
        for event in candidates:
            if event.scheduled_start:
                key = (_normalize_sport(event.sport), event.scheduled_start.date())
                index[key].append(event)

        for record in all_records:
            endpoint = record.get("endpoint", "")
            status_state = record.get("status_state", "pre")
            event_date_str = record.get("date", "")
            is_tournament = record.get("is_tournament", False)

            if not event_date_str:
                continue

            try:
                record_date = date.fromisoformat(event_date_str)
            except Exception:
                continue

            # Determine which ProphetX sport names map to this endpoint
            px_sports = [px for px, endpoints in PX_TO_ESPN.items() if endpoint in endpoints]

            tournament_matches: list[Event] = []

            if is_tournament:
                # Golf: match by tournament name against event.name.
                # ProphetX creates multiple events per tournament (one per market type), e.g.:
                #   "2026 Cognizant Classic in The Palm Beaches - Tournament Winner"
                #   "2026 Cognizant Classic in The Palm Beaches - Top 5 Finish"
                # ESPN returns just the tournament name:
                #   "Cognizant Classic in The Palm Beaches"
                # Update ALL ProphetX events whose name contains the ESPN tournament name.
                event_name = record.get("event_name", "")
                if not event_name:
                    continue

                espn_lower = event_name.lower()
                tournament_matches: list[Event] = []
                fuzzy_best: Event | None = None
                fuzzy_best_score = 0.0

                for event in candidates:
                    if _normalize_sport(event.sport or "") not in px_sports:
                        continue
                    px_lower = (event.name or "").lower()
                    if espn_lower in px_lower:
                        tournament_matches.append(event)
                    else:
                        score = _similarity(event.name, event_name)
                        if score > fuzzy_best_score:
                            fuzzy_best_score = score
                            fuzzy_best = event

                # Prefer substring matches; fall back to fuzzy best
                if tournament_matches:
                    best_match = tournament_matches[0]  # used for alert/log
                    best_score = 1.0
                else:
                    best_match = fuzzy_best
                    best_score = fuzzy_best_score

                match_threshold = FUZZY_THRESHOLD
            else:
                # Tennis / MMA: match by competitor names + date
                home = record.get("home_name", "")
                away = record.get("away_name", "")
                if not home or not away:
                    continue

                date_candidates: list[Event] = []
                for px_sport in px_sports:
                    for delta in (-1, 0, 1):
                        check_date = record_date + timedelta(days=delta)
                        date_candidates.extend(index.get((px_sport, check_date), []))

                best_match = None
                best_score = 0.0

                # Use actual ESPN event datetime for time-proximity scoring;
                # fall back to noon UTC only if the full datetime wasn't parsed
                record_dt = record.get("datetime") or datetime(record_date.year, record_date.month, record_date.day, 12, 0, tzinfo=timezone.utc)

                for event in date_candidates:
                    if not event.home_team or not event.away_team:
                        continue
                    # Try both orderings — MMA/Tennis home/away conventions differ
                    # between providers, so check forward and reversed and take the best.
                    forward = (_similarity(event.home_team, home) + _similarity(event.away_team, away)) / 2
                    reversed_ = (_similarity(event.home_team, away) + _similarity(event.away_team, home)) / 2
                    name_score = max(forward, reversed_)

                    # Time proximity bonus to prefer closer matches (same logic as Sports API worker)
                    time_bonus = 0.0
                    if event.scheduled_start:
                        delta_hours = abs((event.scheduled_start - record_dt).total_seconds()) / 3600
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

                match_threshold = FUZZY_THRESHOLD

            # 12-hour guard for non-tournament matches — reject cross-day mismatches
            if (
                not is_tournament
                and best_match
                and best_score >= match_threshold
                and best_match.scheduled_start
            ):
                hours_apart = abs((best_match.scheduled_start - record_dt).total_seconds()) / 3600
                if hours_apart > 6:
                    log.debug(
                        "espn_time_too_far",
                        home=record.get("home_name", ""),
                        away=record.get("away_name", ""),
                        record_date=str(record_date),
                        scheduled_start=str(best_match.scheduled_start),
                        hours_apart=round(hours_apart, 1),
                    )
                    unmatched += 1
                    continue

            # Build list of events to update — golf can match multiple markets per tournament
            if best_score >= match_threshold and best_match:
                to_update: list[Event] = tournament_matches if is_tournament and tournament_matches else [best_match]
            else:
                to_update = []

            if to_update:
                for event in to_update:
                    event.espn_status = status_state
                    new_status_match = compute_status_match(
                        event.prophetx_status,
                        event.odds_api_status,
                        event.sports_api_status,
                        event.sdio_status,
                        status_state,
                        event.oddsblaze_status,
                    )
                    event.status_match = new_status_match
                    event.last_real_world_poll = now
                    updated += 1
                    _publish_update(str(event.id))
                log.debug(
                    "espn_event_matched",
                    event_ids=[str(e.id) for e in to_update],
                    endpoint=endpoint,
                    status=status_state,
                    match_score=round(best_score, 3),
                )
            else:
                unmatched += 1
                log.debug(
                    "espn_event_unmatched",
                    home=record.get("home_name", ""),
                    away=record.get("away_name", ""),
                    event_name=record.get("event_name", ""),
                    endpoint=endpoint,
                    best_score=round(best_score, 3) if best_match else 0.0,
                )

        session.commit()

    _write_heartbeat()
    _increment_call_counter("poll_espn")

    log.info(
        "poll_espn_complete",
        records_fetched=len(all_records),
        events_updated=updated,
        unmatched=unmatched,
    )
