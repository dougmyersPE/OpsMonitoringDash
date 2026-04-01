"""Unit tests for WS authority helper (is_ws_authoritative) and worker authority wiring."""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call

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


class TestPollAuthorityColumns:
    """Tests for poll_prophetx authority-aware status writes."""

    def _make_poll_event_mock(self, ws_delivered_at=None, prophetx_status="not_started"):
        """Build a mock Event suitable for poll update path."""
        from app.models.event import Event

        existing = MagicMock(spec=Event)
        existing.ws_delivered_at = ws_delivered_at
        existing.prophetx_status = prophetx_status
        existing.odds_api_status = None
        existing.sports_api_status = None
        existing.sdio_status = None
        existing.espn_status = None
        existing.oddsblaze_status = None
        existing.sport = "basketball"
        existing.name = "Old Name"
        existing.home_team = "Lakers"
        existing.away_team = "Celtics"
        existing.scheduled_start = None
        existing.league = "NBA"
        return existing

    def _make_poll_session_mock(self, existing=None):
        """Session mock that supports both single event lookup and scalar/all queries.

        Returns existing for per-event scalar_one_or_none lookups.
        Returns empty list for stale-events and all-events queries (scalars().all()).
        This prevents the stale-ended loop from interfering with update path tests.
        """
        mock_session = MagicMock()

        def _execute_side_effect(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = existing
            # Return empty for bulk all() queries (stale-ended loop, recompute loop)
            result.scalars.return_value.all.return_value = []
            return result

        mock_session.execute.side_effect = _execute_side_effect
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        return mock_session

    def test_poll_create_sets_poll_source(self):
        """Poll create path must set status_source='poll' and status_match in Event constructor."""
        from app.workers.poll_prophetx import run

        mock_session = self._make_poll_session_mock(existing=None)
        captured_events = []
        mock_session.add.side_effect = lambda obj: captured_events.append(obj)

        raw_events = [
            {
                "id": "poll-create-001",
                "status": "not_started",
                "sport": "basketball",
                "name": "Test Game",
            }
        ]

        with (
            patch("app.workers.poll_prophetx.SyncSessionLocal", return_value=mock_session),
            patch("app.workers.poll_prophetx.ProphetXClient") as mock_px_cls,
            patch("app.workers.poll_prophetx._publish_update"),
            patch("app.workers.poll_prophetx._write_heartbeat"),
            patch("app.workers.poll_prophetx._increment_call_counter"),
            patch("app.workers.poll_prophetx.compute_status_match", return_value=True),
        ):
            mock_px = MagicMock()
            mock_px.__aenter__ = AsyncMock(return_value=mock_px)
            mock_px.__aexit__ = AsyncMock(return_value=False)
            mock_px.get_events_raw = AsyncMock(return_value=raw_events)
            mock_px_cls.return_value = mock_px

            # Call run directly (bypass Celery task dispatch)
            run.run(trigger="test")

        assert len(captured_events) == 1, f"Expected 1 captured event, got {len(captured_events)}"
        event_obj = captured_events[0]
        assert event_obj.status_source == "poll", f"Expected 'poll', got {event_obj.status_source!r}"
        assert event_obj.status_match is not None, "status_match should be set on create"

    def test_poll_update_outside_window_sets_poll_source(self):
        """Poll update path with ws_delivered_at=None sets status_source='poll' and clears ws_delivered_at."""
        from app.workers.poll_prophetx import run
        existing = self._make_poll_event_mock(ws_delivered_at=None)
        mock_session = self._make_poll_session_mock(existing=existing)

        raw_events = [
            {
                "id": "poll-update-001",
                "status": "live",
                "sport": "basketball",
                "name": "Test Game",
            }
        ]

        with (
            patch("app.workers.poll_prophetx.SyncSessionLocal", return_value=mock_session),
            patch("app.workers.poll_prophetx.ProphetXClient") as mock_px_cls,
            patch("app.workers.poll_prophetx._publish_update"),
            patch("app.workers.poll_prophetx._write_heartbeat"),
            patch("app.workers.poll_prophetx._increment_call_counter"),
            patch("app.workers.poll_prophetx.compute_status_match", return_value=True),
        ):
            mock_px = MagicMock()
            mock_px.__aenter__ = AsyncMock(return_value=mock_px)
            mock_px.__aexit__ = AsyncMock(return_value=False)
            mock_px.get_events_raw = AsyncMock(return_value=raw_events)
            mock_px_cls.return_value = mock_px

            run.run(trigger="test")

        assert existing.status_source == "poll", f"Expected 'poll', got {existing.status_source!r}"
        assert existing.ws_delivered_at is None, f"Expected None, got {existing.ws_delivered_at!r}"

    def test_poll_update_inside_window_skips_status(self):
        """When WS is authoritative, poll must NOT overwrite prophetx_status."""
        from app.workers.poll_prophetx import run
        five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
        existing = self._make_poll_event_mock(ws_delivered_at=five_min_ago, prophetx_status="live")
        mock_session = self._make_poll_session_mock(existing=existing)

        raw_events = [
            {
                "id": "poll-skip-001",
                "status": "not_started",  # Poll disagrees with WS-delivered "live"
                "sport": "basketball",
                "name": "Test Game",
            }
        ]

        with (
            patch("app.workers.poll_prophetx.SyncSessionLocal", return_value=mock_session),
            patch("app.workers.poll_prophetx.ProphetXClient") as mock_px_cls,
            patch("app.workers.poll_prophetx._publish_update"),
            patch("app.workers.poll_prophetx._write_heartbeat"),
            patch("app.workers.poll_prophetx._increment_call_counter"),
            patch("app.workers.poll_prophetx.compute_status_match", return_value=True),
            patch("app.workers.poll_prophetx.is_ws_authoritative", return_value=True),
        ):
            mock_px = MagicMock()
            mock_px.__aenter__ = AsyncMock(return_value=mock_px)
            mock_px.__aexit__ = AsyncMock(return_value=False)
            mock_px.get_events_raw = AsyncMock(return_value=raw_events)
            mock_px_cls.return_value = mock_px

            run.run(trigger="test")

        # Status must NOT have changed from "live" (WS is authoritative)
        assert existing.prophetx_status == "live", (
            f"Expected prophetx_status unchanged ('live'), got {existing.prophetx_status!r}"
        )

    def test_poll_updates_metadata_inside_window(self):
        """When WS is authoritative, poll must still update metadata fields."""
        from app.workers.poll_prophetx import run
        five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
        existing = self._make_poll_event_mock(ws_delivered_at=five_min_ago, prophetx_status="live")
        mock_session = self._make_poll_session_mock(existing=existing)

        raw_events = [
            {
                "id": "poll-meta-001",
                "status": "not_started",
                "sport": "basketball",
                "name": "Test Game",
                "tournament_name": "NBA 2026",
            }
        ]

        with (
            patch("app.workers.poll_prophetx.SyncSessionLocal", return_value=mock_session),
            patch("app.workers.poll_prophetx.ProphetXClient") as mock_px_cls,
            patch("app.workers.poll_prophetx._publish_update"),
            patch("app.workers.poll_prophetx._write_heartbeat"),
            patch("app.workers.poll_prophetx._increment_call_counter"),
            patch("app.workers.poll_prophetx.compute_status_match", return_value=True),
            patch("app.workers.poll_prophetx.is_ws_authoritative", return_value=True),
        ):
            mock_px = MagicMock()
            mock_px.__aenter__ = AsyncMock(return_value=mock_px)
            mock_px.__aexit__ = AsyncMock(return_value=False)
            mock_px.get_events_raw = AsyncMock(return_value=raw_events)
            mock_px_cls.return_value = mock_px

            run.run(trigger="test")

        # last_prophetx_poll must be updated even when WS is authoritative
        assert existing.last_prophetx_poll is not None, (
            "last_prophetx_poll must be set even when WS is authoritative"
        )
        # League update from tournament_name should also be applied
        assert existing.league == "NBA 2026", (
            f"Expected league='NBA 2026' (metadata update), got {existing.league!r}"
        )

    def test_ended_bypasses_authority_window(self):
        """Poll status 'ended' must overwrite even when WS is authoritative (D-05)."""
        from app.workers.poll_prophetx import run
        five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
        existing = self._make_poll_event_mock(ws_delivered_at=five_min_ago, prophetx_status="live")
        mock_session = self._make_poll_session_mock(existing=existing)

        raw_events = [
            {
                "id": "poll-ended-001",
                "status": "ended",
                "sport": "basketball",
                "name": "Test Game",
            }
        ]

        with (
            patch("app.workers.poll_prophetx.SyncSessionLocal", return_value=mock_session),
            patch("app.workers.poll_prophetx.ProphetXClient") as mock_px_cls,
            patch("app.workers.poll_prophetx._publish_update"),
            patch("app.workers.poll_prophetx._write_heartbeat"),
            patch("app.workers.poll_prophetx._increment_call_counter"),
            patch("app.workers.poll_prophetx.compute_status_match", return_value=True),
            patch("app.workers.poll_prophetx.is_ws_authoritative", return_value=True),
        ):
            mock_px = MagicMock()
            mock_px.__aenter__ = AsyncMock(return_value=mock_px)
            mock_px.__aexit__ = AsyncMock(return_value=False)
            mock_px.get_events_raw = AsyncMock(return_value=raw_events)
            mock_px_cls.return_value = mock_px

            run.run(trigger="test")

        assert existing.prophetx_status == "ended", (
            f"Expected 'ended' to bypass authority window, got {existing.prophetx_status!r}"
        )
        assert existing.status_source == "poll", f"Expected 'poll', got {existing.status_source!r}"

    def test_poll_logs_discrepancy_inside_window(self):
        """When WS-authoritative status differs from poll status, discrepancy is logged."""
        from app.workers.poll_prophetx import run
        five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
        existing = self._make_poll_event_mock(ws_delivered_at=five_min_ago, prophetx_status="live")
        mock_session = self._make_poll_session_mock(existing=existing)

        raw_events = [
            {
                "id": "poll-log-001",
                "status": "not_started",  # Differs from existing "live"
                "sport": "basketball",
                "name": "Test Game",
            }
        ]

        log_calls = []

        def capture_info(event_name, **kwargs):
            log_calls.append((event_name, kwargs))

        with (
            patch("app.workers.poll_prophetx.SyncSessionLocal", return_value=mock_session),
            patch("app.workers.poll_prophetx.ProphetXClient") as mock_px_cls,
            patch("app.workers.poll_prophetx._publish_update"),
            patch("app.workers.poll_prophetx._write_heartbeat"),
            patch("app.workers.poll_prophetx._increment_call_counter"),
            patch("app.workers.poll_prophetx.compute_status_match", return_value=True),
            patch("app.workers.poll_prophetx.is_ws_authoritative", return_value=True),
            patch("app.workers.poll_prophetx.log") as mock_log,
        ):
            mock_log.info.side_effect = capture_info
            mock_px = MagicMock()
            mock_px.__aenter__ = AsyncMock(return_value=mock_px)
            mock_px.__aexit__ = AsyncMock(return_value=False)
            mock_px.get_events_raw = AsyncMock(return_value=raw_events)
            mock_px_cls.return_value = mock_px

            run.run(trigger="test")

        discrepancy_logged = any(
            name == "poll_prophetx_authority_window_skip"
            for name, _ in log_calls
        )
        assert discrepancy_logged, (
            f"Expected 'poll_prophetx_authority_window_skip' log. Got: {log_calls}"
        )

    def test_status_match_recomputed_inside_window(self):
        """compute_status_match must be called even when WS is authoritative."""
        from app.workers.poll_prophetx import run
        five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
        existing = self._make_poll_event_mock(ws_delivered_at=five_min_ago, prophetx_status="live")
        mock_session = self._make_poll_session_mock(existing=existing)

        raw_events = [
            {
                "id": "poll-match-001",
                "status": "not_started",
                "sport": "basketball",
                "name": "Test Game",
            }
        ]

        with (
            patch("app.workers.poll_prophetx.SyncSessionLocal", return_value=mock_session),
            patch("app.workers.poll_prophetx.ProphetXClient") as mock_px_cls,
            patch("app.workers.poll_prophetx._publish_update"),
            patch("app.workers.poll_prophetx._write_heartbeat"),
            patch("app.workers.poll_prophetx._increment_call_counter"),
            patch("app.workers.poll_prophetx.compute_status_match", return_value=True) as mock_csm,
            patch("app.workers.poll_prophetx.is_ws_authoritative", return_value=True),
        ):
            mock_px = MagicMock()
            mock_px.__aenter__ = AsyncMock(return_value=mock_px)
            mock_px.__aexit__ = AsyncMock(return_value=False)
            mock_px.get_events_raw = AsyncMock(return_value=raw_events)
            mock_px_cls.return_value = mock_px

            run.run(trigger="test")

        # compute_status_match must have been called (even in authority-skip branch)
        assert mock_csm.called, "compute_status_match must be called even inside authority window"

    def test_stale_ended_sets_poll_source(self):
        """Stale-ended loop must set status_source='poll' and clear ws_delivered_at."""
        from app.workers.poll_prophetx import run
        five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
        stale_start = datetime.now(timezone.utc) - timedelta(hours=6)

        from app.models.event import Event as _Event
        stale_event = MagicMock(spec=_Event)
        stale_event.prophetx_event_id = "stale-001"
        stale_event.prophetx_status = "live"
        stale_event.scheduled_start = stale_start
        stale_event.ws_delivered_at = five_min_ago
        stale_event.odds_api_status = None
        stale_event.sports_api_status = None
        stale_event.sdio_status = None
        stale_event.espn_status = None
        stale_event.oddsblaze_status = None

        mock_session = MagicMock()
        call_count = [0]

        def _execute_side_effect(stmt):
            result = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                # First bulk query: stale events (empty raw_events means no per-event lookups)
                result.scalars.return_value.all.return_value = [stale_event]
            else:
                # Subsequent queries: all-events recompute loop
                result.scalars.return_value.all.return_value = [stale_event]
            return result

        mock_session.execute.side_effect = _execute_side_effect
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with (
            patch("app.workers.poll_prophetx.SyncSessionLocal", return_value=mock_session),
            patch("app.workers.poll_prophetx.ProphetXClient") as mock_px_cls,
            patch("app.workers.poll_prophetx._publish_update"),
            patch("app.workers.poll_prophetx._write_heartbeat"),
            patch("app.workers.poll_prophetx._increment_call_counter"),
            patch("app.workers.poll_prophetx.compute_status_match", return_value=True),
        ):
            mock_px = MagicMock()
            mock_px.__aenter__ = AsyncMock(return_value=mock_px)
            mock_px.__aexit__ = AsyncMock(return_value=False)
            mock_px.get_events_raw = AsyncMock(return_value=[])
            mock_px_cls.return_value = mock_px

            run.run(trigger="test")

        assert stale_event.status_source == "poll", (
            f"Expected stale-ended loop to set status_source='poll', got {stale_event.status_source!r}"
        )
        assert stale_event.ws_delivered_at is None, (
            f"Expected stale-ended loop to clear ws_delivered_at, got {stale_event.ws_delivered_at!r}"
        )


class TestManualStatusSource:
    """Tests that update_event_status sets status_source='manual' and clears ws_delivered_at."""

    def test_manual_update_sets_manual_source(self):
        """update_event_status.run must set status_source='manual' and ws_delivered_at=None."""
        import uuid
        from app.workers.update_event_status import run as ues_run
        from app.models.event import Event
        from app.models.audit_log import AuditLog
        from app.models.config import SystemConfig

        event_uuid = uuid.uuid4()
        event_id_str = str(event_uuid)

        mock_event = MagicMock(spec=Event)
        mock_event.id = event_uuid
        mock_event.prophetx_event_id = "manual-001"
        mock_event.prophetx_status = "not_started"
        mock_event.real_world_status = None
        mock_event.ws_delivered_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_event
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        # alert_only_mode query returns None (disabled)
        alert_cfg_result = MagicMock()
        alert_cfg_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = alert_cfg_result

        mock_redis = MagicMock()
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = True
        mock_redis.lock.return_value = mock_lock

        with (
            patch("app.workers.update_event_status.SyncSessionLocal", return_value=mock_session),
            patch("app.workers.update_event_status.get_sync_redis", return_value=mock_redis),
        ):
            ues_run.run(event_id=event_id_str, target_status="live", actor="operator")

        assert mock_event.status_source == "manual", (
            f"Expected 'manual', got {mock_event.status_source!r}"
        )
        assert mock_event.ws_delivered_at is None, (
            f"Expected ws_delivered_at=None, got {mock_event.ws_delivered_at!r}"
        )
