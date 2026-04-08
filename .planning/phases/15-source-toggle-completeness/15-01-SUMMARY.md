---
phase: 15-source-toggle-completeness
plan: 01
subsystem: api
tags: [python, fastapi, celery, source-toggle, websocket, prophetx]

# Dependency graph
requires:
  - phase: 14-dashboard-and-health
    provides: OpticOdds health integration and WS shape established
  - phase: 12-consumer-foundation
    provides: source_toggle.py with is_source_enabled() pattern
provides:
  - ProphetX WS toggle guard in _upsert_event skips DB writes when disabled
  - poll_prophetx authority bypass when prophetx_ws toggle is off
  - Usage API returns all 6 source toggle states (odds_api, sports_data, espn, oddsblaze, opticodds, prophetx_ws)
  - seed.py defaults for source_enabled_opticodds and source_enabled_prophetx_ws
affects:
  - frontend SourceToggleSection.tsx (consumes sources_enabled with 6 keys now)
  - future plans wiring toggle UI for the 3 new sources

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ProphetX WS toggle is unique: early return in _upsert_event (not clear_source_and_recompute) because ProphetX status is authoritative — clearing would be destructive"
    - "poll_prophetx authority bypass: ws_toggle_on AND is_ws_authoritative() — short-circuit disables authority when WS toggle is off (D-03)"

key-files:
  created:
    - backend/tests/test_source_toggle.py
  modified:
    - backend/app/seed.py
    - backend/app/api/v1/usage.py
    - backend/app/workers/ws_prophetx.py
    - backend/app/workers/poll_prophetx.py
    - backend/tests/test_ws_upsert.py

key-decisions:
  - "ProphetX WS toggle returns early in _upsert_event without clearing prophetx_status — ProphetX is primary source of truth, clearing would leave events with no status (D-02)"
  - "Authority bypass uses ws_toggle_on AND is_ws_authoritative() — ensures poll_prophetx writes freely when WS is disabled (D-03)"
  - "source_toggle_keys extended to 6 entries in usage.py — frontend reads this to render all toggle rows"

patterns-established:
  - "ProphetX WS toggle pattern: is_source_enabled check inside _upsert_event after event_id guard, before DB open"
  - "Authority bypass pattern: ws_toggle_on = _is_source_enabled('prophetx_ws'); authoritative = ws_toggle_on and is_ws_authoritative(...)"

requirements-completed: [TOGL-01, TOGL-02, TOGL-03, TOGL-04, TOGL-05, TOGL-06]

# Metrics
duration: 25min
completed: 2026-04-07
---

# Phase 15 Plan 01: Backend Toggle Behavior Summary

**ProphetX WS toggle guard added to ws_prophetx._upsert_event, poll_prophetx authority bypass wired for D-03, and usage API extended to return all 6 source toggle states**

## Performance

- **Duration:** 25 min
- **Started:** 2026-04-07T21:10:00Z
- **Completed:** 2026-04-07T21:38:00Z
- **Tasks:** 1 (with TDD)
- **Files modified:** 6

## Accomplishments
- Usage API now returns `sources_enabled` with all 6 keys: odds_api, sports_data, espn, oddsblaze, opticodds, prophetx_ws
- WS consumer skips DB writes when prophetx_ws is disabled (connection stays alive, diagnostics still update)
- poll_prophetx bypasses WS authority window when prophetx_ws toggle is off — ensures events still get status updates from REST API
- Seed script updated with 2 new defaults (opticodds + prophetx_ws, both default true)
- 15 tests pass covering all toggle behaviors

## Task Commits

Each task was committed atomically:

1. **Task 1: Backend toggle behavior — seed, usage API, WS guard, authority bypass** - `b286623` (feat)

**Plan metadata:** (pending docs commit)

## Files Created/Modified
- `backend/tests/test_source_toggle.py` - New test file: TestUsageSourceToggleKeys (6 tests) + TestPollProphetxAuthorityBypass (4 tests)
- `backend/tests/test_ws_upsert.py` - Added TestWsToggle class (2 tests); patched is_source_enabled in existing tests
- `backend/app/seed.py` - Added source_enabled_opticodds and source_enabled_prophetx_ws to SOURCE_ENABLED_DEFAULTS
- `backend/app/api/v1/usage.py` - Extended source_toggle_keys from 3 to 6 sources
- `backend/app/workers/ws_prophetx.py` - Added is_source_enabled import + guard inside _upsert_event
- `backend/app/workers/poll_prophetx.py` - Added _is_source_enabled import + authority bypass logic

## Decisions Made
- ProphetX WS toggle does NOT clear prophetx_status on disable (D-02) — ProphetX is the primary authority; clearing would be destructive and leave events with no status. This differs from all other toggles.
- poll_prophetx authority bypass uses `ws_toggle_on AND is_ws_authoritative()` short-circuit (D-03) — when toggle is off, even recent WS deliveries are ignored so REST API can update freely.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Patched is_source_enabled in existing TestWsUpsertCreatePath tests**
- **Found during:** Task 1 (GREEN phase test run)
- **Issue:** Adding `is_source_enabled` import to ws_prophetx.py caused existing tests to hang — the function tries to open a DB connection, and tests don't mock it
- **Fix:** Added `patch("app.workers.ws_prophetx.is_source_enabled", return_value=True)` to all 3 existing test methods in TestWsUpsertCreatePath
- **Files modified:** backend/tests/test_ws_upsert.py
- **Verification:** All 15 tests pass without hanging
- **Committed in:** b286623 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Auto-fix was necessary for test correctness. No scope creep.

## Issues Encountered
- Test suite hangs when `is_source_enabled` is not mocked — the function calls `SyncSessionLocal` which blocks waiting for DB connection. All WS upsert tests needed the mock added after adding the import to ws_prophetx.py.

## User Setup Required
None - no external service configuration required. New seed rows are idempotent (skipped if already present).

## Next Phase Readiness
- Backend toggle support complete for all 6 sources
- Frontend SourceToggleSection.tsx needs SOURCE_DISPLAY updated with 3 new entries (oddsblaze, opticodds, prophetx_ws) — Phase 15 Plan 02
- Usage API response now delivers all 6 toggle states — frontend can render them once wired

## Self-Check

### Files exist:
- backend/tests/test_source_toggle.py: FOUND
- backend/tests/test_ws_upsert.py: FOUND (modified)
- backend/app/seed.py: FOUND (modified)
- backend/app/api/v1/usage.py: FOUND (modified)
- backend/app/workers/ws_prophetx.py: FOUND (modified)
- backend/app/workers/poll_prophetx.py: FOUND (modified)

### Commits exist:
- b286623: FOUND

## Self-Check: PASSED

---
*Phase: 15-source-toggle-completeness*
*Completed: 2026-04-07*
