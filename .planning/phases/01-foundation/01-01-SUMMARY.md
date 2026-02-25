---
phase: 01-foundation
plan: 01
subsystem: infra
tags: [docker, postgres, redis, fastapi, sqlalchemy, alembic, celery, nginx, uv, pydantic-settings, PyJWT, pwdlib]

# Dependency graph
requires: []
provides:
  - "Docker Compose stack with 6 services (postgres, redis, backend, worker, beat, nginx)"
  - "Async SQLAlchemy engine + session factory for FastAPI (asyncpg)"
  - "Sync SQLAlchemy engine + session factory for Celery (psycopg2)"
  - "Alembic async migrations with users and system_config tables"
  - "Redis pool (async for FastAPI, sync for Celery) with maxmemory 256mb + allkeys-lru"
  - "GET /health endpoint confirming postgres and redis connectivity"
  - "pydantic-settings BaseSettings with ASYNC/SYNC_DATABASE_URL computed properties"
  - "RoleEnum single source of truth (admin, operator, readonly)"
  - "Admin user seeded from ADMIN_EMAIL/ADMIN_PASSWORD at startup"
  - "pytest async test scaffold with smoke test"
affects: [01-02, 01-03, all-subsequent-plans]

# Tech tracking
tech-stack:
  added:
    - "FastAPI 0.115 with lifespan context manager"
    - "SQLAlchemy 2.0 (asyncpg driver for FastAPI, psycopg2-binary for Celery)"
    - "Alembic 1.13 with async env.py pattern"
    - "Redis 7 alpine + redis-py 5 (async + sync pools)"
    - "PostgreSQL 16 alpine"
    - "pydantic-settings 2.x BaseSettings from .env"
    - "PyJWT 2.x (not deprecated python-jose)"
    - "pwdlib 0.2 with BcryptHasher (not deprecated passlib)"
    - "structlog 24.x for JSON logging"
    - "Celery 5.4 + celery-redbeat 2.x (Beat scheduler backed by Redis)"
    - "uv for dependency management with uv.lock for reproducible Docker builds"
    - "nginx alpine as reverse proxy"
  patterns:
    - "Two SQLAlchemy engines: create_async_engine for FastAPI, create_engine for Celery"
    - "Alembic env.py: do_run_migrations callback with begin_transaction inside run_sync"
    - "Startup order: alembic upgrade head -> seed -> uvicorn (tables must exist before seed)"
    - "Redis as separate async pool and sync client — share URL not connection objects"
    - "pydantic-settings with computed @property for connection URL construction"
    - "Docker healthcheck with condition: service_healthy on backend dependencies"

key-files:
  created:
    - "docker-compose.yml"
    - ".env.example"
    - "nginx/nginx.conf"
    - "backend/Dockerfile"
    - "backend/pyproject.toml"
    - "backend/uv.lock"
    - "backend/app/core/config.py"
    - "backend/app/core/constants.py"
    - "backend/app/db/session.py"
    - "backend/app/db/sync_session.py"
    - "backend/app/db/redis.py"
    - "backend/app/api/v1/health.py"
    - "backend/app/main.py"
    - "backend/app/seed.py"
    - "backend/app/models/user.py"
    - "backend/app/models/config.py"
    - "backend/alembic/env.py"
    - "backend/alembic/versions/001_initial_schema.py"
    - "backend/tests/conftest.py"
    - "backend/tests/test_health.py"
  modified: []

key-decisions:
  - "Use PyJWT + pwdlib (not python-jose/passlib) — confirmed from research; passlib breaks on Python 3.13, python-jose abandoned since 2021"
  - "Startup order: alembic upgrade head THEN seed THEN uvicorn — tables must exist before seed can query/insert"
  - "Alembic async env.py uses do_run_migrations callback with begin_transaction inside run_sync — both configure and run_migrations must be in same callback"
  - "nginx.conf must include events{} and http{} blocks — upstream directive not allowed at top level"
  - "Dockerfile adds ENV PATH for venv so all runtime commands use installed packages"
  - "uv.lock generated locally and committed so Docker build can use --frozen flag"

patterns-established:
  - "Two SQLAlchemy engines: async (asyncpg) for FastAPI routes, sync (psycopg2) for Celery workers"
  - "Alembic do_run_migrations callback pattern for async migrations"
  - "Admin user seeded via startup script checking existence before insert"

requirements-completed: [CORE-01, CORE-02]

# Metrics
duration: 8min
completed: 2026-02-25
---

# Phase 1 Plan 01: Docker Compose Foundation Summary

