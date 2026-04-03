"""
OpticOdds AMQP consumer — real-time tennis match status updates via RabbitMQ.

Runs as a standalone Docker service (opticodds-consumer), not a Celery task.
pika BlockingConnection blocks indefinitely; this process lives forever.

Flow:
  1. POST to OpticOdds REST API to start the queue → get queue_name
  2. Cache queue_name in Redis (opticodds:queue_name)
  3. Connect to RabbitMQ at v3-rmq.opticodds.com with pika BlockingConnection
  4. Consume messages with manual ack (auto_ack=False), prefetch_count=10
  5. On each message: map status via _OPTICODDS_CANONICAL, ack, update health keys
  6. On unknown status: log WARNING + fire Slack alert (D-04) with Redis SETNX dedup
  7. On connection failure: reconnect with exponential backoff (5s initial, 60s cap, jitter)
  8. On SIGTERM: call /queue/stop (best-effort) then exit

NOTE (Phase 12 scope): This consumer receives, acks, and logs messages.
DB writes (opticodds_status column) require fuzzy match to identify the event row —
that is Phase 13 scope (TNNS-02). The _write_opticodds_status function will be added
in Phase 13.
"""

import json
import logging
import random
import signal
import sys
import time
from datetime import datetime, timezone

import httpx
import pika
import redis as _sync_redis
import structlog
from slack_sdk.webhook import WebhookClient

from app.core.config import settings

log = structlog.get_logger()

_message_count = [0]  # mutable counter for D-10 raw logging (first 5 messages)
UNKNOWN_STATUS_DEDUP_TTL = 300  # 5-minute dedup window for unknown status Slack alerts

# ─────────────────────────────────────────────────────────────────────────────
# Status mapping (D-05: explicit dict, no default fallthrough)
# ─────────────────────────────────────────────────────────────────────────────

_OPTICODDS_CANONICAL: dict[str, str] = {
    "not_started":   "not_started",
    "scheduled":     "not_started",
    "delayed":       "not_started",
    "start_delayed": "not_started",
    "postponed":     "not_started",
    "in_progress":   "live",
    "live":          "live",
    "suspended":     "live",
    "interrupted":   "live",
    "finished":      "ended",
    "complete":      "ended",
    "retired":       "ended",
    "walkover":      "ended",
    "cancelled":     "ended",
    "abandoned":     "ended",
}

# ─────────────────────────────────────────────────────────────────────────────
# Queue lifecycle helpers (D-01, D-02, D-03)
# ─────────────────────────────────────────────────────────────────────────────


def _start_queue() -> str:
    """POST to OpticOdds REST API to start the queue and return the queue_name.

    Caches queue_name in Redis at opticodds:queue_name (no TTL).
    Calls sys.exit(1) on any failure — consumer cannot operate without a queue (D-02).
    """
    try:
        resp = httpx.post(
            settings.OPTICODDS_BASE_URL,
            headers={"X-Api-Key": settings.OPTICODDS_API_KEY or ""},
            timeout=15,
        )
        resp.raise_for_status()
        queue_name: str = resp.json()["queue_name"]
        r = _sync_redis.from_url(settings.REDIS_URL)
        r.set("opticodds:queue_name", queue_name)
        log.info("opticodds_queue_started", queue_name=queue_name)
        return queue_name
    except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
        log.critical("opticodds_queue_start_failed", error=str(exc))
        sys.exit(1)
    except Exception as exc:
        log.critical("opticodds_queue_start_failed", error=str(exc))
        sys.exit(1)


