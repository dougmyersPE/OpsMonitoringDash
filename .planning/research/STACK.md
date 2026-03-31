# Technology Stack

**Project:** ProphetX Market Monitor — v1.2 WebSocket-Primary Status Authority
**Researched:** 2026-03-31
**Scope:** NEW additions only. The v1.0/v1.1 stack (FastAPI, Celery/Redis/RedBeat, PostgreSQL, React 19, TanStack Query 5, Tailwind 4, shadcn/ui 3, pysher, structlog) is deployed, validated, and unchanged.

---

## Context: What This Covers

v1.2 adds three new capabilities on top of the existing system:

1. **WS diagnostics** — surface what sport_event messages actually contain, end-to-end log tracing
2. **Status authority model** — treat WS-delivered `prophetx_status` as ground truth; demote REST poller to reconciliation
3. **WS connection health on dashboard** — expose connection state, last message timestamp, reconnect count to the UI

This document answers: what stack additions or changes are required for these three capabilities?

**Answer:** No new Python packages. No new npm packages. All three capabilities are achievable with the existing stack through new columns, new Redis keys, and new API/frontend wiring.

---

## Recommended Stack

### No New Dependencies Required

All v1.2 features use already-installed components.

| Capability | Existing Tool | How Used |
|------------|---------------|----------|
| WS diagnostics | structlog (already installed) | Add structured log lines at decode, validate, and DB-write steps in `ws_prophetx.py` |
| Connection state tracking | redis-py (already installed) | `HSET worker:ws_state:prophetx field value` — store connection state, timestamps, counts |
| Status authority model | SQLAlchemy + PostgreSQL (already installed) | New `status_source` column on `events` table; `ws_prophetx.py` sets it to `"ws"` |
| Authority-aware mismatch detection | mismatch_detector.py (already exists) | Extend `compute_status_match()` to skip REST reconciliation when `status_source == "ws"` and WS is healthy |
| Connection health endpoint | FastAPI (already installed) | New route `GET /api/v1/health/ws` reads the Redis hash |
| Dashboard health panel | React + TanStack Query (already installed) | New UI component polls the health endpoint; SSE drives updates |

---

## Feature Implementation Patterns

### Feature 1: WS Diagnostics

**What to add:** Structured log lines at each decode step inside `ws_prophetx.py`.

**Pattern — log at every transformation boundary:**

```python
# After JSON parse of outer wrapper
log.debug("ws_sport_event_received", change_type=change_type, op=op)

# After base64 decode
log.debug("ws_sport_event_decoded", event_id=..., status=..., field_count=len(event_data))

# After _upsert_event completes
log.info("ws_sport_event_written", prophetx_event_id=..., status=..., op=op)
```

**Why structlog over stdlib logging:** Already installed, already used in `ws_prophetx.py`. Adds `event_id` and `status` as typed key-value fields for log querying (`docker logs ws-consumer | grep ws_sport_event_decoded`). No new package needed.

**Confidence:** HIGH — structlog is already in use in this exact file.

---

### Feature 2: Status Authority Model

**What to add:** One new DB column on `events`, one Redis key, one logic change in `mismatch_detector.py`.

**DB schema addition:**

```sql
ALTER TABLE events ADD COLUMN status_source VARCHAR(10) DEFAULT 'poll';
-- Values: 'ws' | 'poll'
-- 'ws' = prophetx_status was last written by ws_prophetx.py
-- 'poll' = prophetx_status was last written by poll_prophetx.py
```

**SQLAlchemy model addition:**

```python
status_source: Mapped[str] = mapped_column(
    String(10), default="poll", nullable=False
)
```

**Why a column and not Redis?** The status_source must persist across ws-consumer restarts and Redis flushes. It is part of the event record's provenance — the right place is the same table that holds `prophetx_status`. A Redis key would be authoritative for the current connection session but not for historical "which worker last updated this event?" queries.

**Alembic migration:** Required. One `ALTER TABLE` with a default — safe to run against live data (no backfill needed; existing rows default to `'poll'`).

**Authority logic in `mismatch_detector.py`:**

The existing `compute_status_match()` already compares ProphetX status against all real-world sources. The authority model change is conceptual, not a new algorithm: when `status_source == 'ws'` and the WS consumer is connected, `prophetx_status` is trusted as ground truth. The REST poller still runs but its writes to `prophetx_status` are conditional:

```python
# In poll_prophetx.py — add guard before updating prophetx_status
ws_healthy = r.hget("worker:ws_state:prophetx", "state") == b"connected"
if not ws_healthy or event.status_source != "ws":
    event.prophetx_status = fetched_status
    event.status_source = "poll"
# If WS is healthy and event came from WS: skip status overwrite,
# but still update last_prophetx_poll timestamp for reconciliation visibility
```

**Why not a more complex state machine?** Two sources (WS and REST), two authority states. `status_source` column + a single Redis `HGET` check covers all cases without a framework. python-statemachine would add a dependency for a two-state problem.

**Confidence:** HIGH — pattern is standard "last-write-wins with source tagging."

---

### Feature 3: WS Connection Health (Redis + API + UI)

**Redis hash schema** (written by `ws_prophetx.py`):

```
Key:    worker:ws_state:prophetx
Type:   Hash
Fields:
  state              string    "connected" | "disconnected" | "reconnecting" | "failed"
  connected_at       ISO-8601  last successful connection timestamp
  last_message_at    ISO-8601  timestamp of last sport_event message processed
  reconnect_count    integer   number of reconnect cycles since process start
  last_error         string    last error message (empty string if none)
  last_error_at      ISO-8601  timestamp of last error (empty string if none)
TTL:    None — hash is live state, not ephemeral; ws-consumer sets it on each state change
```

**Why a Hash and not separate String keys?** `HGETALL` fetches all six fields in a single round-trip. The existing `worker:heartbeat:*` string keys are boolean alive/dead signals. The new hash is richer state for the dashboard display. Both coexist.

**When to write each field:**

| Event | Fields Written |
|-------|----------------|
| `pusher:connection_established` fires | `state=connected`, `connected_at=now` |
| Any sport_event message processed | `last_message_at=now` |
| `_on_error` fires on the socket | `state=reconnecting`, `last_error=str(e)`, `last_error_at=now` |
| Exponential backoff sleep begins | `state=failed`, `reconnect_count=INCR` |
| Clean disconnect (token refresh) | `state=disconnected` |

**Pysher bindable events for state transitions** (confirmed from pysher source):
- `pusher:connection_established` — connection up
- `pusher:connection_failed` — connection failed (pysher handles this internally via `_failed_handler`)
- `pusher:error` — protocol error with Pusher error code

pysher does not expose `pusher:connection_disconnected`. The disconnect is detected via `_on_close` on the underlying `websocket.WebSocketApp`. The current `ws_prophetx.py` already handles this via the `while time.time() < _token.expires_at` exit loop — the ws_state hash write should wrap this lifecycle.

**New FastAPI endpoint:**

```
GET /api/v1/health/ws
```

Returns:
```json
{
  "state": "connected",
  "connected_at": "2026-03-31T12:00:00Z",
  "last_message_at": "2026-03-31T14:23:01Z",
  "reconnect_count": 2,
  "last_error": "",
  "last_error_at": ""
}
```

Implementation: `HGETALL worker:ws_state:prophetx` — one Redis call, returns dict, no transformation.

**Dashboard UI:**

Existing `GET /api/v1/health/workers` already returns boolean alive/dead per worker. Add `ws_prophetx` to that response using the hash `state` field, so the existing health panel in the UI gets the richer state without a new panel.

Alternatively, add a dedicated WS connection panel near the top of the dashboard. The existing `useQuery` + TanStack Query polling pattern (already used for the worker health panel) is sufficient — no new npm packages needed.

**Confidence:** HIGH for Redis hash pattern. HIGH for FastAPI endpoint. MEDIUM for exact UI placement (depends on dashboard layout decisions during implementation).

---

## Alembic Migration Required

| Migration | Type | Risk |
|-----------|------|------|
| `ADD COLUMN status_source VARCHAR(10) DEFAULT 'poll'` | DDL | Safe — non-null with default, no backfill needed |

This is the only schema change. All other additions are Redis keys, log lines, and new API routes.

---

## What NOT to Add

