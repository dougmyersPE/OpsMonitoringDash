# Architecture Research

**Domain:** Real-time external API monitoring system — WebSocket-primary status authority integration
**Researched:** 2026-03-31 (v1.2 milestone — WebSocket-Primary Status Authority)
**Confidence:** HIGH (codebase directly inspected; all integration points verified against live code)

---

## v1.2 Milestone Focus

This document covers the integration of WebSocket-primary status authority into the existing v1.1 architecture. The v1.2 milestone promotes `ws_prophetx.py` from a background data-ingestion service to the authoritative real-time source for `prophetx_status`, with polling workers serving as reconciliation fallback.

The existing stack is unchanged: FastAPI + Celery/RedBeat + Redis + PostgreSQL, React/TypeScript. No new infrastructure is required. All changes are additive to existing components or demotions of existing behavior.

**Key constraint from STATE.md (Blockers/Concerns):** The WS consumer currently receives zero `sport_event` change_type messages — only `market_selections` and `matched_bet`. This means Phase 1 must establish diagnostic instrumentation to confirm the message pipeline works end-to-end before any authority model change is worth building. Building the status authority model on an unconfirmed message flow is the single greatest risk in v1.2.

---

## System Overview (v1.2 Target State)

```
┌──────────────────────────────────────────────────────────────────────┐
│                     ProphetX Platform                                │
│  Pusher broadcast channel (private-broadcast-service=3-device_type=5)│
│  sport_event messages (base64 payload, op=c/u/d)                    │
│  ProphetX REST API (get_sport_events — polling fallback)             │
└─────────┬────────────────────────────────┬────────────────────────────┘
          │ Pusher / WebSocket             │ REST (demoted)
          │                               │
┌─────────▼──────────────────┐   ┌────────▼──────────────────────────────┐
│   ws-consumer container    │   │      Celery Worker container          │
│   ws_prophetx.py           │   │                                       │
│   (standalone Docker svc)  │   │  poll_prophetx (5-min reconciliation) │
│                            │   │  poll_sports_data (SDIO)              │
│  NEW in v1.2:              │   │  poll_odds_api                        │
│  - Structured status log   │   │  poll_sports_api                      │
│  - ws:connection_state key │   │  poll_espn                            │
│  - ws:last_message_at key  │   │  poll_oddsblaze                       │
│  - ws:last_sport_event_at  │   │  poll_critical_check                  │
│  - ws:sport_event_count    │   │                                       │
│  - ws_delivered_at on upsert│  │  CHANGED in v1.2:                     │
│                            │   │  poll_prophetx demoted:               │
│  CHANGED in v1.2:          │   │    - still upserts events             │
│  - _upsert_event sets      │   │    - skips prophetx_status overwrite  │
│    ws_delivered_at in DB   │   │      if WS delivered it recently      │
│  - writes ws state keys    │   │    - primary use: catch missed events │
│    to Redis                │   │      during WS downtime               │
└─────────┬──────────────────┘   └────────────────┬──────────────────────┘
          │ DB write + Redis pub                   │ DB write + Redis pub
          └────────────────┬───────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│                          Redis                                       │
│  Existing keys:                                                      │
│    prophet:updates           (pub/sub channel → SSE fan-out)        │
│    worker:heartbeat:*        (liveness TTL keys)                    │
│    api_calls:*               (daily call counters)                  │
│    api_quota:*               (provider quota cache)                 │
│                                                                      │
│  NEW keys (v1.2):                                                    │
│    ws:connection_state       "connected"|"disconnected"|"reconnecting"│
│    ws:last_message_at        ISO timestamp, 90s TTL                  │
│    ws:last_sport_event_at    ISO timestamp (no TTL — last event time)│
│    ws:sport_event_count      INTEGER via INCR, 8-day TTL             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│                       PostgreSQL                                     │
│  events table (existing columns unchanged):                          │
│    prophetx_status      VARCHAR(50)                                  │
│    last_prophetx_poll   TIMESTAMPTZ                                  │
│    status_match         BOOLEAN                                      │
│    ...all other existing columns                                     │
│                                                                      │
│  NEW column (v1.2):                                                  │
│    ws_delivered_at   TIMESTAMPTZ nullable                            │
│      NULL  = event has never been updated via WS                    │
│      value = last time WS delivered a status update for this event  │
│      used by poll_prophetx reconciliation guard                      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│                     FastAPI Backend                                  │
│  Existing endpoints (unchanged behavior):                            │
│    GET  /api/v1/events          — event list                        │
│    GET  /api/v1/stream          — SSE pub/sub fan-out               │
│    POST /api/v1/events/{id}/sync-status — manual sync trigger       │
│                                                                      │
│  MODIFIED in v1.2:                                                   │
│    GET /api/v1/health/workers   — adds ws_consumer key to response  │
│                                   (reads ws:connection_state +      │
│                                    ws:last_message_at keys)         │
│                                                                      │
│  NEW endpoint (v1.2):                                                │
│    GET /api/v1/health/ws        — WS connection detail              │
│                                   (state, last_message_at,          │
│                                    last_sport_event_at,             │
│                                    sport_event_count)               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│                     React Frontend                                   │
│  Existing pages (unchanged):                                         │
│    MarketsPage, LoginPage, ApiUsagePage                              │
│                                                                      │
│  MODIFIED in v1.2:                                                   │
│    DashboardPage — add WS health indicator to worker status panel   │
│      - Connected / Reconnecting / Disconnected badge                │
│      - "Last sport_event: X min ago" detail                         │
│      - Sport event count (today or rolling)                          │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Component Analysis: New vs. Modified vs. Unchanged

### New Components

#### 1. WS Connection State Redis Keys

**Where:** Written by `ws_prophetx.py`; read by FastAPI health endpoints.
**What:** Four Redis keys tracking WS health and message flow. Written by ws-consumer only.

| Key | Value | TTL | Written when |
|-----|-------|-----|-------------|
| `ws:connection_state` | `"connected"` / `"disconnected"` / `"reconnecting"` | None (explicit overwrite) | Each connection state transition |
| `ws:last_message_at` | ISO timestamp string | 90s | Every Pusher message of any type |
| `ws:last_sport_event_at` | ISO timestamp string | None (last event time, not expiry-based) | Each `sport_event` change_type message |
| `ws:sport_event_count` | INTEGER | 8-day TTL | Each `sport_event` change_type message (INCR) |

The `ws:last_message_at` 90s TTL acts as a secondary liveness signal: if the key expires, no messages have arrived in 90 seconds even if `ws:connection_state` claims "connected." This guards against pysher's silent drop behavior where a stale TCP connection is still "open" but not delivering messages.

#### 2. `ws_delivered_at` DB Column

**Where:** `events` table — new nullable `TIMESTAMPTZ` column, added via Alembic migration.
**What:** Set by `_upsert_event()` in `ws_prophetx.py` whenever a `sport_event` message updates an event's `prophetx_status`. NULL means the event has never been updated via WS.
**Why:** Enables the poll_prophetx reconciliation guard. If `ws_delivered_at` was set within the last N minutes (suggest 10 min), `poll_prophetx` skips overwriting `prophetx_status` with its REST API result, preventing stale REST data from clobbering a fresh WS-delivered status.

**Schema addition to `models/event.py`:**
```python
ws_delivered_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), nullable=True
)
```

**Migration:** New Alembic migration `007_ws_delivered_at.py`. Zero-downtime safe — nullable column, all existing rows start with NULL, which is correctly interpreted as "never received from WS" by the poll guard.

#### 3. GET /api/v1/health/ws Endpoint

**Where:** `backend/app/api/v1/health.py` — new route in the existing health router.
**What:** Returns WS consumer health detail by reading the new Redis keys. No DB queries.

**Response shape:**
```json
{
  "connection_state": "connected",
  "last_message_at": "2026-03-31T14:22:05Z",
  "last_sport_event_at": "2026-03-31T14:22:05Z",
  "sport_event_count": 47,
  "seconds_since_last_message": 12
}
```

#### 4. WS Health Indicator (Frontend)

**Where:** `DashboardPage.tsx` — added to the existing worker health panel.
**What:** Badge/pill showing ws_consumer state. Reads from the modified `GET /api/v1/health/workers` (which gains a `ws_consumer` key) or the new `/api/v1/health/ws` for richer detail.
**Pattern:** Uses existing `useQuery` with `refetchInterval: 30_000` — same pattern as existing worker health check. No new libraries needed.

---

### Modified Components

#### 5. `ws_prophetx.py` — Diagnostics + State Writes

**Existing behavior:** Subscribes to Pusher, decodes `sport_event` messages, calls `_upsert_event()`, writes `worker:heartbeat:ws_prophetx` every 10s.

**v1.2 changes (additive only — no logic rewrites):**
- Write `ws:connection_state "connected"` in `_on_connect` handler
- Write `ws:connection_state "disconnected"` in disconnect/cleanup paths
- Write `ws:connection_state "reconnecting"` at the top of `run()` retry loop
- Write `ws:last_message_at` in `_handle_broadcast_event()` on every call (any change_type)
- Write `ws:last_sport_event_at` and INCR `ws:sport_event_count` inside the `change_type == "sport_event"` branch
- Add structured log fields to `_handle_broadcast_event`: `change_type`, `op`, `prophetx_event_id`, `status_value`
- `_upsert_event()`: set `existing.ws_delivered_at = now` and `event.ws_delivered_at = now` on both create and update paths

The `_patched_handle_event` / `_handle_broadcast_event` routing logic is correct and unchanged. v1.2 adds instrumentation around it.

#### 6. `poll_prophetx.py` — Reconciliation Demotion

**Existing behavior:** Runs every 5 minutes, upserts all active events from REST API including `prophetx_status`, is the primary source of `prophetx_status` data.

**v1.2 change — authority window guard on existing event update path:**

```python
# Constants (top of file, after imports)
WS_AUTHORITY_WINDOW_SECONDS = 10 * 60  # 10 minutes

