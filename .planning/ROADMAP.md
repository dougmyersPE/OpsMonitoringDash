# Roadmap: ProphetX Market Monitor

## Milestones

- ✅ **v1.0 MVP** — Phases 1-3 (shipped 2026-02-26)
- ✅ **v1.1 Stabilization + API Usage** — Phases 4-7 (shipped 2026-03-02)
- ✅ **v1.2 WebSocket-Primary Status Authority** — Phases 8-11 (shipped 2026-04-01)
- ✅ **v1.3 OpticOdds Tennis Integration** — Phases 12-14 (shipped 2026-04-03)
- 🚧 **v1.4 Source Toggle Completeness** — Phase 15 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-3) — SHIPPED 2026-02-26</summary>

- [x] Phase 1: Foundation (3/3 plans) — completed 2026-02-25
- [x] Phase 2: Monitoring Engine (3/3 plans) — completed 2026-02-25
- [x] Phase 3: Dashboard and Alerts (5/5 plans) — completed 2026-02-26

</details>

<details>
<summary>✅ v1.1 Stabilization + API Usage (Phases 4-7) — SHIPPED 2026-03-02</summary>

- [x] Phase 4: Stabilization + Counter Foundation (2/2 plans) — completed 2026-03-02
- [x] Phase 5: Interval Control Backend (2/2 plans) — completed 2026-03-02
- [x] Phase 6: ApiUsagePage (2/2 plans) — completed 2026-03-02
- [x] Phase 7: Documentation Gap Closure (1/1 plan) — completed 2026-03-02

</details>

<details>
<summary>✅ v1.2 WebSocket-Primary Status Authority (Phases 8-11) — SHIPPED 2026-04-01</summary>

- [x] Phase 8: WS Diagnostics and Instrumentation (1/1 plan) — completed 2026-03-31
- [x] Phase 9: Status Authority Model (2/2 plans) — completed 2026-03-31
- [x] Phase 10: WS Health Dashboard (1/1 plan) — completed 2026-04-01
- [x] Phase 11: Tech Debt (2/2 plans) — completed 2026-04-01

</details>

<details>
<summary>✅ v1.3 OpticOdds Tennis Integration (Phases 12-14) — SHIPPED 2026-04-03</summary>

- [x] Phase 12: Consumer Foundation (3/3 plans) — completed 2026-04-03
- [x] Phase 13: Status Processing and Matching (2/2 plans) — completed 2026-04-03
- [x] Phase 14: Dashboard and Health (1/1 plan) — completed 2026-04-03

</details>

### 🚧 v1.4 Source Toggle Completeness (In Progress)

**Milestone Goal:** All data sources are visible and toggleable on the API Usage page — operators can enable/disable OddsBlaze, ProphetX WS, and OpticOdds alongside the existing Odds API / SDIO / ESPN toggles.

- [ ] **Phase 15: Source Toggle Completeness** - OddsBlaze, OpticOdds, and ProphetX WS wired into the Data Sources toggle section with full enable/disable behavior

## Phase Details

<details>
<summary>✅ v1.0 MVP (Phases 1-3) — SHIPPED 2026-02-26</summary>

### Phase 1: Foundation
**Goal**: Project scaffolding, Docker Compose infrastructure, database, and authentication are in place
**Plans**: 3 plans

Plans:
- [x] 01-01: Infrastructure setup
- [x] 01-02: Database models and migrations
- [x] 01-03: JWT auth and RBAC

### Phase 2: Monitoring Engine
**Goal**: ProphetX events are polled, matched to real-world game states, and mismatches detected
**Plans**: 3 plans

Plans:
- [x] 02-01: ProphetX WS consumer and poll worker
- [x] 02-02: SportsDataIO + ESPN + Odds API poll workers
- [x] 02-03: Mismatch detector and status sync

### Phase 3: Dashboard and Alerts
**Goal**: Operators can see all events, mismatches, and low-liquidity markets in real time with Slack and in-app alerts
**Plans**: 5 plans

