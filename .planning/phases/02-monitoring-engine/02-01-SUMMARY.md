---
phase: 02-monitoring-engine
plan: "01"
subsystem: database
tags: [sqlalchemy, alembic, postgresql, redis, rapidfuzz, fuzzy-matching, orm]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: Base ORM class, async DB session, initial migration (001), user/config models pattern

provides:
  - Five SQLAlchemy 2.x ORM models: Event, Market, EventIDMapping, AuditLog, Notification
  - Alembic migration 002 creating all 5 tables with indexes
  - EventMatcher class with confidence-scored fuzzy matching (rapidfuzz) and Redis caching
  - Monitoring package at backend/app/monitoring/

affects:
  - 02-02-prophetx-poller
  - 02-03-sdio-poller
  - 02-04-comparison-engine
  - 02-05-alerting

# Tech tracking
tech-stack:
  added:
    - rapidfuzz 3.14.3 (fuzzy string matching via token_sort_ratio)
  patterns:
    - SQLAlchemy 2.x mapped_column syntax with UUID(as_uuid=True) from sqlalchemy.dialects.postgresql
    - Alembic manual migrations (not autogenerate) matching pattern of 001_initial_schema.py
    - Redis match cache key pattern: match:px:{px_event_id}, 24h TTL
    - REVOKE statement in DO block for graceful dev/prod portability

key-files:
  created:
    - backend/app/models/event.py
    - backend/app/models/market.py
    - backend/app/models/event_id_mapping.py
    - backend/app/models/audit_log.py
    - backend/app/models/notification.py
    - backend/alembic/versions/002_monitoring_schema.py
    - backend/app/monitoring/__init__.py
    - backend/app/monitoring/event_matcher.py
    - backend/tests/test_event_matcher.py
    - backend/.dockerignore
  modified:
    - backend/app/models/__init__.py
    - backend/alembic/env.py
    - backend/pyproject.toml
    - backend/uv.lock

key-decisions:
  - "REVOKE on audit_log wrapped in DO block — role 'prophet_monitor' may not exist in dev/test environments where the connecting user IS the table owner (RESEARCH.md Pitfall 5 confirmed)"
  - "Confidence threshold 0.90 — calibration needed against real API data; 'LA Lakers' vs 'Los Angeles Lakers' scores 0.8574 (below threshold), identical names score 1.0"
  - "Time window 15 min full score, linear decay to 0.0 at 30 min — no score beyond 30 min delta"
  - "Added .dockerignore to exclude local .venv from container build — prevents macOS .venv overwriting Linux container .venv during docker build COPY"

patterns-established:
  - "Audit log is INSERT-only: class docstring documents this, REVOKE at DB level is defense-in-depth"
  - "Redis cache key pattern: match:px:{px_event_id} for match results; 24h TTL"
  - "EventMatcher.find_best_match returns None (no candidate) or dict with is_confirmed and optional is_flagged"

requirements-completed:
  - CORE-03

# Metrics
duration: 5min
completed: 2026-02-25
---

# Phase 2 Plan 01: Monitoring Schema and EventMatcher Summary

**Five SQLAlchemy models, Alembic migration 002, and EventMatcher using rapidfuzz token_sort_ratio with Redis match caching (24h TTL)**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-25T05:06:46Z
- **Completed:** 2026-02-25T05:12:00Z
- **Tasks:** 2
- **Files modified:** 14

## Accomplishments

- Created 5 ORM models (Event, Market, EventIDMapping, AuditLog, Notification) using SQLAlchemy 2.x mapped_column syntax
- Applied Alembic migration 002 creating all 5 tables + indexes; downgrade/upgrade cycle verified clean
- Implemented EventMatcher with weighted confidence scoring: 35% home team, 35% away team, 30% start time proximity
- Redis cache on confirmed matches (>= 0.90) with 24h TTL; cache hits skip fuzzy computation entirely
- All 6 unit tests pass; calibration log shows 'LA Lakers' vs 'Los Angeles Lakers' = 0.8574

## Task Commits

Each task was committed atomically:

1. **Task 1: Five ORM Models + Alembic Migration 002** - `6649fb1` (feat)
2. **Task 2: EventMatcher with Confidence Scoring and Redis Cache** - `1351a00` (feat)

