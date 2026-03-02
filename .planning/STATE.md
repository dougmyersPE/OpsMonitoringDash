---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
last_updated: "2026-03-02T16:54:20.520Z"
progress:
  total_phases: 7
  completed_phases: 7
  total_plans: 18
  completed_plans: 18
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-01)

**Core value:** Operators always know the true health of their ProphetX platform — stale event statuses and low-liquidity markets are caught and resolved before they impact bettors.
**Current focus:** Milestone v1.1 — Stabilization + API Usage

## Current Position

Phase: 7 of 7 — Documentation Gap Closure — COMPLETE
Plan: 1 of 1 — COMPLETE
Status: Phase 7 complete — All documentation gaps closed; all 10 v1.1 requirements pass 3-source cross-reference; milestone v1.1 ready for archive
Last activity: 2026-03-02 — Executed Phase 7 (1 plan, 2 tasks, 5 files)

Progress: [██████████] 100% (v1.1 COMPLETE — All phases 4-7 done; milestone ready for archive)

## Performance Metrics

| Metric | Value |
|--------|-------|
| v1.1 requirements | 10 total |
| Mapped to phases | 10/10 |
| Phases defined | 3 (phases 4-6) |
| Plans complete | 5 |
| Phase 04 P01 | 15min | 2 tasks | 3 files |
| Phase 04 P02 | 4min | 3 tasks | 9 files |
| Phase 05 P01 | 8min | 2 tasks | 4 files |
| Phase 05 P02 | 10min | 2 tasks | 2 files |
| Phase 06 P01 | 12min | 2 tasks | 8 files |
| Phase 06 P02 | 15min | 2 tasks | 13 files |
| Phase 07 P01 | 5min | 2 tasks | 7 files |
| Phase 07 P01 | 5 | 2 tasks | 7 files |

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
- v1.1 roadmap: FREQ-03 (DB-backed intervals, Beat restart survives) assigned to Phase 5 before any UI — RedBeat restart overwrite pitfall must be resolved before frequency controls are exposed to operators
- v1.1 roadmap: USAGE-01 (call counters visible today) assigned to Phase 4 — counters start accumulating during stabilization, providing real data by Phase 6 frontend build
- v1.1 roadmap: api-sports.io quota must be captured and displayed per sport family (Basketball, Hockey, Baseball, American Football each have separate daily quotas) — single "Sports API: N/100" number would be misleading
- v1.1 roadmap: Redis counter pattern must use INCRBY (atomic) not GET/SET — non-atomic under --concurrency=6 causes undercounting
- 04-01: Use game_dt (actual parsed datetime from api-sports.io) instead of noon-UTC proxy (game_start_utc) in poll_sports_api.py time guard — eliminates false-positive root cause
- 04-01: Tighten time-distance threshold from >12h to >6h in both Sports API and ESPN workers — 6h is sufficient for UTC offsets while rejecting consecutive-day matches
- 04-01: Replace guard_midday with record_dt in ESPN worker for consistency with Sports API pattern
- [Phase 04]: Use game_dt (actual parsed datetime from api-sports.io) instead of noon-UTC proxy in time guard
- 04-02: Counter only at successful-completion path -- early returns do not inflate counts (preserves accuracy for Phase 6 usage display)
- 04-02: Usage endpoint requires readonly role (not admin) per USAGE-01 -- operators must see their own call data
- 04-02: Confidence validation is a server-side script requiring human judgment, not an automated test
- 05-01: beat_schedule={} (empty dict) instead of removing key entirely -- ensures setup_schedule() statics cleanup is a no-op
- 05-01: Bootstrap entries use entry.save() directly (not update_from_dict) so they never appear in statics_key and survive cleanup
- 05-01: Beat depends_on postgres (service_healthy) + redis (service_healthy) -- bootstrap needs DB access
- 05-01: Fallback defaults in beat_bootstrap.py match seed.py defaults -- correct behavior even if seed hasn't run yet
- 05-01: Critical check default lowered from 60s to 30s (DB query is cheap, more responsive safety net)
- 05-02: Deferred import of update_redbeat_entry inside _propagate_to_redbeat() -- avoids importing celery_app at module level in API process
- 05-02: run_in_executor for RedBeat propagation -- RedBeat uses sync StrictRedis client
- 05-02: RedBeat propagation is best-effort with try/except -- DB is source of truth, bootstrap syncs on next restart
- [Phase 07]: VERIFICATION.md files created post-audit to close documentation gaps; integration checker had already confirmed all E2E flows before these files were written
- [Phase 07]: REQUIREMENTS.md traceability corrected from Phase 7 to Phase 6 for USAGE-02, USAGE-03, USAGE-04, FREQ-01 — implemented in Phase 6, Phase 7 only closed the doc gap

### Pending Todos

(none)

### Blockers/Concerns

- api-sports.io quota headers: must inspect actual response headers from live worker before deciding SDIO quota display strategy (SDIO may expose no quota headers — but this is low-confidence absence of evidence, not confirmed)
- NCAAB/NCAAF SDIO endpoint paths: exact v3 URL paths must be confirmed via `curl` before modifying `sportsdataio.py`

### Resolved

- ProphetX base URL: `https://api-ss-sandbox.betprophet.co/partner` — confirmed working (WS consumer live)
- ProphetX status enum values confirmed from live DB: `ended`, `live`, `not_started`
- Sports API false-positive root cause: using noon-UTC proxy instead of actual start time, time-distance guard too loose (>12h) — FIXED in 04-01 (commit 338390e)
- RedBeat key names: bootstrap uses same names as previous beat_schedule dict (poll-prophetx, poll-sports-data, etc.) — resolved by using BEAT_NAME_MAP matching existing conventions
- celery_app import in API process: resolved via deferred import inside handler body (_propagate_to_redbeat), only runs when admin PATCHes an interval key

## Session Continuity

Last session: 2026-03-02
Stopped at: Phase 7 executed — all 1 plan complete; all v1.1 documentation gaps closed
Resume file: .planning/phases/07-documentation-gap-closure/07-01-SUMMARY.md
Next: Milestone v1.1 fully complete with all documentation in place. Run /gsd:complete-milestone to archive milestone v1.1.
