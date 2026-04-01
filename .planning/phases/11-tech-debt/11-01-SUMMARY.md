---
phase: 11-tech-debt
plan: 01
subsystem: api
tags: [celery, sqlalchemy, alembic, redis, fastapi, mismatch-detection]

# Dependency graph
requires:
  - phase: 10-ws-health-dashboard
    provides: OddsBlaze as fourth real-world source; final compute_status_match 6-param signature
provides:
  - Sports API client and worker fully deleted
  - Alembic migration 009 dropping sports_api_status column from events table
  - compute_status_match/compute_is_critical reduced to 5-param signatures (px + 4 sources)
  - compute_is_flagged reduced to single sdio_status param
  - All callers updated across 10 worker/API files
affects: [deployment, testing, 11-02]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "4-source mismatch detection: Odds API, SDIO, ESPN, OddsBlaze (Sports API removed)"
    - "compute_is_flagged(sdio_status) — single-source flag detection"

key-files:
  created:
    - backend/alembic/versions/009_drop_sports_api_status.py
  modified:
    - backend/app/monitoring/mismatch_detector.py
    - backend/app/workers/celery_app.py
    - backend/app/workers/beat_bootstrap.py
    - backend/app/workers/source_toggle.py
    - backend/app/workers/rollup_api_usage.py
    - backend/app/workers/ws_prophetx.py
    - backend/app/workers/poll_prophetx.py
    - backend/app/workers/poll_odds_api.py
    - backend/app/workers/poll_espn.py
    - backend/app/workers/poll_oddsblaze.py
    - backend/app/workers/poll_sports_data.py
    - backend/app/workers/poll_critical_check.py
    - backend/app/api/v1/health.py
    - backend/app/api/v1/usage.py
    - backend/app/api/v1/events.py
    - backend/app/api/v1/config.py
    - backend/app/seed.py
    - backend/app/models/event.py
    - backend/app/schemas/event.py
    - backend/app/core/config.py
    - backend/tests/test_health.py
    - backend/tests/test_status_authority.py
    - backend/tests/test_ws_upsert.py

key-decisions:
  - "D-01 full removal: Sports API deleted entirely, not refactored — zero references remain in backend"
  - "Migration 009 uses op.drop_column to remove sports_api_status from events table at deploy time"

patterns-established:
  - "compute_status_match(px_status, odds_api_status, sdio_status, espn_status, oddsblaze_status) — canonical 5-param signature"
  - "compute_is_flagged(sdio_status) — SDIO is the authoritative flag source; Sports API flag detection removed"

requirements-completed: [DEBT-01]

# Metrics
duration: 35min
completed: 2026-04-01
---

# Phase 11 Plan 01: Sports API Removal Summary

**Sports API (api-sports.io) fully excised from backend: client/worker deleted, DB column dropped via migration 009, mismatch detector reduced to 4-source signatures, all callers updated across 10 files**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-04-01T18:53:00Z
- **Completed:** 2026-04-01T19:28:32Z
- **Tasks:** 2
- **Files modified:** 23

## Accomplishments

- Deleted `backend/app/clients/sports_api.py` and `backend/app/workers/poll_sports_api.py` entirely
- Created Alembic migration 009 to drop `sports_api_status` column from `events` table
- Reduced `compute_status_match`, `compute_is_critical` from 6-param to 5-param signatures (4 real-world sources)
- Reduced `compute_is_flagged` from 2-param to 1-param (SDIO only)
- Updated all 10 callers of these functions across worker and API files
- Removed Sports API from health endpoint, usage endpoint, Celery config, beat bootstrap, seed, and config API
- Tests updated to match new signatures and remove `poll_sports_api` from expected worker keys

## Task Commits

