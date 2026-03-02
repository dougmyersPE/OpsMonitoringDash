---
phase: 05-interval-control-backend
plan: 02
subsystem: api
tags: [fastapi, validation, redbeat, redis, celery, pytest]

requires:
  - phase: 05-interval-control-backend
    provides: beat_bootstrap.py with WORKER_TASK_MAP, BEAT_NAME_MAP, update_redbeat_entry()
provides:
  - PATCH /api/v1/config/poll_interval_{worker} validates against per-worker minimums (422 on violation)
  - Valid interval changes propagate to RedBeat in Redis (no Beat restart needed)
  - 6 test cases covering all validation paths
affects: [06-api-usage-page]

tech-stack:
  added: []
  patterns:
    - "Deferred import of celery_app inside handler body to avoid API-process side effects"
    - "run_in_executor for sync RedBeat save() in async FastAPI handler"

key-files:
  created:
    - backend/tests/test_interval_validation.py
  modified:
    - backend/app/api/v1/config.py

key-decisions:
  - "Deferred import of update_redbeat_entry inside _propagate_to_redbeat() -- avoids importing celery_app at module level in API process"
  - "run_in_executor for RedBeat propagation -- RedBeat uses sync StrictRedis client, cannot be called directly in async context"
  - "RedBeat propagation is best-effort with try/except -- DB is source of truth, bootstrap syncs on next restart"
  - "Minimum floor validation reads _min rows from DB (not hardcoded) so they can be tuned without code deploy"

patterns-established:
  - "INTERVAL_WORKER_KEYS dict in config.py maps interval DB keys to worker suffixes"
  - "_validate_interval() reusable for both interval and minimum floor updates"

requirements-completed: [FREQ-02, FREQ-03]

duration: 10min
completed: 2026-03-02
---

# Plan 05-02: Interval validation + RedBeat propagation Summary

**Extended PATCH /config endpoint with per-worker minimum enforcement (422 on violation) and live RedBeat propagation so Beat picks up interval changes within 5 seconds without restart**

## Performance

- **Duration:** 10 min
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- PATCH /api/v1/config/poll_interval_{worker} validates: positive integer check + per-worker minimum from DB
- Below-minimum or invalid values return HTTP 422 with clear error message naming the minimum
- Valid changes commit to DB then propagate to RedBeat via run_in_executor (async-safe)
- Non-interval config keys (e.g., alert_only_mode) pass through unchanged
- 6 pytest test cases all pass covering rejection, acceptance, and passthrough paths

## Task Commits

Each task was committed atomically:

1. **Task 1: Add interval validation and RedBeat propagation to PATCH endpoint** - `d13f3a9` (feat)
2. **Task 2: Write interval validation tests** - `b0b44c3` (test)

## Files Created/Modified
- `backend/app/api/v1/config.py` - Added INTERVAL_WORKER_KEYS, _validate_interval(), _propagate_to_redbeat(), extended update_config()
- `backend/tests/test_interval_validation.py` - NEW: 6 test cases for FREQ-02 validation

## Decisions Made
- Deferred import of beat_bootstrap inside handler body (not module level) to avoid celery_app side effects in API process
- RedBeat propagation wrapped in try/except -- best-effort, DB is authoritative, bootstrap syncs on restart
- Minimum floor keys validated as positive integers too (reuses _validate_interval)

## Deviations from Plan
None - plan executed exactly as written

## Issues Encountered
- Pre-existing test_mismatch_detector failure (from Phase 2, commit 970740d) -- unrelated to Phase 5 changes

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Interval validation and propagation fully operational
- Phase 6 frontend can call PATCH /api/v1/config/poll_interval_{worker} with confidence that validation and live propagation work
- Deploy requires: `docker compose build backend beat && docker compose up -d`

---
*Phase: 05-interval-control-backend*
*Completed: 2026-03-02*
