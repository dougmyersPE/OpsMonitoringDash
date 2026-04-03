# Deferred Items — Phase 13

## Pre-existing test failures in test_mismatch_detector.py

Found during: Task 1 (13-01)
Scope: Out of scope — pre-existing before Plan 13-01 execution

### TestIsMismatch::test_scheduled_to_upcoming_no_mismatch
- `is_mismatch("upcoming", "Scheduled")` returns True but test expects False
- Root cause: `SDIO_TO_PX_STATUS["Scheduled"]` maps to `"not_started"`, not `"upcoming"`
  ProphetX confirmed status is `not_started` (v1.1 shipped), test was written with the old unconfirmed value
- Fix: Update test to use `is_mismatch("not_started", "Scheduled") is False`

### TestGetExpectedPxStatus::test_get_expected_px_status_scheduled
- `get_expected_px_status("Scheduled")` returns `"not_started"` but test expects `"upcoming"`
- Same root cause as above — stale "upcoming" ProphetX value in test
- Fix: Update expected value to `"not_started"`