**Plan metadata:** _(docs commit follows)_

## Files Created/Modified

- `backend/app/models/event.py` - Event ORM model with prophetx_event_id, status fields, flags
- `backend/app/models/market.py` - Market ORM model with ForeignKey to events, liquidity + per-market threshold
- `backend/app/models/event_id_mapping.py` - EventIDMapping linking PX event to SDIO game with confidence score
- `backend/app/models/audit_log.py` - AuditLog append-only model; INSERT-only docstring + DB REVOKE
- `backend/app/models/notification.py` - Notification model for Phase 3 SSE and in-app center
- `backend/alembic/versions/002_monitoring_schema.py` - Migration creating all 5 tables + REVOKE in DO block
- `backend/app/monitoring/__init__.py` - Monitoring package init (empty)
- `backend/app/monitoring/event_matcher.py` - EventMatcher with compute_confidence, cache helpers, find_best_match
- `backend/tests/test_event_matcher.py` - 6 unit tests covering sport mismatch, identical teams, similar names, time decay, empty list, cache hit
- `backend/.dockerignore` - Excludes local .venv from docker build context
- `backend/app/models/__init__.py` - Updated to register all 5 new models
- `backend/alembic/env.py` - Updated to import all 5 new models for autogenerate
- `backend/pyproject.toml` - Added rapidfuzz>=3.14.3
- `backend/uv.lock` - Updated lockfile

## Decisions Made

- REVOKE on `audit_log` uses a `DO $$ BEGIN IF EXISTS ... END $$` block — prevents migration failure when the connecting DB user is the table owner (RESEARCH.md Pitfall 5). Works correctly in production where `prophet_monitor` role exists.
- Added `.dockerignore` excluding `.venv` — the local uv venv (macOS/arm64) was being copied into the container (linux/amd64), breaking alembic startup with "exec: not found" error.
- Confidence threshold stays at 0.90 for now; calibration test reveals 'LA Lakers' vs 'Los Angeles Lakers' scores 0.8574 — this pair would trigger `is_flagged=True` until real API data validates the threshold.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] REVOKE statement failed when prophet_monitor role doesn't exist**
- **Found during:** Task 1 (Alembic migration application)
- **Issue:** `REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM prophet_monitor` raised `UndefinedObjectError` because the role doesn't exist in the dev Docker environment (user `prophet` is the table owner)
- **Fix:** Wrapped REVOKE in a `DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'prophet_monitor') THEN ... END IF; END $$` block
- **Files modified:** backend/alembic/versions/002_monitoring_schema.py
- **Verification:** Migration upgrade and downgrade/upgrade cycle complete without errors
- **Committed in:** 6649fb1 (Task 1 commit)

**2. [Rule 3 - Blocking] Missing .dockerignore caused local venv to overwrite container venv**
- **Found during:** Task 1 (Docker rebuild after uv add rapidfuzz)
- **Issue:** `uv add rapidfuzz` created a local `.venv` (macOS binary) that was copied into the container via `COPY . .`, overwriting the Linux `.venv`, causing alembic startup failure
- **Fix:** Created `backend/.dockerignore` excluding `.venv`, `__pycache__`, etc.
- **Files modified:** backend/.dockerignore (created)
- **Verification:** Docker rebuild and container startup succeeded
- **Committed in:** 6649fb1 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both auto-fixes required for correctness and Docker environment compatibility. No scope creep.

## Issues Encountered

- REVOKE migration failure due to missing role — resolved via DO block (Rule 1)
- Docker venv collision after local package install — resolved via .dockerignore (Rule 3)

## User Setup Required

None — no external service configuration required for this plan.

## Next Phase Readiness

- All 5 monitoring tables exist at revision 002
- EventMatcher ready for integration in 02-02 ProphetX poller and 02-03 SDIO poller
- Confidence threshold (0.90) should be validated against real ProphetX + SportsDataIO data early in Phase 2 (RESEARCH.md Pitfall 2)
- `prophetx_status` field on Event is marked UNCONFIRMED — must validate against live API in 02-02

---
*Phase: 02-monitoring-engine*
*Completed: 2026-02-25*
