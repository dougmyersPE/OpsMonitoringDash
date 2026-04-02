# Architecture Research

**Domain:** Real-time external API monitoring system — OpticOdds RabbitMQ consumer integration
**Researched:** 2026-04-01 (v1.3 milestone — OpticOdds Tennis Integration)
**Confidence:** HIGH (codebase directly inspected; all integration points verified against live code)

---

## v1.3 Milestone Focus

This document covers how an OpticOdds RabbitMQ consumer integrates into the existing v1.2 architecture. The v1.3 milestone adds OpticOdds as a real-time data source for tennis match status via AMQP queue consumption.

The existing architecture is unchanged except for additive components: one new Docker service, one new `events` table column, one new file in the `clients/` layer, one new worker file, minor extensions to `mismatch_detector.py`, `health.py`, and `celery_app.py`. No existing worker files are modified for behavior changes.

**Architecture precedent:** The ProphetX WebSocket consumer (`ws-consumer`) is the exact model to follow. It is a standalone Docker service that runs a blocking long-lived connection loop, writes to PostgreSQL via `SyncSessionLocal`, publishes SSE updates via Redis, and surfaces health via `worker:heartbeat:*` + `ws:*` Redis keys. The OpticOdds consumer replicates this pattern almost exactly.

---

## Current State (v1.2 deployed)

```
Docker Compose services (8 total):
  postgres        — PostgreSQL 16
  redis           — Redis 7
  backend         — FastAPI (uvicorn)
  worker          — Celery worker (concurrency=6)
  beat            — Celery Beat (RedBeat scheduler)
  ws-consumer     — ws_prophetx.py (pysher/Pusher long-lived connection)
  frontend        — React (nginx-served static)
  nginx           — reverse proxy

events table columns relevant to status tracking:
  prophetx_status     VARCHAR(50)   — source of truth for ProphetX state
  odds_api_status     VARCHAR(50)   — from poll_odds_api
  sdio_status         VARCHAR(50)   — from poll_sports_data
  espn_status         VARCHAR(50)   — from poll_espn
  oddsblaze_status    VARCHAR(50)   — from poll_oddsblaze
  status_source       VARCHAR(20)   — "ws" | "poll" | "manual"
  ws_delivered_at     TIMESTAMPTZ   — last WS delivery for auth window guard
  status_match        BOOLEAN       — recomputed after every status write
```

---

## v1.3 Target Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│                      OpticOdds Platform                               │
│  RabbitMQ host: v3-rmq.opticodds.com:5672  vhost: api               │
│  Queue provisioned via POST /fixtures/results/queue/start             │
│  Results stream (JSON messages — same shape as /fixtures/results)     │
└─────────────────────────────┬─────────────────────────────────────────┘
                              │ AMQP (pika BlockingConnection)
                              │
┌─────────────────────────────▼─────────────────────────────────────────┐
│              opticodds-consumer container  [NEW]                      │
│              app/workers/consume_opticodds.py                         │
│              (standalone Docker service — same pattern as ws-consumer)│
│                                                                       │
│  Queue lifecycle:                                                     │
│    On startup → POST /fixtures/results/queue/start → get queue_name  │
│    On shutdown (SIGTERM) → POST /fixtures/results/queue/stop          │
│    Main loop → pika BlockingConnection.start_consuming()             │
│    On AMQP disconnect → exponential backoff reconnect (5s→60s cap)   │
│                                                                       │
│  Message handling:                                                    │
│    JSON decode → extract fixture.status + competitor names           │
│    Map status to canonical form (unplayed→not_started, etc.)         │
│    Fuzzy-match fixture to events table row by sport=tennis + names    │
│    Update opticodds_status + recompute status_match                  │
│    Publish SSE update via prophet:updates Redis channel              │
│    Write worker:heartbeat:opticodds_consumer (30s TTL)               │
│    Write opticodds:connection_state, opticodds:last_message_at       │
└─────────────────────────────┬─────────────────────────────────────────┘
                              │ DB write + Redis pub
