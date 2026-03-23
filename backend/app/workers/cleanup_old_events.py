"""Periodic task to delete events older than 48 hours from the database."""

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import and_, delete, select

from app.db.sync_session import SyncSessionLocal
from app.models.event import Event
from app.models.market import Market
from app.workers.celery_app import celery_app

log = structlog.get_logger()

RETENTION_HOURS = 48


@celery_app.task(name="app.workers.cleanup_old_events.run")
def run():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)

    with SyncSessionLocal() as session:
        # Find event IDs to delete
        stale_ids = session.execute(
            select(Event.id).where(
                and_(
                    Event.prophetx_status == "ended",
                    Event.scheduled_start <= cutoff,
                )
            )
        ).scalars().all()

        if not stale_ids:
            return {"deleted": 0}

        # Delete related markets first (FK constraint)
        session.execute(
            delete(Market).where(Market.event_id.in_(stale_ids))
        )

        # Delete the events
        result = session.execute(
            delete(Event).where(Event.id.in_(stale_ids))
        )
        deleted = result.rowcount
        session.commit()

    log.info("cleanup_old_events", deleted=deleted, cutoff=str(cutoff))
    return {"deleted": deleted}
