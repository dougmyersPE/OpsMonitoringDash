# Phase 12: Consumer Foundation - Research

**Researched:** 2026-04-02
**Domain:** pika AMQP consumer, Docker service lifecycle, Alembic migration, Redis health keys
**Confidence:** HIGH — all findings grounded in direct codebase inspection + prior milestone research (STACK.md, PITFALLS.md, ARCHITECTURE.md) already verified against official pika docs, OpticOdds developer reference, and live docker-compose.yml

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Consumer is fully self-managing — starts queue on boot via OpticOdds REST call, stops queue on SIGTERM. No operator-facing REST endpoints. Operators use `docker compose restart opticodds-consumer` if manual intervention is needed. Matches the `ws-consumer` pattern exactly.
- **D-02:** Queue name cached in Redis after startup REST call. Consumer aborts with fatal log if queue start call fails.
- **D-03:** `OPTICODDS_BASE_URL` configurable env var with default pointing to `/v3/copilot/results/queue/start` path (per Oct 2025 changelog). Easy to override without code change if the path turns out to be `/fixtures/results/queue/start` instead.
- **D-04:** When an unmapped tennis status string arrives: (1) write the raw value verbatim to `opticodds_status` column, (2) log at WARNING level, (3) fire a Slack alert so operators investigate. No data loss, no silent failures.
- **D-05:** Known statuses use the `_OPTICODDS_CANONICAL` mapping dict. No default fallthrough — every status is either explicitly mapped or handled via D-04.
- **D-06:** Standalone Docker service (`opticodds-consumer`), `restart: unless-stopped` — pika `BlockingConnection` blocks indefinitely; Celery incompatible.
- **D-07:** `heartbeat=30`, `blocked_connection_timeout=300` in pika `ConnectionParameters`.
- **D-08:** `auto_ack=False` with manual ack.
- **D-09:** Exponential backoff with jitter on reconnect: 5s initial, 60s cap — mirrors `ws_prophetx.py` pattern.
- **D-10:** Log full raw message body at DEBUG level on first few messages to verify AMQP message schema empirically (MEDIUM confidence on exact JSON field names).

### Claude's Discretion

- Redis health key design for the consumer (key names, TTLs, update frequency) — follow `ws_prophetx.py` patterns with `ws:*` → `rmq:*` prefix adaptation
- DB migration 010 specifics (column type, index decisions)
- Consumer logging verbosity beyond the explicit decisions above
- `opticodds_status` model column mapping details

### Deferred Ideas (OUT OF SCOPE)

- **REST API queue endpoints** — Operator-facing `/api/v1/opticodds/queue/start|stop|status` endpoints. Self-managing consumer is sufficient for now.
- **Health badge** — DASH-01 mapped to Phase 14. Basic health key infrastructure ships in Phase 12 (Redis keys), but the dashboard badge UI ships in Phase 14.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AMQP-01 | OpticOdds RabbitMQ consumer runs as standalone Docker service with pika, auto-reconnect on failure, and heartbeat management | `ws-consumer` Docker service pattern confirmed in docker-compose.yml; pika `BlockingConnection` + exponential backoff pattern confirmed via `ws_prophetx.py` template and STACK.md/PITFALLS.md |
| AMQP-02 | Consumer starts OpticOdds results queue via REST API on startup and caches queue name in Redis | httpx already installed; queue lifecycle REST flow documented in STACK.md; Redis cache pattern (`opticodds:queue_name`) follows ws_prophetx.py precedent |
| TNNS-01 | Events table has `opticodds_status` column (nullable) populated by the consumer for tennis matches | migration 009 is the current head (drop_sports_api_status); migration 010 adds `opticodds_status VARCHAR(50) nullable`; Event model needs one mapped_column addition |
</phase_requirements>

---

## Summary

Phase 12 adds the OpticOdds AMQP consumer as a standalone Docker service — a near-verbatim clone of the existing `ws-consumer` / `ws_prophetx.py` pattern. The prior v1.3 research milestone has already answered every technical question with HIGH confidence. This research phase is primarily a synthesis pass that gives the planner precise "where to touch" guidance and verifies nothing has changed in the codebase since that research was conducted.

