# Feature Research

**Domain:** Internal operations monitoring dashboard — prediction market / sports event lifecycle management
**Researched:** 2026-04-01 (v1.3 update; v1.2 research 2026-03-31; v1.1 research 2026-03-01; original v1 research 2026-02-24)
**Confidence:** HIGH (codebase fully inspected; OpticOdds developer docs consulted; patterns grounded in actual code)

---

## v1.3 Feature Scope: OpticOdds Tennis Integration via RabbitMQ

This section covers the new features for the v1.3 milestone. Prior milestone feature landscapes are preserved below.

### Context: What Is Already Built

The system has a well-established pattern for real-world data source integration:

- Each source gets its own column on the `events` table (`sdio_status`, `odds_api_status`, `espn_status`, `oddsblaze_status`)
- Each worker fuzzy-matches events to ProphetX events by sport + team names + scheduled time
- After writing a source column, the worker calls `compute_status_match()` to recompute the aggregate mismatch indicator
- Worker health is tracked via a Redis heartbeat key (`worker:heartbeat:{name}`) with a TTL; health endpoint reads it
- The WS consumer for ProphetX (`ws_prophetx.py`) runs as a standalone Docker service (not a Celery task) — persistent connection, reconnect logic, Redis heartbeat and connection state keys
- The OddsBlaze worker (`poll_oddsblaze.py`) is the closest existing analogue for a third-party status source: fuzzy match by team names + sport, derive status from `is_live` boolean + start time, write `oddsblaze_status`, recompute `status_match`, publish SSE update

**The gap for v1.3:** Tennis matches on ProphetX are monitored, but no OpticOdds status column exists. OpticOdds delivers results via RabbitMQ push (not polling) — a persistent consumer process is needed, modeled after `ws_prophetx.py` rather than the Celery poll workers.

### OpticOdds RabbitMQ Transport: Confirmed Facts

Based on official OpticOdds developer documentation:

- **Host:** `v3-rmq.opticodds.com` (port 5672, vhost `api`)
- **Auth:** API key as username; password from sales rep. Per-API-key credentials.
- **Queue lifecycle:** POST `/v3/copilot/queue/start` returns queue name; consumer then connects to that named queue
- **Results endpoint:** `/copilot/results/queue/[start|stop|status]` (added Oct 2025 — copilot-specific fixture results)
- **Message format:** JSON-encoded byte streams; all messages have `event` type field + `timestamp` + `data`
- **Queue overflow:** If unread messages exceed 10,000, the queue is cleared and deleted; call `/queue/start` to recreate
- **Python library:** `pika` (standard AMQP 0-9-1 client)
- **Message types seen in results stream:** `ping` (heartbeat), `fixture-results` (status + score update)
- **Results data format:** Matches the `/fixtures/results` REST endpoint structure

**Confidence:** MEDIUM — connection parameters and lifecycle confirmed via official docs; exact `fixture-results` message JSON schema not publicly documented at field level; tennis-specific score structure not confirmed beyond generic period model.

### OpticOdds Fixture Status Values (Confirmed)

From the Fixtures Lifecycle documentation:

| OpticOdds Status | Meaning | Maps To (canonical) |
|-----------------|---------|---------------------|
| `unplayed` | Match not yet started | `scheduled` |
| `live` | Match in progress | `inprogress` |
| `half` | Halftime/set break (less relevant for tennis) | `inprogress` |
| `completed` | Match finished | `final` |
| `cancelled` | Match cancelled | flag-only |
| `suspended` | Match temporarily suspended | flag-only |
| `delayed` | Match delayed | flag-only |

**Tennis-specific note:** OpticOdds status values are sport-agnostic. Tennis does not have a `half` status in practice. The `completed` status covers all match-ending scenarios (normal finish, retirement, walkover). Score data uses generic `periods` model where each period = one set.

### Tennis Score Data: What OpticOdds Provides

From fixture schema inspection:

```json
{
  "id": "opticodds-fixture-id",
  "status": "live",
  "is_live": true,
  "start_date": "2026-04-01T14:00:00Z",
  "home_competitors": [{"id": "...", "name": "Djokovic N."}],
  "away_competitors": [{"id": "...", "name": "Alcaraz C."}],
  "scores": {
    "home": {
      "total": 1,
      "periods": {"1": 6, "2": 4, "3": 3}
    },
    "away": {
      "total": 2,
      "periods": {"1": 4, "2": 6, "3": 6}
    }
  }
}
```

Period keys are set numbers (1, 2, 3). The `total` field is sets won. There is no confirmed separate field for current game score within a set (e.g., 40-15) or tiebreak points — this is a polling-resolution limitation, not a fundamental gap. For the v1.3 goal (status monitoring, not score display), this is sufficient.

**Confidence:** MEDIUM — schema structure confirmed via API reference; exact tennis period field semantics inferred from generic model; no official tennis-specific documentation found.

---

### Table Stakes for v1.3 (Users Expect These)

Features the integration is pointless without. Missing any of these means OpticOdds tennis data has no operational effect.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| `opticodds_status` column on `events` table | The entire source column pattern — sdio, odds_api, espn, oddsblaze — all have dedicated columns. OpticOdds must follow this pattern or it cannot participate in `compute_status_match()` | LOW | DB migration adds one nullable `String(50)` column. Follows `oddsblaze_status` exactly. |
| RabbitMQ consumer process that connects, authenticates, and consumes messages | The source delivers push messages — without a persistent consumer, no data arrives. This is the core delivery mechanism | MEDIUM | Standalone Docker service (`rmq-opticodds`), not a Celery task. Models `ws_prophetx.py`: persistent loop, reconnect on failure, exponential backoff. Uses `pika` library (AMQP). |
| Queue lifecycle: start queue via REST before consuming | OpticOdds requires a POST to `/copilot/results/queue/start` to obtain the queue name. Without this step, there is no queue to connect to | LOW | HTTP call at consumer startup (httpx, same pattern as ProphetX token fetch in ws_prophetx.py). Store queue name in Redis or module-level variable for reconnect. |
| Tennis event matching (OpticOdds fixture → ProphetX event) | OpticOdds uses its own fixture IDs. The system must match incoming messages to existing `events` rows by sport + competitor names + start time | MEDIUM | Follows `poll_oddsblaze.py` fuzzy-match pattern: SequenceMatcher on team names, 0.80 threshold, date window. Tennis sport filter ensures only tennis events are matched. |
| Status normalization: OpticOdds → canonical → ProphetX | `unplayed/live/completed/cancelled` must be mapped to `scheduled/inprogress/final/flag-only` to participate in `compute_status_match()` | LOW | Add `_OPTICODDS_CANONICAL` dict in `mismatch_detector.py` following the exact pattern of `_ODDSBLAZE_CANONICAL`. Update `compute_status_match()` signature to accept `opticodds_status`. |
| `compute_status_match()` updated to include OpticOdds source | OpticOdds status must vote in mismatch detection. Without this, the column is written but ignored | LOW | One new source tuple added to the `sources` list in `compute_status_match()`. Also update `compute_is_critical()`. |
| Consumer writes heartbeat to Redis | The health monitoring pattern requires a heartbeat key with TTL. Without this, `/health/workers` cannot report OpticOdds consumer health | LOW | `r.set("worker:heartbeat:rmq_opticodds", "1", ex=90)` written on every message received and every ping. Mirrors `ws_prophetx.py` heartbeat pattern. |
| `/health/workers` endpoint includes OpticOdds consumer | Operators currently see all worker health badges. OpticOdds consumer must appear here when running | LOW | Add `"rmq_opticodds": results[N] is not None` to the health endpoint dict. Single line addition to `health.py`. |
| Dashboard health badge for OpticOdds consumer | The health badge in `SystemHealth.tsx` surfaces when the consumer is dead. Operators need to see this alongside other workers | LOW | Add `"rmq_opticodds"` to the `WORKERS` array in `SystemHealth.tsx`. Same pattern as adding `ws_prophetx` in v1.2. |
| REST API for queue lifecycle control (start/stop/status) | Operators need a way to start and stop the consumer without SSH access. "Queue stuck? Restart it." Must be an API action | MEDIUM | New endpoints: `POST /api/v1/opticodds/queue/start`, `POST /api/v1/opticodds/queue/stop`, `GET /api/v1/opticodds/queue/status`. Store queue state (running/stopped/queue_name) in Redis. Consumer process reads Redis to know if it should reconnect or exit. |
| SSE update published after status write | Every status write must trigger a dashboard refresh via the existing `prophet:updates` Redis channel | LOW | `r.publish("prophet:updates", json.dumps({"type": "event_updated", "entity_id": ...}))` — copy from `poll_oddsblaze.py` exactly. |