┌─────────────────────────────▼─────────────────────────────────────────┐
│                             Redis                                     │
│  Existing keys (unchanged):                                           │
│    prophet:updates           pub/sub → SSE fan-out                   │
│    worker:heartbeat:*        liveness TTL keys                       │
│    ws:connection_state / ws:last_message_at  (ProphetX WS health)    │
│    api_calls:* / api_quota:* (usage tracking)                        │
│                                                                       │
│  NEW keys (v1.3):                                                     │
│    worker:heartbeat:opticodds_consumer   TTL=30s (written on msgs)   │
│    opticodds:connection_state            "connected"|"reconnecting"   │
│    opticodds:last_message_at             ISO timestamp, 90s TTL      │
│    opticodds:queue_name                  string, persists across restarts│
└─────────────────────────────┬─────────────────────────────────────────┘
                              │
┌─────────────────────────────▼─────────────────────────────────────────┐
│                          PostgreSQL                                   │
│  events table:                                                        │
│    ...all existing columns unchanged...                               │
│    opticodds_status  VARCHAR(50)  nullable  [NEW — migration 010]     │
│      NULL = never received from OpticOdds                            │
│      "not_started" | "live" | "ended"  = mapped from OpticOdds values│
│                                                                       │
│  No new tables required.                                             │
└─────────────────────────────┬─────────────────────────────────────────┘
                              │
┌─────────────────────────────▼─────────────────────────────────────────┐
│                        FastAPI Backend                                │
│  Existing endpoints unchanged except:                                 │
│                                                                       │
│  MODIFIED (v1.3):                                                     │
│    GET /api/v1/health/workers — add opticodds_consumer key           │
│      reads opticodds:connection_state + worker:heartbeat key         │
│                                                                       │
│  Existing event endpoints surface opticodds_status automatically     │
│  (EventSchema picks up new column; no schema changes needed if       │
│  the existing schema includes all dynamic columns already)           │
└─────────────────────────────┬─────────────────────────────────────────┘
                              │
┌─────────────────────────────▼─────────────────────────────────────────┐
│                      React Frontend                                   │
│  MODIFIED (v1.3):                                                     │
│    DashboardPage — OpticOdds consumer health badge (same pattern     │
│      as ProphetX WS health badge from Phase 10)                      │
│    Events table — opticodds_status column (same pattern as           │
│      other source columns)                                           │
└───────────────────────────────────────────────────────────────────────┘
```

---

## Component Analysis: New vs Modified vs Unchanged

### New Components

#### 1. `opticodds-consumer` Docker Service

**Where:** `docker-compose.yml` — ninth service.
**Pattern:** Identical to `ws-consumer`. Standalone Docker service with `restart: unless-stopped`. Not a Celery task.

**Why standalone service, not Celery task:**
- pika's `BlockingConnection.start_consuming()` is a blocking event loop — it must own its thread indefinitely. A Celery task that blocks forever ties up one of the six worker slots and cannot be restarted cleanly via Beat.
- `ws-consumer` established this precedent for the same reason (see ARCHITECTURE.md v1.2, Anti-Pattern 4).
- Docker's `restart: unless-stopped` provides automatic restart on crash without Celery machinery overhead.

**Memory budget:** 128m (same as `ws-consumer` — pika is lightweight; the connection carries one queue).

```yaml
opticodds-consumer:
  build: ./backend
  command: python -m app.workers.consume_opticodds
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

#### 2. `app/workers/consume_opticodds.py`

**Pattern:** Mirrors `ws_prophetx.py` structure: lifecycle management functions, message handler, main `run()` loop with exponential backoff.

Key responsibilities:
- Call `POST /fixtures/results/queue/start` on startup to provision the OpticOdds queue and get `queue_name`.
- Store `queue_name` in Redis (`opticodds:queue_name`) so it survives without re-calling start on every reconnect attempt (call start only if key is absent).
- Open `pika.BlockingConnection` to `v3-rmq.opticodds.com:5672`, vhost `api`, credentials from env.
- Call `channel.basic_consume(queue=queue_name, on_message_callback=_handle_message, auto_ack=True)` and `channel.start_consuming()`.
- In `_handle_message`: decode JSON, extract `fixture.status`, map to canonical form, fuzzy-match to an event row, update `opticodds_status`, recompute `status_match`, commit, publish SSE update.
- Write `worker:heartbeat:opticodds_consumer` (30s TTL) and `opticodds:last_message_at` on each message.
- Write `opticodds:connection_state` on connect/disconnect transitions.
- On `AMQPConnectionError` or any pika exception: sleep with exponential backoff (5s initial, 60s cap), then reconnect (do NOT re-call `/queue/start` — use cached `queue_name` from Redis).
- On SIGTERM: call `POST /fixtures/results/queue/stop` before exiting.

