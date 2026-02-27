"""
Odds API poll worker — runs every 10 minutes via Celery Beat (RedBeat).

Steps:
1. For each mapped sport, fetch scores from The Odds API
2. Build a sport+date index of existing Events in DB
3. Fuzzy-match each game result to an Event by team names + date
4. Update real_world_status and last_real_world_poll on matched events
5. Publish SSE updates, write heartbeat
"""

import asyncio
import json as _json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher

import redis as _sync_redis
import structlog
from sqlalchemy import select

from app.clients.odds_api import OddsAPIClient, SPORT_KEY_MAP
from app.core.config import settings
from app.db.sync_session import SyncSessionLocal
from app.models.event import Event
from app.monitoring.mismatch_detector import compute_status_match
from app.workers.celery_app import celery_app
from app.workers.send_alerts import run as send_alerts_task

log = structlog.get_logger()

FUZZY_THRESHOLD = 0.80  # Both team names must average at or above this to count as a match


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _normalize_sport(sport: str) -> str:
    return sport.strip().lower()


def _derive_status(game: dict) -> str:
    """Map an Odds API game object to a canonical status string."""
    if game.get("completed"):
        return "Final"
    commence_raw = game.get("commence_time")
    if commence_raw:
        try:
            commence = datetime.fromisoformat(commence_raw.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) >= commence:
                return "InProgress"
        except Exception:
            pass
    return "Scheduled"


def _publish_update(entity_id: str) -> None:
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.publish("prophet:updates", _json.dumps({"type": "event_updated", "entity_id": entity_id}))


def _write_heartbeat() -> None:
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.set("worker:heartbeat:poll_odds_api", "1", ex=settings.POLL_INTERVAL_ODDS_API * 3)


@celery_app.task(name="app.workers.poll_odds_api.run", bind=True, max_retries=3)
def run(self):
    """Fetch Odds API scores and update real_world_status on matched events."""
    if not settings.ODDS_API_KEY:
        log.warning("poll_odds_api_skipped", reason="ODDS_API_KEY not configured")
        return

    # ------------------------------------------------------------------ #
    # 1. Fetch scores for all mapped sports                                #
    # ------------------------------------------------------------------ #
    async def _fetch_all() -> list[dict]:
        results: list[dict] = []
        async with OddsAPIClient() as client:
            for prophetx_sport, sport_keys in SPORT_KEY_MAP.items():
                for sport_key in sport_keys:
                    try:
                        games = await client.get_scores(sport_key, days_from=3)
                        for g in games:
                            g["_prophetx_sport"] = prophetx_sport
                        results.extend(games)
                    except Exception as exc:
                        log.warning(
                            "odds_api_sport_fetch_failed",
                            sport_key=sport_key,
                            error=str(exc),
                        )
        return results

    try:
        all_games = asyncio.run(_fetch_all())
    except Exception as exc:
        log.error("poll_odds_api_fetch_failed", error=str(exc), retry=self.request.retries)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    log.info("odds_api_games_fetched", total=len(all_games))

    if not all_games:
        _write_heartbeat()
        return

    # ------------------------------------------------------------------ #
    # 2. Load events and build sport+date index for efficient matching     #
    # ------------------------------------------------------------------ #
    updated = 0
    unmatched = 0
    now = datetime.now(timezone.utc)

    with SyncSessionLocal() as session:
        candidates = session.execute(
            select(Event).where(
                Event.home_team.isnot(None),
                Event.away_team.isnot(None),
                Event.scheduled_start.isnot(None),
            )
        ).scalars().all()

        # Index: (normalized_sport, date) → list[Event]
        index: dict[tuple[str, date], list[Event]] = defaultdict(list)
        for event in candidates:
            key = (_normalize_sport(event.sport), event.scheduled_start.date())  # type: ignore[union-attr]
            index[key].append(event)

        # ------------------------------------------------------------------ #
        # 3. Match each game to an event                                       #
        # ------------------------------------------------------------------ #
        for game in all_games:
            home = game.get("home_team") or ""
            away = game.get("away_team") or ""
            prophetx_sport = game.get("_prophetx_sport", "")
            commence_raw = game.get("commence_time")

            if not home or not away or not commence_raw:
                continue

            try:
                game_date = datetime.fromisoformat(commence_raw.replace("Z", "+00:00")).date()
            except Exception:
                continue

            real_status = _derive_status(game)

            # Check same date and ±1 day to absorb timezone differences
            match_candidates = (
                index.get((prophetx_sport, game_date), [])
                + index.get((prophetx_sport, game_date - timedelta(days=1)), [])
                + index.get((prophetx_sport, game_date + timedelta(days=1)), [])
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
                best_match.odds_api_status = real_status
                new_status_match = compute_status_match(
                    best_match.prophetx_status,
                    real_status,
                    best_match.sports_api_status,
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
                            f"Odds API={real_status} "
                            f"({best_match.away_team} @ {best_match.home_team})"
                        ),
                    )
                log.debug(
                    "odds_api_event_matched",
                    event_id=str(best_match.id),
                    home=home,
                    away=away,
                    status=real_status,
                    match_score=round(best_score, 3),
                )
            else:
                unmatched += 1
                log.debug(
                    "odds_api_event_unmatched",
                    home=home,
                    away=away,
                    sport=prophetx_sport,
                    best_score=round(best_score, 3) if best_match else 0.0,
                )

        session.commit()

    # ------------------------------------------------------------------ #
    # 4. Heartbeat + summary                                               #
    # ------------------------------------------------------------------ #
    _write_heartbeat()

    log.info(
        "poll_odds_api_complete",
        games_fetched=len(all_games),
        events_updated=updated,
        unmatched=unmatched,
    )
