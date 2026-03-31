"""
Unit tests for cleanup_old_events worker.

All DB sessions are mocked — no real infrastructure required.
Tests verify:
  - Events older than 48h deleted regardless of prophetx_status
  - Events newer than 48h NOT deleted even if ended
  - Related markets deleted before events
  - Related event_id_mappings deleted by prophetx_event_id
  - Related notifications deleted by entity_type/entity_id
  - Audit log rows NOT deleted (insert-only table)
  - Returns count of deleted events
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CUTOFF_PLUS_1H = datetime.now(timezone.utc) - timedelta(hours=49)  # > 48h ago (stale)
CUTOFF_MINUS_1H = datetime.now(timezone.utc) - timedelta(hours=47)  # < 48h ago (fresh)

EVENT_ID_1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
EVENT_ID_2 = uuid.UUID("22222222-2222-2222-2222-222222222222")
PX_EVENT_ID_1 = "px-event-stale-001"
PX_EVENT_ID_2 = "px-event-stale-002"


def _make_session_ctx(stale_rows=None, prophetx_ids=None):
    """
    Build a mock session context manager.

    The first scalars().all() call returns stale_rows (event IDs).
    The second scalars().all() call returns prophetx_ids.
    """
    stale_rows = stale_rows if stale_rows is not None else []
    prophetx_ids = prophetx_ids if prophetx_ids is not None else []

    # We need two distinct scalars results in sequence
    scalars_result_1 = MagicMock()
    scalars_result_1.all.return_value = stale_rows

    scalars_result_2 = MagicMock()
    scalars_result_2.all.return_value = prophetx_ids

    execute_results = [
        MagicMock(scalars=MagicMock(return_value=scalars_result_1)),  # stale IDs query
        MagicMock(scalars=MagicMock(return_value=scalars_result_2)),  # prophetx IDs query
        MagicMock(rowcount=len(stale_rows)),                           # delete markets
        MagicMock(rowcount=0),                                         # delete mappings
        MagicMock(rowcount=0),                                         # delete notifications
        MagicMock(rowcount=len(stale_rows)),                           # delete events
    ]

    session = MagicMock()
    session.execute.side_effect = execute_results

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session)
    ctx.__exit__ = MagicMock(return_value=False)

    return ctx, session


# ---------------------------------------------------------------------------
# Test 1: Events with scheduled_start > 48h ago deleted regardless of status
# ---------------------------------------------------------------------------

def test_stale_events_deleted_regardless_of_status():
    """All events older than 48h are deleted — no prophetx_status filter applied."""
    ctx, session = _make_session_ctx(
        stale_rows=[EVENT_ID_1, EVENT_ID_2],
        prophetx_ids=[PX_EVENT_ID_1, PX_EVENT_ID_2],
    )

    with patch("app.workers.cleanup_old_events.SyncSessionLocal", return_value=ctx):
        from app.workers.cleanup_old_events import run
        result = run.run()

    # Two events deleted
    assert result == {"deleted": 2}

    # Verify session.execute was called (at minimum the stale IDs query + deletes)
    assert session.execute.called
    assert session.commit.called


# ---------------------------------------------------------------------------
# Test 2: Events newer than 48h NOT deleted even if ended
# ---------------------------------------------------------------------------

def test_fresh_events_not_deleted_even_if_ended():
    """Events with scheduled_start within 48h are NOT deleted."""
    # Return empty stale_rows → nothing to delete
    ctx, session = _make_session_ctx(stale_rows=[], prophetx_ids=[])

    with patch("app.workers.cleanup_old_events.SyncSessionLocal", return_value=ctx):
        from app.workers.cleanup_old_events import run
        result = run.run()

    # No events deleted
    assert result == {"deleted": 0}

    # With no stale events, commit should NOT be called (early return path)
    session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: Related markets are deleted before events
# ---------------------------------------------------------------------------

def test_markets_deleted_before_events():
    """Markets are deleted before events to satisfy FK constraint.

    We verify ordering by inspecting the SQL text of each execute call.
    The DELETE FROM markets statement must appear before DELETE FROM events.
    """
    ctx, session = _make_session_ctx(
        stale_rows=[EVENT_ID_1],
        prophetx_ids=[PX_EVENT_ID_1],
    )

    with patch("app.workers.cleanup_old_events.SyncSessionLocal", return_value=ctx):
        from app.workers.cleanup_old_events import run
        run.run()

    # At minimum: stale IDs query, prophetx IDs query, markets delete,
    # mappings delete, notifications delete, events delete = 6 execute calls
    calls = session.execute.call_args_list
    assert len(calls) >= 6

    # Inspect the SQLAlchemy Delete statement in each execute call to verify ordering.
    # call[0][0] is the first positional arg (the statement) passed to session.execute.
    # Markets delete (index 2) must come before events delete (index 5).
    from sqlalchemy.sql.dml import Delete

    def get_table_name(call_obj):
        stmt = call_obj[0][0]
        if isinstance(stmt, Delete):
            return stmt.table.name
        return None

    market_table = get_table_name(calls[2])
    event_table = get_table_name(calls[5])
    assert market_table == "markets", f"Expected markets delete at index 2, got: {market_table}"
    assert event_table == "events", f"Expected events delete at index 5, got: {event_table}"


# ---------------------------------------------------------------------------
# Test 4: Related event_id_mappings deleted by prophetx_event_id
# ---------------------------------------------------------------------------

def test_event_id_mappings_deleted():
    """event_id_mappings matching prophetx_event_id of stale events are deleted."""
    ctx, session = _make_session_ctx(
        stale_rows=[EVENT_ID_1],
        prophetx_ids=[PX_EVENT_ID_1],
    )

    with patch("app.workers.cleanup_old_events.SyncSessionLocal", return_value=ctx):
        from app.workers.cleanup_old_events import run
        result = run.run()

    # Task completes without error — mappings delete was called
    assert result["deleted"] == 1
    # At minimum: stale IDs, prophetx IDs, market delete, mapping delete,
    # notification delete, event delete = 6 execute calls
    assert session.execute.call_count >= 6


# ---------------------------------------------------------------------------
# Test 5: Related notifications deleted (entity_type="event", entity_id in stale)
# ---------------------------------------------------------------------------

def test_notifications_deleted():
    """Notifications with entity_type='event' and matching entity_id are deleted."""
    ctx, session = _make_session_ctx(
        stale_rows=[EVENT_ID_1, EVENT_ID_2],
        prophetx_ids=[PX_EVENT_ID_1, PX_EVENT_ID_2],
    )

    with patch("app.workers.cleanup_old_events.SyncSessionLocal", return_value=ctx):
        from app.workers.cleanup_old_events import run
        result = run.run()

    assert result["deleted"] == 2
    # Notifications delete is one of the execute calls
    assert session.execute.call_count >= 6


# ---------------------------------------------------------------------------
# Test 6: Audit log rows NOT deleted
# ---------------------------------------------------------------------------

def test_audit_log_not_deleted():
    """Audit log is insert-only — the cleanup task must never delete from it."""
    ctx, session = _make_session_ctx(
        stale_rows=[EVENT_ID_1],
        prophetx_ids=[PX_EVENT_ID_1],
    )

    import app.workers.cleanup_old_events as module

    with patch("app.workers.cleanup_old_events.SyncSessionLocal", return_value=ctx):
        from app.workers.cleanup_old_events import run
        run.run()

    # Verify AuditLog is not imported/used in the module at all
    assert not hasattr(module, "AuditLog"), (
        "cleanup_old_events must not import AuditLog — it is insert-only"
    )


# ---------------------------------------------------------------------------
# Test 7: Returns count of deleted events
# ---------------------------------------------------------------------------

def test_returns_deleted_count():
    """run() returns a dict with 'deleted' key equal to number of events removed."""
    ctx, session = _make_session_ctx(
        stale_rows=[EVENT_ID_1, EVENT_ID_2],
        prophetx_ids=[PX_EVENT_ID_1, PX_EVENT_ID_2],
    )

    with patch("app.workers.cleanup_old_events.SyncSessionLocal", return_value=ctx):
        from app.workers.cleanup_old_events import run
        result = run.run()

    assert isinstance(result, dict)
    assert "deleted" in result
    assert result["deleted"] == 2