### Differentiators for v1.3 (Operational Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| `opticodds_status` column visible as its own source column in events table | Operators can see OpticOdds reporting `live` while ProphetX still shows `not_started` — per-source transparency that distinguishes OpticOdds from all other sources | LOW | Add `opticodds_status` column to `EventsTable.tsx` alongside existing `oddsblaze_status` column. `SourceStatus` component already handles null/unknown values. |
| Queue connection state in Redis with transition timestamp | Beyond alive/dead heartbeat, track whether the AMQP connection is `connected`, `connecting`, `disconnected`. Mirrors the `ws:connection_state` / `ws:connection_state_since` pattern from v1.2 | LOW | Write `rmq:connection_state` and `rmq:connection_state_since` Redis keys on connection events. Read in `/health/workers` response. Dashboard tooltip shows state + duration. |
| Tennis-specific flag-only statuses handled correctly | Tennis has retirement and walkover scenarios where a match "ends" but requires human review. OpticOdds `cancelled` and `suspended` should not auto-advance ProphetX status | LOW | Add `cancelled` and `suspended` to the flag-only check in the consumer's event handler. Set `is_flagged = True` on matched event. Follow `SKIP_STATUSES` / `FLAG_ONLY_STATUSES` pattern from `mismatch_detector.py`. |
| Queue overflow protection: detect and auto-reinitialize | If consumer falls behind (>10K unread messages), OpticOdds deletes the queue. The consumer must detect this (AMQP channel closure with specific error code) and call `/queue/start` again to reinitialize | MEDIUM | In `pika` channel error callback: if error indicates queue deleted, re-call queue start endpoint and reconnect with new queue name. Log the overflow event. This prevents silent data loss without operator intervention. |

### Anti-Features for v1.3 (Do Not Build)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Live tennis score display (sets, games, current game score) | "Show me 6-4, 3-2 (40-15) in the dashboard" | The dashboard is a status monitor, not a score tracker. Adding score display columns creates UI clutter for every sport and requires frontend schema changes. Score data is available in the OpticOdds payload but the existing dashboard has no score concept | Status columns (`live`, `completed`) are the operational signal operators need. Scores are not actionable for ProphetX status management |
| Extend OpticOdds consumer to non-tennis sports | "While we're here, why not add all sports?" | Tennis is the only sport confirmed as the v1.3 scope. Extending to all sports before the consumer is validated adds risk (different sport ID formats, match structure variations) with no defined operator need | Validate tennis integration end-to-end first. Expand sport coverage in v1.4+ once consumer reliability is established |
| ProphetX write action triggered by OpticOdds data alone | "If OpticOdds says live, update ProphetX automatically" | `update_event_status.py` requires multi-source agreement (`status_match = False` triggers a flag, not an immediate write). OpticOdds is one new voice in the consensus — not sufficient alone. Adding a fast-path write from a single source re-introduces the false-positive risk the multi-source model was built to prevent | Let OpticOdds participate in `compute_status_match()`. If OpticOdds + 2 other sources agree the event is live and ProphetX disagrees, the existing mismatch detection + `update_event_status` worker handles the correction automatically |
| Polling fallback for OpticOdds (HTTP /fixtures/results) | "What if RabbitMQ goes down? Add an HTTP fallback" | The system has 4 other polling sources (SDIO, ESPN, Odds API, OddsBlaze) already running as fallbacks. Adding HTTP polling for OpticOdds tennis-only creates a 5th redundancy for one sport. The existing sources already cover tennis (SDIO has `Walkover`/`Retired` statuses; ESPN covers ATP/WTA). OpticOdds polling would also consume API credits on a potentially metered endpoint | Rely on existing polling sources as fallback. If OpticOdds RabbitMQ is down, the consumer health badge alerts operators. |
| RabbitMQ consumer as Celery task | "Keep it consistent with other workers" | AMQP consumers are blocking I/O loops, not periodic tasks. Running `channel.start_consuming()` inside a Celery task would block the Celery worker thread indefinitely. The `ws_prophetx.py` standalone Docker service pattern is the correct architecture for persistent connection consumers | Follow the `ws_prophetx.py` pattern: standalone Python module run as a separate Docker service (`rmq-opticodds`). |
| Per-message audit log entries | "Log every OpticOdds message to the audit table" | Tennis matches generate high message frequency during live play. An audit log entry per message would grow the audit table at a rate that obscures meaningful action entries (status changes, manual overrides). The audit log is an action log, not a message log | Log status changes to audit table (before/after `opticodds_status`) only when the value changes. Structlog already captures every message at debug level. |

---

## Feature Dependencies for v1.3

```
[opticodds_status DB Column + Migration]
    └──required by──> [OpticOdds Status Written to Events Table]
    └──required by──> [compute_status_match() OpticOdds Support]
    └──required by──> [Dashboard opticodds_status Column]

[_OPTICODDS_CANONICAL dict in mismatch_detector.py]
    └──required by──> [compute_status_match() OpticOdds Support]
    └──required by──> [compute_is_critical() OpticOdds Support]

[compute_status_match() Updated Signature]
    └──required by──> [RabbitMQ Consumer Writes status_match After Each Update]

[Queue Lifecycle: POST /copilot/results/queue/start]
    └──required by──> [RabbitMQ Consumer: Knows Queue Name to Connect To]
    └──required by──> [REST API Queue Start Endpoint]

[RabbitMQ Consumer Process (rmq-opticodds Docker service)]
    └──required by──> [All Real-Time OpticOdds Data Delivery]
    └──required by──> [Consumer Heartbeat in Redis]
    └──required by──> [Queue Connection State Redis Keys]

[Redis Heartbeat Key (worker:heartbeat:rmq_opticodds)]
    └──required by──> [/health/workers OpticOdds Entry]
    └──required by──> [Dashboard Health Badge]

[/health/workers API Update]
    └──required by──> [Dashboard Health Badge (SystemHealth.tsx)]

[REST API Queue Lifecycle Endpoints]
    └──enhances──> [Operator Control Without SSH]
    └──required by──> [Queue Overflow Auto-Reinitialize]

[Tennis Event Matching (fuzzy name + sport + date)]
    └──required by──> [opticodds_status Written to Correct Event Row]
    └──depends on──> [events table has tennis sport rows]
```