Plans:
- [x] 03-01: SSE stream
- [x] 03-02: React dashboard
- [x] 03-03: Slack alerting
- [x] 03-04: In-app notification center
- [x] 03-05: Audit log

</details>

<details>
<summary>✅ v1.1 Stabilization + API Usage (Phases 4-7) — SHIPPED 2026-03-02</summary>

### Phase 4: Stabilization + Counter Foundation
**Goal**: False-positive mismatch alerts eliminated and Redis call counters running on all workers
**Plans**: 2 plans

Plans:
- [x] 04-01: Fix mismatch false-positives (datetime-based threshold)
- [x] 04-02: Redis INCRBY call counters + /api/v1/usage endpoint

### Phase 5: Interval Control Backend
**Goal**: Operators can change poll intervals via the API and changes survive Beat restarts
**Plans**: 2 plans

Plans:
- [x] 05-01: DB-backed intervals + RedBeat bootstrap
- [x] 05-02: Server-enforced minimum intervals (HTTP 422)

### Phase 6: ApiUsagePage
**Goal**: Operators can view API call history, quota status, and adjust intervals from the dashboard
**Plans**: 2 plans

Plans:
- [x] 06-01: API Usage page backend (quota cards, 7-day chart, projections)
- [x] 06-02: API Usage page frontend

### Phase 7: Documentation Gap Closure
**Goal**: All key decisions and constraints documented; no undocumented production behavior
**Plans**: 1 plan

Plans:
- [x] 07-01: Documentation pass

</details>

<details>
<summary>✅ v1.2 WebSocket-Primary Status Authority (Phases 8-11) — SHIPPED 2026-04-01</summary>

### Phase 8: WS Diagnostics and Instrumentation
**Goal**: WS consumer emits observable health signals and pre-existing bugs are fixed before authority logic is built
**Depends on**: Phase 7 (v1.1 complete)
**Requirements**: WSREL-01, WSREL-02
**Success Criteria** (what must be TRUE):
  1. After a WS reconnect, a poll_prophetx reconciliation task fires immediately and is visible in Celery logs
  2. New events created by the WS consumer have a non-NULL status_match value (bug WSREL-02 closed)
  3. Redis keys ws:connection_state, ws:last_message_at, ws:last_sport_event_at, and ws:sport_event_count are present and updating during a live WS session
  4. ws:sport_event_count increments when a sport_event change-type message is received (production gate: confirms ProphetX sends these messages)
**Plans:** 1 plan
Plans:
- [x] 08-01-PLAN.md — Fix WSREL-02 + WSREL-01, add Redis WS diagnostic keys
**Gate**: ws:sport_event_count > 0 must be confirmed in production before Phase 9 begins. If zero after 24-48h covering live game windows, escalate to ProphetX channel investigation.

### Phase 9: Status Authority Model
**Goal**: WS-delivered event status is treated as authoritative; poll_prophetx cannot overwrite it within the authority window
**Depends on**: Phase 8 (production gate must pass)
**Requirements**: AUTH-01, AUTH-02, AUTH-03
**Success Criteria** (what must be TRUE):
  1. Every prophetx_status write records a status_source value of ws, poll, or manual (AUTH-01 column visible in DB)
  2. When WS delivers a status update, poll_prophetx running within 10 minutes does not overwrite prophetx_status (observable via audit log showing no poll source entry after a ws entry)
  3. When WS is authoritative for an event, poll_prophetx still updates teams, scheduled_start, and league metadata (confirming AUTH-03 partial-update path)
  4. A stale REST status arriving after a WS live delivery does not regress the event status (no backward lifecycle transitions visible in the audit log)
**Plans:** 2 plans
Plans:
- [x] 09-01-PLAN.md — Schema + authority helper + config + tests (model columns, migration 008, is_ws_authoritative helper)
- [x] 09-02-PLAN.md — Wire authority logic into workers (ws_prophetx, poll_prophetx, update_event_status)

