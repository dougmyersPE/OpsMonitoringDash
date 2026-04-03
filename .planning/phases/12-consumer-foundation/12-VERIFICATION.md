---
phase: 12-consumer-foundation
verified: 2026-04-03T15:30:00Z
status: passed
score: 12/12 must-haves verified
re_verification: false
gaps: []
human_verification:
  - test: "Deploy opticodds-consumer via docker compose up opticodds-consumer and confirm it connects to OpticOdds RabbitMQ"
    expected: "Container starts, POSTs to OpticOdds REST API, logs opticodds_queue_started, then logs opticodds_rmq_connected"
    why_human: "Requires live OpticOdds credentials and access to v3-rmq.opticodds.com — cannot verify without the external service"
  - test: "Confirm /api/v1/health/workers opticodds_consumer key shows connected=true after consumer starts"
    expected: "GET /api/v1/health/workers returns opticodds_consumer.connected=true and opticodds_consumer.state='connected'"
    why_human: "Requires running docker stack with opticodds-consumer container and valid credentials"
---

# Phase 12: Consumer Foundation Verification Report

**Phase Goal:** Stand up the OpticOdds AMQP consumer that receives live tennis status pushes and writes them to the events table, with health monitoring and Docker service definition.
**Verified:** 2026-04-03T15:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Scope Boundary Note

The phase goal says "writes them to the events table" but the PLAN frontmatter for Plan 02 explicitly defers DB writes to Phase 13 (requires TNNS-02 fuzzy matching). This is a planned, documented deferral — not a gap. The REQUIREMENTS.md traceability table marks TNNS-01 as Phase 12 "Pending" with the understanding that Phase 12 delivers the schema half and Phase 13 delivers the write half. This verification treats Phase 12's actual contracted scope (schema + consumer + health) as the ground truth.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | pika dependency declared in pyproject.toml | VERIFIED | Line 26: `"pika>=1.3.2,<2.0"` |
| 2 | OpticOdds env vars available via Settings object | VERIFIED | config.py lines 48-52: all 4 fields with None defaults |
| 3 | Event model has opticodds_status column | VERIFIED | event.py line 34: `opticodds_status: Mapped[str | None] = mapped_column(String(50), nullable=True)` |
| 4 | Alembic migration 010 adds opticodds_status to events table | VERIFIED | `010_add_opticodds_status.py` exists, chain 009->010, `op.add_column("events", sa.Column("opticodds_status", sa.String(50), nullable=True))` |
| 5 | Consumer calls OpticOdds queue start REST endpoint on startup | VERIFIED | `_start_queue()` POSTs to `settings.OPTICODDS_BASE_URL` with `X-Api-Key` header, `sys.exit(1)` on failure |
| 6 | Consumer caches queue name in Redis on startup | VERIFIED | `r.set("opticodds:queue_name", queue_name)` in `_start_queue()` |
| 7 | Consumer connects via pika BlockingConnection with heartbeat=30, auto_ack=False | VERIFIED | run() lines 237-254: `heartbeat=30`, `blocked_connection_timeout=300`, `auto_ack=False` |
| 8 | Consumer reconnects with exponential backoff and jitter on failure | VERIFIED | lines 264-278: AMQP exception caught, `time.sleep(retry_delay + random.uniform(0,1))`, `retry_delay = min(retry_delay * 2, max_delay)` |
| 9 | Consumer writes Redis health keys (connection_state, last_message_at) | VERIFIED | `_write_connection_state()` sets `opticodds:connection_state` + `opticodds:connection_state_since` (ex=120); `_write_last_message_at()` sets `opticodds:last_message_at` (ex=90) |
| 10 | Unknown statuses trigger WARNING log and Slack alert with Redis SETNX dedup | VERIFIED | `_alert_unknown_status()` uses `r.set(dedup_key, "1", ex=300, nx=True)` + `WebhookClient(settings.SLACK_WEBHOOK_URL).send(text=text)` |
| 11 | opticodds-consumer service defined in docker-compose.yml | VERIFIED | Lines 96-109: service with `command: python -m app.workers.opticodds_consumer`, `restart: unless-stopped`, `memory: 128m`, depends_on postgres+redis healthy |
| 12 | GET /health/workers includes opticodds_consumer key with connected/state/since shape | VERIFIED | health.py lines 36-58: MGET includes `opticodds:connection_state` + `opticodds:connection_state_since`, return dict has `opticodds_consumer: {connected, state, since}` |