### Dependency Notes

- **DB migration is the unblocking first step.** `opticodds_status` column must exist before the consumer can write to it, before `compute_status_match()` can be updated, and before the frontend column can be added. Do the migration in Phase 1.
- **`mismatch_detector.py` changes are pure additions.** Adding `_OPTICODDS_CANONICAL` and updating `compute_status_match()` does not change existing behavior — the new parameter is optional and defaults to `None`, so all existing callers are unaffected.
- **Consumer process is independent of Celery.** No Beat schedule changes are needed. The Docker service restarts independently via `restart: unless-stopped`.
- **Frontend column addition is a last step.** Add `opticodds_status` to `EventsTable.tsx` only after the column is populated with real data. Adding an empty column before data flows creates confusion.
- **Queue lifecycle REST API is a table-stakes feature but lower risk than the consumer itself.** The consumer can be built to auto-start via environment variable config (reads queue name from Redis at startup, calls `/queue/start` if not present). The REST API endpoint adds operator control on top of that baseline.

---

## MVP Definition for v1.3

### Launch With (v1.3 Core)

- [ ] DB migration: add `opticodds_status` nullable `String(50)` column to `events` table
- [ ] `_OPTICODDS_CANONICAL` dict in `mismatch_detector.py` mapping `unplayed/live/half/completed` to `scheduled/inprogress/inprogress/final`
- [ ] `compute_status_match()` updated to accept `opticodds_status` parameter (optional, defaults to `None`)
- [ ] `compute_is_critical()` updated to include OpticOdds source
- [ ] `rmq_opticodds.py` consumer worker: connects to RabbitMQ, calls queue/start to get queue name, consumes `fixture-results` messages, fuzzy-matches to events, writes `opticodds_status`, recomputes `status_match`, publishes SSE update, writes heartbeat
- [ ] Redis heartbeat key `worker:heartbeat:rmq_opticodds` written every message + every ping
- [ ] `rmq-opticodds` Docker service added to `docker-compose.yml`
- [ ] `/health/workers` endpoint updated to include `rmq_opticodds`
- [ ] `SystemHealth.tsx` updated to display OpticOdds consumer badge
- [ ] REST API endpoints: `POST /api/v1/opticodds/queue/start`, `POST /api/v1/opticodds/queue/stop`, `GET /api/v1/opticodds/queue/status`

### Add After Core Is Stable (v1.3 Polish)

- [ ] `opticodds_status` column visible in `EventsTable.tsx` — add only after real data is flowing
- [ ] `rmq:connection_state` and `rmq:connection_state_since` Redis keys — connection state detail in health badge tooltip
- [ ] Queue overflow protection: detect channel deletion error → auto-reinitialize queue → reconnect with new queue name

### Defer (v1.4+)

- [ ] OpticOdds coverage for non-tennis sports — validate tennis reliability first
- [ ] Per-sport message rate display — too granular until operational baseline is established

---

## Feature Prioritization Matrix (v1.3)

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| `opticodds_status` DB column | HIGH | LOW (migration only) | P1 — unblocks everything |
| `_OPTICODDS_CANONICAL` + `compute_status_match()` update | HIGH | LOW (pure addition, no behavior change) | P1 — enables mismatch detection |
| RabbitMQ consumer process (`rmq_opticodds.py`) | HIGH | MEDIUM (new consumer, pika, reconnect logic) | P1 — core delivery mechanism |
| Docker service + heartbeat | HIGH | LOW (copy ws_prophetx pattern) | P1 — required for health monitoring |
| `/health/workers` + dashboard badge | HIGH | LOW (1-2 lines each) | P1 — operator visibility |
| Queue lifecycle REST API | HIGH | MEDIUM (new router, Redis state) | P1 — operator control |
| Tennis event fuzzy matching | HIGH | LOW (copy oddsblaze pattern, tennis sport filter) | P1 — required for data to reach correct rows |
| `opticodds_status` dashboard column | MEDIUM | LOW (copy oddsblaze column) | P2 — add after data is flowing |
| Connection state Redis keys | MEDIUM | LOW (copy ws:connection_state pattern) | P2 |
| Queue overflow auto-reinitialize | MEDIUM | MEDIUM (pika error handling) | P2 |
| Tennis flag-only handling (cancelled/suspended) | MEDIUM | LOW (extend FLAG_ONLY check) | P2 |

**Priority key:**
- P1: Required for OpticOdds tennis data to flow and be monitored
- P2: Operational polish and resilience, add after P1 is stable and verified

---

## OpticOdds Consumer: Technical Pattern

### Consumer Lifecycle

```
startup:
  1. Read OPTICODDS_RMQ_* env vars (host, port, vhost, username, password)
  2. Call POST /copilot/results/queue/start → get queue_name
  3. Store queue_name in Redis key rmq:opticodds:queue_name
  4. Connect to RabbitMQ via pika.BlockingConnection
  5. channel.basic_qos(prefetch_count=100)
  6. channel.basic_consume(queue=queue_name, on_message_callback=_on_message, auto_ack=True)
  7. Write rmq:connection_state = "connected"
  8. channel.start_consuming()  # blocks

on_message(ch, method, properties, body):
  1. Parse JSON body → get event_type + data
  2. If event_type == "ping": write heartbeat, log, return
  3. If event_type == "fixture-results": process_fixture_result(data)
  4. Write heartbeat on every message

process_fixture_result(data):
  1. Extract status, is_live, competitors, start_date, sport
  2. If sport != "tennis": skip (tennis-only scope)
  3. Normalize status → canonical via _OPTICODDS_CANONICAL
  4. Fuzzy-match competitors to events table by name + date (0.80 threshold)
  5. If no match: log unmatched, return
  6. Write opticodds_status to matched event
  7. Recompute status_match via compute_status_match()
  8. Publish SSE update
  9. Log structured event with fixture_id, matched_prophetx_id, status

on_failure:
  1. Write rmq:connection_state = "disconnected"
  2. Exponential backoff (1s, 2s, 4s, 8s, cap 60s)
  3. Re-call queue/start (queue may have been deleted on overflow)
  4. Reconnect and resume
```

### Environment Variables Needed

