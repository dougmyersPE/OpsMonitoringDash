"""Unit tests for Redis WS diagnostic key wiring in ws_prophetx.

Tests that:
- _write_ws_diagnostics("sport_event") sets ws:last_message_at, ws:last_sport_event_at, incr ws:sport_event_count
- _write_ws_diagnostics("odds") sets ws:last_message_at only
- _write_ws_connection_state("connected") sets ws:connection_state with 120s TTL
- _handle_broadcast_event calls _write_ws_diagnostics with the change_type
- _on_connect calls _write_ws_connection_state("connected")
"""

from unittest.mock import MagicMock, patch, call, ANY
import pytest


class TestWriteWsDiagnostics:
    def test_sport_event_sets_all_three_keys(self):
        """_write_ws_diagnostics('sport_event') must set last_message_at, last_sport_event_at, incr count."""
        mock_redis_client = MagicMock()

        with patch("app.workers.ws_prophetx._sync_redis") as mock_sync_redis:
            mock_sync_redis.from_url.return_value = mock_redis_client

            from app.workers.ws_prophetx import _write_ws_diagnostics
            _write_ws_diagnostics("sport_event")

        # ws:last_message_at must be set with 120s TTL
        mock_redis_client.set.assert_any_call("ws:last_message_at", ANY, ex=120)
        # ws:last_sport_event_at must be set (no TTL for sport_event)
        mock_redis_client.set.assert_any_call("ws:last_sport_event_at", ANY)
        # ws:sport_event_count must be incremented
        mock_redis_client.incr.assert_called_once_with("ws:sport_event_count")

    def test_non_sport_event_sets_only_last_message_at(self):
        """_write_ws_diagnostics('odds') must only set ws:last_message_at — no sport_event keys."""
        mock_redis_client = MagicMock()

        with patch("app.workers.ws_prophetx._sync_redis") as mock_sync_redis:
            mock_sync_redis.from_url.return_value = mock_redis_client

            from app.workers.ws_prophetx import _write_ws_diagnostics
            _write_ws_diagnostics("odds")

        # ws:last_message_at must be set
        mock_redis_client.set.assert_called_once_with("ws:last_message_at", ANY, ex=120)
        # ws:last_sport_event_at must NOT be set
        set_calls = [str(c) for c in mock_redis_client.set.call_args_list]
        assert not any("ws:last_sport_event_at" in c for c in set_calls), (
            "ws:last_sport_event_at must NOT be set for non-sport_event change_type"
        )
        # ws:sport_event_count must NOT be incremented
        mock_redis_client.incr.assert_not_called()

    def test_market_change_type_sets_only_last_message_at(self):
        """_write_ws_diagnostics('market') must only set ws:last_message_at."""
        mock_redis_client = MagicMock()

        with patch("app.workers.ws_prophetx._sync_redis") as mock_sync_redis:
            mock_sync_redis.from_url.return_value = mock_redis_client

            from app.workers.ws_prophetx import _write_ws_diagnostics
            _write_ws_diagnostics("market")

        mock_redis_client.set.assert_called_once_with("ws:last_message_at", ANY, ex=120)
        mock_redis_client.incr.assert_not_called()


class TestWriteWsConnectionState:
    def test_connected_sets_connection_state_with_ttl(self):
        """_write_ws_connection_state('connected') must set ws:connection_state with ex=120."""
        mock_redis_client = MagicMock()

        with patch("app.workers.ws_prophetx._sync_redis") as mock_sync_redis:
            mock_sync_redis.from_url.return_value = mock_redis_client

            from app.workers.ws_prophetx import _write_ws_connection_state
            _write_ws_connection_state("connected")

        mock_redis_client.set.assert_called_once_with("ws:connection_state", "connected", ex=120)

    def test_disconnected_sets_connection_state(self):
        """_write_ws_connection_state must accept any state value."""
        mock_redis_client = MagicMock()

        with patch("app.workers.ws_prophetx._sync_redis") as mock_sync_redis:
            mock_sync_redis.from_url.return_value = mock_redis_client

            from app.workers.ws_prophetx import _write_ws_connection_state
            _write_ws_connection_state("disconnected")

        mock_redis_client.set.assert_called_once_with("ws:connection_state", "disconnected", ex=120)


class TestHandleBroadcastEventCallsDiagnostics:
    def test_handle_broadcast_event_calls_write_ws_diagnostics(self):
        """_handle_broadcast_event must call _write_ws_diagnostics with the message change_type."""
        import json, base64

        # Build a minimal sport_event broadcast payload
        event_payload = {
            "event_id": "test-evt-001",
            "status": "not_started",
            "sport": "soccer",
            "name": "Team A vs Team B",
        }
        wrapper = {
            "change_type": "sport_event",
            "op": "c",
            "payload": base64.b64encode(json.dumps(event_payload).encode()).decode(),
        }
        data = json.dumps(wrapper)

        with (
            patch("app.workers.ws_prophetx._write_ws_diagnostics") as mock_diag,
            patch("app.workers.ws_prophetx._upsert_event"),
        ):
            from app.workers.ws_prophetx import _handle_broadcast_event
            _handle_broadcast_event("tournament_123", data)

        mock_diag.assert_called_once_with("sport_event")

    def test_handle_broadcast_event_calls_diagnostics_for_non_sport_event(self):
        """_handle_broadcast_event must call _write_ws_diagnostics even for non-sport_event types."""
        import json

        wrapper = {
            "change_type": "market",
            "op": "u",
            "payload": None,
        }
        data = json.dumps(wrapper)

        with patch("app.workers.ws_prophetx._write_ws_diagnostics") as mock_diag:
            from app.workers.ws_prophetx import _handle_broadcast_event
            _handle_broadcast_event("tournament_456", data)

        mock_diag.assert_called_once_with("market")


class TestOnConnectCallsWriteConnectionState:
    def test_on_connect_calls_write_ws_connection_state_connected(self):
        """_on_connect must call _write_ws_connection_state('connected') on every connection."""
        mock_celery = MagicMock()

        from app.workers import ws_prophetx
        captured_callbacks = {}

        def capture_bind(event_name, callback):
            captured_callbacks[event_name] = callback

        mock_connection = MagicMock()
        mock_connection.bind.side_effect = capture_bind

        mock_pusher_instance = MagicMock()
        mock_pusher_instance.connection = mock_connection

        def connect_then_raise():
            cb = captured_callbacks.get("pusher:connection_established")
            if cb:
                cb("{}")
            raise RuntimeError("test_exit_loop")

        mock_pusher_instance.connect.side_effect = connect_then_raise
        mock_event = MagicMock()
        mock_event.wait.return_value = True

        with (
            patch("app.workers.ws_prophetx.pysher.Pusher", return_value=mock_pusher_instance),
            patch("app.workers.ws_prophetx._get_access_token", return_value="test-token"),
            patch("app.workers.ws_prophetx._get_pusher_config", return_value={"key": "k", "cluster": "us2"}),
            patch("app.workers.ws_prophetx.celery_app", mock_celery),
            patch("app.workers.ws_prophetx._write_ws_connection_state") as mock_conn_state,
            patch("app.workers.ws_prophetx.threading.Event", return_value=mock_event),
        ):
            try:
                ws_prophetx._connect_and_run()
            except RuntimeError as e:
                if "test_exit_loop" not in str(e):
                    raise

            mock_conn_state.assert_called_once_with("connected")