Three deliverables make up the phase. First, `backend/app/workers/opticodds_consumer.py` — a new standalone worker that calls the OpticOdds queue-start REST endpoint on startup, opens a pika `BlockingConnection`, consumes messages with manual ack, maps raw status strings through `_OPTICODDS_CANONICAL`, writes `opticodds_status` via `SyncSessionLocal`, publishes SSE via Redis, writes health keys, and reconnects with exponential backoff on failure. Second, the `opticodds-consumer` Docker Compose service — a copy of `ws-consumer` with a different command and a small memory limit. Third, Alembic migration 010 adding `opticodds_status VARCHAR(50) nullable` to the `events` table and the matching `Event` model column.

The one remaining risk is the REST endpoint path discrepancy flagged in STATE.md (D-03 above): the path `/v3/copilot/results/queue/start` (Oct 2025 changelog) vs `/fixtures/results/queue/start` (earlier research). The env var `OPTICODDS_BASE_URL` absorbs this risk — no code change needed if the path is wrong, only a `.env` update.

**Primary recommendation:** Implement `opticodds_consumer.py` by direct analogy to `ws_prophetx.py`, adapting only the connection layer (pika instead of pysher), the queue lifecycle (REST start/stop calls), and the message handler (status mapping + `opticodds_status` write).

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pika` | `>=1.3.2,<2.0` | AMQP 0-9-1 client for OpticOdds RabbitMQ | Only Python AMQP library used in OpticOdds developer examples; pure-Python, no native deps; `BlockingConnection` is the right adapter for a dedicated-process consumer |
| `httpx` | `>=0.27` (already installed) | Queue lifecycle REST calls (start/stop) | Already in pyproject.toml; synchronous `httpx.Client` works outside FastAPI event loop; no new dep needed |
| `redis-py` | `5.x` (already installed) | Health keys, queue name cache | Existing pattern throughout codebase |
| `structlog` | `>=24.0` (already installed) | Structured logging | Project-wide standard |
| `alembic` | existing | Migration 010 | Sequential numbering; 009 is current head |

### No New Dependencies

Everything Phase 12 needs is already installed. The only pyproject.toml change is adding `pika>=1.3.2,<2.0`.

**Installation:**
```bash
# Inside backend container / virtualenv
pip install pika>=1.3.2,<2.0
# pyproject.toml addition:
# "pika>=1.3.2,<2.0",
```

**Version note:** pika 1.3.2 is the latest stable release (May 2023). A 1.4.0 beta exists but is not stable — do not use. Verified via PyPI.

---

## Architecture Patterns

### Recommended Project Structure (new files only)

```
backend/
├── app/
│   └── workers/
│       └── opticodds_consumer.py   # NEW — mirrors ws_prophetx.py structure
├── alembic/
│   └── versions/
│       └── 010_add_opticodds_status.py   # NEW
```

No new directories. No new client file for Phase 12 — the REST call is simple enough to inline in the consumer using `httpx.Client` directly (OpticOdds queue lifecycle is 2 endpoints, no shared client needed yet; Phase 13 may warrant a dedicated `opticodds_api.py` client).

### Pattern 1: Consumer Module Structure (mirror ws_prophetx.py)

**What:** Single-file standalone consumer with five sections: config/state, Redis helpers, queue lifecycle (start/stop REST), AMQP connection loop, entry point with SIGTERM handler.

**When to use:** Always — matches the established project pattern.

```python
# Source: backend/app/workers/ws_prophetx.py (direct analogue)

# --- Module-level sections (same order as ws_prophetx.py) ---
# 1. Queue lifecycle helpers
def _start_queue() -> str:
    """Call OpticOdds /queue/start; return queue_name. Abort on failure."""
    resp = httpx.post(
        f"{settings.OPTICODDS_BASE_URL}",  # points to .../queue/start
        headers={"X-Api-Key": settings.OPTICODDS_API_KEY},
        timeout=15,
    )
    resp.raise_for_status()
    queue_name = resp.json()["queue_name"]  # field name MEDIUM confidence — D-10 applies
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.set("opticodds:queue_name", queue_name)
    log.info("opticodds_queue_started", queue_name=queue_name)
    return queue_name