# In the existing event update block (existing=True branch):
ws_recent = (
    existing.ws_delivered_at is not None
    and (now - existing.ws_delivered_at).total_seconds() < WS_AUTHORITY_WINDOW_SECONDS
)
if ws_recent:
    log.debug(
        "poll_prophetx_status_skipped_ws_authoritative",
        prophetx_event_id=prophetx_event_id,
        ws_age_seconds=int((now - existing.ws_delivered_at).total_seconds()),
    )
else:
    existing.prophetx_status = status_value
```

**Unchanged in poll_prophetx:**
- All metadata fields: `name`, `home_team`, `away_team`, `scheduled_start`, `league`, `sport`, `last_prophetx_poll` — REST is still a valid source for these
- Stale event marking logic (events absent from REST response → mark ended)
- Full `compute_status_match` recompute pass at end of each poll cycle
- Heartbeat and call counter writes

#### 7. `GET /api/v1/health/workers` — Add ws_consumer Key

**Existing behavior:** Reads 4 `worker:heartbeat:*` keys via Redis MGET, returns boolean per worker.

**v1.2 change:** Add `ws_consumer` to the MGET call and response. Derive boolean from `ws:connection_state == "connected"` AND `ws:last_message_at` key exists (non-expired).

**Backward-compatible change:** Adds a new key to the existing dict response. Existing frontend code that checks for specific keys by name will not break.

---

### Unchanged Components

| Component | Why unchanged |
|-----------|---------------|
| `mismatch_detector.py` | Status comparison logic is source-agnostic. WS-delivered status writes the same `prophetx_status` column; `compute_status_match()` works without changes |
| `update_event_status.py` | Lifecycle guard and idempotency logic unchanged. WS authority model changes what writes to `prophetx_status`, not how corrections are applied downstream |
| `poll_critical_check.py` | Reads `prophetx_status` from DB; benefits automatically from faster WS-delivered updates with no code change |
| `send_alerts.py` | Reads `status_match` and `is_flagged`; authority model doesn't affect these columns |
| `stream.py` (SSE) | `prophet:updates` pub/sub is already published by both WS consumer and poll workers; no change |
| External source poll workers | `poll_sports_data`, `poll_odds_api`, `poll_sports_api`, `poll_espn`, `poll_oddsblaze` — only write their own `*_status` columns, never `prophetx_status` |
| `celery_app.py` | No schedule changes; `poll_prophetx` interval stays at 5 minutes (correct for reconciliation fallback) |
| React pages except Dashboard | `MarketsPage`, `ApiUsagePage`, `LoginPage` — no WS health concern |

---

## Data Flow

### WS-Primary Status Update Flow (v1.2 target state)

```
ProphetX Pusher broadcast channel
    │ sport_event message (base64 payload, op=c/u/d)
    ▼
