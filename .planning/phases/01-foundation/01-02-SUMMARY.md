---
phase: 01-foundation
plan: 02
subsystem: auth
tags: [jwt, pyjwt, pwdlib, bcrypt, rbac, fastapi, sqlalchemy, asyncpg, pytest, pytest-asyncio]

# Dependency graph
requires:
  - phase: 01-01
    provides: "Docker Compose stack, async SQLAlchemy engine, User/SystemConfig models, RoleEnum, pydantic-settings with JWT_SECRET"
provides:
  - "POST /api/v1/auth/login — returns JWT access token using OAuth2PasswordRequestForm"
  - "RBAC dependency factory (require_role) enforcing admin/operator/readonly on any endpoint"
  - "GET /api/v1/config (Admin-only) — lists all SystemConfig key-value pairs"
  - "PATCH /api/v1/config/{key} (Admin-only) — upserts a system config entry"
  - "app/core/security.py — JWT encode/decode (PyJWT) and password hash/verify (pwdlib+bcrypt)"
  - "app/api/deps.py — get_current_user and require_role dependency factory"
  - "seed.py updated to use hash_password from security module"
  - "7 auth/RBAC integration tests all passing"
affects: [01-03, all-subsequent-plans, phase-03-dashboard]

# Tech tracking
tech-stack:
  added:
    - "PyJWT 2.x — jwt.encode/jwt.decode for access token create/verify"
    - "pwdlib 0.2 with BcryptHasher — password hashing (already in pyproject.toml, now used)"
    - "OAuth2PasswordBearer + OAuth2PasswordRequestForm — FastAPI built-in, enables Swagger Authorize button"
    - "pytest-asyncio asyncio_default_test_loop_scope=session — required for asyncpg pool stability across tests"
  patterns:
    - "RBAC via require_role(*roles) factory returning async _checker — dependency injection pattern"
    - "JWT payload: sub (user ID str), role (enum value str), exp (datetime)"
    - "Login endpoint uses form body (OAuth2PasswordRequestForm.username) not JSON body"
    - "Upsert pattern in config PATCH: create new SystemConfig if key not exists, update if exists"
    - "Session-scoped pytest client for ASGI integration tests — prevents asyncpg connection pool reuse across event loops"

key-files:
  created:
    - "backend/app/core/security.py"
    - "backend/app/api/deps.py"
    - "backend/app/api/v1/auth.py"
    - "backend/app/api/v1/config.py"
    - "backend/app/schemas/__init__.py"
    - "backend/app/schemas/auth.py"
    - "backend/app/schemas/config.py"
    - "backend/tests/test_auth.py"
  modified:
    - "backend/app/seed.py"
    - "backend/app/main.py"
    - "backend/tests/conftest.py"
    - "backend/pyproject.toml"

key-decisions:
  - "OAuth2PasswordRequestForm for login (form body not JSON) — enables Swagger UI Authorize button; form.username maps to email field"
  - "config.py created in Task 1 commit (not Task 2 as planned) — main.py imports both auth and config; importing before config.py exists crashes uvicorn"
  - "asyncio_default_test_loop_scope=session in pyproject.toml — asyncpg async pool connections are tied to event loop; function-scoped loops cause pool to fail on 2nd+ test"
  - "operator_token fixture uses SyncSessionLocal to create test user — avoids async session scope issues in fixture setup"

patterns-established:
  - "RBAC: require_role(RoleEnum.admin) in route dependencies=[Depends(...)] guards endpoints"
  - "JWT decode errors (ExpiredSignatureError, InvalidTokenError) map to HTTP 401 in get_current_user"
  - "Test client fixture is session-scoped; operator_token fixture creates user via sync session"

requirements-completed: [AUTH-01, AUTH-02, AUTH-03]

# Metrics
duration: 15min
completed: 2026-02-25
---

# Phase 1 Plan 02: JWT Auth and RBAC Summary

**POST /auth/login returning PyJWT access tokens, three-role RBAC via require_role dependency factory, Admin-only GET/PATCH /config endpoints, and 7 passing auth/RBAC integration tests**

## Performance

- **Duration:** 15 minutes
- **Started:** 2026-02-25T15:42:49Z
- **Completed:** 2026-02-25T15:58:00Z
- **Tasks:** 2 of 2
- **Files modified:** 12 (8 created, 4 modified)

## Accomplishments
- POST /api/v1/auth/login with OAuth2PasswordRequestForm returns JWT token for valid credentials, 401 for invalid — enables Swagger UI "Authorize" button
- RBAC dependency factory (require_role) enforces roles on any endpoint: unauthenticated returns 401, wrong role returns 403, correct role returns 200
- Admin-only GET/PATCH /config endpoints with upsert semantics (create if missing, update if exists)
- seed.py updated to use hash_password from security module (single source of truth for password hashing)
- 7 auth + 1 health = 8 total integration tests all passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Security module, RBAC dependency, and auth endpoint** - `f29bba8` (feat)
2. **Task 2: RBAC enforcement tests** - `56d9367` (feat)

**Plan metadata:** TBD (docs commit)

## Files Created/Modified