def _stop_queue() -> None:
    """Call OpticOdds /queue/stop. Best-effort — log errors but don't raise."""
    stop_url = settings.OPTICODDS_BASE_URL.replace("/start", "/stop")
    try:
        httpx.post(stop_url, headers={"X-Api-Key": settings.OPTICODDS_API_KEY}, timeout=10)
        log.info("opticodds_queue_stopped")
    except Exception:
        log.exception("opticodds_queue_stop_failed")

# 2. Redis helpers
def _write_heartbeat() -> None:
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.set("worker:heartbeat:opticodds_consumer", "1", ex=90)

def _write_connection_state(state: str) -> None:
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.set("opticodds:connection_state", state, ex=120)
    r.set("opticodds:connection_state_since", datetime.now(timezone.utc).isoformat(), ex=120)

def _write_last_message_at() -> None:
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.set("opticodds:last_message_at", datetime.now(timezone.utc).isoformat(), ex=90)

# 3. Message callback
def _on_message(ch, method, properties, body) -> None:
    try:
        if _message_count[0] < 5:  # D-10: log raw body on first few messages
            log.debug("opticodds_raw_message", body=body.decode()[:1000])
            _message_count[0] += 1
        data = json.loads(body)
        raw_status = data.get("status")  # field name MEDIUM confidence
        mapped_status = _OPTICODDS_CANONICAL.get(raw_status) if raw_status else None
        if raw_status and mapped_status is None:  # D-04: unknown status handling
            log.warning("opticodds_unknown_status", raw_status=raw_status)
            # write raw value verbatim + fire Slack alert
        _write_opticodds_status(data, mapped_status or raw_status)
        _write_last_message_at()
        ch.basic_ack(delivery_tag=method.delivery_tag)  # D-08: manual ack
    except Exception:
        log.exception("opticodds_message_error")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

# 4. Main loop
def run() -> None:
    queue_name = _start_queue()  # fatal on failure (D-02)
    retry_delay = 5
    max_delay = 60
    while True:
        try:
            params = pika.ConnectionParameters(
                host="v3-rmq.opticodds.com",
                port=5672,
                virtual_host="api",
                credentials=pika.PlainCredentials(
                    settings.OPTICODDS_RMQ_USERNAME,
                    settings.OPTICODDS_RMQ_PASSWORD,
                ),
                heartbeat=30,              # D-07
                blocked_connection_timeout=300,  # D-07
            )
            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            ch.basic_qos(prefetch_count=10)
            ch.basic_consume(queue=queue_name, on_message_callback=_on_message, auto_ack=False)  # D-08
            _write_connection_state("connected")
            retry_delay = 5  # reset on success
            ch.start_consuming()
        except (pika.exceptions.AMQPConnectionError, pika.exceptions.AMQPChannelError) as exc:
            _write_connection_state("reconnecting")
            log.warning("opticodds_rmq_disconnected", error=str(exc), retry_in=retry_delay)
            time.sleep(retry_delay + random.uniform(0, 1))  # D-09: jitter
            retry_delay = min(retry_delay * 2, max_delay)
        except Exception:
            log.exception("opticodds_rmq_unexpected_error", retry_in=retry_delay)
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)
```

### Pattern 2: Status Mapping Dict

**What:** Explicit `_OPTICODDS_CANONICAL` dict with no fallthrough default. Unknown values handled per D-04 (write raw + warn + alert).

**Note on D-04 vs D-05 interaction:** D-05 says "no default fallthrough" and D-04 says "write raw value verbatim." These are compatible: known statuses go through the canonical map; unknown statuses bypass the map and are written as-is. The `opticodds_status` column stores whatever value arrives; Phase 13 feeds the mapped value to `compute_status_match`.

```python
# Source: .planning/research/PITFALLS.md — status mapping section
_OPTICODDS_CANONICAL: dict[str, str] = {
    "not_started":   "not_started",
    "scheduled":     "not_started",
    "delayed":       "not_started",
    "start_delayed": "not_started",
    "postponed":     "not_started",
    "in_progress":   "live",
    "live":          "live",
    "suspended":     "live",      # match paused, will resume
    "interrupted":   "live",      # brief stoppage
    "finished":      "ended",
    "complete":      "ended",
    "retired":       "ended",     # player retired mid-match
    "walkover":      "ended",     # opponent withdrew pre-match
    "cancelled":     "ended",
    "abandoned":     "ended",
}
```

### Pattern 3: Docker Compose Service

**What:** Direct copy of the `ws-consumer` service block with `command` changed.

```yaml
# Source: docker-compose.yml — ws-consumer block
  opticodds-consumer:
    build: ./backend
    command: python -m app.workers.opticodds_consumer
    env_file: .env
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: 128m
```

### Pattern 4: Alembic Migration 010

**What:** Additive nullable column — no data transformation, no backfill needed.

```python
# Source: backend/alembic/versions/009_drop_sports_api_status.py (pattern reference)
revision = "010"
down_revision = "009"

