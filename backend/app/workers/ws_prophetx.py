"""
ProphetX WebSocket consumer — real-time event updates via Pusher.

Runs as a standalone Docker service (ws-consumer), not a Celery task.
pysher maintains a persistent connection; this process lives forever.

Flow:
  1. Authenticate with ProphetX → get access_token (20 min TTL)
  2. Fetch Pusher connection config (key, cluster)
  3. Connect to Pusher with auth_endpoint pointing at /partner/mm/pusher
  4. Subscribe to broadcast channel → bind sport_event + health_check handlers
  5. Block until ~60s before token expiry, then disconnect and reconnect with fresh token
  6. On any failure, reconnect with exponential backoff (cap 60s)

poll_prophetx continues to run at 5-minute intervals as a reconciliation fallback
to catch events missed during WebSocket downtime or reconnection windows.
"""

import base64
import json
import logging
import signal
import sys
import threading
import time
from datetime import datetime, timezone

import httpx
import pysher
import redis as _sync_redis
import structlog
from sqlalchemy import select

from app.core.config import settings
from app.db.sync_session import SyncSessionLocal
from app.models.event import Event
from app.monitoring.mismatch_detector import compute_status_match

log = structlog.get_logger()

# ─────────────────────────────────────────────────────────────────────────────
# Token state (module-level; single-threaded main loop reads/writes it)
# ─────────────────────────────────────────────────────────────────────────────

class _TokenState:
    access_token: str | None = None
    expires_at: float = 0.0  # unix timestamp (already has 60s safety buffer subtracted)


_token = _TokenState()


def _get_access_token() -> str:
    """Return a valid ProphetX access token, re-authenticating when needed."""
    if _token.access_token and time.time() < _token.expires_at:
        return _token.access_token

    resp = httpx.post(
        f"{settings.PROPHETX_BASE_URL}/auth/login",
        json={"access_key": settings.PROPHETX_ACCESS_KEY, "secret_key": settings.PROPHETX_SECRET_KEY},
        timeout=15,
    )
    resp.raise_for_status()
    payload = resp.json()["data"]
    _token.access_token = payload["access_token"]
    _token.expires_at = payload["access_expire_time"] - 60  # 60s buffer before real expiry
    log.info("ws_prophetx_authenticated", ttl_seconds=int(_token.expires_at - time.time()))
    return _token.access_token  # type: ignore[return-value]