- `backend/app/core/security.py` - JWT encode/decode (PyJWT) and password hash/verify (pwdlib+bcrypt)
- `backend/app/api/deps.py` - OAuth2PasswordBearer scheme, get_current_user dependency, require_role factory
- `backend/app/api/v1/auth.py` - POST /auth/login using OAuth2PasswordRequestForm (Swagger-compatible)
- `backend/app/api/v1/config.py` - GET and PATCH /config (Admin-only) with upsert semantics
- `backend/app/schemas/auth.py` - LoginRequest, TokenResponse, UserInfo Pydantic v2 schemas
- `backend/app/schemas/config.py` - ConfigItem, ConfigUpdateRequest Pydantic v2 schemas
- `backend/app/schemas/__init__.py` - Package init exporting all schemas
- `backend/app/seed.py` - Updated to import hash_password from app.core.security
- `backend/app/main.py` - Added include_router for auth and config routers
- `backend/tests/test_auth.py` - 7 integration tests: login success/fail, unauthenticated 401, admin 200, operator 403, config upsert
- `backend/tests/conftest.py` - Session-scoped client fixture + operator_token fixture
- `backend/pyproject.toml` - asyncio_default_fixture_loop_scope + asyncio_default_test_loop_scope set to "session"

## Decisions Made

- **OAuth2PasswordRequestForm for login:** Uses form body (not JSON) so Swagger UI's "Authorize" button works out of the box. The form.username field maps to our email column — standard OAuth2 pattern.
- **config.py created early:** The plan intended config.py in Task 2, but main.py needed to import it in Task 1. Moving config.py creation into Task 1 was necessary to avoid an ImportError on startup. Treated as a Rule 3 (blocking) auto-fix.
- **Session-scoped pytest event loop:** asyncpg maintains connection pool tied to the event loop. Function-scoped loops (default) cause the pool to throw errors when connections from the prior loop are reused. Setting `asyncio_default_test_loop_scope = "session"` in pyproject.toml fixes this for all tests.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] config.py created in Task 1 commit instead of Task 2**
- **Found during:** Task 1 (main.py update)
- **Issue:** Plan listed config.py as a Task 2 file, but main.py imports `from app.api.v1 import auth, config, health` — uvicorn crashed with `ImportError: cannot import name 'config' from 'app.api.v1'` when the backend was rebuilt after Task 1 files were added
- **Fix:** Created config.py (as specified in Task 2's action block) during Task 1 to unblock main.py startup
- **Files modified:** backend/app/api/v1/config.py
- **Verification:** Backend started successfully, POST /auth/login returned 200 with access_token
- **Committed in:** f29bba8 (Task 1 commit)

**2. [Rule 1 - Bug] pytest-asyncio event loop scope causing asyncpg pool failures**
- **Found during:** Task 2 (running tests)
- **Issue:** 2 of 7 tests failed with asyncpg connection pool errors when running all tests together; passed individually. Root cause: asyncpg pool connections are bound to the event loop; function-scoped loops (default) create a new loop per test, breaking pool connections from prior test
- **Fix:** Added `asyncio_default_fixture_loop_scope = "session"` and `asyncio_default_test_loop_scope = "session"` to `[tool.pytest.ini_options]` in pyproject.toml; made `client` fixture session-scoped in conftest.py
- **Files modified:** backend/pyproject.toml, backend/tests/conftest.py
- **Verification:** All 8 tests pass (7 auth + 1 health)
- **Committed in:** 56d9367 (Task 2 commit)

**3. [Rule 2 - Missing Critical] operator_token fixture uses idempotent check**
- **Found during:** Task 2 (operator_token fixture implementation)
- **Issue:** Plan's operator_token fixture always inserted without checking for existing user — would fail on test re-runs with unique constraint violation
- **Fix:** Added existence check before inserting operator test user in SyncSessionLocal
- **Files modified:** backend/tests/conftest.py
- **Verification:** Running tests twice succeeds without UniqueConstraint error
- **Committed in:** 56d9367 (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (1 blocking, 1 bug, 1 missing critical)
**Impact on plan:** All auto-fixes necessary for correctness. No scope creep — all directly caused by the current task's work.

## Issues Encountered

- Docker image must be rebuilt (not just restarted) when adding new Python files — no volume mount means new files only appear after `docker compose build backend`. This is expected given the Dockerfile COPY-based approach.
- asyncpg connection pool and pytest-asyncio event loop scoping: a well-known issue in async FastAPI + SQLAlchemy testing. Session-scoped event loop is the recommended fix for pytest-asyncio 0.23+.

## User Setup Required

None — no external service configuration required. Stack runs fully from `.env`.

## Next Phase Readiness

- Auth foundation complete: login endpoint, RBAC dependency, and admin-only config endpoint all running
- Any endpoint can be protected by adding `Depends(require_role(RoleEnum.admin))` or `Depends(get_current_user)` as a dependency
- Phase 2 monitoring endpoints will use `require_role(RoleEnum.operator)` for operator-level access
- Phase 3 dashboard auth will reuse the same JWT token flow
- Plan 01-03 (Celery workers) can proceed — auth infrastructure is stable and tested

---
*Phase: 01-foundation*
*Completed: 2026-02-25*

## Self-Check: PASSED

- All 9 created/modified files verified on disk: FOUND
- Commit f29bba8 (Task 1): FOUND
- Commit 56d9367 (Task 2): FOUND
- POST /auth/login with valid credentials: HTTP 200
- GET /config without token: HTTP 401 (correctly rejected)
- No deprecated auth libraries (python-jose, passlib): CONFIRMED
- 8 integration tests passing: CONFIRMED (7 auth + 1 health)