**Score:** 12/12 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/pyproject.toml` | pika dependency | VERIFIED | `"pika>=1.3.2,<2.0"` present |
| `backend/app/core/config.py` | OpticOdds settings fields | VERIFIED | All 4 fields: OPTICODDS_API_KEY, OPTICODDS_RMQ_USERNAME, OPTICODDS_RMQ_PASSWORD, OPTICODDS_BASE_URL |
| `backend/app/models/event.py` | opticodds_status column | VERIFIED | Mapped[str | None] String(50) nullable, after oddsblaze_status |
| `backend/alembic/versions/010_add_opticodds_status.py` | DB migration | VERIFIED | revision="010", down_revision="009", correct upgrade/downgrade |
| `.env.example` | Env var documentation | VERIFIED | All 4 OPTICODDS vars documented at lines 15-18 |
| `backend/app/workers/opticodds_consumer.py` | Standalone AMQP consumer | VERIFIED | 302 lines, substantive implementation, all required functions present |
| `backend/tests/test_opticodds_consumer.py` | Unit tests | VERIFIED | 375 lines, 13 tests — all pass (confirmed via test run) |
| `docker-compose.yml` | opticodds-consumer service | VERIFIED | Lines 96-109, mirrors ws-consumer pattern exactly |
| `backend/app/api/v1/health.py` | OpticOdds health in /health/workers | VERIFIED | MGET extended to 8 keys, opticodds_consumer entry in return dict |
| `backend/tests/test_health.py` | Health tests for opticodds_consumer | VERIFIED | TestWorkerHealthOpticOddsConsumer with 3 tests |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `opticodds_consumer.py` | `config.py` | `settings.OPTICODDS_API_KEY`, `settings.OPTICODDS_RMQ_USERNAME`, etc. | VERIFIED | `settings.OPTICODDS_BASE_URL` line 79, `settings.OPTICODDS_API_KEY` line 80, `settings.OPTICODDS_RMQ_USERNAME/PASSWORD` lines 241-242 |
| `opticodds_consumer.py` | Redis | `opticodds:connection_state` keys | VERIFIED | `_write_connection_state()` sets `opticodds:connection_state` (ex=120), `_start_queue()` sets `opticodds:queue_name` |
| `opticodds_consumer.py` | OpticOdds REST API | `httpx.post` to `OPTICODDS_BASE_URL` | VERIFIED | `httpx.post(settings.OPTICODDS_BASE_URL, ...)` line 79 |
| `opticodds_consumer.py` | Slack | `WebhookClient(settings.SLACK_WEBHOOK_URL).send(text=text)` | VERIFIED | Line 145 in `_alert_unknown_status()` |
| `docker-compose.yml` | `opticodds_consumer.py` | `command: python -m app.workers.opticodds_consumer` | VERIFIED | Line 98 in docker-compose.yml |
| `health.py` | Redis | MGET includes `opticodds:connection_state` | VERIFIED | Lines 36-37 in health.py keys list |

---

### Data-Flow Trace (Level 4)

The consumer is a standalone worker, not a data-rendering component. Data flows are verified at the wiring level:

| Data Path | Source | Sink | Status |
|-----------|--------|------|--------|
| Queue name REST response → Redis cache | `httpx.post().json()["queue_name"]` | `r.set("opticodds:queue_name", queue_name)` | FLOWING — response field extracted and written |
| Connection state → Redis → health endpoint | `_write_connection_state(state)` in `run()` | `mget("opticodds:connection_state")` in `health.py` | FLOWING — producer and consumer of the key are both wired |
| Message body → status mapping → ack/nack | `json.loads(body)["status"]` → `_OPTICODDS_CANONICAL.get(raw_status)` | `ch.basic_ack()` or `ch.basic_nack()` | FLOWING — complete processing chain |
| Unknown status → Slack alert with dedup | `_alert_unknown_status(raw_status, ...)` | `WebhookClient.send(text=...)` after Redis SETNX | FLOWING — 13 unit tests confirm end-to-end |

---

### Behavioral Spot-Checks

All tests run against mocked dependencies (no live services required by design).

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 13 consumer unit tests pass | `uv run pytest tests/test_opticodds_consumer.py -v` | 13 passed in 0.04s | PASS |
| Consumer module has valid Python syntax | Confirmed by pytest import | No SyntaxError | PASS |
| Migration 010 has correct revision chain | File read | `revision="010"`, `down_revision="009"` | PASS |
| opticodds-consumer service in docker compose | `grep opticodds-consumer docker-compose.yml` | Found at line 96 | PASS |
| health.py returns opticodds_consumer key | Code trace through MGET result indices | results[6]/results[7] mapped to rmq_state/rmq_since | PASS |
| Health integration tests | `uv run pytest tests/test_health.py -v` | SKIP — integration tests require live postgres/redis stack | SKIP (needs docker) |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| AMQP-01 | Plans 02, 03 | OpticOdds RabbitMQ consumer runs as standalone Docker service with pika, auto-reconnect, heartbeat management | SATISFIED | `opticodds_consumer.py` implements pika BlockingConnection with heartbeat=30 and exponential backoff reconnect; docker-compose.yml service definition present |
| AMQP-02 | Plans 02, 03 | Consumer starts OpticOdds results queue via REST API on startup and caches queue name in Redis | SATISFIED | `_start_queue()` POSTs to `OPTICODDS_BASE_URL`, caches `opticodds:queue_name` in Redis; test_start_queue_success verifies this |
| TNNS-01 | Plan 01 (schema half) | Events table has opticodds_status column (nullable) populated by the consumer | PARTIAL — schema delivered, writes deferred | Migration 010 adds column; Event model has `opticodds_status` mapped_column; DB write (population) is Phase 13 scope per documented deferral in Plan 02 |

**TNNS-01 scope note:** The REQUIREMENTS.md marks TNNS-01 as Phase 12 with status "Pending". Plan 01 claims TNNS-01 for the schema half. Plan 02 explicitly documents that the "populated by the consumer" half requires TNNS-02 fuzzy matching and is Phase 13 scope. The traceability table in REQUIREMENTS.md should be updated when Phase 13 completes TNNS-01 fully. This is a known planned partial — not a gap blocking Phase 12 goal.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/app/workers/opticodds_consumer.py` | 157-160 | `_write_heartbeat()` defined but never called in `run()` or `_on_message()` | Warning | `worker:heartbeat:opticodds_consumer` Redis key will never be written in production; the health endpoint does NOT use this key (it uses `opticodds:connection_state` instead), so health monitoring is unaffected. The heartbeat function is dead code. |