**Full-stack Docker skeleton running: FastAPI + async SQLAlchemy (asyncpg) + sync engine (psycopg2) + Redis (256mb/allkeys-lru) + Alembic migration creating users/system_config tables + GET /health returning 200 with postgres and redis confirmed**

## Performance

- **Duration:** 8 minutes
- **Started:** 2026-02-25T15:31:14Z
- **Completed:** 2026-02-25T15:39:26Z
- **Tasks:** 2 of 2
- **Files modified:** 22 created, 3 auto-fixed

## Accomplishments
- Docker Compose stack with all 6 services (postgres, redis, backend, worker, beat, nginx) running — worker/beat pending Plan 01-03 for celery_app.py
- Alembic async migration (001_initial_schema) creating `users` and `system_config` tables; admin user seeded from environment variables
- GET /health returns `{"status":"ok","postgres":"connected","redis":"connected"}` — postgres and redis both confirmed live
- Redis maxmemory=268435456 (256mb) and maxmemory-policy=allkeys-lru confirmed via redis-cli
- Two SQLAlchemy engines: async (asyncpg) for FastAPI routes, sync (psycopg2) for Celery workers
- Typed pydantic-settings with computed ASYNC_DATABASE_URL and SYNC_DATABASE_URL properties
- PyJWT + pwdlib used from day one (not deprecated python-jose/passlib)
- pytest async scaffold with smoke test (integration test requires running postgres + redis)

## Task Commits

Each task was committed atomically:

1. **Task 1: Project skeleton, Docker Compose, and settings** - `5735001` (feat)
2. **Task 2: SQLAlchemy models, Alembic async migration, and smoke test** - `4b17471` (feat)

**Plan metadata:** TBD (docs commit)

## Files Created/Modified

- `docker-compose.yml` - 6 services with health checks and condition: service_healthy dependencies
- `.env.example` - 14 environment variables (postgres, redis, jwt, api keys, admin seed)
- `nginx/nginx.conf` - Reverse proxy with events/http/upstream blocks
- `backend/Dockerfile` - python:3.12-slim + uv + venv PATH setup
- `backend/pyproject.toml` - Dependencies: FastAPI, SQLAlchemy, asyncpg, psycopg2, Alembic, redis, PyJWT, pwdlib, celery, redbeat, structlog
- `backend/uv.lock` - Lockfile for reproducible Docker builds (1576 lines, 77 packages)
- `backend/app/core/config.py` - pydantic-settings BaseSettings with ASYNC/SYNC_DATABASE_URL computed properties
- `backend/app/core/constants.py` - RoleEnum (admin, operator, readonly) single source of truth
- `backend/app/db/session.py` - Async engine + async_sessionmaker + Base + get_async_session()
- `backend/app/db/sync_session.py` - Sync engine + sessionmaker + get_sync_session()
- `backend/app/db/redis.py` - Async Redis pool (get_redis_client) + sync (get_sync_redis)
- `backend/app/api/v1/health.py` - GET /health pinging postgres and redis
- `backend/app/main.py` - FastAPI app factory with lifespan + structlog JSON logging
- `backend/app/seed.py` - Admin user seeding (alembic runs first, seed checks existence)
- `backend/app/models/user.py` - User model (UUID PK, email, password_hash, role, name, is_active, created_at, last_login)
- `backend/app/models/config.py` - SystemConfig model (UUID PK, key, value, description, updated_at)
- `backend/app/models/__init__.py` - Imports Base + all models for Alembic metadata registration
- `backend/alembic.ini` - Alembic config (sqlalchemy.url intentionally blank, set in env.py)
- `backend/alembic/env.py` - Async Alembic env.py with do_run_migrations callback pattern
- `backend/alembic/versions/001_initial_schema.py` - Manual migration: users + system_config tables + unique indexes
- `backend/tests/conftest.py` - Async test client fixture (ASGITransport)
- `backend/tests/test_health.py` - Smoke test: GET /health returns 200

## Decisions Made

- **PyJWT + pwdlib over python-jose/passlib:** Research confirmed python-jose abandoned since 2021 (CVEs), passlib breaks on Python 3.13. Using corrected libraries from day one avoids painful auth migration later.
- **Startup command order:** `alembic upgrade head && python -m app.seed && uvicorn` — seed must query the users table, which only exists after migration runs.
- **Alembic async pattern:** `do_run_migrations(connection)` callback with `context.configure()` + `with context.begin_transaction(): context.run_migrations()` inside single `run_sync` call — separating these into two `run_sync` calls breaks the migration context.
- **uv.lock committed:** Required for `--frozen` flag in Dockerfile; generated locally before first build.
- **Worker/beat services declared now, implemented later:** Services are defined in docker-compose.yml to keep all service definitions in one place; they will fail gracefully until Plan 01-03 creates celery_app.py.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Generated uv.lock for Docker --frozen build**
- **Found during:** Task 1 (docker compose build backend)
- **Issue:** Dockerfile uses `uv sync --frozen --no-cache` but no uv.lock existed — Docker build failed with "Unable to find lockfile at uv.lock"
- **Fix:** Ran `uv lock` locally to generate uv.lock (1576 lines, 77 packages resolved)
- **Files modified:** backend/uv.lock (new)
- **Verification:** Docker build completed successfully
- **Committed in:** 5735001 (Task 1 commit)

