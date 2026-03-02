---
phase: 02-monitoring-engine
plan: "03"
subsystem: api
tags: [celery, redis, fastapi, sqlalchemy, audit-log, distributed-lock, pydantic]

# Dependency graph
requires:
  - phase: 02-monitoring-engine plan 01
    provides: DB models (Event, Market, AuditLog), Alembic migrations, celery_app, mismatch_detector
  - phase: 02-monitoring-engine plan 02
    provides: poll_prophetx, poll_sports_data, mismatch_detector, liquidity_monitor, EventMatcher

provides:
  - Idempotent update_event_status Celery task with 120s Redis distributed lock and audit logging
  - send_alerts stub task (Phase 2 logs; Phase 3 wires Slack)
  - SYNC-01 wiring: poll_sports_data enqueues update_status_task for confirmed mismatches
  - SYNC-02 wiring: poll_sports_data enqueues send_alerts_task for flag-only events
  - LIQ-02 wiring: poll_prophetx enqueues send_alerts_task for liquidity breaches
  - GET /api/v1/events — lists all events with status_match and is_flagged
  - POST /api/v1/events/{id}/sync-status — manual operator sync (operator/admin)
  - GET /api/v1/markets — lists all markets with threshold settings
  - PATCH /api/v1/markets/{id}/config — sets/clears per-market liquidity threshold (admin)
  - GET /api/v1/audit-log — paginated, newest-first, operator/admin access
affects:
  - 03-alerting (will replace send_alerts stub with Slack webhook + deduplication)
  - future phases using audit_log (AUDIT-01/AUDIT-02 complete)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Distributed lock pattern: redis_client.lock(blocking=False) + try/finally release for idempotent workers"
    - "Atomic audit logging: AuditLog INSERT in same session.commit() as state mutation"
    - "RoleEnum usage in API routers: require_role(RoleEnum.operator, RoleEnum.admin) — never raw strings"
    - "Celery task stub pattern: log-only Phase 2, wire real action Phase 3"

key-files:
  created:
    - backend/app/workers/update_event_status.py
    - backend/app/workers/send_alerts.py
    - backend/app/schemas/event.py
    - backend/app/schemas/market.py
    - backend/app/schemas/audit.py
    - backend/app/api/v1/events.py
    - backend/app/api/v1/markets.py
    - backend/app/api/v1/audit.py
    - backend/tests/test_update_event_status.py
  modified:
    - backend/app/workers/poll_prophetx.py
    - backend/app/workers/poll_sports_data.py
    - backend/app/main.py

key-decisions:
  - "ProphetX write endpoint stubbed (log-only) — update_event_status logs intended action but does not call API; wire when endpoint path confirmed (expected: PATCH /mm/update_sport_event_status or similar)"
  - "RoleEnum.readonly used instead of plan's 'read_only' string — enum has no underscore; using enum avoids string drift"
  - "Plan's require_role pattern takes RoleEnum values (not strings) per existing deps.py implementation"

patterns-established:
  - "Distributed lock: redis_client.lock(f'lock:{task}:{entity_id}', timeout=120, blocking=False) + try/finally"
  - "Audit atomicity: session.add(AuditLog(...)) before session.commit() in same session as entity mutation"
  - "API role guards: Depends(require_role(RoleEnum.X, RoleEnum.Y)) in router decorator dependencies list"

requirements-completed: [SYNC-01, SYNC-02, SYNC-03, AUDIT-01, AUDIT-02, LIQ-01]

# Metrics
duration: 6min
completed: 2026-02-25
---

# Phase 2 Plan 03: Action Worker, Alert Wiring, and API Endpoints Summary

**Idempotent status update worker with 120s Redis distributed lock, send_alerts Celery stub, SYNC-01/SYNC-02/LIQ-02 alert wiring, and three FastAPI routers (events, markets, audit-log) closing Phase 2 monitoring loop**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-02-25T23:25:32Z
- **Completed:** 2026-02-25T23:31:00Z
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments

- update_event_status Celery task with Redis distributed lock (120s), idempotency guard, atomic audit log, ProphetX write stub, and retry-on-error (max 3); 4 unit tests all passing
- send_alerts stub task wired into both poll workers: poll_sports_data enqueues for flag-only events (SYNC-02), poll_prophetx enqueues for liquidity breaches (LIQ-02); poll_sports_data also enqueues update_status_task for confirmed mismatches (SYNC-01)
- Three FastAPI routers mounted in main.py: GET /events (readonly+), POST /events/{id}/sync-status (operator+), GET /markets (readonly+), PATCH /markets/{id}/config (admin), GET /audit-log paginated newest-first (operator+)
- All five new routes verified in OpenAPI spec and returning valid JSON via live HTTP tests

## Task Commits

Each task was committed atomically:

