# Roadmap: ProphetX Market Monitor

## Overview

### v1.0 (Complete)

Three phases that build in strict dependency order. Phase 1 assembles the infrastructure skeleton, configures Redis with memory limits, sets up JWT auth, and wires the external API clients. Phase 2 delivers the core engine: event ID matching, polling workers, automated status sync, liquidity monitoring, and audit log. Phase 3 makes that value visible and actionable: SSE-driven real-time dashboard, Slack alerting with deduplication, alert-only mode, and in-app notification center.

### v1.1 (Active)

Three phases starting at Phase 4. Phase 4 fixes active false-positive bugs and broken endpoints while laying the Redis counter foundation that all usage display depends on. Phase 5 resolves the RedBeat restart overwrite problem and adds server-side interval enforcement — this backend-only phase must complete before any UI for frequency controls is built. Phase 6 delivers the ApiUsagePage frontend, surfacing call volume, provider quota, 7-day history, projected usage, and per-worker frequency controls to operators.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation** - Infrastructure, database, auth, and API clients — everything every subsequent phase depends on
- [x] **Phase 2: Monitoring Engine** - Event matching, polling workers, auto status sync, liquidity monitoring, and audit log — the core value (completed 2026-02-25)
- [x] **Phase 3: Dashboard and Alerts** - Real-time SSE dashboard, Slack alerting with deduplication, alert-only mode, and notification center (completed 2026-02-26)
- [ ] **Phase 4: Stabilization + Counter Foundation** - Fix false-positive alerts, broken endpoints, and confidence threshold; emit Redis call counters from all workers
- [ ] **Phase 5: Interval Control Backend** - Remove poll intervals from static Beat config, bootstrap from DB on startup, enforce minimum intervals server-side
- [ ] **Phase 6: ApiUsagePage** - Frontend tab showing call volume, provider quota, 7-day chart, projected usage, and per-worker frequency controls

## Phase Details

### Phase 1: Foundation
**Goal**: A running, deployable system where authenticated users can reach a live API backed by PostgreSQL, Redis (with memory limits + RedBeat), and working ProphetX/SportsDataIO API clients
**Depends on**: Nothing (first phase)
**Requirements**: CORE-01, CORE-02, AUTH-01, AUTH-02, AUTH-03
**Success Criteria** (what must be TRUE):
  1. `docker compose up` starts all services (postgres, redis, backend, celery, nginx) without errors and passes a basic health check
  2. Redis is configured with `maxmemory 256mb` and `allkeys-lru` policy; Celery Beat uses RedBeat scheduler (verified: Beat restart produces no duplicate tasks)
  3. A user can log in with email/password and receive a JWT; role-based access is enforced server-side (Admin, Operator, Read-Only roles reject unauthorized requests)
  4. ProphetX API client and SportsDataIO API client successfully authenticate and return raw responses that are logged to confirm actual status enum values
  5. Celery Beat is scheduled (30s interval) but workers do nothing yet beyond logging that they fired
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md — Docker Compose skeleton, PostgreSQL schema, Alembic async migrations, Redis memory config, two SQLAlchemy engines, GET /health endpoint
- [x] 01-02-PLAN.md — JWT authentication (PyJWT + pwdlib), three-role RBAC dependency, system config endpoint, seed admin user
- [x] 01-03-PLAN.md — Celery/RedBeat scaffold with 30s stub poll tasks, ProphetX + SportsDataIO API clients, /probe/clients validation endpoint

### Phase 2: Monitoring Engine
**Goal**: The system continuously polls both APIs, correctly matches ProphetX events to SportsDataIO games, detects mismatches and liquidity breaches, auto-corrects event statuses with idempotent distributed-locked actions, and logs every action to an append-only audit log
**Depends on**: Phase 1
**Requirements**: CORE-03, SYNC-01, SYNC-02, SYNC-03, LIQ-01, LIQ-02, AUDIT-01, AUDIT-02
**Success Criteria** (what must be TRUE):
  1. The event ID matching layer links ProphetX events to SportsDataIO games by sport + teams + start time; only matches with confidence >= 0.90 trigger auto-actions; below-threshold matches are flagged, not acted on
  2. When a real-world game transitions to Live or Ended, ProphetX event status is automatically updated within 30 seconds — and the distributed lock prevents duplicate updates even when two workers detect the same mismatch simultaneously
  3. When a real-world game is postponed or cancelled, the corresponding ProphetX event is flagged on the dashboard with a dashboard indicator and an alert is raised; no automated write action is taken
  4. An operator can manually trigger a status sync for any event from the dashboard (POST endpoint) and the action is executed via the same idempotent action worker path as automated sync
  5. Every automated and manual action is written to the append-only audit log with timestamp, actor, event/market ID, action type, before state, and after state; the application DB user cannot UPDATE or DELETE audit_log rows; the full audit log is viewable with pagination
**Plans**: 3 plans

Plans:
- [x] 02-01-PLAN.md — DB models (Event, Market, EventIDMapping, AuditLog, Notification), Alembic migration 002, and EventMatcher with confidence scoring + Redis cache
- [x] 02-02-PLAN.md — Full poll workers (ProphetX + SportsDataIO), mismatch detector, and liquidity monitor pure functions with unit tests
- [x] 02-03-PLAN.md — update_event_status action worker (distributed lock + idempotent), send_alerts stub, events/markets/audit API endpoints, router wiring