```
OPTICODDS_RMQ_HOST=v3-rmq.opticodds.com
OPTICODDS_RMQ_PORT=5672
OPTICODDS_RMQ_VHOST=api
OPTICODDS_RMQ_USERNAME=<api_key>
OPTICODDS_RMQ_PASSWORD=<from_sales_rep>
OPTICODDS_API_BASE_URL=https://api.opticodds.com  (for queue/start HTTP call)
```

### Queue Start HTTP Call

```python
resp = httpx.post(
    f"{settings.OPTICODDS_API_BASE_URL}/v3/copilot/results/queue/start",
    headers={"X-Api-Key": settings.OPTICODDS_RMQ_USERNAME},
    timeout=15,
)
resp.raise_for_status()
queue_name = resp.json()["queue_name"]
```

**Confidence:** MEDIUM — endpoint path pattern confirmed; exact request/response format inferred from changelog description and REST queue pattern. Must verify against live credentials before implementation.

---

## Sources

- `/Users/doug/OpsMonitoringDash/.planning/PROJECT.md` — v1.3 milestone target features
- `/Users/doug/OpsMonitoringDash/backend/app/workers/ws_prophetx.py` — standalone consumer pattern (full inspection)
- `/Users/doug/OpsMonitoringDash/backend/app/workers/poll_oddsblaze.py` — fuzzy-match + source column pattern (full inspection)
- `/Users/doug/OpsMonitoringDash/backend/app/monitoring/mismatch_detector.py` — canonical status maps, compute_status_match() signature (full inspection)
- `/Users/doug/OpsMonitoringDash/backend/app/models/event.py` — Event schema (full inspection)
- `/Users/doug/OpsMonitoringDash/backend/app/api/v1/health.py` — worker health endpoint pattern (full inspection)
- `/Users/doug/OpsMonitoringDash/docker-compose.yml` — Docker service patterns (full inspection)
- OpticOdds developer documentation — RabbitMQ connection parameters, queue lifecycle, message types: `https://developer.opticodds.com/docs/getting-started` (MEDIUM confidence)
- OpticOdds data ingestion guide — queue message format, pika usage, overflow behavior: `https://developer.opticodds.com/docs/data-ingestion` (MEDIUM confidence)
- OpticOdds fixtures lifecycle — status values (unplayed/live/half/completed/cancelled/suspended/delayed): `https://developer.opticodds.com/reference/fixtures-lifecycle` (MEDIUM confidence)
- OpticOdds fixtures API reference — score structure with periods model: `https://developer.opticodds.com/reference/get_fixtures` (MEDIUM confidence)
- OpticOdds changelog Oct 2025 — copilot-specific results queue endpoints confirmed: `https://developer.opticodds.com/changelog?page=2` (HIGH confidence)

---

*Feature research for: ProphetX Market Monitor v1.3 — OpticOdds Tennis RabbitMQ integration*
*Researched: 2026-04-01*

---

## v1.2 Feature Scope: WebSocket-Primary Status Authority

This section covers the new features for the v1.2 milestone. The v1.1 feature landscape is preserved below.

### Context: What Is Already Built

The WS consumer (`ws_prophetx.py`) is a running Docker service that:
- Maintains a persistent Pusher connection with token refresh and exponential backoff reconnection
- Handles `sport_event` messages (op: create/update/delete) and upserts to the DB
- Writes a Redis heartbeat key (`worker:heartbeat:ws_prophetx`) every 10s and on every Pusher health check
- Publishes SSE updates via `prophet:updates` channel on every event write

The `poll_prophetx` Celery task still runs at its configured interval (5 minutes) and performs the same DB upsert. There is currently no differentiation between a status written by WS vs. a status written by polling — `last_prophetx_poll` is updated by both.

The `update_event_status.py` worker has lifecycle guard logic (no backward regression) but no concept of "which source wrote this status."

**The gap:** When a WS message arrives saying an event is `live`, and 30 seconds later the polling worker also fires and says `not_started` (stale REST response), the poll currently overwrites the WS-delivered status. The WS consumer is working but not yet the authority.

---

### Table Stakes for v1.2 (Users Expect These)

Features that must exist for the WS-primary model to be meaningful. Without these, the WS consumer is just a second writer that competes with polling.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| WS-written status cannot be overwritten by stale polling data | If WS is "primary," a REST poll returning an older status must not win. The whole point of the milestone is authority, not just speed | MEDIUM | Requires `status_source` field (or timestamp comparison) on the Event model so poll_prophetx can detect a WS write is newer and skip the overwrite. The lifecycle guard already prevents backward regression — this extends that to cross-source ordering |
| WS connection health visible on dashboard | Operators currently see 5 worker health badges (ProphetX, SDIO, Odds API, Sports API, ESPN). The WS consumer is a separate Docker service — its health is not shown. When it silently dies, operators don't know | LOW | `worker:heartbeat:ws_prophetx` key already exists. `GET /health/workers` must include it. `SystemHealth.tsx` must display it with a distinct label ("ProphetX WS" vs "ProphetX Poll") |
| poll_prophetx demoted to reconciliation mode | poll_prophetx currently runs every 5 min and writes status unconditionally. After WS is primary, polling should only write status when: (a) the event has no WS-sourced status, or (b) the WS has been silent for longer than a configurable threshold | MEDIUM | Requires either a `status_source` column (`ws` vs `poll`) or a `last_ws_update` timestamp. Poll worker checks: if `last_ws_update` is recent, skip status write |
| WS reconnection gap detection and logging | When Pusher disconnects and reconnects, events that changed during the gap are missed. The system needs to detect that a gap occurred and trigger a reconciliation poll to catch up | MEDIUM | On WS reconnect, log the disconnect timestamp. Compare against `last_prophetx_poll` to identify the gap window. Trigger a poll_prophetx run via `apply_async()` immediately after reconnect |
| End-to-end diagnostic logging for WS messages | Operators (and developers) need to confirm that WS messages are flowing end-to-end: received → decoded → DB written → SSE published. Currently `ws_prophetx.py` has good logging but no way to confirm a specific event's WS message path | LOW | Already mostly exists via structlog events. What's missing: a way to query recent WS activity. Add `status_source` to the audit log or a separate `ws_diagnostics` Redis key with last N messages summary |

### Differentiators for v1.2 (Operational Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| WS connection state displayed with state machine detail | Beyond alive/dead, show the actual Pusher connection state: `connected`, `connecting`, `reconnecting`, `unavailable`. Pusher exposes six states (initialized, connecting, connected, unavailable, failed, disconnected). Surface the current state and last transition time | MEDIUM | pysher's `connection.state` attribute is accessible. Write state transitions to a Redis key `worker:ws_state:ws_prophetx` with timestamp. API endpoint reads it. Dashboard shows "WS: connected (5m)" vs "WS: reconnecting (30s)" |
| Reconciliation run count and last reconciliation timestamp | After WS becomes primary, operators want to know how often the polling fallback was needed. A "reconciliation ran N times today, last at HH:MM" display tells them the WS is healthy (low count) or struggling (high count) | LOW | Increment a Redis counter `ws:reconciliation_runs:{YYYY-MM-DD}` each time poll_prophetx fires in reconciliation mode (gap-triggered). Display on dashboard or API usage tab |
| Events received via WS vs polling breakdown | Show operators what fraction of event updates came from WS vs. polling. If WS is healthy, polling contribution should be near zero for status updates | LOW | Track `status_source` column in Event model. Dashboard summary: "Last 24h: 312 WS updates, 4 poll updates." Validates that WS authority model is working |
| Disconnect duration tracking | When WS goes down, track how long it was disconnected. Surface "longest disconnect in last 7 days" and "total downtime %" metrics | LOW | Store disconnect/reconnect timestamps in Redis as a small ring buffer. Read on demand for dashboard display |