1. **Task 1: update_event_status Worker + send_alerts Stub + Alert Wiring** - `fdeee0b` (feat)
2. **Task 2: Events, Markets, and Audit API Endpoints + Router Wiring** - `14043ee` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `backend/app/workers/update_event_status.py` - Idempotent action worker with distributed lock, idempotency guard, audit logging, ProphetX write stub, retry
- `backend/app/workers/send_alerts.py` - Alert stub (logs alert_type/entity_id/message; Phase 3 wires Slack)
- `backend/app/workers/poll_prophetx.py` - Added send_alerts_task.delay() for liquidity breaches (LIQ-02)
- `backend/app/workers/poll_sports_data.py` - Added update_status_task.delay() for confirmed mismatches (SYNC-01) and send_alerts_task.delay() for flag-only events (SYNC-02)
- `backend/app/schemas/event.py` - EventResponse, EventListResponse (from_attributes=True)
- `backend/app/schemas/market.py` - MarketResponse, MarketConfigUpdate, MarketListResponse
- `backend/app/schemas/audit.py` - AuditLogEntry, AuditLogPage
- `backend/app/api/v1/events.py` - GET /events, POST /events/{id}/sync-status
- `backend/app/api/v1/markets.py` - GET /markets, PATCH /markets/{id}/config
- `backend/app/api/v1/audit.py` - GET /audit-log paginated
- `backend/app/main.py` - Include three new routers at /api/v1 prefix
- `backend/tests/test_update_event_status.py` - 4 unit tests (lock, idempotency, success, not-found)

## Decisions Made

- **ProphetX write endpoint stubbed:** update_event_status logs the intended action and sets px_success=True (stub) but does not call the ProphetX API. The write endpoint path is unconfirmed. Wire when confirmed — expected path: `PATCH /mm/update_sport_event_status` or similar. This is the **primary remaining open item going into Phase 3**.
- **RoleEnum.readonly (no underscore):** The plan pseudocode uses `"read_only"` strings but the codebase defines `RoleEnum.readonly`. All three routers use the enum to prevent string drift.
- **Nginx IP cache issue (deviation Rule 3):** After rebuilding and recreating the backend container, nginx held a stale upstream IP. Fixed by restarting nginx — both containers now resolving correctly via Docker DNS.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Nginx stale upstream IP after backend container recreation**
- **Found during:** Task 2 (route verification)
- **Issue:** Backend container was recreated during `docker compose up -d backend`, changing its IP. Nginx still routing to old IP, returning 502.
- **Fix:** Ran `docker compose restart nginx` to reload upstream resolution
- **Files modified:** None (operational fix)
- **Verification:** `curl http://localhost/api/v1/health` returned `{"status":"ok","postgres":"connected","redis":"connected"}`
- **Committed in:** N/A (operational, no file change)

**2. [Rule 1 - Bug] RoleEnum string mismatch: plan used "read_only", enum is "readonly"**
- **Found during:** Task 2 (router implementation)
- **Issue:** Plan pseudocode used string `"read_only"` in require_role() but RoleEnum.readonly has no underscore
- **Fix:** Used `RoleEnum.readonly` from `app.core.constants` in all router dependencies
- **Files modified:** backend/app/api/v1/events.py, backend/app/api/v1/markets.py
- **Verification:** App imports cleanly, routes register correctly
- **Committed in:** 14043ee (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking operational, 1 bug/string mismatch)
**Impact on plan:** Both necessary for correct operation. No scope creep.

## Issues Encountered

- Tests failed initially when run with system Python (missing httpx, no env vars). Used `.venv/bin/python` with env vars loaded from `../.env` — all 4 tests pass.

## Open Items for Phase 3

1. **ProphetX write endpoint (critical):** update_event_status.py line ~70-75 contains TODO. Endpoint path (`PATCH /mm/update_sport_event_status`) is unconfirmed. Once confirmed, replace the stub block with the real HTTP call via ProphetXClient.
2. **send_alerts Slack webhook:** send_alerts.py is a log-only stub. Phase 3 wires Slack webhook + alert deduplication (ALERT-01, ALERT-02).
3. **ProphetX status enum values:** Still UNCONFIRMED in mismatch_detector.py — update after observing `prophetx_status_values_observed` log from live API.

## Next Phase Readiness

Phase 2 monitoring engine is complete. The full 30-second cycle is now operational:
- poll_prophetx fetches + upserts events/markets, detects liquidity breaches, enqueues alerts
- poll_sports_data fetches SDIO games, matches events, detects mismatches, enqueues status updates, enqueues alerts for flag-only events
- update_event_status processes status updates idempotently with distributed locking and full audit trail
- Operators can manually trigger sync via POST /events/{id}/sync-status
- Audit log is append-only and queryable with pagination

Phase 3 (Alerting) can proceed. Primary blockers: ProphetX write endpoint confirmation + Slack webhook credentials.

---
*Phase: 02-monitoring-engine*
*Completed: 2026-02-25*

## Self-Check: PASSED

All files verified present. Both task commits confirmed in git log (fdeee0b, 14043ee).