**2. [Rule 1 - Bug] Fixed Dockerfile: venv not on PATH**
- **Found during:** Task 2 (backend startup)
- **Issue:** `uv sync` creates `.venv` but Docker CMD runs with system Python — `ModuleNotFoundError: No module named 'structlog'`
- **Fix:** Added `ENV PATH="/app/.venv/bin:$PATH"` after uv sync step
- **Files modified:** backend/Dockerfile
- **Verification:** Backend starts successfully, all imports resolve
- **Committed in:** 4b17471 (Task 2 commit)

**3. [Rule 1 - Bug] Fixed startup order: seed ran before alembic**
- **Found during:** Task 2 (backend startup)
- **Issue:** Plan specified `python -m app.seed && alembic upgrade head` but seed queries users table before it exists — `ProgrammingError: relation "users" does not exist`
- **Fix:** Reordered to `alembic upgrade head && python -m app.seed && uvicorn`
- **Files modified:** docker-compose.yml
- **Verification:** Alembic migration ran first, seed created admin user successfully
- **Committed in:** 4b17471 (Task 2 commit)

**4. [Rule 1 - Bug] Fixed Alembic env.py: split run_sync calls broke migration**
- **Found during:** Task 2 (alembic migration ran but tables not created)
- **Issue:** Initial env.py called `configure` and `run_migrations` in separate `run_sync` calls — migration logged "Running upgrade -> 001" but tables weren't created (transaction context not maintained)
- **Fix:** Extracted `do_run_migrations(connection)` function that calls `context.configure()` + `with context.begin_transaction(): context.run_migrations()` in single callback, passed to single `await connection.run_sync(do_run_migrations)`
- **Files modified:** backend/alembic/env.py
- **Verification:** `\dt` in postgres shows users, system_config, alembic_version tables
- **Committed in:** 4b17471 (Task 2 commit)

**5. [Rule 1 - Bug] Fixed nginx.conf: upstream not in http block**
- **Found during:** Task 2 (nginx startup failure)
- **Issue:** nginx.conf had `upstream backend { ... }` at top level — nginx requires it inside `http {}` block. Error: `"upstream" directive is not allowed here`
- **Fix:** Wrapped in proper `events {}` and `http {}` blocks
- **Files modified:** nginx/nginx.conf
- **Verification:** nginx container starts, GET http://localhost/api/v1/health returns 200
- **Committed in:** 4b17471 (Task 2 commit)

---

**Total deviations:** 5 auto-fixed (1 blocking, 4 bugs)
**Impact on plan:** All auto-fixes were necessary for the stack to function. No scope creep — all fixes directly related to getting the declared infrastructure working.

## Issues Encountered

- The async Alembic env.py pattern from the research file (two separate `run_sync` calls) silently failed — the migration appeared to run but tables weren't created. The correct pattern requires a single callback function passed to `run_sync` that handles both `configure` and `run_migrations` within a `begin_transaction` context.

## User Setup Required

None — no external service configuration required. Stack runs fully from `.env` (copied from `.env.example`).

## Next Phase Readiness

- All infrastructure is running: postgres, redis, FastAPI backend, nginx proxy all confirmed healthy
- Database schema in place (users + system_config tables via migration 001)
- Admin user seeded and ready for auth implementation (Plan 01-02)
- Two SQLAlchemy engines ready: async for FastAPI routes (Plan 01-02 auth endpoints), sync for Celery tasks (Plan 01-03)
- Worker/beat services defined in docker-compose.yml — awaiting celery_app.py from Plan 01-03
- pytest scaffold ready for tests in Plans 01-02 and 01-03

---
*Phase: 01-foundation*
*Completed: 2026-02-25*

## Self-Check: PASSED

- All 20 created files verified on disk: FOUND
- Commit 5735001 (Task 1): FOUND
- Commit 4b17471 (Task 2): FOUND
- GET /health live response: `{"status":"ok","postgres":"connected","redis":"connected"}`
- Redis maxmemory: 268435456 (256mb), maxmemory-policy: allkeys-lru
- DB tables: alembic_version, system_config, users — all present