ws_prophetx._handle_broadcast_event()
    │ SET ws:last_message_at (any msg)
    │ SET ws:last_sport_event_at + INCR ws:sport_event_count (sport_event only)
    ▼
ws_prophetx._upsert_event()
    │ Writes events.prophetx_status = status_value
    │ Writes events.ws_delivered_at = now  [NEW]
    │ Recomputes status_match via compute_status_match()
    │ Commits to PostgreSQL
    ▼
_publish_update("event_updated", prophetx_event_id)
    │ PUBLISH to Redis prophet:updates channel
    ▼
stream.py SSE endpoint (FastAPI)
    │ Forwards update event to all connected browser clients
    ▼
React: queryClient.invalidateQueries(["events"])
    ▼
Dashboard refresh (< 5 seconds end-to-end when WS healthy)
```

### Poll Reconciliation Flow (v1.2 — demoted to fallback)

```
Celery Beat fires poll_prophetx every 5 minutes
    ▼
Fetch ProphetX REST API → events list
    ▼
For each event in REST response:
    existing = DB lookup by prophetx_event_id
    │
    ├─ existing is None → INSERT new event (unchanged)
    │  sets ws_delivered_at = None (new events, not yet received via WS)
    │
    └─ existing is not None → UPDATE
        │
        Check ws_delivered_at  [NEW GUARD]
        │
        ├─ ws_delivered_at within 10 min → SKIP prophetx_status overwrite
        │  Still updates: name, teams, scheduled_start, last_prophetx_poll
        │
        └─ ws_delivered_at NULL or older than 10 min → write prophetx_status
           (existing behavior — REST is best available source)
    ▼
