"""
OpticOdds AMQP consumer — real-time tennis match status updates via RabbitMQ.

Runs as a standalone Docker service (opticodds-consumer), not a Celery task.
pika BlockingConnection blocks indefinitely; this process lives forever.

Flow:
  1. POST to OpticOdds REST API to start the queue → get queue_name
  2. Cache queue_name in Redis (opticodds:queue_name)
  3. Connect to RabbitMQ at v3-rmq.opticodds.com with pika BlockingConnection
  4. Consume messages with manual ack (auto_ack=False), prefetch_count=10
  5. On each message:
     a. Map status via _OPTICODDS_CANONICAL
     b. Fire Slack alert for unknown statuses (D-04) with Redis SETNX dedup
     c. Fuzzy-match to ProphetX event by competitor names + date window (TNNS-02)
     d. Write opticodds_status to DB (verbatim for special statuses, canonical otherwise)
     e. Recompute status_match with 6-param compute_status_match
     f. Fire Slack alert for walkover/retired/suspended with Redis SETNX dedup (D-07)
     g. Update health keys + write heartbeat
  6. On connection failure: reconnect with exponential backoff (5s initial, 60s cap, jitter)
  7. On SIGTERM: call /queue/stop (best-effort) then exit
"""

import json
import logging
import random
import signal
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

import httpx
import pika
import redis as _sync_redis
import structlog
from slack_sdk.webhook import WebhookClient
from sqlalchemy import select

from app.core.config import settings
from app.db.sync_session import SyncSessionLocal
from app.models.event import Event
from app.monitoring.mismatch_detector import compute_status_match

log = structlog.get_logger()

_message_count = [0]  # mutable counter for D-10 raw logging (first 5 messages)
UNKNOWN_STATUS_DEDUP_TTL = 300   # 5-minute dedup window for unknown status Slack alerts
FUZZY_THRESHOLD = 0.75           # Tennis: individual athlete names vary more (ESPN pattern)
SPECIAL_STATUSES = {"walkover", "retired", "suspended"}
SPECIAL_STATUS_DEDUP_TTL = 3600  # 1-hour dedup window for special status alerts

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
# Fuzzy match helpers (mirrors poll_oddsblaze.py / poll_espn.py patterns)
# ─────────────────────────────────────────────────────────────────────────────


def _similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio for fuzzy name comparison (mirrors poll_oddsblaze.py)."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _publish_update(entity_id: str) -> None:
    """Publish SSE update via Redis pub/sub (mirrors poll_oddsblaze.py)."""
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.publish("prophet:updates", json.dumps({"type": "event_updated", "entity_id": entity_id}))


# ─────────────────────────────────────────────────────────────────────────────
# Special status alert (D-07)
# ─────────────────────────────────────────────────────────────────────────────


