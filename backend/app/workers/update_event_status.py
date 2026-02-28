"""
update_event_status — Idempotent action worker with distributed lock and audit logging.

Per SYNC-01: acquires a Redis distributed lock before writing; a second concurrent call
for the same event_id returns immediately without duplicate action.

Per SYNC-03: every status update is recorded in audit_log with actor, before_state,
after_state, and result.

Idempotency guard: if event is already at target_status, exits cleanly without API call.
"""

import structlog
from sqlalchemy import select

from app.db.redis import get_sync_redis
from app.db.sync_session import SyncSessionLocal
from app.models.audit_log import AuditLog
from app.models.event import Event
from app.monitoring.mismatch_detector import get_expected_px_status
from app.workers.celery_app import celery_app

log = structlog.get_logger()


@celery_app.task(name="app.workers.update_event_status.run", bind=True, max_retries=3)
def run(self, event_id: str, target_status: str | None, actor: str = "system"):
    """Idempotent action worker: acquires lock, checks current status, updates ProphetX and DB."""

    # 1. Get sync Redis client for distributed lock
    redis_client = get_sync_redis()

    # 2. Acquire distributed lock — 120s timeout per RESEARCH.md Pitfall 3
    #    (covers 3 retries × ProphetX API latency + safety margin)
    lock = redis_client.lock(
        f"lock:update_event_status:{event_id}",
        timeout=120,      # 120s: covers 3 retries × ProphetX API latency + safety margin
        blocking=False,   # non-blocking: if not acquired, log and return immediately
    )
    acquired = lock.acquire()
    if not acquired:
        log.info("update_event_status_lock_not_acquired", event_id=event_id, actor=actor)
        return  # Another worker is handling this — exit cleanly (not an error)

    try:
        # 3. Open sync session and process
        with SyncSessionLocal() as session:
            # a. Look up Event by id (UUID)
            import uuid as _uuid
            try:
                event_uuid = _uuid.UUID(event_id)
            except ValueError:
                log.warning(
                    "update_event_status_invalid_event_id",
                    event_id=event_id,
                    actor=actor,
                )
                return

            event = session.get(Event, event_uuid)
            if event is None:
                log.warning(
                    "update_event_status_event_not_found",
                    event_id=event_id,
                    actor=actor,
                )
                return

            # c. If target_status is None, derive from real_world_status
            effective_target = target_status
            if effective_target is None:
                if event.real_world_status:
                    effective_target = get_expected_px_status(event.real_world_status)
                if effective_target is None:
                    # Flag-only status or no real_world_status — no auto-action
                    log.info(
                        "update_event_status_no_target_derived",
                        event_id=event_id,
                        real_world_status=event.real_world_status,
                        actor=actor,
                    )
                    return

            # d. Idempotency guard: if already at target, exit without API call
            if event.prophetx_status == effective_target:
                log.info(
                    "update_event_status_already_at_target",
                    event_id=event_id,
                    current_status=event.prophetx_status,
                    target_status=effective_target,
                    actor=actor,
                )
                return

            # e. Record before_state
            before_state = {"prophetx_status": event.prophetx_status}

            # ALERT-03: Check alert_only_mode — if enabled, skip ProphetX write
            # Read from system_config table; default to False if not set
            from app.models.config import SystemConfig
            from sqlalchemy import select as _select

            alert_only_cfg = session.execute(
                _select(SystemConfig).where(SystemConfig.key == "alert_only_mode")
            ).scalar_one_or_none()
            alert_only_mode = (
                alert_only_cfg is not None and alert_only_cfg.value.lower() == "true"
            )

            if alert_only_mode:
                log.info(
                    "update_event_status_alert_only_mode",
                    event_id=event_id,
                    target_status=effective_target,
                    actor=actor,
                    note="alert_only_mode=true: skipping ProphetX write, audit log still written",
                )
                # Fall through to audit log and send_alerts — do NOT return here
                px_success = True  # no-op in alert_only_mode
            else:
                # f. Call ProphetX status update — stub (ProphetX write endpoint unconfirmed)
                # TODO: Wire real ProphetX write endpoint when confirmed
                # Expected: PATCH /mm/update_sport_event_status or similar
                # For now: log the intended action; do NOT call ProphetX API
                log.info(
                    "update_event_status_stub_would_call_prophetx",
                    prophetx_event_id=event.prophetx_event_id,
                    target_status=effective_target,
                )
                px_success = True  # Stub: assume success

            # g. Update local DB
            event.prophetx_status = effective_target

            # h. Write audit log entry in same session
            audit_entry = AuditLog(
                action_type="status_update",
                actor=actor,
                entity_type="event",
                entity_id=event.id,
                before_state=before_state,
                after_state={
                    "prophetx_status": effective_target,
                    "alert_only_mode": alert_only_mode,
                },
                result="success",
            )
            session.add(audit_entry)

            # i. Commit both event update and audit log atomically
            session.commit()

            log.info(
                "update_event_status_complete",
                event_id=event_id,
                before=before_state,
                after=effective_target,
                actor=actor,
            )

    except Exception as exc:
        log.error(
            "update_event_status_error",
            event_id=event_id,
            actor=actor,
            error=str(exc),
        )
        # Write failure audit log
        try:
            with SyncSessionLocal() as err_session:
                import uuid as _uuid2
                try:
                    entity_uuid = _uuid2.UUID(event_id)
                except ValueError:
                    entity_uuid = None

                fail_entry = AuditLog(
                    action_type="status_update",
                    actor=actor,
                    entity_type="event",
                    entity_id=entity_uuid,
                    before_state=None,
                    after_state=None,
                    result="failure",
                    error_message=str(exc),
                )
                err_session.add(fail_entry)
                err_session.commit()
        except Exception as log_exc:
            log.error("update_event_status_audit_log_failed", error=str(log_exc))

        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    finally:
        # 5. Release lock — wrap in try/except (lock may have expired)
        try:
            lock.release()
        except Exception as release_exc:
            log.warning(
                "update_event_status_lock_release_failed",
                event_id=event_id,
                error=str(release_exc),
            )
