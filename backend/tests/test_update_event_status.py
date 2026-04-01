"""
Unit tests for update_event_status worker.

All Redis and DB sessions are mocked — no real infrastructure required.
Tests verify: lock behavior, idempotency guard, successful update, and event-not-found.
"""

import uuid
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(prophetx_status="live", real_world_status="InProgress"):
    """Return a mock Event with required attributes."""
    event = MagicMock()
    event.id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    event.prophetx_event_id = "px-event-001"
    event.prophetx_status = prophetx_status
    event.real_world_status = real_world_status
    return event


def _make_mock_lock(acquired=True):
    """Return a mock Redis lock."""
    lock = MagicMock()
    lock.acquire.return_value = acquired
    return lock


# ---------------------------------------------------------------------------
# Test 1: Lock not acquired — returns cleanly without DB writes
# ---------------------------------------------------------------------------

def test_lock_not_acquired_returns_cleanly():
    """When lock cannot be acquired, task returns immediately without DB writes."""
    mock_redis = MagicMock()
    mock_lock = _make_mock_lock(acquired=False)
    mock_redis.lock.return_value = mock_lock

    with patch("app.workers.update_event_status.get_sync_redis", return_value=mock_redis), \
         patch("app.workers.update_event_status.SyncSessionLocal") as mock_session_cls:

        from app.workers.update_event_status import run

        # Call the underlying function directly (not .delay())
        run.run(event_id=str(uuid.uuid4()), target_status="live", actor="system")

        # Session should never be opened
        mock_session_cls.assert_not_called()

        # Lock was attempted
        mock_lock.acquire.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2: Idempotency guard — already at target, no API call, no audit log
# ---------------------------------------------------------------------------

def test_idempotency_guard_skips_when_already_at_target():
    """When event is already at target_status, task exits without writing."""
    event_id = str(uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    target_status = "live"

    # Event is ALREADY at target_status
    mock_event = _make_event(prophetx_status=target_status)

    mock_redis = MagicMock()
    mock_lock = _make_mock_lock(acquired=True)
    mock_redis.lock.return_value = mock_lock

    mock_session = MagicMock()
    mock_session.get.return_value = mock_event
    mock_session_ctx = MagicMock()
    mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
    mock_session_ctx.__exit__ = MagicMock(return_value=False)

    with patch("app.workers.update_event_status.get_sync_redis", return_value=mock_redis), \
         patch("app.workers.update_event_status.SyncSessionLocal", return_value=mock_session_ctx):

        from app.workers.update_event_status import run
        run.run(event_id=event_id, target_status=target_status, actor="system")

        # session.add() should never be called (no audit entry written)
        mock_session.add.assert_not_called()
        # session.commit() should never be called
        mock_session.commit.assert_not_called()

        # Lock should be released
        mock_lock.release.assert_called_once()


# ---------------------------------------------------------------------------
# Test 3: Successful update — audit log written + event updated
# ---------------------------------------------------------------------------

def test_successful_update_writes_audit_log():
    """When status differs from target, event is updated and audit log is written."""
    event_id = str(uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"))
    before_status = "upcoming"
    target_status = "live"

    mock_event = _make_event(prophetx_status=before_status)

    mock_redis = MagicMock()
    mock_lock = _make_mock_lock(acquired=True)
    mock_redis.lock.return_value = mock_lock

    mock_session = MagicMock()
    mock_session.get.return_value = mock_event
    mock_session_ctx = MagicMock()
    mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
    mock_session_ctx.__exit__ = MagicMock(return_value=False)

    with patch("app.workers.update_event_status.get_sync_redis", return_value=mock_redis), \
         patch("app.workers.update_event_status.SyncSessionLocal", return_value=mock_session_ctx), \
         patch("app.workers.update_event_status.AuditLog") as MockAuditLog:

        from app.workers.update_event_status import run
        run.run(event_id=event_id, target_status=target_status, actor="operator@test.com")

        # Event status should be updated
        assert mock_event.prophetx_status == target_status

        # AuditLog should be constructed with correct args
        MockAuditLog.assert_called_once_with(
            action_type="status_update",
            actor="operator@test.com",
            entity_type="event",
            entity_id=mock_event.id,
            before_state={"prophetx_status": before_status},
            after_state={"prophetx_status": target_status, "status_source": "manual", "alert_only_mode": False},
            result="success",
        )

        # session.add() called for audit entry
        mock_session.add.assert_called_once()

        # session.commit() called to persist both atomically
        mock_session.commit.assert_called_once()

        # Lock released
        mock_lock.release.assert_called_once()


# ---------------------------------------------------------------------------
# Test 4: Event not found — logs warning, returns without error
# ---------------------------------------------------------------------------

def test_event_not_found_returns_cleanly():
    """When event does not exist in DB, task logs warning and returns without error."""
    event_id = str(uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"))

    mock_redis = MagicMock()
    mock_lock = _make_mock_lock(acquired=True)
    mock_redis.lock.return_value = mock_lock

    mock_session = MagicMock()
    mock_session.get.return_value = None  # Event not found
    mock_session_ctx = MagicMock()
    mock_session_ctx.__enter__ = MagicMock(return_value=mock_session)
    mock_session_ctx.__exit__ = MagicMock(return_value=False)

    with patch("app.workers.update_event_status.get_sync_redis", return_value=mock_redis), \
         patch("app.workers.update_event_status.SyncSessionLocal", return_value=mock_session_ctx):

        from app.workers.update_event_status import run

        # Should not raise
        run.run(event_id=event_id, target_status="live", actor="system")

        # session.add() should never be called
        mock_session.add.assert_not_called()
        # session.commit() should never be called
        mock_session.commit.assert_not_called()

        # Lock still released
        mock_lock.release.assert_called_once()