def _stop_queue() -> None:
    """POST to OpticOdds REST API to stop the queue.

    Best-effort — called on SIGTERM. Errors are logged but never re-raised (D-01).
    Derives stop URL by replacing /start with /stop in OPTICODDS_BASE_URL.
    """
    try:
        stop_url = settings.OPTICODDS_BASE_URL.replace("/start", "/stop")
        httpx.post(
            stop_url,
            headers={"X-Api-Key": settings.OPTICODDS_API_KEY or ""},
            timeout=10,
        )
        log.info("opticodds_queue_stopped")
    except Exception as exc:
        log.warning("opticodds_queue_stop_failed", error=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Slack alert helper for unknown statuses (D-04)
# ─────────────────────────────────────────────────────────────────────────────


def _alert_unknown_status(raw_status: str, message_body: str) -> None:
    """Fire a Slack alert for an unknown OpticOdds status string.

    Uses Redis SETNX dedup to prevent duplicate alerts within UNKNOWN_STATUS_DEDUP_TTL.
    Best-effort — never raises (consumer must continue processing).
    """
    if not settings.SLACK_WEBHOOK_URL:
        log.warning("opticodds_slack_not_configured")
        return

    try:
        r = _sync_redis.from_url(settings.REDIS_URL)
        dedup_key = f"opticodds_unknown_status:{raw_status}"
        if not r.set(dedup_key, "1", ex=UNKNOWN_STATUS_DEDUP_TTL, nx=True):
            # Already alerted within the dedup window — skip silently
            return

        text = (
            f":warning: *OpticOdds unknown tennis status*\n"
            f"*Status:* `{raw_status}`\n"
            f"*Body (truncated):* `{message_body[:500]}`\n"
            f"Investigate and add to `_OPTICODDS_CANONICAL` mapping if needed."
        )

        try:
            WebhookClient(settings.SLACK_WEBHOOK_URL).send(text=text)
        except Exception as exc:
            log.warning("opticodds_slack_alert_failed", error=str(exc))
    except Exception as exc:
        log.warning("opticodds_slack_alert_failed", error=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Redis health keys (mirror ws_prophetx.py with opticodds prefix)
# ─────────────────────────────────────────────────────────────────────────────


def _write_heartbeat() -> None:
    """Write worker:heartbeat:opticodds_consumer with 90s TTL."""
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.set("worker:heartbeat:opticodds_consumer", "1", ex=90)


def _write_connection_state(state: str) -> None:
    """Write opticodds:connection_state and opticodds:connection_state_since with 120s TTL.

    Self-expires if consumer dies — absence means disconnected.
    """
    r = _sync_redis.from_url(settings.REDIS_URL)
    now_iso = datetime.now(timezone.utc).isoformat()
    r.set("opticodds:connection_state", state, ex=120)
    r.set("opticodds:connection_state_since", now_iso, ex=120)


def _write_last_message_at() -> None:
    """Write opticodds:last_message_at with 90s TTL on every received message."""
    r = _sync_redis.from_url(settings.REDIS_URL)
    now_iso = datetime.now(timezone.utc).isoformat()
    r.set("opticodds:last_message_at", now_iso, ex=90)


# ─────────────────────────────────────────────────────────────────────────────
# Message callback
# ─────────────────────────────────────────────────────────────────────────────


def _on_message(ch, method, properties, body) -> None:  # type: ignore[type-arg]
    """pika message callback — process one AMQP message.

    - Logs raw body at DEBUG for first 5 messages (D-10)
    - Maps status via _OPTICODDS_CANONICAL
    - Fires Slack alert for unknown statuses (D-04)
    - Updates opticodds:last_message_at health key
    - Manual ack on success, nack (requeue=True) on exception (D-08)
    """
    try:
        # D-10: Log raw body for the first 5 messages to verify AMQP schema empirically
        if _message_count[0] < 5:
            log.debug("opticodds_raw_message", body=body.decode()[:1000])
        _message_count[0] += 1

        data = json.loads(body)
        raw_status = data.get("status")

        if raw_status:
            mapped = _OPTICODDS_CANONICAL.get(raw_status)
            if mapped is None:
                # D-04: Unknown status — log at WARNING and fire Slack alert
                log.warning("opticodds_unknown_status", raw_status=raw_status)
                _alert_unknown_status(raw_status, body.decode()[:1000])

        _write_last_message_at()
        ch.basic_ack(delivery_tag=method.delivery_tag)
        log.debug("opticodds_message_processed", raw_status=raw_status)

    except Exception:
        log.exception("opticodds_message_error")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


# ─────────────────────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────────────────────


def run() -> None:
    """Start the queue, then connect to RabbitMQ and consume indefinitely.

    Reconnects with exponential backoff (5s initial, 60s cap, jitter) on failure (D-09).
    """
    queue_name = _start_queue()  # Fatal on failure (D-02)

    retry_delay = 5
    max_delay = 60

    while True:
        try:
            params = pika.ConnectionParameters(
                host="v3-rmq.opticodds.com",
                port=5672,
                virtual_host="api",
                credentials=pika.PlainCredentials(
                    settings.OPTICODDS_RMQ_USERNAME or "",
                    settings.OPTICODDS_RMQ_PASSWORD or "",
                ),
                heartbeat=30,                  # D-07: faster dead-connection detection
                blocked_connection_timeout=300, # D-07: unblock after 5 minutes
            )
            connection = pika.BlockingConnection(params)
            ch = connection.channel()
            ch.basic_qos(prefetch_count=10)
            ch.basic_consume(
                queue=queue_name,
                on_message_callback=_on_message,
                auto_ack=False,  # D-08: manual ack for resilience
            )

            _write_connection_state("connected")
            retry_delay = 5  # successful connection — reset backoff
            log.info("opticodds_rmq_connected", queue=queue_name)

            # Blocks here; pika calls _on_message for every message
            ch.start_consuming()

        except (pika.exceptions.AMQPConnectionError, pika.exceptions.AMQPChannelError) as exc:
            _write_connection_state("reconnecting")
            jitter = random.uniform(0, 1)
            log.warning(
                "opticodds_rmq_disconnected",
                error=str(exc),
                retry_in=retry_delay + jitter,
            )
            time.sleep(retry_delay + jitter)  # D-09: jitter prevents reconnect storms
            retry_delay = min(retry_delay * 2, max_delay)

        except Exception:
            log.exception("opticodds_rmq_unexpected_error")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [pika] %(message)s",
        stream=sys.stdout,
    )

    log.info("opticodds_consumer_starting")

    def _shutdown(sig, frame):  # type: ignore[type-arg]
        log.info("opticodds_consumer_shutdown", signal=sig)
        _stop_queue()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    run()