def _alert_special_status(raw_status: str, event_name: str, home: str, away: str) -> None:
    """Fire Slack alert for operationally significant tennis statuses (D-07).

    Uses Redis SETNX dedup to prevent duplicate alerts within SPECIAL_STATUS_DEDUP_TTL.
    Best-effort — never raises (consumer must continue processing).
    """
    if not settings.SLACK_WEBHOOK_URL:
        return
    try:
        r = _sync_redis.from_url(settings.REDIS_URL)
        dedup_key = f"opticodds_special_status:{raw_status}:{home}:{away}"
        if not r.set(dedup_key, "1", ex=SPECIAL_STATUS_DEDUP_TTL, nx=True):
            return
        text = (
            f":tennis: *OpticOdds tennis alert: `{raw_status}`*\n"
            f"*Event:* {event_name}\n"
            f"*Players:* {home} vs {away}\n"
            f"This status is expected but operationally significant."
        )
        WebhookClient(settings.SLACK_WEBHOOK_URL).send(text=text)
    except Exception as exc:
        log.warning("opticodds_special_status_alert_failed", error=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# DB write — fuzzy match + status write + status_match recompute (TNNS-02)
# ─────────────────────────────────────────────────────────────────────────────


def _write_opticodds_status(data: dict) -> None:  # type: ignore[type-arg]
    """Fuzzy-match an OpticOdds message to a ProphetX event and write status (D-02, D-04, D-05).

    - Extract competitor names + event datetime from message
    - Query DB for tennis events within +/- 1 day
    - Score by name similarity (SequenceMatcher) with time-proximity bonus
    - Write opticodds_status on best match above FUZZY_THRESHOLD
    - Special statuses (walkover/retired/suspended) written verbatim (D-06)
    - Recompute status_match after write (D-05)
    - No-match messages log at WARNING, do not create new events (D-03)
    """
    raw_status = data.get("status")
    if not raw_status:
        return

    # Extract competitor names from message.
    # OpticOdds message schema: home_team / away_team or participants list.
    home = data.get("home_team") or data.get("home", "")
    away = data.get("away_team") or data.get("away", "")

    if not home and not away:
        participants = data.get("participants", [])
        if len(participants) >= 2:
            home = participants[0].get("name", "") if isinstance(participants[0], dict) else str(participants[0])
            away = participants[1].get("name", "") if isinstance(participants[1], dict) else str(participants[1])

    if not home or not away:
        log.warning("opticodds_no_competitors", data_keys=list(data.keys()))
        return

    # Parse event datetime
    start_time_str = data.get("start_time") or data.get("start_date") or data.get("commence_time")
    event_dt = None
    if start_time_str:
        try:
            event_dt = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass
    if event_dt is None:
        event_dt = datetime.now(timezone.utc)  # fallback: match by name only

    event_date = event_dt.date() if hasattr(event_dt, "date") else event_dt

    now = datetime.now(timezone.utc)

    with SyncSessionLocal() as session:
        candidates = session.execute(
            select(Event).where(
                Event.home_team.isnot(None),
                Event.away_team.isnot(None),
                Event.scheduled_start.isnot(None),
            )
        ).scalars().all()

        # Build date index for tennis events only (mirrors poll_oddsblaze.py)
        index: dict[tuple[str, ...], list] = defaultdict(list)
        for ev in candidates:
            sport = (ev.sport or "").strip().lower()
            if "tennis" not in sport:
                continue
            key = (sport, ev.scheduled_start.date())  # type: ignore[union-attr]
            index[key].append(ev)

        # Check +/- 1 day to absorb timezone differences
        match_candidates = []
        for sport_key in index:
            if "tennis" in sport_key[0]:
                if sport_key[1] in (
                    event_date,
                    event_date - timedelta(days=1),
                    event_date + timedelta(days=1),
                ):
                    match_candidates.extend(index[sport_key])

        best_match = None
        best_score = 0.0

        for db_event in match_candidates:
            forward = (
                _similarity(db_event.home_team or "", home)
                + _similarity(db_event.away_team or "", away)
            ) / 2
            reversed_ = (
                _similarity(db_event.home_team or "", away)
                + _similarity(db_event.away_team or "", home)
            ) / 2
            name_score = max(forward, reversed_)

            # Time proximity bonus (mirrors poll_oddsblaze.py)
            time_bonus = 0.0
            if db_event.scheduled_start and event_dt:
                delta_hours = abs((db_event.scheduled_start - event_dt).total_seconds()) / 3600
                if delta_hours <= 1:
                    time_bonus = 0.15
                elif delta_hours <= 6:
                    time_bonus = 0.10
                elif delta_hours <= 12:
                    time_bonus = 0.05

            score = name_score + time_bonus
            if score > best_score:
                best_score = score
                best_match = db_event

        if best_match and best_score >= FUZZY_THRESHOLD:
            # 12-hour guard — reject cross-day mismatches
            if best_match.scheduled_start and event_dt:
                hours_apart = abs((best_match.scheduled_start - event_dt).total_seconds()) / 3600
                if hours_apart > 12:
                    log.warning(
                        "opticodds_time_too_far",
                        home=home, away=away,
                        hours_apart=round(hours_apart, 1),
                    )
                    return

            # D-06: Special statuses written verbatim; normal statuses use canonical
            if raw_status in SPECIAL_STATUSES:
                best_match.opticodds_status = raw_status
            else:
                mapped = _OPTICODDS_CANONICAL.get(raw_status, raw_status)
                best_match.opticodds_status = mapped

            # D-05: Recompute status_match with 6 args
            best_match.status_match = compute_status_match(
                best_match.prophetx_status,
                best_match.odds_api_status,
                best_match.sdio_status,
                best_match.espn_status,
                best_match.oddsblaze_status,
                best_match.opticodds_status,
            )
            best_match.last_real_world_poll = now
            session.commit()
            _publish_update(str(best_match.id))

            log.info(
                "opticodds_event_matched",
                event_id=str(best_match.id),
                home=home, away=away,
                status=raw_status,
                match_score=round(best_score, 3),
            )

            # D-07: Alert on special statuses
            if raw_status in SPECIAL_STATUSES:
                event_name = f"{best_match.home_team} vs {best_match.away_team}"
                _alert_special_status(raw_status, event_name, home, away)

        else:
            # D-03: No match found — log WARNING, do NOT create new events
            log.warning(
                "opticodds_event_unmatched",
                home=home, away=away,
                best_score=round(best_score, 3) if best_match else 0.0,
            )


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
    - Fuzzy-matches event and writes opticodds_status to DB (Phase 13 / TNNS-02)
    - Fires Slack alert for special statuses (D-07)
    - Updates opticodds:last_message_at health key + writes heartbeat
    - Manual ack AFTER DB write so failure causes nack + requeue (D-08)
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

        # Phase 13: fuzzy match + DB write + special alert
        _write_opticodds_status(data)

        _write_last_message_at()
        _write_heartbeat()  # Wire heartbeat on every processed message (Phase 12 Pitfall 5)
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
