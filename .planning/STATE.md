# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-24)

**Core value:** Operators always know the true health of their ProphetX platform — stale event statuses and low-liquidity markets are caught and resolved before they impact bettors.
**Current focus:** Phase 3 complete — all 5 plans executed (including gap closure 03-05)

## Current Position

Phase: 3 of 3 (Dashboard and Alerts) — COMPLETE
Plan: 5 of 5 in current phase — COMPLETE
Status: Phase 3 complete — all plans executed including gap closure
Last activity: 2026-02-26 — Completed Plan 03-05 (gap closure: send_alerts wired, SSE timeout-based banner, notification nav links, last_prophetx_poll field fix)

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**
- Total plans completed: 6
- Average duration: 9 min
- Total execution time: 0.92 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation | 3/3 | 43 min | 14.3 min |
| 02-monitoring-engine | 3/5 | 16 min | 5.3 min |
| 03-dashboard-and-alerts | 5/5 | 18 min | 3.6 min |

**Recent Trend:**
- Last 5 plans: 15 min, 20 min, 5 min, 5 min, 5 min
- Trend: stable

*Updated after each plan completion*
| Phase 02-monitoring-engine P02 | 5 | 2 tasks | 7 files |
| Phase 02-monitoring-engine P03 | 6 | 2 tasks | 12 files |
| Phase 03-dashboard-and-alerts P01 | 4 | 3 tasks | 17 files |
| Phase 03-dashboard-and-alerts P02 | 4 | 2 tasks | 10 files |
| Phase 03-dashboard-and-alerts P03 | 3 | 2 tasks | 8 files |
| Phase 03-dashboard-and-alerts P04 | 5 | 2 tasks | 4 files |
| Phase 03 P05 | 2min | 3 tasks | 5 files |

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
- 02-01: REVOKE on audit_log wrapped in DO block — role 'prophet_monitor' may not exist in dev/test where connecting user IS the table owner
- 02-01: Confidence threshold 0.90 — 'LA Lakers' vs 'Los Angeles Lakers' scores 0.8574 (below threshold); validate against real API data in 02-02+
- 02-01: .dockerignore excludes .venv — local macOS venv overwrote Linux container venv during docker build COPY without it
- 02-01: EventMatcher cache key pattern: match:px:{px_event_id}, 24h TTL; invalidate when scheduled_start changes
- [Phase 02-monitoring-engine]: SDIO_TO_PX_STATUS all ProphetX values marked UNCONFIRMED — update after prophetx_status_values_observed log captured from live API
- [Phase 02-monitoring-engine]: poll_sports_data polls NBA/MLB/NHL/Soccer only — NFL/NCAAB/NCAAF excluded per 404 from RESEARCH.md
- [Phase 02-monitoring-engine]: ProphetX write endpoint stubbed in update_event_status — log-only until endpoint path confirmed; expected PATCH /mm/update_sport_event_status
- [Phase 02-monitoring-engine]: RoleEnum.readonly (no underscore) used in API routers — plan used 'read_only' string but enum definition has no underscore; using enum avoids string drift
- 03-01: shadcn/ui v3 requires paths alias in root tsconfig.json (not tsconfig.app.json) for Vite init flow to detect the alias
- 03-01: Tailwind v4 uses CSS @import "tailwindcss" with @tailwindcss/vite plugin — no tailwind.config.ts file needed
- 03-01: useSse hook mounted once at DashboardPage level (in SseProvider) — never inside sub-components to prevent duplicate EventSource connections
- 03-01: TanStack Query cache key convention established: ["events"], ["markets"], ["worker-health"], ["notifications"]
- [Phase 03-dashboard-and-alerts]: SSE auth uses ?token= query param — EventSource API cannot send Authorization headers
- [Phase 03-dashboard-and-alerts]: Worker heartbeat via Redis key TTL (90s) not Celery inspect — simpler and more reliable
- [Phase 03-dashboard-and-alerts]: Alert deduplication: SETNX alert_dedup:{type}:{id} with 300s TTL prevents duplicate Slack alerts within 5 minutes
- [Phase 03-dashboard-and-alerts]: alert_only_mode read fresh from system_config DB at task start — not cached — real-time config changes take effect immediately
- [Phase 03-dashboard-and-alerts]: PATCH /mark-all-read route declared before PATCH /{notification_id}/read to prevent FastAPI path conflict where string 'mark-all-read' would be interpreted as UUID
- [Phase 03-dashboard-and-alerts]: Notification DB write placed before Slack guard in send_alerts.py — in-app notifications appear even without SLACK_WEBHOOK_URL configured
- 03-04: frontend/nginx.conf handles SPA fallback internally — outer nginx just proxy_passes to frontend:80, keeping concerns separated
- 03-04: SSE location block (/api/v1/stream) declared before /api/ block — most-specific match wins in Nginx location matching
- 03-04: chunked_transfer_encoding off in SSE block prevents Nginx from re-chunking SSE frames, ensuring individual event delivery
- [Phase 03]: 03-05: send_alerts import placed inside task body to avoid circular import — failure-path alert wrapped in its own try/except — Matches SystemConfig import pattern; prevents alert enqueue failure from blocking retry logic
- [Phase 03]: 03-05: lastOpenRef initialized to Date.now() at mount so 15s grace starts from mount preventing false-positive banner — Browser SSE connects asynchronously; starting grace period from mount avoids immediate banner flash on first load
- [Phase 03]: 03-05: Plain <a href> anchor used for notification nav (no useNavigate) — Hash URLs work without React Router for same-page scrolling; simpler than router dependency

### Pending Todos

None.

### Blockers/Concerns

- SportsDataIO NFL/NCAAB/NCAAF endpoint paths return 404 (different URL format than NBA/MLB/NHL/Soccer) — needs research
- Event ID matching confidence threshold (0.90) must be validated against real ProphetX + SportsDataIO data
- /api/v1/health/workers returns 404 despite correct route registration — needs investigation (likely path conflict or import error in workers module)

### Resolved
- ProphetX base URL: `https://api-ss-sandbox.betprophet.co/partner` — confirmed working (WS consumer live)
- ProphetX status enum values confirmed from live DB: `ended`, `live`, `not_started`

## Session Continuity

Last session: 2026-02-28
Stopped at: Critical alert tier shipped and deployed. All session work committed. Clean state.
Resume file: None
