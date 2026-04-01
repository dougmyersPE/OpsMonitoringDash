"""Unit tests for WSREL-01 reconnect reconciliation in ws_prophetx.

Tests that _on_connect (inner function of _connect_and_run) dispatches an
immediate poll_prophetx reconciliation run via celery_app.send_task.

Strategy: Mock pusher.Pusher so that pusher_client.connect() triggers the
_on_connect callback synchronously (simulating Pusher firing the event),
then raise RuntimeError after the callback runs to short-circuit the
blocking while loop. All assertions happen inside the patch context.
"""

from unittest.mock import MagicMock, patch, call
import pytest


class TestWsReconnectReconciliation:
    def _run_connect_and_capture(self, mock_celery):
        """
        Run _connect_and_run with mocks that:
        1. Capture the _on_connect callback from connection.bind()
        2. Invoke it synchronously when connect() is called (simulating Pusher connect event)
        3. Raise RuntimeError after callback runs to exit the blocking while loop

        mock_celery is injected so callers can configure side effects before calling.
        """
        from app.workers import ws_prophetx

        captured_callbacks = {}

        def capture_bind(event_name, callback):
            captured_callbacks[event_name] = callback

        mock_connection = MagicMock()
        mock_connection.bind.side_effect = capture_bind

        mock_pusher_instance = MagicMock()
        mock_pusher_instance.connection = mock_connection

        # connect() fires the _on_connect callback then raises to break the while loop
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
            patch("app.workers.ws_prophetx._write_ws_connection_state", MagicMock(), create=True),
            patch("app.workers.ws_prophetx.threading.Event", return_value=mock_event),
        ):
            try:
                ws_prophetx._connect_and_run()
            except RuntimeError as e:
                if "test_exit_loop" not in str(e):
                    raise  # unexpected error

            # Return the captured callback reference for additional assertions
            return captured_callbacks.get("pusher:connection_established")

    def test_on_connect_dispatches_poll_prophetx(self):
        """_on_connect must call celery_app.send_task with poll_prophetx.run and trigger kwarg."""
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
            patch("app.workers.ws_prophetx._write_ws_connection_state", MagicMock(), create=True),
            patch("app.workers.ws_prophetx.threading.Event", return_value=mock_event),
        ):
            try:
                ws_prophetx._connect_and_run()
            except RuntimeError as e:
                if "test_exit_loop" not in str(e):
                    raise

            # Assert inside the patch context
            mock_celery.send_task.assert_called_once_with(
                "app.workers.poll_prophetx.run",
                kwargs={"trigger": "ws_reconnect"},
            )

    def test_on_connect_resilient_to_broker_failure(self):
        """_on_connect must NOT raise if celery_app.send_task raises an exception."""
        mock_celery = MagicMock()
        mock_celery.send_task.side_effect = Exception("broker down")

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
                try:
                    cb("{}")
                except Exception as exc:
                    pytest.fail(
                        f"_on_connect raised {exc!r} when broker fails — must be caught silently"
                    )
            raise RuntimeError("test_exit_loop")

        mock_pusher_instance.connect.side_effect = connect_then_raise
        mock_event = MagicMock()
        mock_event.wait.return_value = True

        with (
            patch("app.workers.ws_prophetx.pysher.Pusher", return_value=mock_pusher_instance),
            patch("app.workers.ws_prophetx._get_access_token", return_value="test-token"),
            patch("app.workers.ws_prophetx._get_pusher_config", return_value={"key": "k", "cluster": "us2"}),
            patch("app.workers.ws_prophetx.celery_app", mock_celery),
            patch("app.workers.ws_prophetx._write_ws_connection_state", MagicMock(), create=True),
            patch("app.workers.ws_prophetx.threading.Event", return_value=mock_event),
        ):
            try:
                ws_prophetx._connect_and_run()
            except RuntimeError as e:
                if "test_exit_loop" not in str(e):
                    raise  # unexpected — broker failure propagated through connect()

    def test_on_connect_callback_registered_on_connection_established(self):
        """The _on_connect callback must be registered for 'pusher:connection_established' event."""
        mock_celery = MagicMock()

        from app.workers import ws_prophetx
        captured_bind_calls = []

        def capture_bind(event_name, callback):
            captured_bind_calls.append((event_name, callback))
            raise RuntimeError("test_exit_after_bind")  # exit after first bind

        mock_connection = MagicMock()
        mock_connection.bind.side_effect = capture_bind

        mock_pusher_instance = MagicMock()
        mock_pusher_instance.connection = mock_connection

        with (
            patch("app.workers.ws_prophetx.pysher.Pusher", return_value=mock_pusher_instance),
            patch("app.workers.ws_prophetx._get_access_token", return_value="test-token"),
            patch("app.workers.ws_prophetx._get_pusher_config", return_value={"key": "k", "cluster": "us2"}),
            patch("app.workers.ws_prophetx.celery_app", mock_celery),
        ):
            try:
                ws_prophetx._connect_and_run()
            except RuntimeError as e:
                if "test_exit_after_bind" not in str(e):
                    raise

        assert len(captured_bind_calls) == 1
        event_name, callback = captured_bind_calls[0]
        assert event_name == "pusher:connection_established"
        assert callable(callback), "_on_connect must be a callable"


class TestPollProphetxTriggerKwarg:
    def test_run_accepts_trigger_kwarg(self):
        """poll_prophetx.run must accept a trigger kwarg defaulting to 'scheduled'."""
        import inspect
        from app.workers.poll_prophetx import run

        # For Celery bind=True tasks, the actual function is accessible via run attribute
        # (the task object has a .run attribute pointing to the decorated function)
        underlying_fn = getattr(run, "run", None) or getattr(run, "__wrapped__", None)
        assert underlying_fn is not None, (
            "Cannot access underlying function for poll_prophetx.run. "
            "Expected .run or __wrapped__ attribute."
        )

        sig = inspect.signature(underlying_fn)
        params = list(sig.parameters.keys())

        assert "trigger" in params, (
            f"poll_prophetx.run must have 'trigger' parameter, got: {params}"
        )
        assert sig.parameters["trigger"].default == "scheduled", (
            f"trigger must default to 'scheduled', got: {sig.parameters['trigger'].default}"
        )

    def test_run_trigger_default_is_scheduled(self):
        """Verify trigger parameter default value is 'scheduled'."""
        import inspect
        from app.workers.poll_prophetx import run

        underlying_fn = getattr(run, "run", None) or getattr(run, "__wrapped__", None)
        assert underlying_fn is not None

        sig = inspect.signature(underlying_fn)
        trigger_param = sig.parameters.get("trigger")
        assert trigger_param is not None, "trigger parameter missing from poll_prophetx.run"
        assert trigger_param.default == "scheduled"