Mark stale events as ended (unchanged — REST is authoritative for event presence)
    ▼
Full compute_status_match recompute pass (unchanged)
    ▼
Commit + publish SSE updates
```

### WS Connection Health Monitoring Flow

```
ws_prophetx._on_connect()
    │ SET ws:connection_state "connected"
    ▼
ws_prophetx main loop (every 10s)
    │ SETEX ws:last_message_at (from most recent message)
    │ SET worker:heartbeat:ws_prophetx (existing — unchanged)
    ▼
FastAPI GET /api/v1/health/workers  [MODIFIED]
    │ MGET includes ws:connection_state + ws:last_message_at
    │ Returns ws_consumer: bool
    ▼
FastAPI GET /api/v1/health/ws  [NEW]
    │ Returns full WS health detail
    ▼
React DashboardPage: WsHealthIndicator  [NEW]
    │ Badge: connected / reconnecting / disconnected
    └─ Detail: "last sport_event: X min ago"
```

---

## Architectural Patterns

### Pattern 1: WS Authority Window Guard

**What:** Before `poll_prophetx` overwrites `prophetx_status`, check `ws_delivered_at`. If WS delivered a status update within the last `WS_AUTHORITY_WINDOW_SECONDS` (10 min), skip the REST overwrite for `prophetx_status` only — other metadata fields still update normally.

**When to use:** Only in `poll_prophetx` for the `prophetx_status` field. Do not apply to event metadata (name, teams, scheduled_start) — REST is a valid and often more complete source for those fields.

**Trade-off:** If WS delivers a wrong status, the authority window delays REST correction by up to 10 minutes + the next poll interval (5 min) = up to 15 minutes total. This is acceptable; the 30-second dashboard freshness requirement is met by WS when healthy, and 15-minute REST correction covers the degraded path.

### Pattern 2: Redis as WS Health Signal Store

**What:** WS consumer writes connection state and message timestamps to Redis. FastAPI health endpoint reads them. No DB round-trip for health checks.

**When to use:** Any fast-changing operational state for health monitoring. This is identical to the existing `worker:heartbeat:*` pattern.

**Trade-off:** Redis is not durable. If Redis restarts, health state resets to unknown until ws-consumer next writes. Acceptable — health keys are soft signals, not business data.

**Key discipline:** Only ws-consumer writes `ws:*` keys. Poll workers never write to them. FastAPI is the only reader.

### Pattern 3: Diagnostic-First Development

**What:** Add structured logging and observable state (Redis keys) to ws_prophetx.py. Deploy. Observe real message flow. Only then build the authority model on top of confirmed behavior.

**When to use:** Any time the underlying data source behavior is unconfirmed in production. STATE.md documents zero `sport_event` messages observed — this is the trigger.

**Trade-off:** Delays the authority model by one deploy/observe cycle (24–48 hours). The alternative — building on an assumed message flow — risks rebuilding three phases of logic if ProphetX doesn't send `sport_event` messages on this channel or sends them in an unexpected format.

---

## Anti-Patterns

### Anti-Pattern 1: Unconditional WS Authority (Remove Poll Writes)

**What people do:** Mark WS as always authoritative and remove `prophetx_status` writes from `poll_prophetx` entirely.

**Why it's wrong:** WS reconnection windows (pysher default: 5s backoff, up to 60s max) create gaps. During a 60-second WS outage, ProphetX may transition an event from `not_started` to `live`. Without REST reconciliation, this transition is invisible until WS reconnects. The lifecycle guard in `update_event_status.py` would then also block REST from correcting the state.

**Do this instead:** Use the authority window guard. WS wins for fresh data; REST wins for stale-or-absent WS data. Keep `poll_prophetx` on its 5-minute schedule as the safety net.

### Anti-Pattern 2: Building Authority Logic Before Confirming WS Message Flow

**What people do:** Write `ws_delivered_at`, the poll guard, and the demotion logic before verifying that ProphetX actually sends `sport_event` change_type messages on the broadcast channel.

**Why it's wrong:** STATE.md records zero `sport_event` messages observed in production. The authority model is worthless — and potentially harmful — if the message source doesn't exist. Discovering this after three phases of implementation creates significant rework.

**Do this instead:** Phase 1 is exclusively diagnostic. Add logging and Redis state keys. Deploy. Confirm `ws:sport_event_count` increments before writing a single line of Phase 2 code.

### Anti-Pattern 3: DB Writes for Every WS Health Signal

**What people do:** Record every WS message as a DB row for durable health history.

**Why it's wrong:** ws-consumer is single-threaded. DB writes on every Pusher message (including non-sport-event messages like `market_selections`) add latency on the critical message path and unnecessary DB load. The 90s `ws:last_message_at` TTL in Redis is sufficient for health monitoring.

**Do this instead:** Redis for health signals (volatile, fast). DB only for business data: `ws_delivered_at` on the event row is the only durable WS-sourced data needed.

### Anti-Pattern 4: Moving ws-consumer into Celery

**What people do:** Make ws-consumer a Celery task for unified monitoring and restart management.

**Why it's wrong:** pysher's `run()` is a blocking event loop. A Celery task that blocks indefinitely ties up a worker slot permanently and prevents Celery's retry/backoff logic from working correctly. The ws-consumer's own `while True` loop with exponential backoff is the correct pattern for a persistent WS connection.

**Do this instead:** Keep `ws-consumer` as a standalone Docker service with `restart: unless-stopped`. Surface health via the Redis state keys.

---

## Build Order

```
Phase 1: WS Diagnostics + Logging (independent of Phase 2+)
  ws_prophetx.py:
    - Add ws:connection_state writes in _on_connect, disconnect, and run() retry loop
    - Add ws:last_message_at SETEX in _handle_broadcast_event (any message)
    - Add ws:last_sport_event_at SET + ws:sport_event_count INCR on sport_event branch
    - Add structured log fields: change_type, op, prophetx_event_id, status_value
  health.py:
    - Add GET /api/v1/health/ws endpoint (reads new Redis keys)
    - Modify GET /api/v1/health/workers to add ws_consumer key

  DEPLOY GATE: observe 24-48h in production
  GATE PASS condition: ws:sport_event_count > 0 and ws:last_sport_event_at is set
  GATE FAIL action: escalate to ProphetX — ask whether broadcast channel
    carries sport_event change_type or whether a different channel is needed

