---
phase: 05-interval-control-backend
plan: 01
subsystem: infra
tags: [celery, redbeat, redis, postgresql, beat-bootstrap]

requires:
  - phase: 04-stabilization-counter-foundation
    provides: Redis call counters, system_config table, poll workers
provides:
  - DB-backed poll interval defaults (6 workers) and minimum floors (6 rows)
  - beat_bootstrap.py module for reading DB intervals and writing RedBeat entries
  - Empty beat_schedule in celery_app.py (no overwrite on restart)
  - Beat container bootstrap step in docker-compose.yml
affects: [05-02, 06-api-usage-page]

tech-stack:
  added: []
  patterns:
    - "beat_bootstrap.py sync DB read -> RedBeatSchedulerEntry.save() -> Redis"
    - "seed.py seed_intervals() check-exists-insert pattern for system_config rows"

key-files:
  created:
    - backend/app/workers/beat_bootstrap.py
  modified:
    - backend/app/seed.py
    - backend/app/workers/celery_app.py
    - docker-compose.yml

key-decisions:
  - "beat_schedule={} (empty dict) instead of removing key entirely -- ensures setup_schedule() statics cleanup is a no-op"
  - "Bootstrap entries use entry.save() directly (not update_from_dict) so they never appear in statics_key and survive cleanup"
  - "Beat depends_on postgres (service_healthy) + redis (service_healthy) -- bootstrap needs DB access"
  - "Fallback defaults in beat_bootstrap.py match seed.py defaults -- correct behavior even if seed hasn't run yet"
  - "Critical check default lowered from 60s to 30s (DB query is cheap, more responsive safety net)"

patterns-established:
  - "WORKER_TASK_MAP and BEAT_NAME_MAP dicts as canonical worker registry in beat_bootstrap.py"
  - "update_redbeat_entry() single-entry helper for runtime propagation (used by Plan 05-02)"

requirements-completed: [FREQ-03]

duration: 8min
completed: 2026-03-02
---

# Plan 05-01: DB-backed intervals + Beat bootstrap Summary

**Replaced static beat_schedule dict with DB-seeded intervals and a pre-Beat bootstrap that writes RedBeat entries from system_config, ensuring operator-configured intervals survive Beat restarts**

## Performance

- **Duration:** 8 min
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Removed all 6 hardcoded worker schedule entries from celery_app.py (replaced with empty dict + explanatory comment)
- Created seed_intervals() in seed.py that inserts 12 system_config rows (6 interval defaults + 6 minimum floors) on first boot
- Created beat_bootstrap.py with bootstrap_beat_schedule() and update_redbeat_entry() functions
- Wired bootstrap into Beat container command via docker-compose.yml (runs before celery beat)

## Task Commits

Each task was committed atomically:

1. **Task 1: Seed interval config rows and create beat bootstrap module** - `5c2a37e` (feat)
2. **Task 2: Remove beat_schedule from celery_app and wire bootstrap into Beat container** - `8d011f2` (feat)

## Files Created/Modified
- `backend/app/seed.py` - Added seed_intervals() with 12 system_config rows (6 intervals + 6 minimums)
- `backend/app/workers/beat_bootstrap.py` - NEW: reads DB intervals, writes RedBeat entries via save()
- `backend/app/workers/celery_app.py` - beat_schedule reduced to empty dict with comment
- `docker-compose.yml` - Beat command prefixed with bootstrap; added postgres dependency

## Decisions Made
- Set `beat_schedule={}` explicitly (not removed entirely) to ensure RedBeat's statics cleanup is a no-op
- Bootstrap entries bypass statics_key because save() is called directly (not through update_from_dict)
- Added postgres dependency to beat service so bootstrap can read system_config
- Did NOT add backend dependency to beat -- bootstrap has fallback defaults if seed hasn't run yet

## Deviations from Plan
None - plan executed exactly as written

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- WORKER_TASK_MAP and BEAT_NAME_MAP are exported for Plan 05-02's PATCH endpoint validation
- update_redbeat_entry() is ready for Plan 05-02's runtime propagation
- System needs `docker compose build backend beat && docker compose up -d` to deploy

---
*Phase: 05-interval-control-backend*
*Completed: 2026-03-02*
