---
phase: 12-consumer-foundation
plan: 01
subsystem: database
tags: [pika, rabbitmq, alembic, postgresql, opticodds, config]

# Dependency graph
requires:
  - phase: 11-tech-debt
    provides: Migration 009 (drop sports_api_status) and Sports API removal
provides:
  - pika AMQP dependency declared
  - OpticOdds env vars (API key, RMQ credentials, base URL) available via Settings
  - opticodds_status column on events table (migration 010)
  - Event model column mapping for opticodds_status
affects:
  - 12-02-consumer-module
  - 12-03-docker-integration

# Tech tracking
tech-stack:
  added: [pika>=1.3.2 (AMQP client for RabbitMQ/OpticOdds consumer)]
  patterns: [nullable status column per data source, env vars with None defaults for optional integrations]

key-files:
  created:
    - backend/alembic/versions/010_add_opticodds_status.py
  modified:
    - backend/pyproject.toml
    - backend/app/core/config.py
    - backend/app/models/event.py
    - .env.example

key-decisions:
  - "OpticOdds credentials use str|None=None defaults so deployments without credentials do not fail on startup"
  - "pika added as direct dependency (not optional) since consumer module requires it"

patterns-established:
  - "New external data source status column: String(50) nullable, grouped with other *_status columns in Event model"
  - "Migration chain: each migration references immediate predecessor via down_revision"

requirements-completed: [TNNS-01]

# Metrics
duration: 15min
completed: 2026-04-03
---

# Phase 12 Plan 01: Consumer Foundation Summary

**pika AMQP dependency, four OpticOdds Settings fields, and opticodds_status VARCHAR(50) column (migration 010) laying the schema foundation for the OpticOdds AMQP consumer**

## Performance

- **Duration:** 15 min
- **Started:** 2026-04-03T14:00:00Z
- **Completed:** 2026-04-03T14:15:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added `pika>=1.3.2,<2.0` to pyproject.toml — AMQP client library required by Plan 02 consumer module
- Added `OPTICODDS_API_KEY`, `OPTICODDS_RMQ_USERNAME`, `OPTICODDS_RMQ_PASSWORD`, `OPTICODDS_BASE_URL` to Settings class with safe None defaults
- Created alembic migration 010 adding `opticodds_status VARCHAR(50) NULLABLE` to events table (chain: 009 -> 010)
- Added `opticodds_status` mapped_column to Event model, grouped with all other `*_status` columns

## Task Commits

Each task was committed atomically:

1. **Task 1: Add pika dependency and OpticOdds config settings** - `978d53d` (feat)
2. **Task 2: Add opticodds_status column — migration 010 and Event model** - `76afe92` (feat)

## Files Created/Modified

- `backend/pyproject.toml` - Added pika>=1.3.2,<2.0 dependency
- `backend/app/core/config.py` - Added OpticOdds section with 4 env var fields
- `.env.example` - Documented all four OpticOdds env vars
- `backend/alembic/versions/010_add_opticodds_status.py` - New migration adding opticodds_status column
- `backend/app/models/event.py` - Added opticodds_status mapped_column

## Decisions Made

- OpticOdds credentials use `str | None = None` defaults so existing deployments without credentials do not break on startup — optional integration pattern consistent with ODDS_API_KEY and other optional sources
- `pika` added as a core (not optional) dependency since the consumer module is a first-class service in Plan 02

## Deviations from Plan

**One structural deviation:** The plan's interface section assumed `oddsblaze_status` would be the last status column in the worktree's event.py, but the worktree branch predates the OddsBlaze integration (phases 8-11 were executed in the main branch). `opticodds_status` was therefore added after `espn_status` (the last status column present in this worktree). When this branch merges to main, the column will appear between `oddsblaze_status` and `status_source` — functionally correct, order is cosmetic only.

No auto-fix deviation rules triggered.

## Issues Encountered

The executor worktree is at commit `b31f2af` (pre-v1.2), which does not include migrations 007-009 or the phases 8-11 code changes. The plan was executed against this branch state; migration 010 correctly references `down_revision = "009"` so the chain will be valid when merged to main where migrations 007-009 exist.

## Next Phase Readiness

- Plan 02 (consumer module) can now import `pika`, read OpticOdds credentials via `settings.OPTICODDS_API_KEY` etc., and write `opticodds_status` to the events table
- Plan 03 (Docker integration) can reference the consumer service once Plan 02 is complete
- No blockers for Plan 02 execution

---
*Phase: 12-consumer-foundation*
*Completed: 2026-04-03*