### Phase 10: WS Health Dashboard
**Goal**: Operators can see WS connection health alongside worker badges on the dashboard
**Depends on**: Phase 8
**Requirements**: WSHLT-01, WSHLT-02, WSHLT-03
**Success Criteria** (what must be TRUE):
  1. GET /api/v1/health/workers response includes a ws_prophetx key with connection status (WSHLT-01)
  2. Dashboard displays a ProphetX WS health badge alongside existing worker badges (WSHLT-02)
  3. Dashboard shows Pusher connection state detail (connected / connecting / reconnecting / unavailable) with the timestamp of the last state transition (WSHLT-03)
  4. WS health badge reflects current state within 30 seconds of a connection change
**Plans:** 1 plan
Plans:
- [x] 10-01-PLAN.md — Extend health endpoint with ws_prophetx + WS badge in SystemHealth.tsx
**UI hint**: yes

### Phase 11: Tech Debt
**Goal**: Sports API integration fully removed — client, worker, DB column, and all references eliminated
**Depends on**: Nothing (independent of Phases 8-10; can run any time)
**Requirements**: DEBT-01
**Success Criteria** (what must be TRUE):
  1. No Sports API client, worker, config, or DB column exists in the codebase
  2. All other poll workers and mismatch detection continue working with remaining sources (Odds API, SDIO, ESPN, OddsBlaze)
  3. API Usage page displays only active sources; no Sports API quota/interval/toggle remains
**Plans:** 2 plans
Plans:
- [x] 11-01-PLAN.md — Remove Sports API backend (client, worker, migration, mismatch, config, tests)
- [x] 11-02-PLAN.md — Remove Sports API frontend + update docs

</details>

<details>
<summary>✅ v1.3 OpticOdds Tennis Integration (Phases 12-14) — SHIPPED 2026-04-03</summary>

### Phase 12: Consumer Foundation
**Goal**: OpticOdds RabbitMQ consumer runs as a standalone Docker service, the queue lifecycle is managed automatically, and the DB schema is ready to receive tennis status data
**Depends on**: Phase 11 (v1.2 complete)
**Requirements**: AMQP-01, AMQP-02, TNNS-01
**Success Criteria** (what must be TRUE):
  1. `docker compose ps` shows `opticodds-consumer` running with `restart: unless-stopped`; service recovers automatically after a forced kill
  2. On startup, the consumer calls the OpticOdds queue start REST endpoint, logs the returned queue name, and caches it in Redis — no manual queue provisioning step needed
  3. The `events` table has an `opticodds_status` nullable VARCHAR(50) column (migration 010 applied); existing rows are unaffected
  4. Consumer reconnects to the RabbitMQ broker with exponential backoff after a simulated connection drop; logs show backoff delays increasing between attempts
**Plans**: 3 plans
Plans:
- [x] 12-01-PLAN.md — Schema + config + pika dependency + opticodds_status migration
- [x] 12-02-PLAN.md — OpticOdds AMQP consumer module + unit tests
- [x] 12-03-PLAN.md — Docker Compose service + health endpoint extension + health tests

### Phase 13: Status Processing and Matching
**Goal**: Incoming OpticOdds tennis messages are matched to ProphetX events, statuses are written to the DB, special statuses trigger Slack alerts, and mismatch detection includes OpticOdds as a source
**Depends on**: Phase 12
**Requirements**: TNNS-02, TNNS-03, AMQP-03, MISM-01
**Success Criteria** (what must be TRUE):
  1. A tennis fixture message from OpticOdds is matched to the correct ProphetX event by competitor names and date window; `opticodds_status` is written to that event row in the DB
  2. `walkover`, `retired`, and `suspended` statuses appear verbatim in the `opticodds_status` column and generate a Slack alert (observable in Slack channel and audit log)
  3. Redis keys `rmq:connection_state` and `rmq:last_message_at` are present and reflect current consumer state (observable via `redis-cli GET`)
  4. For tennis events, `compute_status_match` returns False when `opticodds_status` disagrees with `prophetx_status`; for non-tennis events, a NULL `opticodds_status` does not affect the match result
