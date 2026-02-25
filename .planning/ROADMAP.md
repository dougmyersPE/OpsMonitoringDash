# Roadmap: ProphetX Market Monitor

## Overview

Three phases that build in strict dependency order. Phase 1 assembles the infrastructure skeleton, configures Redis with memory limits, sets up JWT auth, and wires the external API clients — nothing else can start without this. Phase 2 delivers the core engine: the event ID matching layer (the hardest and most critical piece), the polling workers, automated status sync, liquidity monitoring, and the audit log — this is where the tool's primary value is actually produced. Phase 3 makes that value visible and actionable: the SSE-driven real-time dashboard, Slack alerting with deduplication, alert-only mode for safe rollout, and the in-app notification center.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation** - Infrastructure, database, auth, and API clients — everything every subsequent phase depends on
- [ ] **Phase 2: Monitoring Engine** - Event matching, polling workers, auto status sync, liquidity monitoring, and audit log — the core value
- [ ] **Phase 3: Dashboard and Alerts** - Real-time SSE dashboard, Slack alerting with deduplication, alert-only mode, and notification center

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
- [ ] 01-03-PLAN.md — Celery/RedBeat scaffold with 30s stub poll tasks, ProphetX + SportsDataIO API clients, /probe/clients validation endpoint

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
**Plans**: TBD

Plans:
- [ ] 02-01: Event ID matching layer (event_matcher.py, event_id_mappings table, confidence scoring, Redis caching of matches)
- [ ] 02-02: Poll workers (poll_prophetx + poll_sports_data), mismatch detector, liquidity monitor, and distributed lock pattern
- [ ] 02-03: Action workers (update_event_status with idempotent retry, send_alerts stub), audit writer, liquidity threshold config, and manual sync endpoint

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
**Plans**: TBD

Plans:
- [ ] 03-01: React dashboard shell, login page, EventsTable and MarketsTable with SSE integration and mismatch/liquidity highlighting
- [ ] 03-02: Slack alerting worker with deduplication, alert-only mode flag, system health indicator, in-app notification center, and admin config panel
- [ ] 03-03: Production hardening: Nginx SSE config, SSE heartbeat + reconnect banner, Docker Compose production settings, and end-to-end smoke test

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 2/3 | In progress | - |
| 2. Monitoring Engine | 0/3 | Not started | - |
| 3. Dashboard and Alerts | 0/3 | Not started | - |