Phase 2: DB Schema + Authority Model (requires Phase 1 GATE to pass)
  Alembic migration 007_ws_delivered_at.py:
    - Add ws_delivered_at TIMESTAMPTZ nullable to events table
  ws_prophetx._upsert_event():
    - Set ws_delivered_at = now on both INSERT and UPDATE paths
  poll_prophetx.py:
    - Add WS_AUTHORITY_WINDOW_SECONDS = 10 * 60 constant
    - Add authority window guard before prophetx_status overwrite on existing events

Phase 3: WS Health on Dashboard (requires Phase 1; Phase 2 optional)
  DashboardPage.tsx:
    - Add WsHealthIndicator component
    - Reads /api/v1/health/workers ws_consumer key or /api/v1/health/ws for detail
    - Renders: connection state badge + "last sport_event: X min ago"
  No backend changes needed (endpoint built in Phase 1)

Phase 4: Tech Debt (no dependencies — can run at any time)
  SportsApiClient: align with BaseAPIClient inheritance
  Sports API Redis reads: replace 15 sequential reads with MGET
```

**Phase ordering rationale:**

- Phase 1 before everything: the STATE.md blocker (zero sport_event messages) makes Phases 2 and 3 contingent on confirmed message delivery. Log-first, then build.
- Phase 2 before Phase 3 is a recommendation, not a hard requirement: the dashboard health indicator reads the Phase 1 Redis keys and does not need `ws_delivered_at`. However, shipping the authority model before the UI is the correct order — dashboard shows the model's effect, not just connectivity.
- Phase 4 has no dependencies on any other v1.2 phase and can run at any time, including in parallel with Phase 1.

---

## Integration Points

### ws-consumer ↔ PostgreSQL

| Direction | What | Notes |
|-----------|------|-------|
| ws-consumer writes | `prophetx_status`, `ws_delivered_at`, `status_match`, `last_prophetx_poll` | SyncSessionLocal — synchronous SQLAlchemy session |
| poll_prophetx reads | `ws_delivered_at` — guard check before prophetx_status overwrite | Standard session.get() / select() |
| poll_prophetx writes | Same columns minus `ws_delivered_at`; skips `prophetx_status` when WS recent | Authority window skips the write, still updates metadata |

**Race condition assessment:** ws-consumer is single-threaded (one pysher callback at a time). poll_prophetx is a Celery task. Occasional concurrent DB writes to the same event row are possible but benign: last writer wins for `prophetx_status`, and `ws_delivered_at` accurately records which source was more recent. No distributed lock is needed — this is an operational monitoring tool, not a financial transaction system.

### ws-consumer ↔ Redis

| Key | Writer | Reader | Pattern |
|-----|--------|--------|---------|
| `worker:heartbeat:ws_prophetx` | ws-consumer (every 10s) | FastAPI /health/workers | Existing TTL heartbeat — unchanged |
| `ws:connection_state` | ws-consumer (on state change) | FastAPI /health/ws, /health/workers | New explicit write, no TTL |
| `ws:last_message_at` | ws-consumer (every message) | FastAPI /health/ws | New SETEX 90s TTL |
| `ws:last_sport_event_at` | ws-consumer (sport_event only) | FastAPI /health/ws | New SET, no TTL |
| `ws:sport_event_count` | ws-consumer (sport_event only) | FastAPI /health/ws | New INCR, 8-day TTL |
| `prophet:updates` | ws-consumer + all poll workers | FastAPI SSE stream | Existing pub/sub — unchanged |

### poll_prophetx ↔ ws_prophetx (indirect, via DB)

These two components do not communicate directly. Coordination is mediated entirely through the `events` table:
- ws-consumer writes `ws_delivered_at`
- poll_prophetx reads `ws_delivered_at` to decide whether to overwrite `prophetx_status`

This is the correct integration pattern for independent processes sharing a database. No direct IPC, no new message queue.

### FastAPI ↔ Frontend (WS health display)

The existing `/api/v1/health/workers` polling approach (TanStack Query `refetchInterval: 30_000`) is the correct pattern. The frontend does not need a new WebSocket connection to display WS status — SSE already handles real-time event updates, and health status is a low-frequency (30s) polling concern.

---

## Scaling Considerations

This is an internal operator tool on a single Hetzner CX23 VPS. Scale is not a concern for v1.2. Architectural choices are constrained by simplicity and deployment cost.

| Concern | Current approach | Notes |
|---------|-----------------|-------|
| WS message throughput | Single-threaded pysher consumer; synchronous Redis writes | Sufficient for one broadcast channel at current ProphetX event volume |
| Concurrent DB writes | ws-consumer and poll_prophetx may write same row concurrently | Last-writer-wins is acceptable; no financial risk |
| Health endpoint load | Redis MGET — sub-millisecond; no concern | No change from v1.1 |

---

## Sources

- Direct codebase inspection (2026-03-31):
  - `workers/ws_prophetx.py` — full file
  - `workers/poll_prophetx.py` — full file
  - `workers/update_event_status.py` — full file
  - `workers/poll_critical_check.py` — full file
  - `monitoring/mismatch_detector.py` — full file
  - `api/v1/health.py` — full file
  - `api/v1/stream.py` — full file
  - `models/event.py` — full file
  - `workers/celery_app.py` — full file
  - `docker-compose.yml` — full file
- `.planning/PROJECT.md` — v1.2 goals, constraints, tech debt
- `.planning/STATE.md` — active blockers including zero sport_event messages observed
- Previous architecture research `v1.1` (this file, prior version) — integration patterns validated in production

---

*Architecture research for: ProphetX Market Monitor v1.2 — WebSocket-Primary Status Authority*
*Researched: 2026-03-31*
