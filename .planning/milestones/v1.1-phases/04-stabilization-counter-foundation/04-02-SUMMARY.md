---
phase: 04-stabilization-counter-foundation
plan: 02
subsystem: workers, api
tags: [redis-counter, usage-api, confidence-threshold, poll-workers, INCRBY]

# Dependency graph
requires:
  - phase: 04-stabilization-counter-foundation
    provides: "Plan 01 fixed time guards in Sports API and ESPN workers; /health/workers regression test added"
  - phase: 03-dashboard-and-alerts
    provides: "5 poll workers with _write_heartbeat pattern, async Redis client, FastAPI router registration"
provides:
  - "Redis INCRBY call counters in all 5 poll workers (api_calls:{worker}:{date} keys with 8-day TTL)"
  - "GET /api/v1/usage endpoint returning today's call counts for all 5 workers"
  - "Confidence threshold validation script (scripts/validate_confidence.py) for STAB-03"
affects: [phase-5, phase-6]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Redis INCRBY counter pattern: api_calls:{worker_name}:{YYYY-MM-DD} with 8-day TTL, set-on-first-write"
    - "Counter placement: only at successful-completion path (after DB commit, before final log), never at early-return heartbeats"
    - "Usage endpoint: async Redis MGET for single round-trip fetch of all counter keys"

key-files:
  created:
    - backend/app/api/v1/usage.py
    - backend/scripts/validate_confidence.py
  modified:
    - backend/app/workers/poll_prophetx.py
    - backend/app/workers/poll_sports_data.py
    - backend/app/workers/poll_odds_api.py
    - backend/app/workers/poll_sports_api.py
    - backend/app/workers/poll_espn.py
    - backend/app/main.py
    - backend/app/monitoring/event_matcher.py

key-decisions:
  - "Counter only increments on successful-completion path -- early returns (no API key, no events, no games) do not inflate counts"
  - "Usage endpoint requires readonly role minimum (not admin) per USAGE-01: 'Operator can see total API calls'"
  - "Confidence validation is a server-side script (not automated test) because it queries live production data and requires human judgment"
  - "Fixed join column in validation script: EventIDMapping.prophetx_event_id (actual column) instead of plan's px_event_id"

patterns-established:
  - "Redis counter pattern: _increment_call_counter() function in each worker, atomic INCR with date-keyed auto-reset"
  - "Usage API pattern: MGET for bulk key reads, return 0 (not null) for missing keys"

requirements-completed: [USAGE-01, STAB-02, STAB-03]

# Metrics
duration: 4min
completed: 2026-03-02
---

# Phase 4 Plan 2: Redis Call Counters + Usage Endpoint + Confidence Validation Summary

**Redis INCRBY call counters in all 5 poll workers, GET /api/v1/usage endpoint for daily counts, and confidence threshold validation script for STAB-03**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-02T04:00:05Z
- **Completed:** 2026-03-02T04:03:38Z
- **Tasks:** 3 completed (Task 4 deployment checkpoint pending)
- **Files modified:** 8

## Accomplishments
- All 5 poll workers now atomically increment `api_calls:{worker}:{YYYY-MM-DD}` Redis counters after each successful poll cycle using Redis INCR
- New GET /api/v1/usage endpoint serves today's call counts for all 5 workers with single-round-trip MGET, returning 0 for inactive workers
- Confidence threshold validation script ready for server execution via `docker exec` to satisfy STAB-03
- Counter keys have 8-day TTL (set on first write) for automatic cleanup

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Redis call counter to all 5 poll workers** - `a4ee97f` (feat)
2. **Task 2: Create /api/v1/usage endpoint and register router** - `b48e4a2` (feat)
3. **Task 3: Create confidence threshold validation script for STAB-03** - `146bbac` (feat)

**Task 4: Deploy Phase 4 to Hetzner server** - PENDING (checkpoint:human-verify, requires SSH deployment)