| Avoid | Why | What to Use Instead |
|-------|-----|---------------------|
| python-statemachine or transitions | Two authority states (ws/poll) don't justify a state machine library. String comparison on `status_source` + Redis `HGET` is sufficient. | `status_source` column + Redis HGET |
| prometheus-client | Operational overhead for a single WS consumer process. The Redis hash is the observability surface — it already integrates with the existing dashboard. | Redis hash + `/api/v1/health/ws` endpoint |
| websockets (Python library) | pysher is already integrated and working. Replacing it mid-milestone introduces reconnect logic regression risk. | pysher (already installed) |
| PysherPlus (fork) | The currently installed pysher 1.0.7 works. The only known issue (error 4200 reconnect loop) is in the ProphetX error code range 4200-4299 (reconnect immediately). The existing exponential backoff in `ws_prophetx.py::run()` already handles this correctly by catching exceptions at the outer loop. | pysher (already installed) |
| A separate "diagnostics" Celery task | WS diagnostics are log lines, not a polling task. Structlog output goes to Docker logs, readable with `docker logs ws-consumer --follow`. | structlog debug log lines in ws_prophetx.py |
| New frontend library for connection status display | The connection state display is a small status badge + timestamp. shadcn/ui Badge + Card components handle it. | shadcn/ui (already installed) |
| Server-Sent Events changes for WS health | SSE already pushes `event_updated` messages on every WS-triggered DB write. Connection health is a separate slow-polling concern (poll every 5s is fine). | TanStack Query `useQuery` with `refetchInterval: 5000` |

---

## Version Compatibility Notes

| Package | Installed Version | Notes |
|---------|-------------------|-------|
| pysher | 1.0.7 | Maintenance mode (last release Feb 2022). Bindable events confirmed from source: `pusher:connection_established`, `pusher:connection_failed`, `pusher:pong`, `pusher:ping`, `pusher:error`. State values from source: `"initialized"`, `"connecting"`, `"connected"`, `"unavailable"`, `"failed"`. No replacement needed — works correctly for this use case. |
| redis-py | 5.x (already installed) | `HSET`, `HGETALL`, `HINCRBY` are core commands — available in all Redis 7.x + redis-py 5.x combinations. No version concern. |
| SQLAlchemy | 2.x (already installed) | Mapped column with String type and default is standard ORM pattern. Alembic `add_column` migration is well-supported. |
| Alembic | already installed | `op.add_column` with server_default is the correct migration pattern for a non-null column with a default. |

---

## Integration Points (How New Code Connects to Existing Code)

| New Code | Connects To | How |
|----------|-------------|-----|
| `ws_prophetx.py` Redis hash writes | `/api/v1/health/ws` endpoint | FastAPI reads same Redis key |
| `events.status_source` column | `poll_prophetx.py` | REST poller reads `status_source` before overwriting `prophetx_status` |
| `events.status_source` column | `ws_prophetx.py::_upsert_event()` | WS writer sets `status_source = "ws"` on every sport_event write |
| `/api/v1/health/ws` | Frontend health panel | TanStack Query `useQuery` polls at 5s interval |
| structlog debug lines | Docker logs | `docker logs ws-consumer --since 1h | grep ws_sport_event` |

---

## Installation

```bash
# No new dependencies — nothing to install.
# Backend: all required packages (pysher, redis-py, structlog, sqlalchemy, alembic) already in pyproject.toml
# Frontend: all required packages (shadcn/ui, TanStack Query, React) already in package.json
```

The only deployment action needed is running the Alembic migration for the `status_source` column.

---

## Sources

- pysher source code (locally installed): `python3 -c "import inspect,pysher; print(inspect.getsource(pysher.connection))"` — confirmed all bindable event names and state values. HIGH confidence.
- Pusher Channels WebSocket Protocol (https://pusher.com/docs/channels/library_auth_reference/pusher-websockets-protocol/) — confirmed `pusher:connection_established`, `pusher:error`, `pusher:ping`/`pusher:pong` as server-to-client events. `pusher:connection_failed` is legacy/internal to pysher; not a server-sent event. HIGH confidence.
- pysher PyPI (https://pypi.org/project/Pysher/) / GitHub (https://github.com/deepbrook/Pysher) — version 1.0.7/1.0.8 (2022), maintenance mode, no active development. MEDIUM confidence on long-term support (not needed — pysher is working in production today).
- redis-py HSET/HGETALL docs — standard hash commands, no version sensitivity. HIGH confidence.
- Existing codebase (`ws_prophetx.py`, `poll_prophetx.py`, `health.py`, `event.py`, `mismatch_detector.py`) — confirmed current patterns, integration points, and what already exists. HIGH confidence.

---

*Stack research for: ProphetX Market Monitor v1.2 — WebSocket-Primary Status Authority*
*Researched: 2026-03-31*
