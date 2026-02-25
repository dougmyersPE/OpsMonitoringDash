# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-24)

**Core value:** Operators always know the true health of their ProphetX platform — stale event statuses and low-liquidity markets are caught and resolved before they impact bettors.
**Current focus:** Phase 1 — Foundation

## Current Position

Phase: 1 of 3 (Foundation)
Plan: 2 of 3 in current phase
Status: In progress
Last activity: 2026-02-25 — Completed Plan 01-02 (JWT auth, RBAC, /auth/login, /config endpoints, 8 passing tests)

Progress: [██░░░░░░░░] 22%

## Performance Metrics

**Velocity:**
- Total plans completed: 2
- Average duration: 11.5 min
- Total execution time: 0.38 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation | 2/3 | 23 min | 11.5 min |

**Recent Trend:**
- Last 5 plans: 8 min, 15 min
- Trend: stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Pre-roadmap: Use RedBeat (not default file-based scheduler) from day one — prevents duplicate tasks on Beat restart
- Pre-roadmap: Set Redis maxmemory 256mb + allkeys-lru in docker-compose.yml during Phase 1 — prevents OOM killing the Celery broker
- Pre-roadmap: Event ID matching layer (CORE-03) must be built and validated before poll workers produce meaningful comparisons
- Pre-roadmap: Alert deduplication (ALERT-02) ships in same phase as alerting (ALERT-01) — cannot be retrofitted
- Pre-roadmap: Alert-only mode (ALERT-03) ships before alerting is enabled in production — safe rollout plan
- 01-01: Use PyJWT + pwdlib (not python-jose/passlib) — python-jose abandoned since 2021, passlib breaks on Python 3.13
- 01-01: Startup order: alembic upgrade head THEN seed THEN uvicorn — seed queries users table which requires migration first
- 01-01: Alembic async env.py pattern: single do_run_migrations callback with configure + begin_transaction inside run_sync
- 01-01: nginx.conf requires events{} and http{} wrapper blocks — upstream directive not valid at top level
- 01-01: Worker/beat services declared in docker-compose.yml now but await celery_app.py from Plan 01-03
- 01-02: OAuth2PasswordRequestForm for login (form body not JSON) — enables Swagger UI Authorize button; form.username maps to email
- 01-02: config.py created in Task 1 commit (not Task 2 as planned) — main.py imports both auth and config; config.py must exist before uvicorn starts
- 01-02: asyncio_default_test_loop_scope=session in pyproject.toml — asyncpg pool connections are tied to event loop; function-scoped loops break pool on 2nd+ test
- 01-02: operator_token fixture uses SyncSessionLocal to create test user — avoids async session scope issues in fixture setup

### Pending Todos

None.

### Blockers/Concerns

- ProphetX status enum values are unconfirmed — Phase 1 API client must log raw responses before Phase 2 builds comparison logic
- Event ID matching confidence threshold (0.90) must be validated against real ProphetX + SportsDataIO data early in Phase 2

## Session Continuity

Last session: 2026-02-25
Stopped at: Completed 01-02-PLAN.md — JWT auth, RBAC dependency, /auth/login, /config endpoints, and 8 passing integration tests. Ready for Plan 01-03 (Celery workers).
Resume file: None — clean state, no mid-plan work