## Files Created/Modified
- `backend/app/workers/poll_prophetx.py` - Added _increment_call_counter function and call at successful completion
- `backend/app/workers/poll_sports_data.py` - Added _increment_call_counter function and call at successful completion
- `backend/app/workers/poll_odds_api.py` - Added _increment_call_counter function and call at final heartbeat only
- `backend/app/workers/poll_sports_api.py` - Added _increment_call_counter function and call at final heartbeat only
- `backend/app/workers/poll_espn.py` - Added _increment_call_counter function and call at final heartbeat only
- `backend/app/api/v1/usage.py` - New endpoint returning daily call counts per worker (readonly+ auth)
- `backend/app/main.py` - Registered usage.router at /api/v1 prefix
- `backend/app/monitoring/event_matcher.py` - Added validation documentation comment to CONFIDENCE_THRESHOLD
- `backend/scripts/validate_confidence.py` - New standalone script for threshold validation against live data

## Decisions Made
- Counter placed only at successful-completion path (next to final `_write_heartbeat()`) -- early-return heartbeats at lines where no API work was done do NOT increment the counter, ensuring counts reflect actual external API fetches
- Usage endpoint uses `require_role(RoleEnum.readonly)` (accepts readonly, operator, admin) matching the pattern from events.py and markets.py -- per USAGE-01 requirement
- Validation script joins on `Event.prophetx_event_id == EventIDMapping.prophetx_event_id` (corrected from plan which referenced nonexistent `px_event_id` column)
- For workers that already import `settings` at module level (poll_odds_api, poll_sports_api, poll_espn), the `_increment_call_counter` function uses `settings` directly rather than lazy-importing, since it's already available

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed join column in validation script**
- **Found during:** Task 3 (confidence validation script)
- **Issue:** Plan specified `Event.id == EventIDMapping.px_event_id` but EventIDMapping has `prophetx_event_id` column (no `px_event_id` column exists)
- **Fix:** Changed join to `Event.prophetx_event_id == EventIDMapping.prophetx_event_id`
- **Files modified:** backend/scripts/validate_confidence.py
- **Committed in:** 146bbac (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Column name correction necessary for script to work against actual schema. No scope creep.

## Pending: Task 4 (Deployment Checkpoint)

Task 4 is a `checkpoint:human-verify` requiring deployment to the Hetzner server. Steps needed:

1. SSH into the Hetzner server
2. Pull latest code
3. Rebuild and restart all services: `docker compose build backend worker beat && docker compose up -d`
4. Verify GET /api/v1/health/workers returns 200 (STAB-02)
5. Verify GET /api/v1/usage returns correct JSON shape (USAGE-01)
6. Wait for one poll cycle and confirm counter increments
7. Run confidence validation: `docker exec <backend_container> python scripts/validate_confidence.py` (STAB-03)

## Issues Encountered
- Local Python environment missing `pwdlib` dependency (only installed in Docker) -- prevented running full import verification locally. Verified syntax parsing and code structure instead. Same issue noted in 04-01 SUMMARY.

## User Setup Required

None - no new environment variables or external service configuration required. Deployment uses existing Docker Compose setup.

## Next Phase Readiness
- All Phase 4 code changes complete and committed locally
- Deployment to Hetzner is the only remaining step before Phase 4 is fully done
- Redis call counters will start accumulating data immediately upon deployment, providing real usage history for Phase 6 ApiUsagePage
- Phase 5 (Interval Control Backend) can proceed with planning once Phase 4 is deployed

## Self-Check: PASSED

- All 9 created/modified files exist on disk
- Commit a4ee97f (Task 1) found in git log
- Commit b48e4a2 (Task 2) found in git log
- Commit 146bbac (Task 3) found in git log
- SUMMARY.md created at expected path

---
*Phase: 04-stabilization-counter-foundation*
*Completed: 2026-03-02 (code complete; deployment pending)*