### Anti-Features for v1.2 (Do Not Build)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Full WS message replay / event sourcing buffer | "We want to replay all missed events on reconnect" | Pusher does not provide server-side message replay. Building a custom replay buffer requires persisting all incoming WS messages to Redis or DB — adds complexity for a 5-minute polling fallback that already covers the gap | Use poll_prophetx reconciliation run on reconnect. Gap window at this scale is 5 min max; events already in DB. Replay is unnecessary |
| Message sequence numbering / gap detection at message level | "We need to know exactly which messages were missed" | Pusher's protocol does not expose sequence numbers. You cannot ask Pusher "replay messages after ID 1234." The reconnection gap is handled at the event level (DB state comparison), not the message level | Compare DB state vs. ProphetX REST state in the reconciliation poll. That covers all gaps regardless of cause |
| WS as sole data source (remove polling entirely) | "If WS is primary, polling is waste" | WS connection is single-point-of-failure for a prediction market operator. Polling at 5-min intervals is insurance, not waste. Reconnection windows, token refresh windows (~20 min TTL), and Pusher outages all create gaps | Keep polling at 5-min interval as reconciliation. Operators can increase interval once WS track record is established |
| Client-side (browser) WebSocket health monitoring | "Show WS status with latency and message rate in the dashboard" | The WS consumer is a server-side Python process (pysher), not a browser WebSocket. Browser-level WS monitoring (OpenTelemetry, etc.) doesn't apply. The dashboard is already SSE-based | Expose server-side WS state via existing `/health/workers` endpoint and Redis keys |
| Automated WS failover to polling-only mode | "If WS dies, automatically increase poll frequency" | Adds feedback loop complexity. Poll interval changes require Beat restart (established pattern from v1.1). Risk of oscillation if WS flaps | Alert operators when WS has been down > N minutes. Let them decide if polling interval adjustment is needed |

---

## Feature Dependencies for v1.2

```
[status_source Field on Event Model]
    └──required by──> [WS Cannot Be Overwritten by Stale Poll]
    └──required by──> [poll_prophetx Reconciliation Mode]
    └──required by──> [WS vs Poll Update Breakdown Display]
    └──required by──> [Audit Log Source Attribution]

[WS Reconnect Gap Detection]
    └──required by──> [Reconciliation Poll Trigger on Reconnect]
    └──required by──> [Disconnect Duration Tracking]

[GET /health/workers includes ws_prophetx]
    └──required by──> [WS Connection Health Badge on Dashboard]
    └──enhances──> [WS Connection State Detail (state machine)]

[worker:ws_state:ws_prophetx Redis Key]
    └──required by──> [WS Connection State Detail Display]
    └──required by──> [Disconnect Duration Tracking]

[Existing worker:heartbeat:ws_prophetx]
    └──already provides──> [Basic alive/dead detection]
    └──enhances──> [WS Connection Health Badge] (just need to surface it in API + UI)

[poll_prophetx Reconciliation Mode]
    └──enhances──> [Reconciliation Run Count Display]
    └──conflicts──> [poll_prophetx Unconditional Status Write] (must change existing behavior)
```

### Dependency Notes

- **`status_source` is the load-bearing schema change.** Everything in the WS-primary model — preventing poll overwrites, tracking source attribution, driving reconciliation decisions — flows from knowing whether the current `prophetx_status` came from WS or polling. This is the v1.2 foundation, analogous to how Redis counters were the v1.1 foundation.
- **Health badge requires only two changes:** add `ws_prophetx` to the health endpoint response dict and add it to the `WORKERS` array in `SystemHealth.tsx`. The Redis key already exists.
- **Reconciliation mode change is a behavior change to existing code.** `poll_prophetx.py` must be modified to check `status_source` and `last_ws_update` before overwriting. This is the riskiest change — requires careful testing to ensure it doesn't create silent status stagnation if WS stops working.
- **Reconnect gap detection requires state in the WS consumer.** `ws_prophetx.py` must write a disconnect timestamp to Redis when it disconnects and read it on reconnect to calculate the gap.

---

## MVP Definition for v1.2

### Launch With (v1.2 Core)

- [ ] `status_source` column on `events` table — values: `ws`, `poll`, `manual`. Foundation for authority model. DB migration required.
- [ ] WS consumer writes `status_source = 'ws'` on every event upsert.
- [ ] `poll_prophetx` respects `status_source`: if `status_source == 'ws'` and `last_prophetx_poll` (from WS) is recent (< reconciliation threshold, e.g., 10 min), skip status write. Write only metadata updates (teams, scheduled_start).
- [ ] `GET /health/workers` includes `ws_prophetx` key (the Redis key already exists — just wire it up).
- [ ] `SystemHealth.tsx` displays "WS" badge alongside existing worker badges.
- [ ] WS reconnect gap detection: on reconnect, log gap duration and trigger immediate poll_prophetx run via `apply_async()`.
- [ ] End-to-end diagnostic confirmation: verify structlog entries flow from WS receive → DB write → SSE publish for a known event.

### Add After Core Is Stable (v1.2 Polish)

- [ ] `worker:ws_state:ws_prophetx` Redis key with Pusher connection state + last transition timestamp — display on dashboard as "WS: connected (12m ago)."
- [ ] Reconciliation run counter in Redis — displayed on API Usage tab or dashboard.
- [ ] Source attribution in audit log — `before_state` and `after_state` include `status_source` field.

### Defer (v1.3+)

- [ ] WS vs. polling update breakdown chart — useful operational metric once WS has track record.
- [ ] Disconnect duration history / uptime % — requires ring buffer; worth adding after data accumulates.
- [ ] Per-sport WS message rate — too granular for current operational needs.

---

## Feature Prioritization Matrix (v1.2)

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| `status_source` DB column | HIGH | LOW (migration + 2 write sites) | P1 — foundation |
| poll_prophetx reconciliation mode | HIGH | MEDIUM (behavior change + testing) | P1 — core authority model |
| WS health badge on dashboard | HIGH | LOW (API line + UI line) | P1 — operator visibility |
| WS reconnect gap detection + reconciliation trigger | HIGH | MEDIUM (state tracking in WS consumer) | P1 — prevents missed events |
| End-to-end diagnostic verification | MEDIUM | LOW (inspection + log confirmation) | P1 — confidence building |
| WS connection state detail (beyond alive/dead) | MEDIUM | MEDIUM (state machine + Redis + UI) | P2 |
| Reconciliation run counter + display | LOW | LOW | P2 |
| Source attribution in audit log | MEDIUM | LOW (add field) | P2 |

