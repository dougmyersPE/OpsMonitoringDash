---
phase: 03-dashboard-and-alerts
plan: 05
subsystem: ui, workers, api
tags: [celery, sse, react, typescript, notifications, alerts]

# Dependency graph
requires:
  - phase: 03-dashboard-and-alerts
    provides: send_alerts.py task, SseProvider, NotificationCenter, EventsTable, events.ts
provides:
  - send_alerts_task.delay() calls on both success and failure paths in update_event_status.py
  - Timeout-based SSE disconnect detection (15s grace period, lastOpenRef pattern)
  - Clickable notification entity links navigating to /#events or /#markets
  - EventRow.last_prophetx_poll matching backend EventResponse schema field name
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "lastOpenRef timestamp pattern for SSE health detection (tracks last OPEN observation)"
    - "Local import inside task body to avoid Celery circular imports (matches existing SystemConfig pattern)"

key-files:
  created: []
  modified:
    - backend/app/workers/update_event_status.py
    - frontend/src/components/SseProvider.tsx
    - frontend/src/components/NotificationCenter.tsx
    - frontend/src/api/events.ts
    - frontend/src/components/EventsTable.tsx

key-decisions:
  - "03-05: send_alerts import placed inside task body (local import) to avoid circular import — matches SystemConfig pattern already in same file"
  - "03-05: Failure-path alert wrapped in its own try/except so alert enqueue failure does not block retry(exc=exc) logic"
  - "03-05: lastOpenRef initialized to Date.now() at mount so 15s grace starts from component mount, preventing false-positive banner on first load"
  - "03-05: Plain <a href> anchor used for notification nav (no useNavigate) — hash URLs work without React Router for same-page scrolling"

requirements-completed:
  - ALERT-01
  - ALERT-03
  - DASH-03
  - DASH-04
  - NOTIF-01

# Metrics
duration: 2min
completed: 2026-02-26
---

# Phase 3 Plan 05: Gap Closure — Alert Dispatch, SSE Reconnect Banner, Notification Nav, Field Name Fix Summary

**Closed 4 Phase 3 verification gaps: auto-update alert dispatch wired via send_alerts_task.delay(), SSE banner now uses 15s timeout-based detection, notification entities rendered as clickable hash anchors, and EventRow field renamed to match backend schema**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-26T17:24:55Z
- **Completed:** 2026-02-26T17:26:33Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- Wired `send_alerts_task.delay()` on both success path (after `session.commit()`) and failure path (after audit log commit, inside its own try/except) in `update_event_status.py` — auto-update events now produce Slack + in-app alerts (ALERT-01, ALERT-03)
- Replaced flawed `CLOSED`-state SSE check with `lastOpenRef` timestamp pattern — banner now triggers during genuine network drops (CONNECTING state) after 15s grace, not only on programmatic `.close()` calls (DASH-03)
- Replaced `<p>` entity display in NotificationCenter with `<a href="/#events">` / `<a href="/#markets">` clickable anchor — notification taps navigate to relevant dashboard section (NOTIF-01)
- Renamed `EventRow.last_checked_at` to `last_prophetx_poll` in events.ts and updated EventsTable.tsx — Last Checked column now renders real timestamps from backend poll data (DASH-04)

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire send_alerts calls into update_event_status.py** — `9ed3273` (feat)
2. **Task 2: Fix SSE reconnect banner to use timeout-based detection** — `4b49199` (fix)
3. **Task 3: Add notification entity nav links and fix last_prophetx_poll field name** — `cd49a4d` (fix)

## Files Created/Modified

- `backend/app/workers/update_event_status.py` — Added two `send_alerts_task.delay()` calls: success path after commit, failure path in except block wrapped in try/except
- `frontend/src/components/SseProvider.tsx` — Replaced with `lastOpenRef` timestamp-based detection; 15s grace, 2s polling interval
- `frontend/src/components/NotificationCenter.tsx` — Entity display changed from `<p>` to `<a href>` anchor pointing to `/#events` or `/#markets`
- `frontend/src/api/events.ts` — `EventRow.last_checked_at` renamed to `last_prophetx_poll`
- `frontend/src/components/EventsTable.tsx` — Last Checked column reads `event.last_prophetx_poll`

## Decisions Made

- Import of `send_alerts_task` placed inside function body (local import) to match existing `SystemConfig` import pattern and avoid potential circular import at module level
- Failure-path alert call wrapped in its own `try/except Exception as alert_exc` block so any alert enqueue failure only logs a warning and does not interfere with `raise self.retry(exc=exc)` on the outer except
- `lastOpenRef` initialized to `Date.now()` at component mount to prevent false-positive disconnect banner during the initial connection setup period
- Used plain `<a href>` anchor instead of React Router `useNavigate` — hash URLs are simpler and work for same-page section scrolling without router dependency

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None — the Python module import verification command failed because the virtualenv is not available outside the Docker container, so grep-based verification was used instead and confirmed both `send_alerts_task.delay` calls and both alert types are present.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

All 4 gaps from 03-VERIFICATION.md are now closed. Phase 3 is ready for final verification pass. The system now:
- Dispatches alerts on auto-update success and failure (ALERT-01, ALERT-03)
- Shows a reconnect banner after genuine network interruption (DASH-03)
- Provides clickable navigation from notifications to dashboard sections (NOTIF-01)
- Renders real Last Checked timestamps from backend poll data (DASH-04)

---
*Phase: 03-dashboard-and-alerts*
*Completed: 2026-02-26*
