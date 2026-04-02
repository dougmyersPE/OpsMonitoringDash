# Technology Stack

**Project:** ProphetX Market Monitor — v1.3 OpticOdds Tennis Integration
**Researched:** 2026-04-01
**Confidence:** HIGH (pika and httpx verified via PyPI/official docs; OpticOdds REST endpoints verified via developer.opticodds.com/reference; threading pattern verified via pika official docs)
**Scope:** NEW additions only. The existing validated stack (FastAPI, Celery/Redis/RedBeat, PostgreSQL, React 19, TanStack Query 5, Tailwind 4, shadcn/ui 3, pysher, structlog, httpx, redis-py) is unchanged.

---

## Context: What This Covers

v1.3 adds OpticOdds as a real-time data source for tennis match status monitoring via RabbitMQ. The integration has two distinct concerns:

1. **RabbitMQ consumer** — long-running AMQP consumer connecting to OpticOdds's managed RabbitMQ broker (`v3-rmq.opticodds.com`) to receive tennis results messages
2. **Queue lifecycle REST calls** — HTTP calls to OpticOdds REST API (`POST /fixtures/results/queue/start`, `POST /fixtures/results/queue/stop`, `GET /fixtures/results/queue/status`) to obtain and manage the queue name before connecting

This document answers: what one new Python library is needed, and how does the consumer fit into the existing Docker/Celery architecture?

---

## New Dependencies Required

### One New Python Package

| Package | Version | Purpose | Why |
|---------|---------|---------|-----|
| `pika` | `>=1.3.2` | AMQP 0-9-1 client for OpticOdds RabbitMQ broker | The only Python AMQP library directly documented and used in OpticOdds developer examples. Pure-Python, no native dependencies, supports `BlockingConnection` for a dedicated-thread consumer pattern. Version 1.3.2 is the current stable release (May 2023). A 1.4.0 beta adds adaptive heartbeats/retry logic but is not yet stable — pin `>=1.3.2,<2.0`. |

**`httpx` is already installed** (`>=0.27` in pyproject.toml; dev group pins `>=0.28.1`). Use it for the OpticOdds REST lifecycle calls. No new HTTP client needed.

---

## Recommended Stack Additions

### Core Addition: `pika` for AMQP

**Version:** `1.3.2` (stable, May 2023). Pin `>=1.3.2,<2.0`.