**Priority key:**
- P1: Required for WS-primary model to be real (not just cosmetic)
- P2: Operational visibility enhancements, add after P1 is stable

---

## WS-Primary Authority Model: Technical Pattern

Based on codebase inspection and domain research, the authority model works as follows:

### Status Write Decision (poll_prophetx)

```
on each poll cycle, for each event:
  if event.status_source == 'ws' and event.last_prophetx_poll is recent:
      skip status write (WS is authoritative)
      update metadata only (teams, scheduled_start, league)
  else:
      write status as today (poll is filling the gap)
      set status_source = 'poll'
```

"Recent" threshold: if `last_prophetx_poll` (the WS write timestamp) is within `RECONCILIATION_THRESHOLD` (suggested default: 10 minutes = 2x the poll interval), treat WS as fresh. If older, the WS has likely missed updates and polling should catch up.

### Reconnect Gap Recovery Pattern

```
on ws_prophetx reconnect:
  gap_seconds = now - disconnect_timestamp (from Redis)
  log gap duration
  if gap_seconds > POLL_INTERVAL_PROPHETX:
      trigger poll_prophetx.run.apply_async()
      increment ws:reconciliation_runs:{date}
  clear disconnect_timestamp
```

### Why Not Sequence Numbers

Pusher does not expose message sequence numbers or server-side replay. The reconnection recovery must be event-state-based (compare DB state to REST API state), not message-log-based. This is the correct approach for this architecture. (MEDIUM confidence — confirmed via Pusher protocol docs; pysher library inspection.)

---

## Sources

- `/Users/doug/OpsMonitoringDash/backend/app/workers/ws_prophetx.py` — existing WS consumer (full inspection)
- `/Users/doug/OpsMonitoringDash/backend/app/workers/poll_prophetx.py` — existing poll worker
- `/Users/doug/OpsMonitoringDash/backend/app/workers/update_event_status.py` — lifecycle guard pattern
- `/Users/doug/OpsMonitoringDash/backend/app/models/event.py` — current Event schema
- `/Users/doug/OpsMonitoringDash/frontend/src/components/SystemHealth.tsx` — worker health display
- `/Users/doug/OpsMonitoringDash/backend/app/api/v1/health.py` — health endpoint (missing ws_prophetx)
- Pusher Channels connection states documentation (`https://pusher.com/docs/channels/using_channels/connection/`) — six states confirmed (HIGH confidence)
- WebSocket reconnection state sync patterns (`https://websocket.org/guides/reconnection/`) — sequence numbers, replay, external persistence (MEDIUM confidence — patterns confirmed; Pusher-specific limitation confirmed via Pusher protocol docs)
- WebSocket connection health monitoring patterns (`https://oneuptime.com/blog/post/2026-01-24-websocket-connection-health-monitoring/view`) — uptime_seconds, last_ping_received, connection_status metrics (MEDIUM confidence)

---

*Feature research for: ProphetX Market Monitor v1.2 — WebSocket-primary status authority*
*Researched: 2026-03-31*

---

## v1.1 Feature Scope: API Usage Monitoring + Stabilization (Reference)

*(Preserved from 2026-03-01 research. Already shipped.)*

---

### Table Stakes for v1.1 (Users Expect These)

These are required for the API Usage tab to be genuinely useful. Without them, the tab delivers incomplete information that operators cannot act on.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Per-provider quota display (used / limit / remaining) | Operators configuring poll intervals need to know current standing against monthly limits before adjusting — a "remaining calls" number is the minimum viable signal | MEDIUM | Odds API: read `x-requests-remaining` + `x-requests-used` headers on every poll response. Sports API (api-sports.io): read `x-ratelimit-requests-remaining` + `x-ratelimit-requests-limit` headers. SDIO: no documented quota — display "unlimited" per official docs. ESPN: no documented quota — display "N/A" |
| Internal call counter per worker | Odds API and Sports API headers only reflect the provider's counter — they don't tell you which worker made which calls. An internal Redis `INCR` counter per worker per day gives attribution and lets you see who's consuming quota fastest | LOW | Redis key pattern: `api_calls:{worker}:{YYYY-MM-DD}`. Increment on each outbound call inside the client. Reset naturally when date rolls over (key TTL = 48h). No DB schema change needed |
| Total monthly call volume across all workers | Operators need one number: "how many calls have we made this month across all sources?" to assess whether usage is on track | LOW | Aggregate Redis daily counters into a rolling monthly total. Computed at read time — no separate counter needed |
| Per-worker poll frequency control (UI) | The single biggest lever for controlling API costs. Currently requires `.env` edit + container rebuild — operators cannot adjust without engineering involvement | HIGH | Requires: (1) DB-backed schedule table (sqlalchemy-celery-beat or equivalent), (2) API endpoint to read/write intervals, (3) UI controls in the API Usage tab, (4) Beat scheduler restart or dynamic interval update. This is the most complex feature in v1.1 |
| Projected monthly call volume at current rate | If you're 10 days in and have used 40% of quota, you'll exceed limits. Operators need a projection, not just current consumption | LOW | `(calls_this_month / days_elapsed) * days_in_month`. Computed in the API layer — no storage needed |

### Differentiators (Operational Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Quota alert threshold (configurable % warning) | "Alert me when Odds API is at 80% of monthly quota" prevents surprise quota exhaustion mid-month | LOW | Store `api_usage_alert_threshold` in SystemConfig (default 80%). Check on each provider poll response. Fire Slack alert via existing deduplication system |
| Per-worker pause toggle | When approaching quota limits, operators want to pause the highest-consumption workers without stopping everything | MEDIUM | Celery Beat dynamic schedule: set interval to 0 or use a `worker_enabled` flag checked at task start. Simpler than full interval control — just a boolean |
| Provider status badge (last poll success/fail) | Was the last Odds API call successful? Did it return quota headers? A green/red indicator next to each provider's quota tells operators whether the displayed numbers are current | LOW | Already tracked in worker heartbeat keys (`worker:heartbeat:{name}`). Extend heartbeat payload to include last HTTP status code |
| Call cost breakdown by sport key | For Odds API: each sport key is 1 credit. With 5 sport keys at 10-min intervals, knowing which sport keys consume the most helps operators decide which to disable off-season | MEDIUM | Extend Redis counter to include sport key dimension: `api_calls:odds_api:{sport_key}:{YYYY-MM-DD}`. Requires updating the Odds API client to pass sport key to counter |