def _get_pusher_config(token: str) -> dict:
    """Fetch Pusher key + cluster from ProphetX connection-config endpoint."""
    resp = httpx.get(
        f"{settings.PROPHETX_BASE_URL}/websocket/connection-config",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    # Flat response: {app_id, cluster, key, service} — no "data" wrapper
    log.info("ws_prophetx_pusher_config", key=body.get("key"), cluster=body.get("cluster"))
    return body.get("data", body)


# ─────────────────────────────────────────────────────────────────────────────
# Redis helpers (mirrors poll_prophetx patterns exactly)
# ─────────────────────────────────────────────────────────────────────────────

def _publish_update(update_type: str, entity_id: str) -> None:
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.publish("prophet:updates", json.dumps({"type": update_type, "entity_id": entity_id}))


def _write_heartbeat() -> None:
    r = _sync_redis.from_url(settings.REDIS_URL)
    # 90s TTL — written every 10s in the main loop and on every Pusher health_check
    r.set("worker:heartbeat:ws_prophetx", "1", ex=90)


# ─────────────────────────────────────────────────────────────────────────────
# DB upsert (same logic as poll_prophetx, extracted for WebSocket events)
# ─────────────────────────────────────────────────────────────────────────────

def _upsert_event(event_data: dict, op: str | None) -> None:
    """Write a Pusher sport_event payload to the database and publish SSE."""
    prophetx_event_id = str(
        event_data.get("event_id") or event_data.get("id") or ""
    )
    if not prophetx_event_id:
        log.warning("ws_prophetx_event_missing_id", keys=list(event_data.keys()))
        return

    now = datetime.now(timezone.utc)

    # op=d (delete) — ProphetX removed the event; treat as ended
    if op == "d":
        with SyncSessionLocal() as session:
            existing = session.execute(
                select(Event).where(Event.prophetx_event_id == prophetx_event_id)
            ).scalar_one_or_none()
            if existing and (existing.prophetx_status or "").lower() not in ("ended", "cancelled"):
                existing.prophetx_status = "ended"
                existing.last_prophetx_poll = now
                existing.status_match = compute_status_match(
                    "ended",
                    existing.odds_api_status,
                    existing.sports_api_status,
                    existing.sdio_status,
                    existing.espn_status,
                    existing.oddsblaze_status,
                )
                session.commit()
                log.info("ws_prophetx_event_deleted", prophetx_event_id=prophetx_event_id)
                _publish_update("event_updated", prophetx_event_id)
        return

    # op=c or op=u — upsert
    status_value = event_data.get("status") or event_data.get("event_status")

    competitors = event_data.get("competitors") or []
    home_team = next(
        (c.get("name") or c.get("display_name") for c in competitors if c.get("side") == "home"),
        None,
    )
    away_team = next(
        (c.get("name") or c.get("display_name") for c in competitors if c.get("side") == "away"),
        None,
    )
    if not home_team and not away_team:
        event_name = event_data.get("name") or event_data.get("display_name") or ""
        if " at " in event_name:
            parts = event_name.split(" at ", 1)
            away_team = parts[0].strip()
            home_team = parts[1].strip()

    scheduled_raw = event_data.get("scheduled") or event_data.get("scheduled_start")
    scheduled_start = None
    if scheduled_raw is not None:
        try:
            if isinstance(scheduled_raw, (int, float)):
                scheduled_start = datetime.fromtimestamp(scheduled_raw, tz=timezone.utc)
            else:
                scheduled_start = datetime.fromisoformat(str(scheduled_raw))
                if scheduled_start.tzinfo is None:
                    scheduled_start = scheduled_start.replace(tzinfo=timezone.utc)
        except Exception:
            pass

    tournament_name = event_data.get("tournament_name")

    with SyncSessionLocal() as session:
        existing = session.execute(
            select(Event).where(Event.prophetx_event_id == prophetx_event_id)
        ).scalar_one_or_none()

        if existing is None:
            event = Event(
                prophetx_event_id=prophetx_event_id,
                sport=str(
                    event_data.get("sport") or event_data.get("sport_name") or "unknown"
                ),
                league=tournament_name,
                name=str(
                    event_data.get("name") or event_data.get("display_name") or prophetx_event_id
                ),
                home_team=home_team,
                away_team=away_team,
                scheduled_start=scheduled_start,
                prophetx_status=status_value,
                last_prophetx_poll=now,
                status_match=compute_status_match(status_value, None, None, None, None, None),
            )
            session.add(event)
            log.info(
                "ws_prophetx_event_created",
                prophetx_event_id=prophetx_event_id,
                status=status_value,
            )
        else:
            existing.sport = str(
                event_data.get("sport") or event_data.get("sport_name") or existing.sport
            )
            if tournament_name:
                existing.league = tournament_name
            existing.name = str(
                event_data.get("name") or event_data.get("display_name") or existing.name
            )
            existing.home_team = home_team or existing.home_team
            existing.away_team = away_team or existing.away_team
            if scheduled_start is not None:
                existing.scheduled_start = scheduled_start
            existing.prophetx_status = status_value
            existing.last_prophetx_poll = now
            existing.status_match = compute_status_match(
                status_value,
                existing.odds_api_status,
                existing.sports_api_status,
                existing.sdio_status,
                existing.espn_status,
                existing.oddsblaze_status,
            )
            log.info(
                "ws_prophetx_event_updated",
                prophetx_event_id=prophetx_event_id,
                status=status_value,
            )

        session.commit()

    _publish_update("event_updated", prophetx_event_id)


# ─────────────────────────────────────────────────────────────────────────────
# Pusher event handlers
# ─────────────────────────────────────────────────────────────────────────────

def _handle_broadcast_event(event_name: str, data: str) -> None:
    """Handle any event on the broadcast channel.

    Broadcast channel events arrive as tournament_{id} — NOT as "sport_event".
    The change_type field inside the payload tells us what kind of update it is:
      - "sport_event"  → upsert Event in DB + publish SSE
      - "market"       → market created/updated (not handled in v1)
      - "market_line"  → market line odds update (not handled in v1)

    Pusher data shape:
      {"change_type": "sport_event", "op": "c|u|d", "payload": "<base64>", "timestamp": ...}
    """
    try:
        wrapper = json.loads(data) if isinstance(data, str) else data
        change_type = wrapper.get("change_type")
        op = wrapper.get("op")

        if change_type != "sport_event":
            log.debug(
                "ws_prophetx_non_event_update",
                pusher_event=event_name,
                change_type=change_type,
                op=op,
            )
            return

        payload_raw = wrapper.get("payload")
        if payload_raw is None:
            log.warning("ws_prophetx_sport_event_no_payload", pusher_event=event_name)
            return

        # Decode base64 → JSON string → dict
        if isinstance(payload_raw, str):
            try:
                decoded = base64.b64decode(payload_raw).decode()
                event_data = json.loads(decoded)
            except Exception:
                event_data = json.loads(payload_raw)
        else:
            event_data = payload_raw

        # WS payload structure: {"id": "...", "info": {event fields}, "tournament_id": "..."}
        # Flatten info to top level for _upsert_event compatibility.
        # For op=d, info.event_id is 0 (empty) — use the top-level id instead.
        info = event_data.get("info")
        if info is not None:
            flat = dict(info)
            flat["event_id"] = str(info.get("event_id") or event_data.get("id") or "")
            event_data = flat

        _upsert_event(event_data, op)

    except Exception:
        log.exception("ws_prophetx_broadcast_handler_error", pusher_event=event_name, raw=str(data)[:300])


# ─────────────────────────────────────────────────────────────────────────────
# Connection lifecycle
# ─────────────────────────────────────────────────────────────────────────────

BROADCAST_CHANNEL = "private-broadcast-service=3-device_type=5"


def _connect_and_run() -> None:
    """
    Open a Pusher connection, subscribe to the broadcast channel, and block
    until the token is about to expire (at which point we return so run()
    can re-authenticate and reconnect with fresh headers).
    """
    token = _get_access_token()
    config = _get_pusher_config(token)
    pusher_key = config["key"]
    pusher_cluster = config["cluster"]

    # ProphetX Pusher auth endpoint — pysher POSTs socket_id + channel_name here
    auth_endpoint = f"{settings.PROPHETX_BASE_URL}/mm/pusher"

    pusher_client = pysher.Pusher(
        key=pusher_key,
        cluster=pusher_cluster,
        auth_endpoint=auth_endpoint,
        auth_endpoint_headers={"Authorization": f"Bearer {token}"},
        reconnect_interval=5,
    )

    connection_ready = threading.Event()

    def _on_connect(data: str) -> None:
        log.info("ws_prophetx_connected")
        connection_ready.set()

    pusher_client.connection.bind("pusher:connection_established", _on_connect)
    pusher_client.connect()

    if not connection_ready.wait(timeout=20):
        log.error("ws_prophetx_connection_timeout")
        pusher_client.disconnect()
        raise RuntimeError("Pusher connection timed out after 20s")

    # Subscribe to broadcast channel.
    # Events arrive as tournament_{id} — pysher's named bind() won't match them.
    # Patch _handle_event on the channel instance to catch ALL incoming events.
    channel = pusher_client.subscribe(BROADCAST_CHANNEL)

    def _patched_handle_event(event_name: str, data: str) -> None:
        # Dispatch any explicitly registered pysher callbacks (e.g. subscription_succeeded)
        if event_name in channel.event_callbacks:
            for callback, args, kwargs in channel.event_callbacks[event_name]:
                callback(data, *args, **kwargs)
        # Route every non-pusher event through our universal handler
        if not event_name.startswith("pusher"):
            _handle_broadcast_event(event_name, data)

    channel._handle_event = _patched_handle_event
    log.info("ws_prophetx_subscribed", channel=BROADCAST_CHANNEL)

    # Block until token is about to expire.
    # pysher handles brief network drops internally (reconnect_interval=5).
    # When token expiry is near, we return so run() can reconnect with fresh auth headers.
    while time.time() < _token.expires_at:
        time.sleep(10)
        _write_heartbeat()  # belt-and-suspenders: also written on every health_check

    log.info("ws_prophetx_token_expiring_reconnect")
    pusher_client.disconnect()


def run() -> None:
    """Main loop: connect, block, reconnect. Retries with exponential backoff on failure."""
    retry_delay = 5
    max_delay = 60

    while True:
        try:
            _connect_and_run()
            retry_delay = 5  # clean exit (token refresh) — reset backoff
        except Exception:
            log.exception("ws_prophetx_connection_error", retry_in=retry_delay)
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Expose pysher's standard-library logger so raw WS messages appear in Docker logs.
    # pysher logs every incoming message at INFO via logging.getLogger('pysher.connection').
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [pysher] %(message)s",
        stream=sys.stdout,
    )

    log.info("ws_prophetx_starting")

    def _shutdown(sig, frame):  # type: ignore[type-arg]
        log.info("ws_prophetx_shutdown", signal=sig)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    run()