### Phase 3: Dashboard and Alerts
**Goal**: Operators see all events and markets in a real-time dashboard that updates via SSE within 30 seconds of any change, receive Slack alerts with deduplication, can toggle alert-only mode for safe rollout, and have an in-app notification center with read/unread state
**Depends on**: Phase 2
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04, ALERT-01, ALERT-02, ALERT-03, NOTIF-01
**Success Criteria** (what must be TRUE):
  1. The dashboard shows all ProphetX events with their ProphetX status vs. real-world status side by side; mismatches are visually highlighted; the dashboard reflects status changes within 30 seconds via SSE without a page refresh
  2. The dashboard shows all markets with current liquidity vs. configured threshold; below-threshold markets are highlighted; system health shows polling worker status and last-checked timestamps per event
  3. When the SSE connection drops, a visible "Connection lost — reconnecting..." banner appears within 20 seconds; SSE heartbeats keep the Nginx connection alive
  4. Slack receives an alert for each alertable condition (mismatch detected, auto-update success/failure, low liquidity, postponed/cancelled event, API retries exhausted); a maximum of 1 alert per event per condition type fires within any 5-minute window (Redis TTL deduplication)
  5. When alert-only mode is enabled via admin config, the system detects mismatches and sends alerts but makes no write calls to the ProphetX API; toggling this flag requires no code deployment
**Plans**: 5 plans

Plans:
- [x] 03-01-PLAN.md — React SPA scaffold (Vite+shadcn+TanStack Query+Zustand+React Router+axios), Login page, EventsTable with mismatch highlighting, MarketsTable with liquidity highlighting, SystemHealth indicator, SseProvider + useSse hook
- [x] 03-02-PLAN.md — SSE backend endpoint (sse-starlette + Redis pub/sub), verify_token_from_query dep, worker heartbeats, Redis publish in poll workers, Slack alerting (slack-sdk + SETNX dedup), alert_only_mode guard in update_event_status
- [x] 03-03-PLAN.md — Notifications backend API (list + mark-read), NotificationCenter component (bell icon + Sheet panel + unread badge)
- [x] 03-04-PLAN.md — Frontend Dockerfile (multi-stage), frontend/nginx.conf (SPA fallback), docker-compose frontend service, nginx/nginx.conf SSE location block (proxy_buffering off), end-to-end smoke test checkpoint
- [x] 03-05-PLAN.md — Gap closure: send_alerts wiring in update_event_status, SSE reconnect banner timeout fix, notification entity navigation links, last_prophetx_poll field name correction

### Phase 4: Stabilization + Counter Foundation
**Goal**: False-positive mismatch alerts are eliminated, all broken endpoints return correct responses, the confidence threshold is validated against real data, and Redis call counters are emitting from all 5 workers so that one week of real usage data exists before the frontend is built
**Depends on**: Phase 3
**Requirements**: STAB-01, STAB-02, STAB-03, USAGE-01
**Success Criteria** (what must be TRUE):
  1. No false-positive mismatch alerts fire for Sports API when game start times differ by more than the tightened time-distance guard; sports with no active events are skipped without error
  2. `GET /api/v1/health/workers` returns a valid JSON response (200 or appropriate status) instead of 404
  3. Event matching confidence threshold has been tested against a sample of real ProphetX + source data; any tuning applied is documented with before/after match rates
  4. An operator visiting the API Usage tab (or calling `/api/v1/usage`) can see total calls made by each worker today (the counter increments each poll cycle and resets at midnight UTC)
**Plans**: 2 plans

Plans:
- [ ] 04-01-PLAN.md — Fix Sports API + ESPN time guards (use actual game datetime, tighten >12h to >6h), add /health/workers regression test
- [ ] 04-02-PLAN.md — Redis INCRBY call counters in all 5 workers, GET /api/v1/usage endpoint, confidence threshold validation script

### Phase 5: Interval Control Backend
**Goal**: Poll intervals are stored in the database as the authoritative source of truth; Beat never overwrites operator-configured intervals on restart; server enforces minimum intervals so no worker can be configured to abuse an external API
**Depends on**: Phase 4
**Requirements**: FREQ-02, FREQ-03
**Success Criteria** (what must be TRUE):
  1. After an Admin sets a poll interval via PATCH `/api/v1/config/poll_interval_{worker}`, restarting the Beat container does not revert the interval to the code default — the DB-persisted value survives
  2. A PATCH request setting a poll interval below the per-worker minimum returns HTTP 422 with a clear error message; the interval is not applied
**Plans**: TBD

### Phase 6: ApiUsagePage
**Goal**: Operators and Admins can open the API Usage tab and immediately see provider quota status, per-worker call volume today and over the past 7 days, projected monthly burn rate, and — for Admins — live-updating interval controls per worker
**Depends on**: Phase 5
**Requirements**: USAGE-02, USAGE-03, USAGE-04, FREQ-01
**Success Criteria** (what must be TRUE):
  1. Operator can see used/remaining/limit quota for Odds API and Sports API (per sport family) on the API Usage tab; fields show "—" rather than stale or zero values when provider data is unavailable
  2. Operator can see a 7-day bar chart of call volume per worker; the chart reflects accumulated `api_usage_snapshots` data and is not blank on day one
  3. Operator can see projected monthly call volume computed from the current polling rate; the projection updates when an Admin changes a poll interval
  4. Admin can enter a new poll interval for any worker, save it, and the change takes effect within 5 seconds without restarting any container; the interval input is not visible to Operator or Read-Only users
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 3/3 | Complete | 2026-02-25 |
| 2. Monitoring Engine | 3/3 | Complete | 2026-02-25 |
| 3. Dashboard and Alerts | 5/5 | Complete | 2026-02-26 |
| 4. Stabilization + Counter Foundation | 0/2 | Not started | - |
| 5. Interval Control Backend | 0/? | Not started | - |
| 6. ApiUsagePage | 0/? | Not started | - |
