# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-24)

**Core value:** Operators always know the true health of their ProphetX platform — stale event statuses and low-liquidity markets are caught and resolved before they impact bettors.
**Current focus:** Phase 1 complete — ready for Phase 2 (Polling + Comparison)

## Current Position

Phase: 1 of 3 (Foundation) — COMPLETE
Plan: 3 of 3 in current phase
Status: Phase 1 complete
Last activity: 2026-02-25 — Completed Plan 01-03 (Celery workers, RedBeat, ProphetX + SportsDataIO clients, probe endpoint)

Progress: [███░░░░░░░] 33%

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: 14.3 min
- Total execution time: 0.71 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation | 3/3 | 43 min | 14.3 min |

**Recent Trend:**
- Last 5 plans: 8 min, 15 min, 20 min
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
- 01-03: Worker command uses -Q celery,default — Celery routes to 'celery' queue by default; -Q default alone silently starves the worker
- 01-03: ProphetX base URL (api.prophetx.co) DNS failure — placeholder; must get correct URL + real API key from Doug before Phase 2
- 01-03: SportsDataIO header auth locked (Ocp-Apim-Subscription-Key) — never query param; key in URL logs to Nginx access log

### Pending Todos

None.

### Blockers/Concerns

- **PHASE 2 BLOCKER:** ProphetX correct base URL needed — `api.prophetx.co` does not resolve; contact Doug for real URL + API key
- **PHASE 2 BLOCKER:** ProphetX status enum values still unconfirmed (no successful API call yet) — required before Phase 2 comparison logic
- SportsDataIO NFL/NCAAB/NCAAF endpoint paths return 404 (different URL format than NBA/MLB/NHL/Soccer) — needs research for Phase 2 sport coverage
- Event ID matching confidence threshold (0.90) must be validated against real ProphetX + SportsDataIO data early in Phase 2

## Session Continuity

Last session: 2026-02-25
Stopped at: Completed 01-03-PLAN.md — Celery workers, RedBeat scheduler, ProphetX + SportsDataIO clients, Admin probe endpoint, 5 unit tests. Phase 1 Foundation complete.
Resume file: None — clean state, Phase 1 done