1. **Task 1: Delete Sports API files, create migration, update model/schema/config** - `728cb79` (feat)
2. **Task 2: Update mismatch detector, all workers, health, usage, celery, config API, seed, and tests** - `bf62769` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `backend/alembic/versions/009_drop_sports_api_status.py` - Migration dropping sports_api_status column
- `backend/app/clients/sports_api.py` - DELETED
- `backend/app/workers/poll_sports_api.py` - DELETED
- `backend/app/models/event.py` - Removed sports_api_status column definition
- `backend/app/schemas/event.py` - Removed sports_api_status field; updated is_critical call to 5-arg
- `backend/app/core/config.py` - Removed SPORTS_API_KEY and POLL_INTERVAL_SPORTS_API settings
- `backend/app/monitoring/mismatch_detector.py` - Removed Sports API flag/canonical sets and function; updated compute_status_match, compute_is_critical, compute_is_flagged signatures
- `backend/app/workers/celery_app.py` - Removed poll_sports_api from include list
- `backend/app/workers/beat_bootstrap.py` - Removed sports_api entries from all maps
- `backend/app/workers/source_toggle.py` - Removed sports_api from SOURCE_COLUMN_MAP; updated compute_status_match call
- `backend/app/workers/rollup_api_usage.py` - Removed poll_sports_api from WORKER_NAMES
- `backend/app/api/v1/health.py` - Removed poll_sports_api key; adjusted ws result indexes (4→[4], 5→[5])
- `backend/app/api/v1/usage.py` - Removed SPORTS_API_FAMILIES, poll_sports_api entries, sports_api quota section
- `backend/app/api/v1/events.py` - Removed poll_sports_api import and delay() call
- `backend/app/api/v1/config.py` - Removed poll_interval_sports_api from INTERVAL_WORKER_KEYS
- `backend/app/seed.py` - Removed poll_interval_sports_api, poll_interval_sports_api_min, source_enabled_sports_api
- `backend/app/workers/ws_prophetx.py` - Updated 3 compute_status_match calls to 5-arg
- `backend/app/workers/poll_prophetx.py` - Updated 5 compute_status_match calls to 5-arg
- `backend/app/workers/poll_odds_api.py` - Updated compute_status_match call to 5-arg
- `backend/app/workers/poll_espn.py` - Updated compute_status_match call to 5-arg
- `backend/app/workers/poll_oddsblaze.py` - Updated compute_status_match call to 5-arg
- `backend/app/workers/poll_sports_data.py` - Updated compute_status_match to 5-arg; compute_is_flagged to 1-arg; removed sports_api_status from log
- `backend/app/workers/poll_critical_check.py` - Updated compute_is_critical to 5-arg; removed SportsAPI from Slack message sources
- `backend/tests/test_health.py` - Removed poll_sports_api from expected_workers list
- `backend/tests/test_status_authority.py` - Removed sports_api_status = None from all mock Events
- `backend/tests/test_ws_upsert.py` - Removed sports_api_status = None from mock Event; updated assert_called_once_with to 5-arg

## Decisions Made

- Full removal (D-01 decision from discussion log): Sports API deleted entirely, not refactored. No partial stubs.
- Migration 009 uses `op.drop_column` — deferred to deployment, not applied in dev without DB.
- `compute_is_flagged` reduced to SDIO-only: Sports API flag statuses (CANC, PSP, SUSP, ABD) were redundant; SDIO FLAG_ONLY_STATUSES fully covers postponement/cancellation cases.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed indentation error in models/event.py after line deletion**
- **Found during:** Task 2 (test run discovery)
- **Issue:** Deleting `sports_api_status` line left `sdio_status` without leading whitespace (Python IndentationError)
- **Fix:** Restored 4-space indent on `sdio_status` mapped_column line
- **Files modified:** backend/app/models/event.py
- **Verification:** Python import succeeded; mismatch_detector direct test passed
- **Committed in:** bf62769 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - indentation bug)
**Impact on plan:** Minimal — caused by how the edit tool handled the deletion. Fixed immediately.

## Issues Encountered

- Local test run not possible (FastAPI version incompatibility in dev environment vs Docker). Used direct Python import test to verify function signatures and logic. Tests will be fully validated when deployed to Docker.

## Next Phase Readiness

- Backend is clean: zero `sports_api` references in any Python file
- Migration 009 ready to apply on deployment (`alembic upgrade head`)
- Plan 11-02 (MGET optimization for Sports API quota reads) is now N/A since Sports API quota code was also removed
- Ready for phase 11-02 (remaining tech debt items)

---
*Phase: 11-tech-debt*
*Completed: 2026-04-01*
