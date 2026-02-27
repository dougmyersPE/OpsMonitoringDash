"""
Sports API poll worker — runs every 30 minutes via Celery Beat (RedBeat).

Steps:
1. For each sport, fetch games for today and yesterday from api-sports.io
2. Build a sport+date index of existing Events in DB
3. Fuzzy-match each game to an Event by team names + date
4. Update sports_api_status and recompute status_match on matched events
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

from app.clients.sports_api import SportsApiClient, PX_TO_API_SPORTS
from app.core.config import settings
from app.db.sync_session import SyncSessionLocal
from app.models.event import Event
from app.monitoring.mismatch_detector import compute_status_match
from app.workers.celery_app import celery_app
from app.workers.send_alerts import run as send_alerts_task

log = structlog.get_logger()

FUZZY_THRESHOLD = 0.80


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _normalize_sport(sport: str) -> str:
    return sport.strip().lower()


def _publish_update(entity_id: str) -> None:
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.publish("prophet:updates", _json.dumps({"type": "event_updated", "entity_id": entity_id}))


def _write_heartbeat() -> None:
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.set("worker:heartbeat:poll_sports_api", "1", ex=1800)  # 30-min TTL matches schedule


@celery_app.task(name="app.workers.poll_sports_api.run", bind=True, max_retries=3)
def run(self):
    """Fetch Sports API scores and update sports_api_status on matched events."""
    if not settings.SPORTS_API_KEY:
        log.warning("poll_sports_api_skipped", reason="SPORTS_API_KEY not configured")
        return

    now = datetime.now(timezone.utc)
    today = now.date()
    yesterday = today - timedelta(days=1)

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
                for game_date in (today, yesterday):
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

            for event in match_candidates:
                home_sim = _similarity(event.home_team or "", home)
                away_sim = _similarity(event.away_team or "", away)
                score = (home_sim + away_sim) / 2
                if score > best_score:
                    best_score = score
                    best_match = event

            if best_match and best_score >= FUZZY_THRESHOLD:
                best_match.sports_api_status = status_short
                new_status_match = compute_status_match(
                    best_match.prophetx_status,
                    best_match.odds_api_status,
                    status_short,
                    best_match.sdio_status,
                )
                best_match.status_match = new_status_match
                best_match.last_real_world_poll = now
                updated += 1
                _publish_update(str(best_match.id))
                if not new_status_match:
                    send_alerts_task.delay(
                        alert_type="status_mismatch",
                        entity_type="event",
                        entity_id=str(best_match.id),
                        message=(
                            f"Status mismatch: ProphetX={best_match.prophetx_status}, "
                            f"Sports API={status_short} "
                            f"({best_match.away_team} @ {best_match.home_team})"
                        ),
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

    log.info(
        "poll_sports_api_complete",
        games_fetched=len(all_games),
        events_updated=updated,
        unmatched=unmatched,
    )
