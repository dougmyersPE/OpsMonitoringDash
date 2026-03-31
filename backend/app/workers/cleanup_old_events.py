"""Periodic task to delete events older than 48 hours from the database."""

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import delete, select

from app.db.sync_session import SyncSessionLocal
from app.models.event import Event
from app.models.event_id_mapping import EventIDMapping
from app.models.market import Market
from app.models.notification import Notification
from app.workers.celery_app import celery_app

log = structlog.get_logger()

RETENTION_HOURS = 48


@celery_app.task(name="app.workers.cleanup_old_events.run")
def run():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)

    with SyncSessionLocal() as session:
        # Find IDs of stale events (no status filter — all events older than cutoff)
        stale_ids = session.execute(
            select(Event.id).where(Event.scheduled_start <= cutoff)
        ).scalars().all()

        if not stale_ids:
            return {"deleted": 0}

        # Collect prophetx_event_ids for mapping cleanup (no FK, matched by value)
        prophetx_ids = session.execute(
            select(Event.prophetx_event_id).where(Event.id.in_(stale_ids))
        ).scalars().all()
        # Filter out None values
        prophetx_ids = [pid for pid in prophetx_ids if pid is not None]

        # Delete related markets first (FK constraint requires this before Event deletion)
        markets_deleted = session.execute(
            delete(Market).where(Market.event_id.in_(stale_ids))
        ).rowcount

        # Delete related event_id_mappings (no FK — matched by prophetx_event_id value)
        mappings_deleted = 0
        if prophetx_ids:
            mappings_deleted = session.execute(
                delete(EventIDMapping).where(
                    EventIDMapping.prophetx_event_id.in_(prophetx_ids)
                )
            ).rowcount

        # Delete related notifications (no FK — matched by entity_type + entity_id)
        notifications_deleted = session.execute(
            delete(Notification).where(
                Notification.entity_type == "event",
                Notification.entity_id.in_(stale_ids),
            )
        ).rowcount

        # Delete the events themselves
        result = session.execute(
            delete(Event).where(Event.id.in_(stale_ids))
        )
        deleted = result.rowcount
        session.commit()

    log.info(
        "cleanup_old_events",
        deleted=deleted,
        markets_deleted=markets_deleted,
        mappings_deleted=mappings_deleted,
        notifications_deleted=notifications_deleted,
        cutoff=str(cutoff),
    )
    return {"deleted": deleted}
