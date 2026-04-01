"""Unit tests for ws_prophetx._upsert_event create path — WSREL-02.

Verifies that new events created via the WS consumer get a non-NULL status_match
value computed from compute_status_match(), not left as NULL.
"""

from unittest.mock import MagicMock, patch, call
import pytest


def _make_session_mock(existing=None):
    """Build a mock SyncSessionLocal context manager that returns existing on execute()."""
    mock_session = MagicMock()
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = existing
    mock_session.execute.return_value = mock_execute_result
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    return mock_session


class TestWsUpsertCreatePath:
    def test_create_path_sets_status_match_not_none(self):
        """_upsert_event op=c must create an Event with status_match set (not None)."""
        from app.workers.ws_prophetx import _upsert_event

        mock_session = _make_session_mock(existing=None)
        captured_events = []

        def capture_add(obj):
            captured_events.append(obj)

        mock_session.add.side_effect = capture_add

        with (
            patch("app.workers.ws_prophetx.SyncSessionLocal", return_value=mock_session),
            patch("app.workers.ws_prophetx.compute_status_match", return_value=True) as mock_csm,
            patch("app.workers.ws_prophetx._publish_update"),
        ):
            _upsert_event(
                {
                    "event_id": "test-123",
                    "status": "not_started",
                    "sport": "soccer",
                    "name": "Test Event",
                },
                "c",
            )

        # compute_status_match should have been called with all-None external sources
        mock_csm.assert_called_once_with("not_started", None, None, None, None)

        # The Event added to session must have status_match set
        assert len(captured_events) == 1, "session.add() must be called exactly once for op=c"
        event_obj = captured_events[0]
        assert event_obj.status_match is not None, (
            "WSREL-02: WS-created Event must have status_match set, got None"
        )
        assert event_obj.status_match is True

    def test_create_path_status_match_is_true_when_all_sources_none(self):
        """For a newly created event (no external source data), status_match=True (no disagreement)."""
        from app.workers.ws_prophetx import _upsert_event

        mock_session = _make_session_mock(existing=None)
        captured_events = []
        mock_session.add.side_effect = lambda obj: captured_events.append(obj)

        with (
            patch("app.workers.ws_prophetx.SyncSessionLocal", return_value=mock_session),
            patch("app.workers.ws_prophetx._publish_update"),
        ):
            _upsert_event(
                {"event_id": "test-456", "status": "not_started", "sport": "basketball"},
                "c",
            )

        assert len(captured_events) == 1
        # With all external sources None, compute_status_match always returns True
        assert captured_events[0].status_match is True

    def test_update_path_still_calls_compute_status_match(self):
        """Existing update path (op=u) should still compute status_match from existing columns."""
        from app.workers.ws_prophetx import _upsert_event
        from app.models.event import Event

        existing = MagicMock(spec=Event)
        existing.prophetx_status = "not_started"
        existing.odds_api_status = None
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
            patch("app.workers.ws_prophetx.compute_status_match", return_value=True) as mock_csm,
            patch("app.workers.ws_prophetx._publish_update"),
        ):
            _upsert_event(
                {"event_id": "test-789", "status": "live", "sport": "soccer"},
                "u",
            )

        # Update path must also call compute_status_match
        mock_csm.assert_called_once()