def upgrade() -> None:
    op.add_column("events", sa.Column("opticodds_status", sa.String(50), nullable=True))

def downgrade() -> None:
    op.drop_column("events", "opticodds_status")
```

**No index required** — `opticodds_status` will be read as part of full event row fetches; no queries filter by it in isolation. Phase 13 (fuzzy match + mismatch) will read the column but always joins on `prophetx_event_id`. Skip the index for now.

### Pattern 5: Event Model Column Addition

**What:** One `mapped_column` line in `backend/app/models/event.py`, following the existing nullable status column pattern.

```python
# Source: backend/app/models/event.py — after oddsblaze_status line
opticodds_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
```

### Pattern 6: Health Endpoint Extension

**What:** Add `opticodds_consumer` to the existing MGET in `health.py`, following the `ws_prophetx` shape established in Phase 10.

```python
# Source: backend/app/api/v1/health.py — worker_health()
# Add to keys list:
"opticodds:connection_state",
"opticodds:connection_state_since",
# Add to return dict:
"opticodds_consumer": {
    "connected": rmq_state == "connected",
    "state": rmq_state,
    "since": rmq_since,
},
```

### Pattern 7: Settings Extension

**What:** Four new env vars in `backend/app/core/config.py`. All optional with `None` default so existing deployments that lack OpticOdds credentials don't break on startup.

```python
# Source: backend/app/core/config.py — External APIs section
OPTICODDS_API_KEY: str | None = None
OPTICODDS_RMQ_USERNAME: str | None = None   # = API key value per OpticOdds docs
OPTICODDS_RMQ_PASSWORD: str | None = None
OPTICODDS_BASE_URL: str = "https://api.opticodds.com/v3/copilot/results/queue/start"  # D-03
```

**Note on OPTICODDS_BASE_URL:** The env var stores the FULL start URL. The stop URL is derived at runtime by replacing `/start` with `/stop`. This keeps the config simple — one env var covers the path uncertainty (D-03).

### Anti-Patterns to Avoid

- **`auto_ack=True`:** OpticOdds Getting Started guide shows this; do not copy it. Use `auto_ack=False` + manual `basic_ack` (D-08 / Pitfall 5).
- **`heartbeat=0`:** Disables heartbeats entirely; broker cannot detect dead TCP connections. Use `heartbeat=30` (D-07).
- **pika inside a Celery task:** `BlockingConnection.start_consuming()` blocks indefinitely; incompatible with Celery worker lifecycle (D-06 / Pitfall 6).
- **Hard-coded queue name:** Queue name is dynamic, assigned per-API-key by the `/start` response. Never hard-code it.
- **Missing `virtual_host="api"`:** Default vhost is `/`; OpticOdds uses `api` — connection will fail silently or connect to wrong vhost.
- **Calling `_start_queue()` again inside the reconnect loop:** Queue start is called once at process startup, not on every AMQP reconnect. Reconnect loop re-uses the cached `queue_name`; calling start again would provision a new queue and lose messages buffered in the old one.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| AMQP consumer connection | Custom TCP/AMQP framing | `pika.BlockingConnection` | Protocol compliance, heartbeat handling, framing — hundreds of edge cases |
| Exponential backoff | Custom sleep loop | Copy `ws_prophetx.py` run() loop exactly | Already battle-tested in production with same backoff parameters |
| Redis health writes | Custom key scheme | Mirror `ws:*` key pattern → `opticodds:*` | Consistent with existing `/health/workers` reader |
| Fuzzy name matching | Custom Levenshtein | `difflib.SequenceMatcher` (already used in `poll_oddsblaze.py`) | Already imported and tested; Phase 12 does NOT implement fuzzy match (Phase 13 scope) |
| Queue name persistence | In-memory module variable | Redis key `opticodds:queue_name` | Survives container restart; `ws_prophetx.py` pattern |
| Alembic migration | Manual `ALTER TABLE` | `op.add_column()` in 010 migration | Keeps migration history consistent; `alembic upgrade head` handles it |

**Key insight:** Every problem in Phase 12 already has a solved, in-production answer in this codebase. The value of this phase is correct wiring, not invention.

---

## Common Pitfalls

### Pitfall 1: Heartbeat Starvation (pika BlockingConnection)
**What goes wrong:** Message handler blocks the I/O loop; broker closes connection with "missed heartbeat" after `heartbeat` seconds of no response.
**Why it happens:** pika's `BlockingConnection` is single-threaded; any work in the callback competes with the I/O pump.
**How to avoid:** `heartbeat=30` (D-07) gives 30 seconds of tolerance. Tennis message processing (DB upsert + Redis write) is well under 1 second under normal conditions. If processing ever approaches 30s under lock contention, delegate to a thread (not needed for Phase 12).
**Warning signs:** `AMQPHeartbeatTimeout` in logs; consumer reconnects every ~30s like clockwork.

### Pitfall 2: Reconnect Storm
**What goes wrong:** Tight reconnect loop hammers OpticOdds broker during outages; may trigger IP-level rate limiting.
**Why it happens:** No backoff between connection attempts.
**How to avoid:** D-09 — 5s initial, 60s cap, random jitter. Pattern is already in `ws_prophetx.py` `run()` loop.
**Warning signs:** CPU spike during known broker outage; hundreds of `AMQPConnectionError` per minute.

### Pitfall 3: Queue Not Started — Consumer Receives Nothing
**What goes wrong:** Consumer connects successfully to broker, `basic_consume` succeeds, `start_consuming` waits indefinitely — no messages arrive, no error raised.
**Why it happens:** OpticOdds queue is provisioned by REST API, not by AMQP connection. The broker accepts connections even when no producer is feeding the queue.
**How to avoid:** `_start_queue()` called unconditionally at process startup before pika connection opens (D-01, D-02).
**Warning signs:** `worker:heartbeat:opticodds_consumer` is set (consumer alive) but `opticodds:last_message_at` is NULL after a period with scheduled tennis matches.

### Pitfall 4: Stop URL Derivation Breaks on Path Change
**What goes wrong:** If `OPTICODDS_BASE_URL` contains a path with something other than `/start` at the end, `.replace("/start", "/stop")` may produce a wrong URL.
**Why it happens:** Brittle string replacement.
**How to avoid:** Keep `OPTICODDS_BASE_URL` as the full start URL. The stop URL replacement `replace("/start", "/stop")` is reliable given the known path patterns. Alternatively, add a separate `OPTICODDS_STOP_URL` env var or derive both from a base + distinct path config. For Phase 12, the single-env-var pattern is sufficient given the constraint set.

### Pitfall 5: `compute_status_match()` Receives Raw OpticOdds Status
**What goes wrong:** Passing `"in_progress"` directly to `compute_status_match()` produces wrong results; the function expects `"live"` (ProphetX canonical values).
**Why it happens:** The raw OpticOdds value is stored in `opticodds_status`; the canonical mapping happens before calling `compute_status_match`. Forgetting the mapping step silently produces false mismatches.
**How to avoid:** Phase 12 does NOT call `compute_status_match()` — Phase 13 adds that integration (TNNS-02 / MISM-01). In Phase 12, the consumer writes `opticodds_status` and nothing else. This eliminates the risk entirely for this phase.
**Warning signs (Phase 13):** `status_match = False` on tennis events that appear correctly matched.

### Pitfall 6: Missing virtual_host="api" in ConnectionParameters
**What goes wrong:** pika connects to the `/` vhost (default) instead of `api`; connection succeeds at TCP level but the queue does not exist on that vhost.
**Why it happens:** `ConnectionParameters` `virtual_host` defaults to `/`.
**How to avoid:** Always set `virtual_host="api"` explicitly. Verified from OpticOdds developer docs.

---

## Code Examples

### Full run() Loop with Backoff (verified pattern)

```python
# Source: backend/app/workers/ws_prophetx.py run() — adapted for pika

