"""Unit tests for opticodds_consumer.py

All external dependencies are mocked — no running PostgreSQL, Redis, or RabbitMQ needed.

Covers:
  - _start_queue: success path (REST call, queue_name cache in Redis)
  - _start_queue: failure path (HTTPStatusError → sys.exit(1))
  - _stop_queue: best-effort (no raise on failure)
  - _on_message: ack on success
  - _on_message: nack on exception
  - _on_message: raw body logging for first 5 messages (D-10 counter)
  - _OPTICODDS_CANONICAL: known status mappings
  - Unknown status triggers WARNING log (D-04)
  - _write_connection_state: sets both Redis keys with correct TTL
  - _write_heartbeat: sets worker:heartbeat:opticodds_consumer with ex=90
  - _alert_unknown_status: Slack WebhookClient dispatch with Redis SETNX dedup (D-04)
"""

import json
import sys
from unittest.mock import MagicMock, patch, ANY, call

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_mock_channel():
    ch = MagicMock()
    ch.basic_ack = MagicMock()
    ch.basic_nack = MagicMock()
    return ch


def _make_mock_method(delivery_tag=1):
    method = MagicMock()
    method.delivery_tag = delivery_tag
    return method


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: _start_queue success
# ─────────────────────────────────────────────────────────────────────────────


class TestStartQueueSuccess:
    def test_start_queue_calls_post_with_correct_url_and_header(self):
        """_start_queue POSTs to OPTICODDS_BASE_URL with X-Api-Key header and caches queue_name."""
        mock_redis_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"queue_name": "test-queue-123"}
        mock_response.raise_for_status = MagicMock()

        with patch("app.workers.opticodds_consumer._sync_redis") as mock_redis, \
             patch("app.workers.opticodds_consumer.httpx") as mock_httpx, \
             patch("app.workers.opticodds_consumer.settings") as mock_settings:

            mock_settings.OPTICODDS_BASE_URL = "https://api.opticodds.com/v3/copilot/results/queue/start"
            mock_settings.OPTICODDS_API_KEY = "test-api-key"
            mock_settings.REDIS_URL = "redis://redis:6379"
            mock_redis.from_url.return_value = mock_redis_client
            mock_httpx.post.return_value = mock_response

            from app.workers.opticodds_consumer import _start_queue
            result = _start_queue()

        # Verify POST call
        mock_httpx.post.assert_called_once_with(
            "https://api.opticodds.com/v3/copilot/results/queue/start",
            headers={"X-Api-Key": "test-api-key"},
            timeout=15,
        )
        # Verify Redis cache
        mock_redis_client.set.assert_called_once_with("opticodds:queue_name", "test-queue-123")
        # Verify return value
        assert result == "test-queue-123"


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: _start_queue failure → sys.exit(1)
# ─────────────────────────────────────────────────────────────────────────────


class TestStartQueueFailure:
    def test_start_queue_exits_on_http_error(self):
        """_start_queue calls sys.exit(1) when REST call raises HTTPStatusError."""
        import httpx as real_httpx

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.request = MagicMock()

        with patch("app.workers.opticodds_consumer._sync_redis"), \
             patch("app.workers.opticodds_consumer.httpx") as mock_httpx, \
             patch("app.workers.opticodds_consumer.settings") as mock_settings, \
             patch("app.workers.opticodds_consumer.sys") as mock_sys:

            mock_settings.OPTICODDS_BASE_URL = "https://api.opticodds.com/v3/copilot/results/queue/start"
            mock_settings.OPTICODDS_API_KEY = "bad-key"
            mock_settings.REDIS_URL = "redis://redis:6379"
            mock_httpx.post.side_effect = real_httpx.HTTPStatusError(
                "401", request=MagicMock(), response=MagicMock()
            )
            mock_httpx.HTTPStatusError = real_httpx.HTTPStatusError
            mock_httpx.ConnectError = real_httpx.ConnectError
            mock_httpx.TimeoutException = real_httpx.TimeoutException

            from app.workers.opticodds_consumer import _start_queue
            _start_queue()

        mock_sys.exit.assert_called_once_with(1)


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: _stop_queue best-effort (no raise on failure)
# ─────────────────────────────────────────────────────────────────────────────


class TestStopQueueNoRaise:
    def test_stop_queue_does_not_raise_on_exception(self):
        """_stop_queue must silently handle any exception (best-effort)."""
        with patch("app.workers.opticodds_consumer.httpx") as mock_httpx, \
             patch("app.workers.opticodds_consumer.settings") as mock_settings:

            mock_settings.OPTICODDS_BASE_URL = "https://api.opticodds.com/v3/copilot/results/queue/start"
            mock_settings.OPTICODDS_API_KEY = "key"
            mock_httpx.post.side_effect = ConnectionError("network gone")

            from app.workers.opticodds_consumer import _stop_queue
            # Must not raise
            _stop_queue()


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: _on_message acks on success
# ─────────────────────────────────────────────────────────────────────────────


