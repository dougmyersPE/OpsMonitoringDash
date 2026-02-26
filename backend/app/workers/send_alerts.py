"""
send_alerts — Slack alert delivery with Redis SETNX deduplication.

ALERT-01: Delivers Slack alerts for all alertable conditions.
ALERT-02: Redis SETNX pattern: SET alert_dedup:{alert_type}:{entity_id} 1 NX EX 300
           — only one alert per event per condition type per 5 minutes fires.
"""

import redis as sync_redis
import structlog
from slack_sdk.webhook import WebhookClient

from app.core.config import settings
from app.workers.celery_app import celery_app

log = structlog.get_logger()


@celery_app.task(name="app.workers.send_alerts.run", bind=True, max_retries=3)
def run(
    self,
    alert_type: str,
    entity_id: str,
    entity_type: str,
    message: str,
    metadata: dict | None = None,
):
    """
    Deliver a Slack alert with Redis SETNX deduplication.

    Deduplication: if alert_dedup:{alert_type}:{entity_id} exists in Redis,
    this alert is skipped (already sent within the 5-minute window).
    """
    r = sync_redis.from_url(settings.REDIS_URL)
    dedup_key = f"alert_dedup:{alert_type}:{entity_id}"

    # ALERT-02: SETNX — only set if key does not exist; expire after 5 minutes
    acquired = r.set(dedup_key, "1", ex=300, nx=True)
    if not acquired:
        log.info(
            "alert_deduplicated",
            alert_type=alert_type,
            entity_id=entity_id,
            entity_type=entity_type,
        )
        return

    log.info(
        "alert_sending",
        alert_type=alert_type,
        entity_id=entity_id,
        entity_type=entity_type,
        message=message,
    )

    if not settings.SLACK_WEBHOOK_URL:
        log.warning(
            "slack_webhook_not_configured",
            alert_type=alert_type,
            hint="Set SLACK_WEBHOOK_URL in .env to enable Slack delivery",
        )
        return

    # ALERT-01: Deliver via Slack SDK WebhookClient
    webhook = WebhookClient(settings.SLACK_WEBHOOK_URL)
    response = webhook.send(
        text=message,
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*[{alert_type.upper()}]* {message}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Entity: `{entity_type}:{entity_id}`"
                            + (f" | {metadata}" if metadata else ""),
                    }
                ],
            },
        ],
    )

    if response.status_code != 200:
        log.error(
            "slack_send_failed",
            status=response.status_code,
            body=response.body,
            alert_type=alert_type,
        )
        raise self.retry(countdown=60)

    log.info("alert_sent", alert_type=alert_type, entity_id=entity_id)
