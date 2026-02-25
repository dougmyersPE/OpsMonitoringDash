"""
send_alerts — Alert stub worker.

Phase 2 stub: logs alert details via structlog.
Phase 3 wires Slack webhook and alert deduplication (ALERT-01, ALERT-02).
"""

import structlog

from app.workers.celery_app import celery_app

log = structlog.get_logger()


@celery_app.task(name="app.workers.send_alerts.run")
def run(
    alert_type: str,
    entity_id: str,
    entity_type: str,
    message: str,
    metadata: dict | None = None,
):
    """Phase 2 stub: logs alert. Phase 3 wires Slack webhook."""
    log.info(
        "send_alert_stub",
        alert_type=alert_type,
        entity_type=entity_type,
        entity_id=entity_id,
        message=message,
        metadata=metadata or {},
    )