#### 3. `app/clients/opticodds_api.py`

**Pattern:** Inherits from `BaseAPIClient` (same as all other clients in `app/clients/`).
**Responsibilities:** `start_queue()`, `stop_queue()`, `queue_status()` — thin wrappers over the three REST endpoints. Returns `queue_name` from the start response. Uses `OPTICODDS_API_KEY` from settings.

#### 4. `opticodds_status` Column — Alembic Migration 010

**What:** `ALTER TABLE events ADD COLUMN opticodds_status VARCHAR(50)` (nullable).
**Migration file:** `backend/alembic/versions/010_add_opticodds_status.py`
**Zero-downtime safe:** nullable column, all existing rows start NULL.

#### 5. `_OPTICODDS_CANONICAL` Mapping in `mismatch_detector.py`

**What:** New dict mapping OpticOdds status strings to canonical form. Added alongside the existing `_ODDSBLAZE_CANONICAL` dict.

```python
_OPTICODDS_CANONICAL: dict[str, str] = {
    "unplayed": "scheduled",
    "live": "inprogress",
    "half": "inprogress",     # halftime — match still in progress
    "completed": "final",
    "cancelled": "final",     # treat cancelled as final for mismatch purposes
    "suspended": "inprogress",
    "delayed": "scheduled",
}
```

`compute_status_match()` gains one new source tuple:
```python
(opticodds_status, _OPTICODDS_CANONICAL),
```

The function signature gains `opticodds_status: str | None = None` parameter. All existing call sites pass it as a keyword arg or accept the default.

---

### Modified Components

#### 6. `app/workers/celery_app.py` — No Schedule Changes

`consume_opticodds.py` is NOT added to `include=[]` — it is a standalone service, not a Celery task. No changes to the beat schedule.

#### 7. `app/core/config.py` — New Env Vars

Three new fields:
```python
OPTICODDS_API_KEY: str | None = None
OPTICODDS_RMQ_USERNAME: str | None = None   # separate from API key
OPTICODDS_RMQ_PASSWORD: str | None = None
```

The RabbitMQ username and password are separate credentials provided by the OpticOdds sales team (distinct from the API key used for REST calls). Both must be in `.env`.

#### 8. `app/api/v1/health.py` — Add `opticodds_consumer` Key

**Existing:** `GET /health/workers` reads 4 heartbeat keys + 2 WS keys.
**v1.3 change:** Add `opticodds:connection_state` to the MGET call. Return `opticodds_consumer: { connected: bool, state: str }` in the response. Same pattern as `ws_prophetx` in v1.2.

#### 9. `app/monitoring/mismatch_detector.py` — Add OpticOdds Canonical Mapping

As described above: new dict + new tuple in `compute_status_match()` + new tuple in `compute_is_critical()`.

**Backward compatibility:** All callers that pass positional args to `compute_status_match()` already pass 5 args (px + 4 sources). The new `opticodds_status` is a 6th keyword arg with default `None` — call sites that don't pass it are unaffected.

#### 10. `app/models/event.py` — New Column Declaration

```python
opticodds_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
```

Added after `oddsblaze_status` for column ordering consistency.

---

### Unchanged Components

| Component | Why unchanged |
|-----------|---------------|
| `ws_prophetx.py` | ProphetX WS consumer is independent; no interaction with OpticOdds |
| `poll_prophetx.py` | Only manages `prophetx_status`; not affected by new source column |
| `poll_espn.py`, `poll_odds_api.py`, `poll_oddsblaze.py`, `poll_sports_data.py` | Each worker owns its own column; no cross-dependencies |
| `update_event_status.py` | Status sync logic reads `prophetx_status` and triggers sync; unchanged |
| `send_alerts.py` | Reads `status_match` (recomputed automatically by consumer); no change |
| `stream.py` (SSE) | `prophet:updates` pub/sub is unchanged; consumer publishes to same channel |
| `celery_app.py` beat schedule | No new periodic tasks; consumer is standalone service |
| React pages (non-dashboard) | `MarketsPage`, `ApiUsagePage`, `LoginPage` — unaffected |

---

## AMQP Connection Lifecycle

This is the most novel part of v1.3. pika's `BlockingConnection` requires careful management for production reliability.

### Queue Start — Call Once, Cache Result