**Why pika over alternatives:**
- OpticOdds developer docs explicitly use pika with `BlockingConnection` and provide connection parameters for it
- `aio-pika` (async wrapper) is not needed — the consumer runs in a dedicated thread/process, not in the async FastAPI event loop
- `kombu` (Celery's AMQP library) is already installed but is a higher-level abstraction oriented toward Celery task queues; using it to consume an external non-Celery queue would require awkward `ConsumerStep` bootstep wiring with no benefit over plain pika

**Connection parameters (confirmed from OpticOdds docs):**
```python
pika.ConnectionParameters(
    host="v3-rmq.opticodds.com",
    port=5672,
    virtual_host="api",
    credentials=pika.PlainCredentials(OPTICODDS_RMQ_USERNAME, OPTICODDS_RMQ_PASSWORD),
    heartbeat=600,            # prevent broker-side timeout on idle consumers
    blocked_connection_timeout=300,
)
```

### Existing Package: `httpx` for REST Lifecycle Calls

Already in pyproject.toml (`>=0.27`). Use the synchronous `httpx.Client` (not async) inside the consumer process since it runs outside FastAPI's event loop.

**OpticOdds REST endpoints for queue lifecycle:**

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/fixtures/results/queue/start` | Start queue; response body contains the queue name to pass to AMQP |
| `POST` | `/fixtures/results/queue/stop` | Stop and release the queue |
| `GET` | `/fixtures/results/queue/status` | Poll queue health / confirm it is active |

**Authentication:** `X-Api-Key: <api_key>` request header. Confirmed from OpticOdds API reference.

**Rate limits** (from OpticOdds FAQ): queue lifecycle endpoints fall under "all other endpoints" — 2500 requests per 15-second window. No throttling concern for start/stop/status calls.

---

## Consumer Architecture: Dedicated Docker Service (Recommended)

### Pattern: Mirror `ws-consumer`

The existing `ws-consumer` service in `docker-compose.yml` runs `python -m app.workers.ws_prophetx` as a standalone process — not a Celery task, not a Celery worker. This is exactly the right pattern for the OpticOdds consumer.

**Why a dedicated service over a Celery task:**
- `pika.BlockingConnection.start_consuming()` blocks indefinitely on the I/O loop. Celery tasks are expected to return. Wrapping a blocking AMQP consumer in a Celery task requires `acks_late`, a `time_limit`, or forked process tricks — all fragile.
- The `ws-consumer` pattern is already validated in production. Same process lifecycle, same health-via-Redis pattern, same Docker restart policy.
- A dedicated process isolates AMQP failure from Celery worker failure. If the RabbitMQ consumer crashes, Celery workers keep polling.

**Recommended `docker-compose.yml` addition:**
```yaml
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

No new Docker networking needed. The container reaches `v3-rmq.opticodds.com:5672` over the existing outbound internet path — same as how `ws-consumer` reaches `api-ss-sandbox.betprophet.co`. No local RabbitMQ broker required.

### Threading Model Inside the Consumer Process

pika's `BlockingConnection` is **not thread-safe** — all connection operations must run on one thread. The recommended pattern (from pika official docs):

- **Main thread:** owns the `BlockingConnection`, runs `channel.start_consuming()` (blocks in the I/O loop)
- **Message processing:** The `on_message` callback dispatches message body to a `threading.Thread` or directly to Redis/DB operations if they are fast (< heartbeat interval)

For tennis match status updates, processing is fast (a Redis write + a DB upsert). Delegating to a thread pool is optional but should be done if processing ever approaches the 600-second heartbeat interval.

**Reconnection pattern** (use exception loop, not recursion):
```python
while True:
    try:
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.basic_qos(prefetch_count=100)
        channel.basic_consume(queue=queue_name, on_message_callback=on_message, auto_ack=True)
        channel.start_consuming()
    except pika.exceptions.AMQPConnectionError as e:
        log.warning("opticodds_rmq_disconnected", error=str(e))
        time.sleep(backoff_seconds)  # exponential backoff with cap
    except KeyboardInterrupt:
        break
```

This mirrors the recovery pattern in pika's official multi-host example and is consistent with how `ws_prophetx.py` handles reconnects.

### Queue Lifecycle: Start Before Connect, Stop on Shutdown

The queue name is dynamic — obtained from `POST /fixtures/results/queue/start` before the AMQP connection is opened. The process lifecycle is:

1. On startup: `POST /fixtures/results/queue/start` → extract `queue_name` from response
2. Open AMQP connection to `v3-rmq.opticodds.com:5672` using `queue_name`
3. On shutdown (SIGTERM): `POST /fixtures/results/queue/stop`, then close AMQP connection

This is a synchronous sequence — no async needed.

---

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `aio-pika` | Async AMQP wrapper. Not needed — consumer runs in a dedicated thread/process outside FastAPI's event loop. Adds complexity with zero benefit here. | `pika` `BlockingConnection` in a dedicated thread |
| Local RabbitMQ broker in Docker Compose | OpticOdds hosts the broker at `v3-rmq.opticodds.com`. Adding a local broker would be for a different use case (e.g., Celery broker migration). Not needed. | Outbound TCP to `v3-rmq.opticodds.com:5672` |
| `kombu` for this consumer | Already installed as a Celery dependency, but `ConsumerStep` bootstep pattern is designed for consuming Celery-compatible messages off the Celery broker. Wiring it to an external OpticOdds queue adds indirection. | Plain `pika` |
| `celery-message-consumer` (PyPI) | Third-party wrapper designed to consume arbitrary AMQP messages inside Celery workers. Brings in extra deps; the dedicated-service pattern is simpler and already proven in this codebase. | Dedicated `opticodds-consumer` service |
| Celery task wrapping `start_consuming()` | Blocking tasks in Celery require `time_limit` and break normal worker semantics. High risk of silent timeout failures. | Dedicated process matching `ws-consumer` pattern |
| `requests` for REST lifecycle calls | Already using `httpx` project-wide. No reason to introduce a second HTTP client. | `httpx.Client` (synchronous, already installed) |

---

## pyproject.toml Change

```toml
dependencies = [
    # ... existing entries ...
    "pika>=1.3.2,<2.0",
]
```

Single line addition. All other capabilities (HTTP calls, Redis state, DB writes, SSE push, health endpoint) use already-installed packages.

---

## Version Compatibility

| Package | Version | Compatibility Notes |
|---------|---------|---------------------|
| `pika` | `>=1.3.2,<2.0` | Python 3.12 supported (pika supports >=3.7). No known conflicts with existing deps. |
| `httpx` | `>=0.27` (already installed) | Synchronous `httpx.Client` usage requires no async context. Full compatibility with Python 3.12. |
| `redis-py` | `5.x` (already installed) | Consumer will write health state via the same Redis hash pattern as `ws-consumer`. No version concerns. |

---

## Integration Points

| New Code | Connects To | How |
|----------|-------------|-----|
| `app/workers/opticodds_consumer.py` | `httpx.Client` | POST /fixtures/results/queue/start at process startup to get queue name |
| `app/workers/opticodds_consumer.py` | `v3-rmq.opticodds.com:5672` | pika `BlockingConnection` consuming tennis results messages |
| `app/workers/opticodds_consumer.py` | Redis `worker:ws_state:opticodds` hash | Writes connection state (connected/disconnected/reconnecting) — same pattern as ProphetX WS consumer |
| `app/workers/opticodds_consumer.py` | PostgreSQL `events` table | Writes OpticOdds tennis status via SQLAlchemy (same `_upsert_event` pattern as other workers) |
| `app/api/v1/health.py` | Redis hash | Exposes OpticOdds consumer health state via existing `/api/v1/health/workers` endpoint |
| `compute_status_match()` | `events.opticodds_status` column | New column feeds mismatch detection alongside `espn_status`, `odds_api_status` |

---

## Environment Variables Required

```bash
OPTICODDS_API_KEY=<api_key_from_sales>
OPTICODDS_RMQ_USERNAME=<username_equals_api_key>
OPTICODDS_RMQ_PASSWORD=<password_from_sales>
```

Note: OpticOdds credentials are API-key-scoped — if multiple API keys exist, each has distinct RMQ credentials. The `OPTICODDS_RMQ_USERNAME` is the API key value itself (confirmed from OpticOdds docs: "Username: Your API Key").

---

## Sources

- OpticOdds Developer Docs — Getting Started with RabbitMQ: https://developer.opticodds.com/docs/getting-started — confirmed host, port, vhost, pika usage, queue name from /start response. MEDIUM confidence (page confirmed connection params; /start endpoint path confirmed via /reference page).
- OpticOdds API Reference: https://developer.opticodds.com/reference/getting-started — confirmed REST endpoint paths (`/fixtures/results/queue/start`, `/stop`, `/status`), `X-Api-Key` auth header. MEDIUM confidence (retrieved via WebFetch; endpoint paths confirmed but response schema not fully documented publicly).
- pika PyPI: https://pypi.org/project/pika/ — version 1.3.2, released May 2023, Python >=3.7. HIGH confidence.
- pika heartbeat docs: https://pika.readthedocs.io/en/stable/examples/heartbeat_and_blocked_timeouts.html — confirmed `heartbeat=600`, `blocked_connection_timeout=300` parameters. HIGH confidence.
- pika blocking connection docs: https://pika.readthedocs.io/en/stable/modules/adapters/blocking.html — confirmed single-thread constraint, `add_callback_threadsafe()` as only thread-safe method, recommended thread-per-message delegation pattern. HIGH confidence.
- pika multi-host recovery example: https://pika.readthedocs.io/en/stable/examples/blocking_consume_recover_multiple_hosts.html — confirmed exception-loop reconnection pattern. HIGH confidence.
- Existing codebase `docker-compose.yml` and `ws_prophetx.py` — confirmed `ws-consumer` dedicated-service pattern as precedent. HIGH confidence.
- Existing `backend/pyproject.toml` — confirmed `httpx>=0.27` already installed, `pika` absent. HIGH confidence.

---

*Stack research for: ProphetX Market Monitor v1.3 — OpticOdds Tennis RabbitMQ Integration*
*Researched: 2026-04-01*