### Anti-Features (Do Not Build)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Dynamic interval updates without container restart | Operators want "set it and live" frequency control | RedBeat stores schedule state in Redis and reads it at Beat startup. Changing intervals in DB while Beat is running requires either Beat restart or a custom scheduler loop. Django-celery-beat solves this but requires significant scheduler replacement — not appropriate for a one-container Beat setup | Require a Beat restart after interval change (one `docker compose restart beat` command); document this clearly in the UI tooltip. Acceptable operational cost vs. scheduler complexity |
| Real-time call-per-second rate display | Monitoring dashboards show "requests per second" | This system has at most 6 concurrent workers and ~30s poll intervals — never more than ~1 req/sec average. Rate display adds complexity for a metric that will always show "0.0" or "0.1" | Show calls per cycle and calls per day instead — operationally meaningful for this system |
| Full API call log (every request) | "Show me every API call made" | PostgreSQL table growing at 30 rows/minute = 1.3M rows/month. Requires log rotation, indexes, and a query interface. No actionable use case beyond what Redis counters already provide | Keep Redis counters (daily granularity). Add structured log lines already emitted by workers. Archive logs via Docker log rotation |
| Automated quota throttling (auto-reduce interval when near limit) | Sounds smart — system adjusts itself | Requires feedback loop logic that could interact badly with Beat's scheduling state. Risk: system oscillates intervals every poll cycle as quota approaches threshold | Alert at 80% threshold; let operators make the interval adjustment manually |

---

## Feature Dependencies for v1.1

```
[Redis API Call Counters]
    └──required by──> [Per-Worker Internal Call Display]
    └──required by──> [Total Monthly Volume]
    └──required by──> [Projected Monthly Volume]
    └──required by──> [Call Cost by Sport Key]

[Provider Response Header Capture]
    └──required by──> [Per-Provider Quota Display (used/limit/remaining)]
    └──required by──> [Quota Alert at Threshold]
    (requires BaseAPIClient to capture and store headers from Odds API + Sports API responses)

[Per-Provider Quota Display] ──enhances──> [Projected Monthly Volume]
    (provider quota remaining = ground truth; internal counter = attribution)

[DB-Backed Schedule Table]
    └──required by──> [Per-Worker Poll Frequency Control (UI)]
    └──required by──> [Per-Worker Pause Toggle]
    (replaces hardcoded beat_schedule in celery_app.py)

[Per-Worker Poll Frequency Control]
    └──requires──> [Beat Restart on Interval Change]
    (RedBeat re-reads schedule from Redis on startup; interval changes take effect after restart)

[Existing Worker Heartbeat Keys]
    └──enhances──> [Provider Status Badge]
    (extend heartbeat to include last_http_status)

[Existing Slack Alerting + Deduplication]
    └──required by──> [Quota Alert Threshold]
    (reuses existing send_alerts.py + Redis TTL dedup pattern)
```

### Dependency Notes

- **Redis counters before any display feature**: All call-count display features depend on the counters being incremented correctly in the client layer. The counter increment must be in `BaseAPIClient._get()` or in each specific client's methods — not in the workers — so all clients benefit automatically.
- **Provider headers require BaseAPIClient refactor**: Currently `BaseAPIClient._get()` discards the `Response` object and returns only `response.json()`. To capture `x-requests-remaining` headers, `_get()` must return the raw `Response` or a tuple `(data, headers)`. This is a breaking change to every client. Plan the refactor carefully.
- **Beat schedule DB migration is a prerequisite for interval controls**: Until the beat schedule is stored in a table rather than hardcoded in `celery_app.py`, no UI can change intervals at runtime.

---

## MVP Definition for v1.1

### Launch With (v1.1)

- [x] Redis `INCR` counter per worker per day in `BaseAPIClient` — every outbound call counted. Foundation for everything else.
- [x] Response header capture in Odds API client — capture and store `x-requests-remaining`, `x-requests-used`, `x-requests-last` from every Odds API response into Redis key `api_quota:odds_api`.
- [x] Response header capture in Sports API client — capture and store `x-ratelimit-requests-remaining`, `x-ratelimit-requests-limit` from every Sports API response into Redis key `api_quota:sports_api`.
- [x] API Usage tab in frontend — shows per-provider quota (used/remaining/limit), internal call counts by worker, projected monthly total.
- [x] DB-backed poll intervals — migrate `beat_schedule` intervals from hardcoded `celery_app.py` to a `worker_schedule` table in PostgreSQL. Read at Beat startup. Admin can update via API.
- [x] UI controls for poll intervals — slider or number input per worker in the API Usage tab. Admin-only. Displays "requires Beat restart to take effect" warning.

### Defer (v1.2+)

- [ ] Per-sport-key call breakdown — useful but adds counter dimension complexity. Defer until operators request sport-level attribution.
- [ ] Quota alert Slack notification — useful but not blocking. The quota display itself prevents surprise exhaustion for operators watching the dashboard.
- [ ] Per-worker pause toggle — interval control covers the use case (set to very long interval = effectively paused).

---

## Feature Prioritization Matrix (v1.1)

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Redis call counters (internal) | HIGH | LOW | P1 — foundation for all display |
| Odds API quota header capture | HIGH | MEDIUM | P1 — requires BaseAPIClient refactor |
| Sports API quota header capture | HIGH | MEDIUM | P1 — same refactor |
| API Usage tab UI (read-only) | HIGH | MEDIUM | P1 — the visible deliverable |
| DB-backed poll intervals | HIGH | HIGH | P1 — enables operator control |
| UI poll interval controls | HIGH | MEDIUM | P1 — depends on DB-backed intervals |
| Projected monthly volume display | MEDIUM | LOW | P1 — computed at read time, cheap |
| Quota alert Slack notification | MEDIUM | LOW | P2 — reuses existing alerting |
| Per-sport-key call breakdown | LOW | MEDIUM | P2 |
| Per-worker pause toggle | MEDIUM | MEDIUM | P2 |

**Priority key:**
- P1: Must have for v1.1 launch
- P2: Add after core usage tab is working

---

## Call Volume Reference (As-Built)

Actual call volume based on production code and current intervals:

| Worker | Interval | Calls/Cycle | Calls/Hour | Calls/Day | Calls/Month | Quota |
|--------|----------|-------------|------------|-----------|-------------|-------|
| poll_sports_data | 30s | 18+ (6 sports × 3 dates, non-soccer) | 2,160 | 51,840 | ~1.6M | SDIO: unlimited |
| poll_odds_api | 600s | ~5 (active sport keys) | 30 | 720 | ~21,600 | 500/month (free tier) |
| poll_sports_api | 1800s | ~15 (5 sports × 3 dates) | 30 | 720 | ~21,600 | 100/day (free tier) |
| poll_espn | 600s | ~5 (sports × date) | 30 | 720 | ~21,600 | No published limit |
| poll_prophetx | 300s | ~1-5 (pagination) | 12-60 | 288-1,440 | ~9K-43K | ProphetX: unconfirmed |

**Critical finding**: Odds API free tier is 500 calls/month. At current 600s interval with ~5 sport keys, the system burns ~21,600 calls/month — 43x the free tier. The existing 600s interval was set to conserve usage but is not conservative enough for the free tier. The API Usage tab will make this visible; operators need interval controls to manage it.

**Sports API (api-sports.io)**: Free tier is 100 calls/day. Current 1800s interval generates ~720 calls/day — 7x the free tier. Same issue as Odds API.

---

## Dynamic Interval Control: Technical Options

The "per-worker poll frequency control" feature has three implementation paths. Listed in order of implementation effort:

### Option A: Restart-Required DB Intervals (RECOMMENDED)
Store intervals in a `worker_schedule` PostgreSQL table. `celery_app.py` reads from DB on startup instead of hardcoded dict. Admin changes interval via UI → DB update → operator runs `docker compose restart beat` → new interval takes effect.

**Effort:** Medium — DB migration + API endpoint + UI + Beat startup change
**Complexity:** Low — no scheduler replacement, no Redis state management
**Beat restart:** Required after every change (acceptable — documented in UI tooltip)
**Confidence:** HIGH — established pattern; FastAPI + SQLAlchemy already in place

### Option B: sqlalchemy-celery-beat Library
Replace RedBeat with `sqlalchemy-celery-beat`. Stores schedule in PostgreSQL. Beat polls the DB for schedule changes at configurable intervals. No restart required for interval changes.

**Effort:** High — replaces the Beat scheduler (RedBeat → sqlalchemy-celery-beat); risks disrupting existing RedBeat lock behavior
**Complexity:** High — `redbeat_lock_timeout=900` behavior must be replicated; `LockNotOwnedError` risk from PITFALLS.md returns
**Beat restart:** Not required
**Confidence:** MEDIUM — library exists and works but scheduler replacement in production carries risk

### Option C: Redis-Backed Dynamic Schedule (Custom)
Keep RedBeat. Add a Redis key `worker:interval:{name}` that workers check at task start. If interval has changed since last run, tasks self-reschedule via `apply_async(countdown=new_interval)`.

**Effort:** High — requires each worker to implement self-scheduling logic; bypasses Beat entirely
**Complexity:** High — Beat and worker self-scheduling can drift; hard to debug
**Confidence:** LOW — non-standard pattern; high risk of scheduling inconsistencies

**Recommendation: Option A.** Restart-required interval control is entirely adequate for an internal ops tool where interval changes happen once every few weeks. The added complexity of Option B or C is not justified by the use case.

---

## v1 Feature Landscape (Reference — Already Built)

### Table Stakes (Completed in v1)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Real-time event status table | Core purpose — operators must see all ProphetX events and their current ProphetX vs. real-world status at a glance | MEDIUM | SSE stream from Redis pub/sub; dual-status columns with mismatch indicator |
| Real-time market liquidity table | Core purpose — operators must see all markets with current liquidity vs. configured threshold | MEDIUM | Same SSE stream; highlight below-threshold markets |
| Automated status sync (Upcoming → Live → Ended) | The system's primary value — removing manual status correction | HIGH | Requires event ID matching layer; Celery worker; ProphetX write API |
| Postponed/cancelled event flagging | Without this, bettors remain in open positions on dead events — high operational risk | MEDIUM | Detection only in v1; alert + dashboard highlight |
| Status mismatch highlighting | Operators must be able to spot problems instantly without reading every row | LOW | CSS color coding: amber = mismatch detected, red = action failed |
| Slack webhook alerting | Team must know about issues even when not watching the dashboard | LOW | Slack Block Kit messages; one webhook URL in config |
| In-app notification center | Audit trail of what the system has done; read/unread state | MEDIUM | Bell icon + panel; notifications link to relevant event/market |
| Configurable liquidity thresholds | Each market has different liquidity needs; global default plus per-market override | LOW | Admin-only; stored in SystemConfig and Market tables |
| Audit log (append-only) | Compliance, debugging, accountability | MEDIUM | PostgreSQL append-only table; no DELETE; before/after state in JSON |
| JWT authentication | Multi-user tool requires authentication | LOW | Standard FastAPI/JWT pattern; email + password |
| Role-based access control (Admin, Operator, Read-Only) | Multiple team members with different permission levels | MEDIUM | Three roles; server-side enforcement |
| Manual status sync trigger | Operators need an override for cases where automation fails | LOW | POST /events/{id}/sync-status; Operator + Admin only |
| "Last checked" timestamps | Operators must know data freshness | LOW | Display last_prophetx_poll and last_real_world_poll per row |
| System health indicator | If polling workers are down, operators must know immediately | MEDIUM | Worker heartbeat via Redis keys; banner/badge |
| Auto-retry with exponential backoff | ProphetX API failures must not silently drop actions | MEDIUM | Celery retry with 1s/2s/4s backoff |
| Alert deduplication | Without this, one stuck event generates 120 Slack alerts/hour | MEDIUM | Redis TTL key per event + condition type |
| Alert-only mode flag | Required for safe production rollout | LOW | Single config flag: auto_updates_enabled |

### Differentiators (Completed in v1)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Event ID matching layer with confidence scoring | Bridges ProphetX and SportsDataIO ID spaces; gates auto-actions at ≥0.90 confidence | HIGH | fuzzy string matching + time window; stored as event_id_mappings table |
| Multi-source status confirmation | 4 real-world sources (SDIO, Odds API, Sports API, ESPN) reduce false positive risk | HIGH | Each worker updates its own source column; status_match is True only when ProphetX agrees with real-world consensus |
| 5 supplementary data source workers | SDIO + Odds API + Sports API + ESPN + ProphetX WS — redundancy across all major sports data providers | HIGH | Each source is a separate Celery worker with independent failure isolation |

### Anti-Features (Deferred from v1)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Automated liquidity top-up | Operators want hands-free liquidity management | ProphetX API liquidity mechanics unconfirmed; financial risk | Alert-only; add after API mechanics confirmed and 2+ stable weeks |
| Email/SMS alerting | Some team members prefer email | Adds integration complexity for marginal gain over Slack | Slack + in-app for v1 |
| Historical analytics charts | "It would be great to see trends" | Requires time-series aggregation + chart library — significant scope | Audit log covers v1 debugging needs |
| Automated quota throttling | System adjusts its own poll intervals near quota limit | Risk of oscillation; complex feedback loop | Alert at 80% threshold; manual adjustment |

---

## Sources

- `/Users/doug/OpsMonitoringDash/.planning/PROJECT.md` — v1.2 milestone target features
- `/Users/doug/OpsMonitoringDash/backend/app/workers/ws_prophetx.py` — full WS consumer inspection
- `/Users/doug/OpsMonitoringDash/backend/app/api/v1/health.py` — worker health endpoint (ws_prophetx missing)
- `/Users/doug/OpsMonitoringDash/frontend/src/components/SystemHealth.tsx` — worker health display
- Pusher Channels connection documentation (`https://pusher.com/docs/channels/using_channels/connection/`) — six connection states (HIGH confidence)
- WebSocket reconnection state sync guide (`https://websocket.org/guides/reconnection/`) — sequence numbers, external persistence patterns (MEDIUM confidence)
- WebSocket connection health monitoring (`https://oneuptime.com/blog/post/2026-01-24-websocket-connection-health-monitoring/view`) — dashboard metrics patterns (MEDIUM confidence)
- The Odds API v4 documentation — quota headers confirmed (HIGH confidence, from v1.1 research)
- api-football.com rate limit documentation — quota headers confirmed (HIGH confidence, from v1.1 research)

---
*Feature research for: ProphetX Market Monitor v1.2 — WebSocket-primary status authority + v1.1/v1 reference*
*Researched: 2026-03-31*
