---
phase: 09-status-authority-model
plan: "01"
subsystem: database
tags: [sqlalchemy, alembic, migration, celery, websocket, status-authority]

# Dependency graph
requires:
  - phase: 08-ws-diagnostics-instrumentation
    provides: WS consumer emitting Redis health keys; gate for Phase 9
provides:
  - is_ws_authoritative() pure helper function in backend/app/monitoring/authority.py
  - WS_AUTHORITY_WINDOW_SECONDS setting (default 600) in Settings class
  - Event model columns: status_source (String 20) and ws_delivered_at (DateTime timezone)
  - Alembic migration 008 adding both columns with down_revision=007
  - 5-test TestAuthorityHelper test suite for the helper function
affects:
  - 09-02-status-authority-worker-wiring (uses all artifacts from this plan)
  - 10-ws-health-dashboard (status_source column for source tracking)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure helper function pattern in backend/app/monitoring/ (no DB/network deps)"
    - "Alembic nullable column migration pattern (revision chain: 007 -> 008)"
    - "TDD: write failing tests first, then implement helper to green"

key-files:
  created:
    - backend/app/monitoring/authority.py
    - backend/alembic/versions/008_add_status_authority_columns.py
    - backend/tests/test_status_authority.py
  modified:
    - backend/app/core/config.py
    - backend/app/models/event.py

key-decisions:
  - "Boundary check is elapsed < threshold (strictly less than): exactly at boundary returns False"
  - "Naive datetime input coerced to UTC via replace(tzinfo=timezone.utc) before comparison"
  - "No index on ws_delivered_at: not needed at current query patterns and scale"
  - "status_source String(20) accommodates 'ws', 'poll', 'manual' values with headroom"

patterns-established:
  - "Pure authority check: is_ws_authoritative(ws_delivered_at, threshold_seconds) — no side effects"
  - "Config setting WS_AUTHORITY_WINDOW_SECONDS in Settings for operationally tunable window"

requirements-completed: [AUTH-01, AUTH-02]

# Metrics
duration: 4min
completed: 2026-04-01
---

# Phase 9 Plan 01: Status Authority Schema Summary

**Pure is_ws_authoritative() helper, Event model columns (status_source + ws_delivered_at), Alembic migration 008, and WS_AUTHORITY_WINDOW_SECONDS=600 config setting with 5 TDD unit tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-01T03:02:46Z
- **Completed:** 2026-04-01T03:06:53Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Created `is_ws_authoritative()` pure helper function that returns True when WS delivery is within the authority window
- Added `status_source` (String 20) and `ws_delivered_at` (DateTime timezone) columns to Event model
- Created Alembic migration 008 with correct revision chain (007 -> 008) adding both nullable columns
- Added `WS_AUTHORITY_WINDOW_SECONDS: int = 600` to Settings class in config.py
- 5 unit tests in `TestAuthorityHelper` covering: None input, within window, expired window, naive datetime coercion, exact boundary

## Task Commits

Each task was committed atomically:

1. **Task 1: Add authority helper, config setting, and unit tests** - `f959f9b` (feat)
2. **Task 2: Add Event model columns and Alembic migration 008** - `d707362` (feat)

## Files Created/Modified

- `backend/app/monitoring/authority.py` - Pure is_ws_authoritative() function (no DB/network deps)
- `backend/tests/test_status_authority.py` - 5 TestAuthorityHelper unit tests (TDD)
- `backend/app/core/config.py` - Added WS_AUTHORITY_WINDOW_SECONDS: int = 600 after POLL_INTERVAL_ODDSBLAZE
- `backend/app/models/event.py` - Added status_source and ws_delivered_at columns after oddsblaze_status
- `backend/alembic/versions/008_add_status_authority_columns.py` - Migration 008 (down_revision=007)

## Decisions Made

- **Boundary exclusive (<, not <=):** elapsed < threshold_seconds means exactly at the boundary returns False. This is stricter (slightly prefers poll authority at the exact boundary) and matches the plan spec.
- **Naive datetime coercion:** Helper coerces naive datetimes to UTC via `replace(tzinfo=timezone.utc)` rather than raising. This handles cases where DB returns naive datetimes from some drivers.
- **No index on ws_delivered_at:** The column will be read via single-row lookups (by event), not range scans. No index needed at this scale.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Pre-existing test failure in `test_mismatch_detector.py::TestIsMismatch::test_scheduled_to_upcoming_no_mismatch` was confirmed as pre-existing (exists before any changes in this plan). Out of scope per deviation boundary rules; logged for awareness.
- `test_auth.py` and other DB-requiring tests fail locally without a running PostgreSQL instance. These tests require the running Docker environment on the server and are expected to fail in local execution without env setup.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All artifacts for Plan 09-02 are ready: `is_ws_authoritative()`, `WS_AUTHORITY_WINDOW_SECONDS`, `status_source`, and `ws_delivered_at` columns
- Plan 09-02 can now wire authority logic into ws_prophetx worker (sets ws + ws_delivered_at on delivery) and poll_prophetx worker (checks is_ws_authoritative() before writing prophetx_status)
- Migration 008 must be run on the server before Plan 09-02 deployment: `docker compose exec backend alembic upgrade head`

---
*Phase: 09-status-authority-model*
*Completed: 2026-04-01*