class TestOnMessageAck:
    def test_on_message_acks_on_success(self):
        """_on_message must call basic_ack on successful processing."""
        ch = _make_mock_channel()
        method = _make_mock_method()
        body = json.dumps({"status": "in_progress"}).encode()

        with patch("app.workers.opticodds_consumer._sync_redis") as mock_redis, \
             patch("app.workers.opticodds_consumer.settings") as mock_settings:
            mock_redis.from_url.return_value = MagicMock()
            mock_settings.REDIS_URL = "redis://redis:6379"

            from app.workers.opticodds_consumer import _on_message
            _on_message(ch, method, None, body)

        ch.basic_ack.assert_called_once_with(delivery_tag=method.delivery_tag)
        ch.basic_nack.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: _on_message nacks on exception
# ─────────────────────────────────────────────────────────────────────────────


class TestOnMessageNack:
    def test_on_message_nacks_on_exception(self):
        """_on_message must call basic_nack with requeue=True when json.loads raises."""
        ch = _make_mock_channel()
        method = _make_mock_method()
        body = b"not valid json {"

        from app.workers.opticodds_consumer import _on_message
        _on_message(ch, method, None, body)

        ch.basic_nack.assert_called_once_with(delivery_tag=method.delivery_tag, requeue=True)
        ch.basic_ack.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: D-10 raw logging counter (first 5 messages only)
# ─────────────────────────────────────────────────────────────────────────────


class TestRawLoggingCounter:
    def test_raw_body_logged_for_first_5_messages_only(self):
        """_on_message logs raw body at DEBUG level for messages 0-4 but not 5+."""
        import app.workers.opticodds_consumer as consumer_mod

        # Reset counter
        consumer_mod._message_count[0] = 0

        ch = _make_mock_channel()
        method = _make_mock_method()
        body = json.dumps({"status": "in_progress"}).encode()

        debug_calls = []

        with patch("app.workers.opticodds_consumer._sync_redis") as mock_redis, \
             patch("app.workers.opticodds_consumer.settings") as mock_settings, \
             patch("app.workers.opticodds_consumer.log") as mock_log:
            mock_redis.from_url.return_value = MagicMock()
            mock_settings.REDIS_URL = "redis://redis:6379"

            # Count debug calls with opticodds_raw_message
            def capture_debug(event_name, **kwargs):
                if event_name == "opticodds_raw_message":
                    debug_calls.append(event_name)

            mock_log.debug.side_effect = capture_debug

            from app.workers.opticodds_consumer import _on_message
            for _ in range(6):
                _on_message(ch, method, None, body)

        # Should have logged raw body exactly 5 times (messages 0-4)
        assert len(debug_calls) == 5, f"Expected 5 raw log calls, got {len(debug_calls)}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: Canonical status mapping
# ─────────────────────────────────────────────────────────────────────────────


class TestCanonicalMapping:
    def test_known_statuses_map_correctly(self):
        """_OPTICODDS_CANONICAL maps known statuses to their canonical values."""
        from app.workers.opticodds_consumer import _OPTICODDS_CANONICAL

        assert _OPTICODDS_CANONICAL["in_progress"] == "live"
        assert _OPTICODDS_CANONICAL["live"] == "live"
        assert _OPTICODDS_CANONICAL["suspended"] == "live"
        assert _OPTICODDS_CANONICAL["finished"] == "ended"
        assert _OPTICODDS_CANONICAL["complete"] == "ended"
        assert _OPTICODDS_CANONICAL["walkover"] == "ended"
        assert _OPTICODDS_CANONICAL["retired"] == "ended"
        assert _OPTICODDS_CANONICAL["cancelled"] == "ended"
        assert _OPTICODDS_CANONICAL["abandoned"] == "ended"
        assert _OPTICODDS_CANONICAL["not_started"] == "not_started"
        assert _OPTICODDS_CANONICAL["scheduled"] == "not_started"
        assert _OPTICODDS_CANONICAL["postponed"] == "not_started"
        assert len(_OPTICODDS_CANONICAL) >= 15


# ─────────────────────────────────────────────────────────────────────────────
# Test 8: Unknown status triggers WARNING log
# ─────────────────────────────────────────────────────────────────────────────


