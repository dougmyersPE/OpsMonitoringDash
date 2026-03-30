"""
Critical alert check — runs every 60 seconds via Celery Beat.

Fires a Slack webhook for any event where ProphetX shows not-started
(not_started / upcoming) but at least one real-world source reports the
event as live / in-progress.

Deduplication: one alert per ProphetX event ID per 5 minutes (Redis SETNX).
"""

import httpx
import redis as _sync_redis
import structlog
from sqlalchemy import select

from app.core.config import settings
from app.db.sync_session import SyncSessionLocal
from app.models.event import Event
from app.monitoring.mismatch_detector import compute_is_critical
from app.workers.celery_app import celery_app

log = structlog.get_logger()

DEDUP_TTL = 300  # seconds — one alert per event per 5-minute window


@celery_app.task(name="app.workers.poll_critical_check.run", bind=True, max_retries=2)
def run(self):
    """Query DB for critical events and send a Slack alert for each new one."""
    from app.workers.send_alerts import are_alerts_enabled

    if not are_alerts_enabled():
        log.info("critical_check_skipped", reason="alerts disabled")
        return

    with SyncSessionLocal() as session:
        events = session.execute(select(Event)).scalars().all()

    critical = [
        e for e in events
        if compute_is_critical(
            e.prophetx_status,
            e.odds_api_status,
            e.sports_api_status,
            e.sdio_status,
            e.espn_status,
            e.oddsblaze_status,
        )
    ]

    if not critical:
        log.debug("critical_check_clean")
        return

    if not settings.SLACK_WEBHOOK_URL:
        log.warning("critical_check_slack_not_configured", critical_count=len(critical))
        return

    r = _sync_redis.from_url(settings.REDIS_URL)
    sent = 0

    for event in critical:
        dedup_key = f"critical_alert:{event.prophetx_event_id}"
        if not r.set(dedup_key, "1", ex=DEDUP_TTL, nx=True):
            log.debug("critical_alert_deduplicated", event_id=event.prophetx_event_id)
            continue

        sources = []
        if event.odds_api_status:
            sources.append(f"OddsAPI={event.odds_api_status}")
        if event.sports_api_status:
            sources.append(f"SportsAPI={event.sports_api_status}")
        if event.sdio_status:
            sources.append(f"SDIO={event.sdio_status}")
        if event.espn_status:
            sources.append(f"ESPN={event.espn_status}")

        text = (
            f":red_circle: *ProphetX event not started but sources say LIVE*\n"
            f"*Event ID:* `{event.prophetx_event_id}`\n"
            f"*Event:* {event.name}\n"
            f"*ProphetX status:* `{event.prophetx_status}`\n"
            f"*Sources:* {', '.join(sources)}"
        )

        try:
            resp = httpx.post(
                settings.SLACK_WEBHOOK_URL,
                json={"text": text},
                timeout=10.0,
            )
            if resp.status_code == 200:
                log.info(
                    "critical_alert_sent",
                    event_id=event.prophetx_event_id,
                    event_name=event.name,
                )
                sent += 1
            else:
                log.error(
                    "critical_alert_slack_failed",
                    status=resp.status_code,
                    body=resp.text,
                    event_id=event.prophetx_event_id,
                )
        except Exception as exc:
            log.error("critical_alert_send_error", error=str(exc), event_id=event.prophetx_event_id)

    log.info("critical_check_complete", critical_found=len(critical), alerts_sent=sent)
