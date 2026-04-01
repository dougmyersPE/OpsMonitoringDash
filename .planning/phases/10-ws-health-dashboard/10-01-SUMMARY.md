---
phase: 10-ws-health-dashboard
plan: 01
subsystem: ui
tags: [redis, websocket, health, dashboard, react, fastapi, pytest]

# Dependency graph
requires:
  - phase: 08-ws-diagnostics-and-instrumentation
    provides: "Redis ws:connection_state key written by _write_ws_connection_state in ws_prophetx.py"
  - phase: 04-stabilization-counter-foundation
    provides: "/health/workers endpoint with Redis heartbeat mget pattern"
provides:
  - "ws:connection_state_since companion Redis key written atomically with ws:connection_state (120s TTL)"
  - "Extended /health/workers endpoint returning ws_prophetx nested object with connected/state/since"
  - "WS health badge in SystemHealth.tsx alongside poll worker badges with green/red binary coloring"
  - "Native tooltip on WS badge showing Pusher state name + relative transition time"
  - "TestWorkerHealthWsProphetX integration tests (3 tests) and TestWriteWsConnectionStateSince unit tests (2 tests)"
affects: [11-ws-health-dashboard, future-phases]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Nested ws_prophetx object in /health/workers response (connected/state/since vs flat boolean)"
    - "Optional interface field (ws_prophetx?) for backward-compatible backend/frontend deploys"
    - "wsTitle() helper pattern for tooltip text with relative time using formatDistanceToNow"

key-files:
  created:
    - backend/tests/test_ws_diagnostics.py
  modified:
    - backend/app/workers/ws_prophetx.py
    - backend/app/api/v1/health.py
    - backend/tests/test_health.py
    - frontend/src/components/SystemHealth.tsx

key-decisions:
  - "ws_prophetx returned as nested object (not flat boolean) to expose state/since fields without breaking existing poll worker shape"
  - "ws_prophetx? optional field on WorkerHealth interface so frontend doesn't crash on partial backend deploy"
  - "WS badge rendered separately from WORKERS.map() because ws_prophetx is an object, not a boolean"
  - "Native HTML title attribute for tooltip (D-04: no styled component, zero new dependencies)"

patterns-established:
  - "Companion Redis key pattern: write both ws:connection_state and ws:connection_state_since atomically in same function"
  - "YAGNI: did not read ws:sport_event_count or ws:last_message_at in health endpoint (not displayed)"

requirements-completed: [WSHLT-01, WSHLT-02, WSHLT-03]

# Metrics
duration: 12min
completed: 2026-04-01
---

# Phase 10 Plan 01: WS Health Dashboard Summary

**ProphetX WebSocket connection health surfaced on operator dashboard via extended /health/workers endpoint and WS badge with Pusher state tooltip**

## Performance

- **Duration:** 12 min
- **Started:** 2026-04-01T14:50:47Z
- **Completed:** 2026-04-01T15:02:50Z
- **Tasks:** 2 auto + 1 auto-approved checkpoint
- **Files modified:** 5

## Accomplishments
- Extended `_write_ws_connection_state` to atomically write `ws:connection_state_since` ISO UTC timestamp alongside `ws:connection_state` (both with 120s TTL)
- Extended `/health/workers` to include `ws_prophetx: {connected, state, since}` nested object via mget of 7 Redis keys in single round-trip
- Added WS health badge to SystemHealth.tsx: green when `connected === true`, red otherwise; native tooltip shows `ProphetX WS: {state}\nSince: {relative_time}`
- All 9 new tests pass (4 unit tests in test_ws_diagnostics.py + 3 integration tests in TestWorkerHealthWsProphetX + 2 existing health tests)

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend backend — companion Redis key + health endpoint + tests** - `f4d7acb` (feat)
2. **Task 2: Add WS health badge to SystemHealth.tsx with tooltip** - `c240321` (feat)
3. **Task 3: Visual verification of WS badge** - auto-approved (checkpoint:human-verify, non-blocking)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `backend/app/workers/ws_prophetx.py` - `_write_ws_connection_state` writes `ws:connection_state_since` companion key
- `backend/app/api/v1/health.py` - `/health/workers` extended with ws:connection_state keys + ws_prophetx object
- `backend/tests/test_health.py` - Added `TestWorkerHealthWsProphetX` class (3 tests)
- `backend/tests/test_ws_diagnostics.py` - Created: `TestWriteWsConnectionState` + `TestWriteWsConnectionStateSince` (4 unit tests)
- `frontend/src/components/SystemHealth.tsx` - `WsProphetXHealth` interface, `wsTitle()` helper, WS badge JSX

## Decisions Made
- ws_prophetx returned as nested object with connected/state/since fields — richer than boolean, exposes state detail to frontend for tooltip without breaking existing response shape
- Optional `ws_prophetx?` field on WorkerHealth interface — frontend gracefully handles backend deploys ahead of it
- WS badge rendered after WORKERS.map() as IIFE — cannot go in WORKERS array since ws_prophetx is an object, not a boolean
- YAGNI: did not read `ws:sport_event_count` or `ws:last_message_at` in health endpoint (not displayed in this phase)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Test infrastructure: Colima/Docker not running at start; started Colima and launched test-postgres/test-redis containers with host-accessible ports (5433, 6380) to run integration tests. Test .env adjusted accordingly.
- Pre-existing test failures in test_auth.py, test_mismatch_detector.py, test_update_event_status.py (5 tests) — unrelated to this plan's changes, pre-existing in the codebase.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- WS health badge is live; operators can see WebSocket connection health on dashboard within 30s of a state change
- The `_write_ws_connection_state` function needs to be called by the WS consumer lifecycle (connected/disconnected events) to populate the Redis keys — Phase 8 instrumented this; this plan adds the frontend surface
- No blockers for next phase

## Self-Check: PASSED

All files created/modified exist on disk. All task commits verified in git log. All key content patterns present in files.

---
*Phase: 10-ws-health-dashboard*
*Completed: 2026-04-01*