```
consume_opticodds.run() starts
    │
    Check Redis: opticodds:queue_name exists?
    │
    ├─ YES → use cached queue_name, skip start call
    │         (queue persists across consumer restarts)
    │
    └─ NO  → POST /fixtures/results/queue/start
              response: { queue_name: "XXXXXXXX_results_..." }
              SET opticodds:queue_name in Redis (no TTL — intentionally persistent)
              proceed with queue_name
```

**Why cache in Redis:** If the consumer crashes and restarts, calling `/queue/start` again may provision a new queue and orphan the old one. The cached name lets restarts reconnect to the existing queue. Only call `/queue/start` if the Redis key is absent (fresh deploy) or explicitly cleared.

**Why no TTL on the Redis key:** The queue name is durable — it persists until explicitly stopped. TTL expiry would cause spurious re-provisioning on container restarts.

### AMQP Connection with Backoff Reconnect

```python
def run() -> None:
    retry_delay = 5
    max_delay = 60

    while True:
        try:
            queue_name = _get_or_start_queue()
            _connect_and_consume(queue_name)
            retry_delay = 5  # clean exit — reset backoff
        except (pika.exceptions.AMQPConnectionError,
                pika.exceptions.ConnectionClosedByBroker,
                pika.exceptions.ChannelWrongStateError,
                Exception) as exc:
            log.exception("opticodds_consumer_error", retry_in=retry_delay, exc=str(exc))
            _write_connection_state("reconnecting")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)

def _connect_and_consume(queue_name: str) -> None:
    credentials = pika.PlainCredentials(
        settings.OPTICODDS_RMQ_USERNAME,
        settings.OPTICODDS_RMQ_PASSWORD
    )
    params = pika.ConnectionParameters(
        host="v3-rmq.opticodds.com",
        port=5672,
        virtual_host="api",
        credentials=credentials,
        heartbeat=30,              # detect dead connections within 60s
        blocked_connection_timeout=300,
    )
    connection = pika.BlockingConnection(params)
    _write_connection_state("connected")
    channel = connection.channel()
    channel.basic_consume(
        queue=queue_name,
        on_message_callback=_handle_message,
        auto_ack=True,
    )
    log.info("opticodds_consumer_consuming", queue=queue_name)
    channel.start_consuming()   # blocks until exception
```

**Heartbeat 30s:** pika default is 60s. At 30s the broker detects a dead TCP connection within 60s of the last heartbeat. The consumer's main thread must not block for longer than the heartbeat interval — message processing must be fast (DB write + Redis pub = sub-millisecond for tennis event counts at this scale).

**auto_ack=True:** Consistent with the ProphetX WS consumer pattern. For a monitoring tool that derives status from a stream (not a work queue requiring exactly-once processing), acknowledging on receipt is correct. If the consumer crashes mid-message, the message is lost — acceptable given that the next matching message or a poll fallback will update the row.

### Queue Stop on Shutdown

```python
def _shutdown(sig, frame):
    log.info("opticodds_consumer_shutdown", signal=sig)
    try:
        opticodds_client.stop_queue(queue_name)
    except Exception:
        log.exception("opticodds_queue_stop_failed")
    sys.exit(0)

signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT, _shutdown)
```

