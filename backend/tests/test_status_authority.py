"""Unit tests for WS authority helper (is_ws_authoritative) and worker authority wiring."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

import pytest

from app.monitoring.authority import is_ws_authoritative


def _make_session_mock(existing=None):
    """Build a mock SyncSessionLocal context manager that returns existing on execute()."""
    mock_session = MagicMock()
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = existing
    mock_session.execute.return_value = mock_execute_result
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    return mock_session


class TestAuthorityHelper:
    """Tests for the is_ws_authoritative() pure helper function."""

    def test_none_delivered_at_returns_false(self):
        """When ws_delivered_at is None, returns False immediately."""
        result = is_ws_authoritative(None, 600)
        assert result is False

    def test_within_window_returns_true(self):
        """When ws_delivered_at is 5 minutes ago, returns True (within 600s window)."""
        five_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
        result = is_ws_authoritative(five_minutes_ago, 600)
        assert result is True

    def test_expired_window_returns_false(self):
        """When ws_delivered_at is 15 minutes ago, returns False (exceeds 600s window)."""
        fifteen_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=15)
        result = is_ws_authoritative(fifteen_minutes_ago, 600)
        assert result is False

    def test_naive_datetime_coerced_to_utc(self):
        """Naive datetime 5 minutes ago is coerced to UTC and returns True."""
        # Naive datetime (no tzinfo), equivalent to 5 minutes ago in UTC
        five_minutes_ago_naive = datetime.utcnow() - timedelta(minutes=5)
        assert five_minutes_ago_naive.tzinfo is None
        result = is_ws_authoritative(five_minutes_ago_naive, 600)
        assert result is True

    def test_exactly_at_boundary_returns_false(self):
        """When elapsed == threshold (exactly at boundary), returns False (not strictly <)."""
        # We mock datetime.now to control exact elapsed time
        fixed_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        # ws_delivered_at is exactly 600 seconds before "now"
        delivered_at = fixed_now - timedelta(seconds=600)

        with patch("app.monitoring.authority.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            # Make replace() still work for naive datetime coercion
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            result = is_ws_authoritative(delivered_at, 600)

        assert result is False


class TestWsAuthorityColumns:
    """Tests that ws_prophetx._upsert_event sets status_source='ws' and ws_delivered_at on all paths."""

    def test_create_sets_ws_source(self):
        """_upsert_event create path (existing=None) must set status_source='ws' and ws_delivered_at."""
        from app.workers.ws_prophetx import _upsert_event
        from app.models.event import Event

        mock_session = _make_session_mock(existing=None)
        captured_events = []
        mock_session.add.side_effect = lambda obj: captured_events.append(obj)

        with (
            patch("app.workers.ws_prophetx.SyncSessionLocal", return_value=mock_session),
            patch("app.workers.ws_prophetx.compute_status_match", return_value=True),
            patch("app.workers.ws_prophetx._publish_update"),
        ):
            _upsert_event(
                {
                    "event_id": "ws-create-001",
                    "status": "not_started",
                    "sport": "soccer",
                    "name": "Test Event",
                },
                "c",
            )

        assert len(captured_events) == 1
        event_obj = captured_events[0]
        assert event_obj.status_source == "ws", f"Expected 'ws', got {event_obj.status_source!r}"
        assert isinstance(event_obj.ws_delivered_at, datetime), (
            f"Expected datetime, got {event_obj.ws_delivered_at!r}"
        )

    def test_update_sets_ws_source(self):
        """_upsert_event update path (existing event) must set status_source='ws' and ws_delivered_at."""
        from app.workers.ws_prophetx import _upsert_event
        from app.models.event import Event

        existing = MagicMock(spec=Event)
        existing.prophetx_status = "not_started"
        existing.odds_api_status = None
        existing.sports_api_status = None
        existing.sdio_status = None
        existing.espn_status = None
        existing.oddsblaze_status = None
        existing.sport = "soccer"
        existing.name = "Old Name"
        existing.home_team = None
        existing.away_team = None
        existing.scheduled_start = None
        existing.league = None

        mock_session = _make_session_mock(existing=existing)

        with (
            patch("app.workers.ws_prophetx.SyncSessionLocal", return_value=mock_session),
            patch("app.workers.ws_prophetx.compute_status_match", return_value=True),
            patch("app.workers.ws_prophetx._publish_update"),
        ):
            _upsert_event(
                {"event_id": "ws-update-001", "status": "live", "sport": "soccer"},
                "u",
            )

        assert existing.status_source == "ws", f"Expected 'ws', got {existing.status_source!r}"
        assert isinstance(existing.ws_delivered_at, datetime), (
            f"Expected datetime, got {existing.ws_delivered_at!r}"
        )

    def test_delete_sets_ws_source(self):
        """_upsert_event op=d path must set status_source='ws' on the ended event."""
        from app.workers.ws_prophetx import _upsert_event
        from app.models.event import Event

        existing = MagicMock(spec=Event)
        existing.prophetx_status = "live"
        existing.odds_api_status = None
        existing.sports_api_status = None
        existing.sdio_status = None
        existing.espn_status = None
        existing.oddsblaze_status = None

        mock_session = _make_session_mock(existing=existing)

        with (
            patch("app.workers.ws_prophetx.SyncSessionLocal", return_value=mock_session),
            patch("app.workers.ws_prophetx.compute_status_match", return_value=True),
            patch("app.workers.ws_prophetx._publish_update"),
        ):
            _upsert_event(
                {"event_id": "ws-delete-001"},
                "d",
            )

        assert existing.status_source == "ws", f"Expected 'ws', got {existing.status_source!r}"
        assert isinstance(existing.ws_delivered_at, datetime), (
            f"Expected datetime, got {existing.ws_delivered_at!r}"
        )