class TestUnknownStatusWarning:
    def test_unknown_status_triggers_warning_log(self):
        """_on_message logs WARNING when status is not in _OPTICODDS_CANONICAL."""
        ch = _make_mock_channel()
        method = _make_mock_method()
        body = json.dumps({"status": "BIZARRE_UNKNOWN_STATUS"}).encode()

        with patch("app.workers.opticodds_consumer._sync_redis") as mock_redis, \
             patch("app.workers.opticodds_consumer.settings") as mock_settings, \
             patch("app.workers.opticodds_consumer._alert_unknown_status"), \
             patch("app.workers.opticodds_consumer.log") as mock_log:
            mock_redis.from_url.return_value = MagicMock()
            mock_settings.REDIS_URL = "redis://redis:6379"
            mock_settings.SLACK_WEBHOOK_URL = None

            from app.workers.opticodds_consumer import _on_message
            _on_message(ch, method, None, body)

        # Warning must be logged with the raw status
        mock_log.warning.assert_called_once_with(
            "opticodds_unknown_status",
            raw_status="BIZARRE_UNKNOWN_STATUS",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test 9a: _write_connection_state sets both Redis keys
# ─────────────────────────────────────────────────────────────────────────────


class TestWriteConnectionStateRedis:
    def test_write_connection_state_sets_both_keys_with_ttl(self):
        """_write_connection_state sets opticodds:connection_state and opticodds:connection_state_since."""
        mock_redis_client = MagicMock()

        with patch("app.workers.opticodds_consumer._sync_redis") as mock_redis, \
             patch("app.workers.opticodds_consumer.settings") as mock_settings:
            mock_redis.from_url.return_value = mock_redis_client
            mock_settings.REDIS_URL = "redis://redis:6379"

            from app.workers.opticodds_consumer import _write_connection_state
            _write_connection_state("connected")

        mock_redis_client.set.assert_any_call("opticodds:connection_state", "connected", ex=120)
        mock_redis_client.set.assert_any_call("opticodds:connection_state_since", ANY, ex=120)
        assert mock_redis_client.set.call_count == 2

    def test_write_heartbeat_sets_correct_key_and_ttl(self):
        """_write_heartbeat sets worker:heartbeat:opticodds_consumer with ex=90."""
        mock_redis_client = MagicMock()

        with patch("app.workers.opticodds_consumer._sync_redis") as mock_redis, \
             patch("app.workers.opticodds_consumer.settings") as mock_settings:
            mock_redis.from_url.return_value = mock_redis_client
            mock_settings.REDIS_URL = "redis://redis:6379"

            from app.workers.opticodds_consumer import _write_heartbeat
            _write_heartbeat()

        mock_redis_client.set.assert_called_once_with(
            "worker:heartbeat:opticodds_consumer", "1", ex=90
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test 10: D-04 Slack alert dispatch with dedup
# ─────────────────────────────────────────────────────────────────────────────


class TestUnknownStatusSlackAlert:
    def test_alert_unknown_status_calls_slack_webhook_client(self):
        """_alert_unknown_status fires Slack WebhookClient when not deduplicated."""
        mock_redis_client = MagicMock()
        mock_redis_client.set.return_value = True  # nx=True → not already sent
        mock_webhook_instance = MagicMock()

        with patch("app.workers.opticodds_consumer._sync_redis") as mock_redis, \
             patch("app.workers.opticodds_consumer.WebhookClient") as mock_wc_cls, \
             patch("app.workers.opticodds_consumer.settings") as mock_settings:
            mock_redis.from_url.return_value = mock_redis_client
            mock_wc_cls.return_value = mock_webhook_instance
            mock_settings.REDIS_URL = "redis://redis:6379"
            mock_settings.SLACK_WEBHOOK_URL = "https://hooks.slack.com/test"

            from app.workers.opticodds_consumer import _alert_unknown_status
            _alert_unknown_status("BIZARRE_VALUE", '{"status": "BIZARRE_VALUE"}')

        # WebhookClient instantiated with the webhook URL
        mock_wc_cls.assert_called_once_with("https://hooks.slack.com/test")
        # .send() called with text containing the unknown status
        send_kwargs = mock_webhook_instance.send.call_args
        assert send_kwargs is not None
        text = send_kwargs.kwargs.get("text") or (send_kwargs.args[0] if send_kwargs.args else "")
        assert "BIZARRE_VALUE" in text

    def test_alert_unknown_status_dedup_prevents_duplicate_slack_call(self):
        """_alert_unknown_status must NOT call WebhookClient when Redis SETNX returns False."""
        mock_redis_client = MagicMock()
        mock_redis_client.set.return_value = False  # nx=True → already sent within window

        with patch("app.workers.opticodds_consumer._sync_redis") as mock_redis, \
             patch("app.workers.opticodds_consumer.WebhookClient") as mock_wc_cls, \
             patch("app.workers.opticodds_consumer.settings") as mock_settings:
            mock_redis.from_url.return_value = mock_redis_client
            mock_settings.REDIS_URL = "redis://redis:6379"
            mock_settings.SLACK_WEBHOOK_URL = "https://hooks.slack.com/test"

            from app.workers.opticodds_consumer import _alert_unknown_status
            _alert_unknown_status("BIZARRE_VALUE", '{"status": "BIZARRE_VALUE"}')

        # WebhookClient must NOT be instantiated (dedup prevented it)
        mock_wc_cls.assert_not_called()

    def test_alert_unknown_status_skips_when_no_webhook_url(self):
        """_alert_unknown_status logs warning and returns early when SLACK_WEBHOOK_URL is falsy."""
        with patch("app.workers.opticodds_consumer._sync_redis"), \
             patch("app.workers.opticodds_consumer.WebhookClient") as mock_wc_cls, \
             patch("app.workers.opticodds_consumer.settings") as mock_settings, \
             patch("app.workers.opticodds_consumer.log") as mock_log:
            mock_settings.SLACK_WEBHOOK_URL = None

            from app.workers.opticodds_consumer import _alert_unknown_status
            _alert_unknown_status("SOME_STATUS", "body")

        mock_wc_cls.assert_not_called()
        mock_log.warning.assert_called_once_with("opticodds_slack_not_configured")
