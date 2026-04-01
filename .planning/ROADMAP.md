# Roadmap: ProphetX Market Monitor

## Milestones

- ✅ **v1.0 MVP** — Phases 1-3 (shipped 2026-02-26)
- ✅ **v1.1 Stabilization + API Usage** — Phases 4-7 (shipped 2026-03-02)
- 🚧 **v1.2 WebSocket-Primary Status Authority** — Phases 8-11 (in progress)

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

### 🚧 v1.2 WebSocket-Primary Status Authority (In Progress)

**Milestone Goal:** Elevate ProphetX WebSocket messages to the authoritative real-time source for event status, with polling workers serving as reconciliation/validation. Surface WS health on the dashboard.

- [ ] **Phase 8: WS Diagnostics and Instrumentation** - Instrument WS consumer with Redis health keys and fix pre-existing bugs; gate for Phase 9
- [ ] **Phase 9: Status Authority Model** - Add ws_delivered_at column and demote poll_prophetx to reconciliation fallback
- [ ] **Phase 10: WS Health Dashboard** - Surface WS connection health on dashboard with state detail
- [ ] **Phase 11: Tech Debt** - Align SportsApiClient with BaseAPIClient pattern

## Phase Details

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
**Plans:** 1/2 plans executed
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
- [ ] 10-01-PLAN.md — Extend health endpoint with ws_prophetx + WS badge in SystemHealth.tsx
**UI hint**: yes

### Phase 11: Tech Debt
**Goal**: SportsApiClient uses BaseAPIClient consistently, eliminating the architectural inconsistency
**Depends on**: Nothing (independent of Phases 8-10; can run any time)
**Requirements**: DEBT-01
**Success Criteria** (what must be TRUE):
  1. SportsApiClient inherits from BaseAPIClient and uses its shared request/retry/logging machinery
  2. Sports API poll worker behavior is unchanged (same data fetched, same Redis writes, same call counter increments)
  3. No regression in Sports API quota display or call count tracking on the API Usage page
**Plans**: TBD

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
| 8. WS Diagnostics and Instrumentation | v1.2 | 0/1 | Planning | - |
| 9. Status Authority Model | v1.2 | 1/2 | In Progress|  |
| 10. WS Health Dashboard | v1.2 | 0/1 | Planning | - |
| 11. Tech Debt | v1.2 | 0/? | Not started | - |

---
*Full phase details for completed milestones archived in milestones/v1.0-ROADMAP.md and milestones/v1.1-ROADMAP.md*