import random
import time
import pika

def run() -> None:
    queue_name = _start_queue()  # fatal abort on failure (D-02)
    retry_delay = 5
    max_delay = 60

    while True:
        try:
            params = pika.ConnectionParameters(
                host="v3-rmq.opticodds.com",
                port=5672,
                virtual_host="api",
                credentials=pika.PlainCredentials(
                    settings.OPTICODDS_RMQ_USERNAME,
                    settings.OPTICODDS_RMQ_PASSWORD,
                ),
                heartbeat=30,
                blocked_connection_timeout=300,
            )
            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            ch.basic_qos(prefetch_count=10)
            ch.basic_consume(
                queue=queue_name,
                on_message_callback=_on_message,
                auto_ack=False,
            )
            _write_connection_state("connected")
            log.info("opticodds_consumer_connected", queue=queue_name)
            retry_delay = 5  # reset backoff on clean connect
            ch.start_consuming()
        except (pika.exceptions.AMQPConnectionError, pika.exceptions.AMQPChannelError) as exc:
            _write_connection_state("reconnecting")
            log.warning("opticodds_rmq_disconnected", error=str(exc), retry_in=retry_delay)
            time.sleep(retry_delay + random.uniform(0, 1))
            retry_delay = min(retry_delay * 2, max_delay)
        except Exception:
            _write_connection_state("reconnecting")
            log.exception("opticodds_rmq_unexpected_error", retry_in=retry_delay)
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)
```

### SIGTERM Handler (entry point)

```python
# Source: backend/app/workers/ws_prophetx.py __main__ block
if __name__ == "__main__":
    log.info("opticodds_consumer_starting")

    def _shutdown(sig, frame):
        log.info("opticodds_consumer_shutdown", signal=sig)
        _stop_queue()   # best-effort; D-01
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    run()
```

### Message Callback with Manual Ack

```python
# Source: .planning/research/PITFALLS.md Pitfall 5 — manual ack pattern