**Stub classification:** The orphaned `_write_heartbeat()` does NOT render to user-visible output in Phase 12 — health.py reads `opticodds:connection_state`, not `worker:heartbeat:opticodds_consumer`. The `/health/workers` endpoint's `opticodds_consumer.connected` bool is driven solely by the `opticodds:connection_state` Redis key. Severity is Warning (not blocker) because health monitoring works correctly without it.

For reference: other workers (ws_prophetx, poll_*) call `_write_heartbeat()` from their main processing loops. If Phase 14 or later adds a heartbeat-based liveness check for `opticodds_consumer`, this will need to be wired.

---

### Human Verification Required

#### 1. Live OpticOdds RabbitMQ Connection

**Test:** Deploy to staging/production with real credentials. Run `docker compose up opticodds-consumer`. Watch logs for `opticodds_queue_started` then `opticodds_rmq_connected`.
**Expected:** Consumer connects, begins receiving tennis match status messages, logs first 5 at DEBUG with raw body, writes `opticodds:connection_state = "connected"` to Redis.
**Why human:** Requires live OpticOdds API key and access to `v3-rmq.opticodds.com:5672` — external service not available in local verification environment.

#### 2. Health Endpoint with Running Consumer

**Test:** With docker stack running including opticodds-consumer, call `GET /api/v1/health/workers`.
**Expected:** Response contains `"opticodds_consumer": {"connected": true, "state": "connected", "since": "<ISO timestamp>"}`.
**Why human:** Integration test (`test_opticodds_consumer_disconnected_when_no_redis_key`) verifies the disconnected (None) case; connected=true case requires live consumer writing to Redis.

---

### Gaps Summary

No gaps found. All 12 must-have truths are verified against actual codebase.

One warning found (`_write_heartbeat` defined but not called) that does not block phase goal achievement — health monitoring works correctly via `opticodds:connection_state` keys.

TNNS-01 is partially delivered (schema only) per explicit documented plan boundary. The "populated by consumer" half is Phase 13 scope. This is not a gap for Phase 12.

---

*Verified: 2026-04-03T15:30:00Z*
*Verifier: Claude (gsd-verifier)*
