---
phase: 13-status-processing-and-matching
plan: "01"
subsystem: monitoring
tags: [mismatch-detector, status-matching, opticodds, tennis, celery-workers]

# Dependency graph
requires:
  - phase: 12-consumer-foundation
    provides: "opticodds_status column on Event model, opticodds consumer infrastructure"
provides:
  - "_OPTICODDS_CANONICAL dict in mismatch_detector.py with 17-entry scheduled/inprogress/final mapping"
  - "compute_status_match 6-param signature (opticodds_status as 6th arg)"
  - "compute_is_critical 6-param signature (opticodds_status counts toward 2-source threshold)"
  - "All 13 call sites updated to pass opticodds_status"
  - "source_toggle SOURCE_COLUMN_MAP includes opticodds entry"
affects:
  - "13-02-PLAN.md (consumer DB write uses compute_status_match — now 6-param)"
  - "Any future plan extending mismatch detection sources"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_OPTICODDS_CANONICAL follows _ODDSBLAZE_CANONICAL pattern: raw source values -> scheduled/inprogress/final"
    - "NULL-safe source params: None is skipped, no effect on non-tennis events"
    - "compute_status_match extended with new source by adding param + (status, canonical_map) tuple to sources list"

key-files:
  created: []
  modified:
    - backend/app/monitoring/mismatch_detector.py
    - backend/app/workers/poll_prophetx.py
    - backend/app/workers/ws_prophetx.py
    - backend/app/workers/poll_sports_data.py
    - backend/app/workers/poll_espn.py
    - backend/app/workers/poll_oddsblaze.py
    - backend/app/workers/poll_odds_api.py
    - backend/app/workers/source_toggle.py
    - backend/tests/test_mismatch_detector.py
    - backend/tests/test_ws_upsert.py

key-decisions:
  - "_OPTICODDS_CANONICAL maps both raw OpticOdds values (in_progress/finished) AND consumer canonical outputs (not_started/live/ended) AND verbatim special statuses (walkover/retired/suspended)"
  - "opticodds_status=None for new event creation (no data yet) — explicit None rather than relying on default"

patterns-established:
  - "6-param compute_status_match: px_status, odds_api, sdio, espn, oddsblaze, opticodds — positional order"
  - "source_toggle.clear_source_and_recompute passes None for the cleared column, ev.opticodds_status otherwise"

requirements-completed: [MISM-01, AMQP-03]

# Metrics
duration: 10min
completed: 2026-04-03
---

# Phase 13 Plan 01: Status Processing and Matching Summary

**OpticOdds extended as 6th mismatch detection source with _OPTICODDS_CANONICAL mapping and all 13 call sites updated**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-03T14:43:47Z
- **Completed:** 2026-04-03T14:55:00Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Added `_OPTICODDS_CANONICAL` dict (17 entries) mapping raw OpticOdds values + consumer outputs to canonical scheduled/inprogress/final
- Extended `compute_status_match()` and `compute_is_critical()` to 6-param signatures; OpticOdds now participates in mismatch detection for tennis events
- Updated all 13 call sites across 5 worker files + source_toggle to pass `opticodds_status` as the 6th argument
- Added `TestComputeStatusMatchOpticOdds` test class (10 tests) covering disagree/agree/NULL-safe/critical-threshold scenarios

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Add failing OpticOdds tests** - `92be9ee` (test)
2. **Task 1 GREEN: Add _OPTICODDS_CANONICAL + extend both function signatures** - `9fa3fe0` (feat)
3. **Task 2: Update all compute_status_match call sites + source_toggle** - `e26292f` (feat)

**Auto-fix:** `da09bda` (fix: update test_ws_upsert to match new 6-arg signature)

## Files Created/Modified
- `backend/app/monitoring/mismatch_detector.py` - Added _OPTICODDS_CANONICAL dict, extended compute_status_match and compute_is_critical to 6 params
- `backend/app/workers/poll_prophetx.py` - 5 call sites updated (new events pass None, existing events pass event.opticodds_status)
- `backend/app/workers/ws_prophetx.py` - 3 call sites updated (new events pass None, existing events pass existing.opticodds_status)
- `backend/app/workers/poll_sports_data.py` - 1 call site updated
- `backend/app/workers/poll_espn.py` - 1 call site updated
- `backend/app/workers/poll_oddsblaze.py` - 1 call site updated
- `backend/app/workers/poll_odds_api.py` - 1 call site updated
- `backend/app/workers/source_toggle.py` - Added opticodds to SOURCE_COLUMN_MAP + ev.opticodds_status in clear_source_and_recompute
- `backend/tests/test_mismatch_detector.py` - Added TestComputeStatusMatchOpticOdds (10 tests), imported compute_is_critical
- `backend/tests/test_ws_upsert.py` - Updated assert_called_once_with to 6 args (auto-fix)

## Decisions Made
- `_OPTICODDS_CANONICAL` handles both raw API values (`in_progress`, `finished`) and the consumer's canonical outputs (`not_started`, `live`, `ended`) plus verbatim special statuses (`walkover`, `retired`, `suspended`) — one dict covers all cases because D-06 says special statuses are written verbatim
- New event creation explicitly passes `None` as 6th arg rather than relying on default, to make intent clear at call sites

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test_ws_upsert assertion to match new 6-arg signature**
- **Found during:** Task 2 (verify step)
- **Issue:** `test_create_path_sets_status_match_not_none` was asserting `compute_status_match` called with 5 args; now called with 6
- **Fix:** Changed `assert_called_once_with("not_started", None, None, None, None)` to include the 6th `None`
- **Files modified:** backend/tests/test_ws_upsert.py
- **Verification:** `pytest tests/test_ws_upsert.py` — 3 passed
- **Committed in:** da09bda

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug: stale test assertion)
**Impact on plan:** Necessary correctness fix. No scope creep.

## Issues Encountered
- Pre-existing test failures (not caused by this plan): `TestIsMismatch::test_scheduled_to_upcoming_no_mismatch` and `TestGetExpectedPxStatus::test_get_expected_px_status_scheduled` — both assert `"upcoming"` as the ProphetX status for Scheduled/not_started games, but the actual mapping was updated to `"not_started"` in v1.1. Logged to `deferred-items.md` in this phase directory.

## Known Stubs
None — all OpticOdds status data flows through `_OPTICODDS_CANONICAL` to real mismatch detection logic.

## Next Phase Readiness
- `compute_status_match` is 6-param — Plan 13-02 consumer DB writes can call it directly passing `best_match.opticodds_status`
- `source_toggle` includes opticodds — admin disable/enable flow works for OpticOdds source

---
*Phase: 13-status-processing-and-matching*
*Completed: 2026-04-03*