**Plans**: 2 plans
Plans:
- [x] 13-01-PLAN.md — Mismatch detector extension + all call site updates + source_toggle
- [x] 13-02-PLAN.md — Consumer fuzzy match + DB write + special status alerts + heartbeat wiring + tests

### Phase 14: Dashboard and Health
**Goal**: Operators can see OpticOdds consumer health alongside other worker badges and the OpticOdds status column in the events table
**Depends on**: Phase 13
**Requirements**: DASH-01, DASH-02
**Success Criteria** (what must be TRUE):
  1. GET /api/v1/health/workers includes an `opticodds_consumer` key; SystemHealth component shows an OpticOdds badge with connection state tooltip (connected / reconnecting / disconnected)
  2. The events table on the dashboard shows an `OpticOdds` column; tennis events display their current `opticodds_status` value; non-tennis events show `—`
  3. The OpticOdds health badge updates within 30 seconds of a consumer connection state change
**Plans**: 1 plan
Plans:
- [x] 14-01-PLAN.md — OpticOdds health badge and events table column
**UI hint**: yes

</details>

### Phase 15: Source Toggle Completeness
**Goal**: Operators can enable/disable OddsBlaze, OpticOdds, and ProphetX WS from the Data Sources section on the API Usage page, and each source respects its enabled state at runtime
**Depends on**: Phase 14 (v1.3 complete)
**Requirements**: TOGL-01, TOGL-02, TOGL-03, TOGL-04, TOGL-05, TOGL-06
**Success Criteria** (what must be TRUE):
  1. The Data Sources toggle section on the API Usage page lists OddsBlaze, OpticOdds, and ProphetX WS alongside the existing Odds API / SDIO / ESPN toggles — each showing current enabled state
  2. Toggling OddsBlaze off causes poll_oddsblaze to skip polling on the next scheduled run and clears any stale OddsBlaze data (observable via API Usage page and absence of new OddsBlaze entries in audit log)
  3. Toggling OpticOdds off causes poll_opticodds to skip polling on the next scheduled run and clears stale OpticOdds data (same observable pattern)
  4. Toggling ProphetX WS off causes the WS consumer to skip writing status updates to the DB while keeping the connection alive for health monitoring (observable: health badge stays green, no new ws-sourced audit log entries)
  5. Re-enabling any of the three sources restores normal polling/writing behavior within one poll cycle
**Plans**: TBD
**UI hint**: yes

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.0 | 3/3 | Complete | 2026-02-25 |
| 2. Monitoring Engine | v1.0 | 3/3 | Complete | 2026-02-25 |
| 3. Dashboard and Alerts | v1.0 | 5/5 | Complete | 2026-02-26 |
| 4. Stabilization + Counter Foundation | v1.1 | 2/2 | Complete | 2026-03-02 |
| 5. Interval Control Backend | v1.1 | 2/2 | Complete | 2026-03-02 |
| 6. ApiUsagePage | v1.1 | 2/2 | Complete | 2026-03-02 |
| 7. Documentation Gap Closure | v1.1 | 1/1 | Complete | 2026-03-02 |
| 8. WS Diagnostics and Instrumentation | v1.2 | 1/1 | Complete | 2026-03-31 |
| 9. Status Authority Model | v1.2 | 2/2 | Complete | 2026-03-31 |
| 10. WS Health Dashboard | v1.2 | 1/1 | Complete | 2026-04-01 |
| 11. Tech Debt | v1.2 | 2/2 | Complete | 2026-04-01 |
| 12. Consumer Foundation | v1.3 | 3/3 | Complete | 2026-04-03 |
| 13. Status Processing and Matching | v1.3 | 2/2 | Complete | 2026-04-03 |
| 14. Dashboard and Health | v1.3 | 1/1 | Complete | 2026-04-03 |
| 15. Source Toggle Completeness | v1.4 | 0/? | Not started | - |

---
*Full phase details for completed milestones archived in milestones/v1.0-ROADMAP.md and milestones/v1.1-ROADMAP.md*