**Note:** Docker sends SIGTERM on `docker stop` / `docker-compose down`. The shutdown handler has ~10 seconds (Docker's default stop grace period) to call `/queue/stop` before SIGKILL. If the stop call fails (network issue), the queue remains active on OpticOdds' side until TTL — acceptable for a monitoring tool.

---

## Data Flow

### OpticOdds RabbitMQ Message Flow

```
OpticOdds RabbitMQ broker (v3-rmq.opticodds.com)
    │ AMQP delivery — JSON body
    │ same shape as GET /fixtures/results response
    ▼
consume_opticodds._handle_message()
    │ json.loads(body)
    │ extract fixture.status, fixture.id, competitors
    │ map status: "unplayed"→"not_started", "live"→"live", "completed"→"ended"
    │ sport filter: process only tennis sport events
    ▼
_fuzzy_match_event(competitors, scheduled_start)
    │ Select events WHERE sport ILIKE 'tennis' AND scheduled_start BETWEEN now-4h AND now+24h
    │ Fuzzy match player names (SequenceMatcher, threshold 0.75 — same as poll_espn)
    │ Tennis is individual sport: match by both competitor names against home_team/away_team
    ▼
existing.opticodds_status = mapped_status
existing.last_real_world_poll = now
existing.status_match = compute_status_match(
    existing.prophetx_status,
    existing.odds_api_status,
    existing.sdio_status,
    existing.espn_status,
    existing.oddsblaze_status,
    opticodds_status=mapped_status,  # new parameter
)
session.commit()
    ▼
_publish_update(prophetx_event_id)
    │ PUBLISH to Redis prophet:updates channel
    ▼
FastAPI SSE stream → browser dashboard refresh
    ▼
write worker:heartbeat:opticodds_consumer (30s TTL)
write opticodds:last_message_at (90s TTL)
```

### OpticOdds Status Mapping

| OpticOdds value | Canonical | ProphetX equivalent | Notes |
|-----------------|-----------|--------------------|----|
| `unplayed` | `scheduled` | `not_started` | match not yet started |
| `live` | `inprogress` | `live` | in progress |
| `half` | `inprogress` | `live` | halftime — still active |
| `completed` | `final` | `ended` | match finished |
| `cancelled` | `final` | `ended` | treat as terminal; flag_only handled by SDIO |
| `suspended` | `inprogress` | `live` | temporary halt; still considered live |
| `delayed` | `scheduled` | `not_started` | delayed start |

These status strings are confirmed from the OpticOdds Fixtures Lifecycle documentation (`developer.opticodds.com/reference/fixtures-lifecycle`).

### Tennis Fuzzy Matching

Tennis events have two individual competitors (not teams). The matching strategy mirrors `poll_espn.py` for tennis:

1. Filter events WHERE `sport` ILIKE `%tennis%` AND `scheduled_start` BETWEEN `now - 4h` AND `now + 24h`
2. For each OpticOdds fixture, extract player 1 and player 2 names from `competitors` array
3. Compare against `home_team` (player 1) and `away_team` (player 2) using `SequenceMatcher`
4. Match is confirmed when both player name similarities average >= 0.75
5. On match: update `opticodds_status` on the matched row

**No new table needed for ID mapping:** OpticOdds fixture IDs are not stored in the `events` table (unlike ProphetX's own `prophetx_event_id`). Fuzzy matching by player name + date is the correct pattern for external sources — already validated for ESPN tennis in production.

---

## `opticodds_status` Column Alongside Existing Source Columns

The new column fits the established per-source column pattern exactly:

| Column | Source | Worker | Update mechanism |
|--------|--------|--------|-----------------|
| `prophetx_status` | ProphetX | `ws_prophetx.py` (primary) + `poll_prophetx` (fallback) | WS push + poll |
| `odds_api_status` | The Odds API | `poll_odds_api` (Celery) | Poll every 10 min |
| `sdio_status` | SportsDataIO | `poll_sports_data` (Celery) | Poll every 30s |
| `espn_status` | ESPN (unofficial) | `poll_espn` (Celery) | Poll every 10 min |
| `oddsblaze_status` | OddsBlaze | `poll_oddsblaze` (Celery) | Poll every 2 min |
| `opticodds_status` | OpticOdds | `consume_opticodds` (standalone svc) | AMQP push (new) |

`compute_status_match()` treats all source columns symmetrically: if a column is NULL (no data), it is skipped. If it has a value that disagrees with `prophetx_status` in canonical form, `status_match` is set to False. This means `opticodds_status` participates in mismatch detection automatically once it has data.

**OpticOdds is tennis-only in v1.3:** All other events will have NULL `opticodds_status` — correctly skipped by `compute_status_match()`. No sport filter is needed in the mismatch detector; the NULL skip handles it.

---

## Architectural Patterns

### Pattern 1: Standalone Docker Service for Long-Lived Connections

**What:** Any component requiring a persistent blocking connection (WS, AMQP) runs as its own Docker service, not as a Celery task.

**When to use:** When the connection lifecycle is `connect → block indefinitely → reconnect on failure`. Blocking a Celery worker indefinitely is wrong; Docker's `restart: unless-stopped` is the correct retry mechanism.

**Precedent:** `ws-consumer` (ProphetX pysher). `opticodds-consumer` is the second instance of this pattern.

**Trade-off:** Two standalone Docker services instead of one. Cost is minimal on a VPS — each service is ~128m RAM and has no CPU idle cost while waiting on the AMQP channel.

### Pattern 2: Queue Lifecycle via REST at Service Boundaries

**What:** Call `POST /fixtures/results/queue/start` once on startup (or first run), cache the `queue_name`, call `POST /fixtures/results/queue/stop` on SIGTERM. Reconnection after AMQP errors uses the cached name without re-calling start.

**When to use:** Any externally-managed queue where provisioning has side effects (e.g. creating a named queue on the broker). This avoids orphaned queues from spurious restarts.

**Cache store:** Redis key `opticodds:queue_name` with no TTL. The queue persists on OpticOdds' side regardless of whether the consumer is running; the name should survive container restarts.

### Pattern 3: Per-Source Status Column + Canonical Mismatch Comparison

**What:** Each external data source writes to its own `*_status` column. `compute_status_match()` normalizes all sources to `scheduled / inprogress / final` before comparing. ProphetX status is the reference.

**When to use:** Every new data source integration. The pattern is established and production-validated across 5 sources.

**Trade-off:** Schema gains one column per source. At current scale (6 sources), this is trivially managed. The alternative (a JSONB column or a separate source_statuses table) would complicate the mismatch detector and dashboard queries without benefit at this scale.

### Pattern 4: Heartbeat + Connection State Redis Keys for Health

**What:** Consumer writes `worker:heartbeat:*` (TTL key for liveness) and `opticodds:connection_state` (explicit state string) on each message and on connection transitions. FastAPI reads these for the `/health/workers` endpoint.

**Precedent:** `ws:connection_state` + `worker:heartbeat:ws_prophetx` from v1.2.

**TTL discipline:** `worker:heartbeat:opticodds_consumer` uses a 30s TTL — shorter than the poll workers (which use 3x their poll interval) because AMQP messages may arrive less frequently than ATP/WTA match frequency. If no messages arrive for 30s, the heartbeat expires and the health endpoint shows the consumer as potentially stale. The `opticodds:connection_state` key separately tracks whether the AMQP connection is established.

---

## Anti-Patterns

### Anti-Pattern 1: Celery Task for AMQP Consumer

**What people do:** Register `consume_opticodds` as a Celery task in `celery_app.py` and schedule it via Beat.

**Why it's wrong:** `channel.start_consuming()` blocks indefinitely. A Celery task that never returns ties up one of the six concurrency slots permanently, preventing other tasks from running. Beat would also try to fire the task again on schedule, causing duplicate consumers. The existing `ws-consumer` anti-pattern documentation (v1.2 ARCHITECTURE.md, Anti-Pattern 4) covers this exactly.

**Do this instead:** Standalone Docker service with `restart: unless-stopped`.

### Anti-Pattern 2: Re-Calling Queue Start on Every Reconnect

**What people do:** Call `POST /fixtures/results/queue/start` inside the pika reconnect loop so the queue is always fresh.

**Why it's wrong:** Each `/queue/start` call may provision a new named queue on the OpticOdds broker. Repeated calls on every TCP reconnection (which may happen multiple times during network blips) can accumulate orphaned queues or exhaust per-account queue limits. The queue provisioned on the initial start persists on the broker; reconnects only need a new pika connection to the existing queue.

**Do this instead:** Call `/queue/start` once on the first run. Cache `queue_name` in Redis with no TTL. Reconnect loops use the cached name.

### Anti-Pattern 3: Storing OpticOdds Fixture ID in Events Table

**What people do:** Add an `opticodds_fixture_id` column to `events` and maintain a mapping table.

**Why it's wrong:** OpticOdds fixture IDs are not available in the existing events table (populated from ProphetX). Building and maintaining a mapping requires a separate join table, an ID-resolution polling worker, and brittle reconciliation. The fuzzy name-matching approach already proven for ESPN tennis avoids all of this.

**Do this instead:** Fuzzy match by competitor names + date window on every incoming message. At tennis event volumes (typically <20 live matches at any moment), this is trivially fast. No persistent ID mapping needed.

### Anti-Pattern 4: Applying OpticOdds Status to Non-Tennis Events

**What people do:** Process all sports from the OpticOdds results queue (not just tennis).

**Why it's wrong:** OpticOdds is being integrated specifically for tennis coverage in v1.3. Other sports already have SDIO, ESPN, OddsBlaze, or Odds API coverage. Adding OpticOdds for all sports expands the fuzzy matching scope, increases false-match risk, and complicates the feature set without a scoped requirement.

**Do this instead:** Filter in `_handle_message` to only process fixtures where `sport.name` (or the sport field) is `tennis`. All other messages are acknowledged (auto_ack=True) and discarded with a debug log.

---

## Build Order

```
Phase 1: AMQP Infrastructure + Plumbing (no frontend; validates end-to-end connection)
  New files:
    backend/app/clients/opticodds_api.py
      - OpticOddsClient(BaseAPIClient) with start_queue(), stop_queue(), queue_status()
    backend/app/workers/consume_opticodds.py
      - Stub: connect, consume, log messages, disconnect — NO DB writes yet
      - Write heartbeat + opticodds:connection_state + opticodds:last_message_at to Redis
      - Graceful SIGTERM handler calling queue stop
  Config:
    backend/app/core/config.py — add OPTICODDS_API_KEY, OPTICODDS_RMQ_USERNAME, OPTICODDS_RMQ_PASSWORD
  Docker:
    docker-compose.yml — add opticodds-consumer service

  DEPLOY GATE: run consumer, confirm AMQP connection established + messages flowing
  GATE condition: opticodds:connection_state == "connected" AND
                  opticodds:last_message_at is set AND
                  log shows received messages with fixture data

Phase 2: DB Schema + Status Updates (requires Phase 1 gate)
  DB:
    backend/alembic/versions/010_add_opticodds_status.py
      - op.add_column("events", Column("opticodds_status", String(50), nullable=True))
    backend/app/models/event.py
      - Add opticodds_status mapped_column
  Mismatch detector:
    backend/app/monitoring/mismatch_detector.py
      - Add _OPTICODDS_CANONICAL dict
      - Add opticodds_status parameter + source tuple to compute_status_match()
      - Add opticodds_status parameter + source tuple to compute_is_critical()
  Consumer:
    backend/app/workers/consume_opticodds.py
      - Add tennis sport filter
      - Add fuzzy matching logic (reuse SequenceMatcher pattern from poll_espn.py)
      - Add opticodds_status write + status_match recompute + SSE publish

Phase 3: Health Endpoint + Dashboard Badge (requires Phase 1; Phase 2 recommended first)
  Backend:
    backend/app/api/v1/health.py
      - Add opticodds_consumer keys to MGET in /health/workers
      - Return opticodds_consumer: { connected: bool, state: str } in response
  Frontend:
    OpticOdds consumer health badge on DashboardPage (same pattern as ProphetX WS badge)
    opticodds_status column in events table (same pattern as existing source columns)

Phase 4: Tech Debt + Observability (no dependencies)
  Add opticodds_status to API Usage tab source breakdown (if desired)
  Add opticodds:queue_name display in admin or health UI
```

**Phase ordering rationale:**

- Phase 1 before everything: AMQP connection behavior with OpticOdds is unconfirmed. Credentials, queue provisioning, message format, and connection stability must be observed in production before building any status logic on top of it. This is the same diagnostic-first discipline applied in v1.2 Phase 1.
- Phase 2 requires Phase 1 gate to pass: writing `opticodds_status` to the DB is worthless if the AMQP connection cannot be established or messages arrive in an unexpected format.
- Phase 3 can technically run after Phase 1 (health endpoint only needs the Redis keys from Phase 1). Recommended after Phase 2 so the dashboard reflects actual status data, not just connectivity.
- Phase 4 has no dependencies and can run at any time.

---

## Integration Points

### opticodds-consumer ↔ PostgreSQL

| Direction | What | Notes |
|-----------|------|-------|
| Consumer reads | `events` WHERE sport=tennis AND scheduled_start in window | SyncSessionLocal, same as ws_prophetx |
| Consumer writes | `opticodds_status`, `last_real_world_poll`, `status_match` | Synchronous commit after each match |
| No other worker reads `opticodds_status` directly | All cross-source comparison is via `compute_status_match()` | Clean boundary |

### opticodds-consumer ↔ Redis

| Key | Writer | Reader | Notes |
|-----|--------|--------|-------|
| `worker:heartbeat:opticodds_consumer` | Consumer (each message) | FastAPI /health/workers | 30s TTL |
| `opticodds:connection_state` | Consumer (on transitions) | FastAPI /health/workers | No TTL |
| `opticodds:last_message_at` | Consumer (each message) | FastAPI (optional detail endpoint) | 90s TTL |
| `opticodds:queue_name` | Consumer (on first start) | Consumer (on reconnect) | No TTL |
| `prophet:updates` | Consumer (after each DB write) | FastAPI SSE stream | Existing pub/sub channel |

### opticodds-consumer ↔ OpticOdds REST + RabbitMQ

| Call | When | What |
|------|------|------|
| `POST /fixtures/results/queue/start` | Startup (if `opticodds:queue_name` absent in Redis) | Provisions queue, returns `queue_name` |
| `GET /fixtures/results/queue/status` | Optional: can be called for health diagnostic | Returns queue enabled/active state |
| `POST /fixtures/results/queue/stop` | SIGTERM handler | Deprovisioned queue |
| AMQP consume | Persistent connection | Stream of fixture result update messages |

### opticodds-consumer ↔ Other Workers (No Direct Interaction)

The consumer is completely independent of all Celery poll workers and of `ws_prophetx.py`. They share the PostgreSQL `events` table (each worker owns its own column) and the Redis `prophet:updates` pub/sub channel. There is no direct IPC between them.

---

## Scaling Considerations

This is an internal operator tool on a single Hetzner CX23 VPS (2 vCPU, 4 GB RAM). Scale is not a concern for v1.3.

| Concern | Current approach | Notes |
|---------|-----------------|-------|
| AMQP message throughput | Single-threaded pika blocking consumer | Tennis event count is low (tens of active matches); each message is a sub-millisecond DB write |
| Memory | 128m limit on opticodds-consumer service | pika + structlog + SQLAlchemy sync session = well under 100m at this scale |
| Queue name persistence | Redis key with no TTL | If Redis is wiped, next start provisions a new queue — one-time nuisance, not a data risk |
| Total Docker service count | 9 services after v1.3 | CX23 has 4 GB RAM; 9 services with stated limits total ~1.8 GB — within budget |

---

## Sources

### Primary (HIGH confidence — direct inspection)

- `docker-compose.yml` — 8 existing services, memory budgets, service dependency patterns
- `app/workers/ws_prophetx.py` — full file — architectural template for opticodds-consumer
- `app/models/event.py` — full file — confirmed existing column names and column addition pattern
- `app/monitoring/mismatch_detector.py` — full file — confirmed `compute_status_match()` parameter pattern; `_ODDSBLAZE_CANONICAL` is the direct template for `_OPTICODDS_CANONICAL`
- `app/api/v1/health.py` — full file — confirmed current Redis keys read; modification approach
- `app/workers/celery_app.py` — confirmed standalone service (not Celery task) is correct for blocking consumers
- `app/workers/poll_espn.py` — confirmed fuzzy matching approach for tennis (lines 1-60)
- `app/clients/oddsblaze_api.py` — confirmed `BaseAPIClient` inheritance pattern
- `app/core/config.py` — confirmed env var pattern for optional API keys
- `backend/alembic/versions/007_add_oddsblaze_status.py` — confirmed migration pattern for new source column
- `backend/alembic/versions/009_drop_sports_api_status.py` — confirmed next migration ID is 010

### Secondary (MEDIUM confidence — official docs, verified)

- OpticOdds developer portal (`developer.opticodds.com/docs/getting-started`) — RabbitMQ host `v3-rmq.opticodds.com`, port 5672, vhost `api`, pika connection pattern confirmed
- OpticOdds API reference (`developer.opticodds.com/reference/getting-started`) — `POST /fixtures/results/queue/start`, `POST /fixtures/results/queue/stop`, `GET /fixtures/results/queue/status` confirmed
- OpticOdds Fixtures Lifecycle (`developer.opticodds.com/reference/fixtures-lifecycle`) — status values `unplayed`, `live`, `half`, `completed`, `cancelled`, `suspended`, `delayed` confirmed
- pika documentation (`pika.readthedocs.io/en/stable/`) — `BlockingConnection`, `ConnectionParameters`, heartbeat parameter, `basic_consume` with `auto_ack`
- pika reconnection examples (`pika.readthedocs.io/en/stable/examples/blocking_consume_recover_multiple_hosts.html`) — exception handling pattern for reconnection confirmed

### Tertiary (informational)

- WebSearch: OpticOdds RabbitMQ queue_name caching pattern — no specific documentation found; cache-on-first-call approach derived from queue provisioning semantics

---

*Architecture research for: ProphetX Market Monitor v1.3 — OpticOdds Tennis Integration*
*Researched: 2026-04-01*
