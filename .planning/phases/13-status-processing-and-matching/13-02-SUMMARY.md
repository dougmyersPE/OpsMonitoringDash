---
phase: 13-status-processing-and-matching
plan: "02"
subsystem: workers
tags: [opticodds, tennis, fuzzy-match, rabbitmq, celery, slack, redis]

# Dependency graph
requires:
  - phase: 13-status-processing-and-matching
    plan: "01"
    provides: "compute_status_match 6-param signature, _OPTICODDS_CANONICAL in mismatch_detector.py"
  - phase: 12-consumer-foundation
    provides: "opticodds_consumer.py baseline: queue lifecycle, _alert_unknown_status, health keys"
provides:
  - "_write_opticodds_status(): fuzzy-match incoming tennis messages to ProphetX events by competitor names + date window, write opticodds_status to DB"
  - "_alert_special_status(): Slack alert for walkover/retired/suspended with Redis SETNX dedup (1h TTL)"
  - "_similarity(): SequenceMatcher ratio helper (FUZZY_THRESHOLD=0.75)"
  - "_write_heartbeat() wired into _on_message (was dead code in Phase 12)"
  - "30 unit tests covering all new paths (17 new + 13 existing Phase 12 tests)"
affects:
  - "Any future plan using opticodds_status in DB — data now flows from messages to DB"
  - "Dashboard mismatch display — tennis events will now have opticodds_status populated"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fuzzy match pattern from poll_oddsblaze.py applied to AMQP consumer: SequenceMatcher + time proximity bonus + 12-hour guard"
    - "Special status verbatim write: walkover/retired/suspended written as-is (not canonical) to opticodds_status"
    - "Redis SETNX dedup with 1h TTL for special status alerts (separate dedup key from unknown status alerts)"

key-files:
  created: []
  modified:
    - backend/app/workers/opticodds_consumer.py
    - backend/tests/test_opticodds_consumer.py

key-decisions:
  - "FUZZY_THRESHOLD=0.75 (not 0.80): Tennis players have abbreviated/transliterated names that vary more than team names — ESPN pattern"
  - "Special statuses (walkover/retired/suspended) written verbatim to opticodds_status, not canonicalized — _OPTICODDS_CANONICAL in mismatch_detector handles both"
  - "_write_heartbeat wired on every processed message (was defined but never called in Phase 12)"
  - "ack moved after _write_opticodds_status: DB write failure causes nack + requeue (D-08 correctness)"

patterns-established:
  - "AMQP consumer DB write: fuzzy match → verbatim/canonical write → compute_status_match → commit → _publish_update → special alert"
  - "Mock _write_opticodds_status in tests of _on_message to isolate single-call assertions"

requirements-completed: [TNNS-02, TNNS-03]

# Metrics
duration: 7min
completed: 2026-04-03
---

# Phase 13 Plan 02: Status Processing and Matching Summary

**OpticOdds consumer now fuzzy-matches tennis messages to ProphetX events and writes opticodds_status with verbatim special status handling and Slack alerting**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-04-03T14:56:41Z
- **Completed:** 2026-04-03T15:03:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Added `_write_opticodds_status()`: fuzzy-matches by competitor names + date window (FUZZY_THRESHOLD=0.75), writes opticodds_status verbatim for special statuses, calls `compute_status_match()` 6-param after every write
- Added `_alert_special_status()`: Slack webhook alert for walkover/retired/suspended with Redis SETNX dedup key `opticodds_special_status:{status}:{home}:{away}` (1h TTL)
- Added `_similarity()` and `_publish_update()` helpers (mirrors poll_oddsblaze.py pattern)
- Wired `_write_heartbeat()` in `_on_message` (was dead code in Phase 12, now called on every processed message)
- Moved `ch.basic_ack` to after `_write_opticodds_status` so DB write failure causes nack+requeue
- 30 unit tests: 13 existing (Phase 12) + 17 new (TestSimilarity, TestFuzzyMatch, TestAlertSpecialStatus, TestOnMessageHeartbeat)

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Add failing existence tests for Phase 13 functions** - `8ea63fb` (test)
2. **Task 1 GREEN: Implement fuzzy match, DB write, special status alert, heartbeat wiring** - `d3f1d16` (feat)
3. **Task 2: Add comprehensive unit tests for all new paths** - `a27cce1` (feat)

## Files Created/Modified
- `backend/app/workers/opticodds_consumer.py` - Added _similarity, _publish_update, _alert_special_status, _write_opticodds_status; updated _on_message to call them; updated module docstring
- `backend/tests/test_opticodds_consumer.py` - Added TestSimilarity, TestFuzzyMatch, TestAlertSpecialStatus, TestOnMessageHeartbeat; fixed TestUnknownStatusWarning to mock _write_opticodds_status; added datetime import

## Decisions Made
- FUZZY_THRESHOLD=0.75 (lower than poll_oddsblaze.py's 0.80): Tennis athlete names are abbreviated/transliterated more than team names, requiring looser threshold — consistent with poll_espn.py approach
- Special statuses written verbatim: `_OPTICODDS_CANONICAL` in mismatch_detector.py already handles `walkover`/`retired`/`suspended` as final, so verbatim write is safe and preserves precision
- ack moved after DB write: any DB exception causes nack+requeue rather than silent loss (D-08)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed TestUnknownStatusWarning to mock _write_opticodds_status**
- **Found during:** Task 2 (running tests after adding TestFuzzyMatch classes)
- **Issue:** `TestUnknownStatusWarning.test_unknown_status_triggers_warning_log` asserted `log.warning` called exactly once with `opticodds_unknown_status`, but `_on_message` now also calls `_write_opticodds_status` which in turn logs `opticodds_no_competitors` (message had no home/away), causing 2 warning calls
- **Fix:** Added `patch("app.workers.opticodds_consumer._write_opticodds_status")` to the test's context manager
- **Files modified:** backend/tests/test_opticodds_consumer.py
- **Verification:** All 30 tests pass
- **Committed in:** a27cce1 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug: existing test assertion broke when _write_opticodds_status was wired into _on_message)
**Impact on plan:** Necessary correctness fix. No scope creep.

## Issues Encountered
- Pre-existing test failures (not caused by this plan): `TestIsMismatch::test_scheduled_to_upcoming_no_mismatch` and `TestGetExpectedPxStatus::test_get_expected_px_status_scheduled` in test_mismatch_detector.py — both assert `"upcoming"` as ProphetX status but mapping was updated to `"not_started"` in v1.1. Deferred (logged in 13-01-SUMMARY as known issue).

## Known Stubs
None — opticodds_status is written from real message data to the real DB. All code paths are wired end-to-end.

## Next Phase Readiness
- OpticOdds consumer is fully functional: receives messages, fuzzy-matches to ProphetX events, writes opticodds_status, recomputes status_match, alerts on special statuses
- Tennis events on dashboard will now show opticodds_status populated after the consumer processes messages
- Phase 13 complete: both plans (mismatch detector extension + consumer DB writes) are done

---
*Phase: 13-status-processing-and-matching*
*Completed: 2026-04-03*