_message_count = [0]  # mutable container for closure increment

def _on_message(ch, method, properties, body) -> None:
    try:
        if _message_count[0] < 5:  # D-10: debug log first 5 messages
            log.debug("opticodds_raw_message", body=body.decode("utf-8", errors="replace")[:1000])
        _message_count[0] += 1

        data = json.loads(body)
        raw_status = data.get("status")  # field name MEDIUM confidence
        mapped_status = _OPTICODDS_CANONICAL.get(raw_status.lower()) if raw_status else None

        if raw_status and mapped_status is None:
            # D-04: unknown status — write raw, warn, Slack alert
            log.warning("opticodds_unknown_status", raw_status=raw_status)
            _send_slack_alert(f"OpticOdds unknown tennis status: `{raw_status}`")
            mapped_status = raw_status  # store verbatim per D-04

        _write_opticodds_status(data, mapped_status)
        _write_heartbeat()
        _write_last_message_at()
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except json.JSONDecodeError:
        log.error("opticodds_message_json_error", body_snippet=body[:200])
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)  # discard malformed
    except Exception:
        log.exception("opticodds_message_processing_failed")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
```

### Redis Key Design (Claude's Discretion — following ws:* precedent)

```
worker:heartbeat:opticodds_consumer    TTL=90s  value="1"  (written every message + periodic)
opticodds:connection_state             TTL=120s value="connected"|"reconnecting"|"disconnected"
opticodds:connection_state_since       TTL=120s value=ISO timestamp
opticodds:last_message_at              TTL=90s  value=ISO timestamp
opticodds:queue_name                   no TTL   value=<queue_name_from_start_api>
```

Self-expiring TTLs mean absence = disconnected, consistent with the `ws:*` pattern in `ws_prophetx.py`.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Running persistent consumers as Celery tasks | Dedicated Docker service (`ws-consumer` pattern) | Phase 8 (ws_prophetx) | Isolates consumer failure from Celery; no slot starvation |
| Manual queue provisioning (operator pre-flight step) | Self-managing consumer calls REST start on boot | D-01 (CONTEXT.md) | No operator intervention needed; restart recovers automatically |

**No deprecated approaches in scope for this phase.**

---

## Open Questions

1. **OpticOdds REST endpoint path (D-03)**
   - What we know: Two paths documented — `/v3/copilot/results/queue/start` (Oct 2025 changelog) and `/fixtures/results/queue/start` (earlier research). D-03 defaults to the v3/copilot path.
   - What's unclear: Which is live as of April 2026.
   - Recommendation: Implement with `OPTICODDS_BASE_URL` env var defaulting to the v3/copilot path. Log the URL used at startup. First deployment attempt will confirm or deny via HTTP status code. If 404, update `.env` to the `/fixtures/` path — zero code change needed.

2. **Exact JSON field names in OpticOdds AMQP message body (D-10)**
   - What we know: Messages are JSON; likely contains `status`, competitor names, fixture ID. Exact field paths are MEDIUM confidence.
   - What's unclear: Whether status is at top-level `status`, nested `fixture.status`, or another path.
   - Recommendation: Implement D-10 (log full raw body at DEBUG for first 5 messages). Plan the message handler to read several candidate paths with fallback. Phase 13 (fuzzy match) will need confirmed field names; Phase 12 only needs `status` for the DB write.

3. **"Queue already active" handling on consumer restart**
   - What we know: If container is killed (SIGKILL) without calling stop, the queue may already be active on OpticOdds side.
   - What's unclear: Whether `/start` returns an error, a new queue name, or idempotently returns the existing queue name.
   - Recommendation: Treat `/start` as idempotent — call it unconditionally on startup regardless of whether the queue was previously active. If the response contains a queue name, use it. If it returns HTTP 4xx suggesting the queue is active, call `/stop` then `/start` as a recovery sequence. Cache the returned queue name in Redis as a fallback if the restart call fails.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | Container build/deploy | Yes | 29.2.1 | — |
| Python | Worker code | Yes | 3.11.7 (local) / 3.12 (Docker) | — |
| pytest | Test execution | Yes | 8.4.2 | — |
| pika (PyPI) | Worker import | Not installed locally | 1.3.2 latest stable | Runs in Docker; `pip install pika>=1.3.2,<2.0` inside image |
| OpticOdds RabbitMQ broker | Integration test | Not verifiable locally | — | Unit tests mock pika; broker only needed for E2E smoke test on VPS |
| OpticOdds REST API | Queue start/stop | Not verifiable locally | — | Mock in unit tests; live test requires credentials |

**Missing dependencies with no fallback:** None for unit/integration test execution. The OpticOdds live broker and credentials are required only for the E2E smoke test (Success Criterion 2); this runs on the VPS after deploy, not in the local test suite.

**Missing dependencies with fallback:** pika — not installed in local virtualenv but present in Docker image after pyproject.toml update. All tests that exercise `opticodds_consumer.py` must mock `pika.BlockingConnection`.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2 + pytest-asyncio |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`) |
| Quick run command | `cd backend && python -m pytest tests/test_opticodds_consumer.py -x -q` |
| Full suite command | `cd backend && python -m pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AMQP-01 | Consumer reconnects with exponential backoff after simulated connection drop | unit | `pytest tests/test_opticodds_consumer.py::test_reconnect_backoff -x` | ❌ Wave 0 |
| AMQP-01 | Docker service defined with `restart: unless-stopped` | smoke (manual) | `docker compose ps` after `docker compose kill opticodds-consumer` | N/A |
| AMQP-02 | Startup calls queue start REST endpoint; queue name cached in Redis | unit | `pytest tests/test_opticodds_consumer.py::test_queue_start_called_on_startup -x` | ❌ Wave 0 |
| AMQP-02 | Consumer aborts with fatal log if queue start fails | unit | `pytest tests/test_opticodds_consumer.py::test_fatal_abort_on_queue_start_failure -x` | ❌ Wave 0 |
| TNNS-01 | Migration 010 applies cleanly; `opticodds_status` column exists | unit | `pytest tests/test_migration_010.py -x` (or alembic check in CI) | ❌ Wave 0 |
| TNNS-01 | Existing rows unaffected (column is nullable; no backfill) | unit | `pytest tests/test_migration_010.py::test_existing_rows_unaffected -x` | ❌ Wave 0 |
| Status mapping | Known OpticOdds statuses map to canonical values | unit | `pytest tests/test_opticodds_consumer.py::test_status_mapping -x` | ❌ Wave 0 |
| Status mapping | Unknown status written verbatim; WARNING logged | unit | `pytest tests/test_opticodds_consumer.py::test_unknown_status_written_raw -x` | ❌ Wave 0 |
| Health key | `opticodds:connection_state` written on connect | unit | `pytest tests/test_opticodds_consumer.py::test_connection_state_key_written -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd backend && python -m pytest tests/test_opticodds_consumer.py -x -q`
- **Per wave merge:** `cd backend && python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_opticodds_consumer.py` — covers AMQP-01, AMQP-02, status mapping, health keys (all tests above)
- [ ] `tests/test_migration_010.py` — covers TNNS-01 (migration applies; existing rows unaffected)

*(All existing test infrastructure is in place — conftest.py, pytest config, AsyncClient fixture. No framework install needed. Only the two new test files are missing.)*

---

## Project Constraints (from CLAUDE.md)

No `CLAUDE.md` found in `/Users/doug/OpsMonitoringDash/`. No project-level overrides to apply.

---

## Sources

### Primary (HIGH confidence)
- `backend/app/workers/ws_prophetx.py` — Full standalone consumer pattern: reconnect loop, SIGTERM handler, Redis health keys, `_write_heartbeat()`, `SyncSessionLocal` usage. Direct implementation template.
- `docker-compose.yml` — Confirmed `ws-consumer` service definition (verbatim model for `opticodds-consumer`); memory limit 128m; `restart: unless-stopped`; `depends_on` with healthcheck conditions.
- `backend/app/models/event.py` — Current Event model; `oddsblaze_status` line is the insertion point for `opticodds_status`.
- `backend/app/core/config.py` — Settings pattern; confirmed `httpx` already installed; env var binding style.
- `backend/app/api/v1/health.py` — Current `worker_health()` MGET keys; confirmed `ws_prophetx` nested object shape to replicate for `opticodds_consumer`.
- `backend/alembic/versions/009_drop_sports_api_status.py` — Confirmed 009 is current migration head; 010 is next.
- `backend/app/monitoring/mismatch_detector.py` — `compute_status_match()` 5-parameter signature; `_ODDSBLAZE_CANONICAL` pattern for status dict; confirmed Phase 12 does NOT extend `compute_status_match` (Phase 13 scope).
- `.planning/research/STACK.md` — pika `ConnectionParameters`, `heartbeat=600` original recommendation (superseded by D-07 `heartbeat=30`), `virtual_host="api"`, OpticOdds broker host/port/vhost. HIGH confidence from prior official-docs verification.
- `.planning/research/PITFALLS.md` — All 6 critical pitfalls with prevention strategies. HIGH confidence.
- `.planning/research/ARCHITECTURE.md` — Redis key design (`opticodds:*`), v1.3 target architecture diagram, file placement.

### Secondary (MEDIUM confidence)
- `.planning/research/STACK.md` OpticOdds REST endpoint paths — `/fixtures/results/queue/start` confirmed from developer.opticodds.com/reference as of research date (2026-04-01); D-03 notes `/v3/copilot/results/queue/start` may be the current live path per Oct 2025 changelog.
- `.planning/research/PITFALLS.md` OpticOdds JSON message field names — `"status"` as the status field is MEDIUM confidence; empirical verification deferred to D-10 debug logging on first deployment.

### Tertiary (LOW confidence)
- OpticOdds `queue_name` response field name — assumed from STACK.md (`resp.json()["queue_name"]`); not confirmed from official public docs. Log full response at INFO on startup to confirm.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pika version, httpx, redis-py all confirmed from existing codebase and PyPI
- Architecture: HIGH — all patterns copied directly from verified in-production ws_prophetx.py and docker-compose.yml
- Pitfalls: HIGH — six pitfalls verified against official pika docs and direct codebase inspection in prior research
- OpticOdds endpoint paths: MEDIUM — two candidate paths documented; env var design absorbs the uncertainty
- OpticOdds message schema: MEDIUM — field names inferred; D-10 debug logging provides empirical validation on first deploy

**Research date:** 2026-04-02
**Valid until:** 2026-05-02 (30 days — pika is stable; OpticOdds API may change; verify path before coding)
