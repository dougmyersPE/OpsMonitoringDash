# Phase 5: Interval Control Backend - Context

**Gathered:** 2026-03-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Make poll intervals DB-backed and runtime-adjustable with server-enforced minimums. Remove static env var / beat_schedule coupling so intervals persist across Beat restarts. All 6 scheduled tasks (5 poll workers + critical check) become configurable. Phase 6 builds the frontend UI on top of this backend.

</domain>

<decisions>
## Implementation Decisions

### Minimum intervals per worker
- Minimum intervals are DB-configurable (not hardcoded constants) so they can be tuned without a code deploy
- Initial minimum values:
  - ProphetX: 60s
  - SportsDataIO: 15s
  - Odds API: 600s (10 min) — hard floor due to 500 calls/month free tier
  - Sports API: 600s (10 min) — floor due to per-sport daily quotas
  - ESPN: 60s
  - Critical Check: 15s
- PATCH request below minimum returns HTTP 422 with clear error message

### Default values and seeding
- Seed from env vars on first boot: startup hook reads POLL_INTERVAL_* env vars and inserts as initial DB rows (if no row exists yet)
- Consistent with existing admin user seed pattern (runs on every boot, checks if rows exist, inserts if missing)
- Keep current production defaults: ProphetX=300s, SDIO=30s, Odds=600s, Sports API=1800s, ESPN=600s
- Exception: Critical Check default lowered from 60s to 30s (DB query is cheap, more responsive safety net)
- DB is sole source of truth after initial seed — env vars are ignored for intervals once DB rows exist

### Critical check task
- poll_critical_check becomes configurable (same pattern as other workers) instead of hardcoded 60s
- Minimum: 15s (harmless — DB-only query, no external API calls)
- Default: 30s (lowered from current 60s)

### Claude's Discretion
- RedBeat integration approach (bootstrap from DB vs `from_key` API)
- Change propagation mechanism (how quickly DB changes reach running Beat)
- DB key naming convention for interval config rows
- Whether minimums are stored in same system_config table or separate

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches for the RedBeat integration and propagation mechanism.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `SystemConfig` model (app/models/config.py): Generic key-value store, already has GET/PATCH endpoints (admin-only)
- `PATCH /api/v1/config/{key}`: Upserts config values, admin-only auth — can extend for interval validation
- `config.py` Settings: Has `POLL_INTERVAL_*` env var definitions with defaults — seed source

### Established Patterns
- RedBeat already configured as Beat scheduler (`redbeat.RedBeatScheduler`) with Redis URL
- `beat_schedule` dict in `celery_app.py` reads env vars at import — this is what needs replacing
- Admin user seed runs on every startup, checks existence before insert — same pattern for interval seed
- `alert_only_mode` is read fresh from system_config at task start (not cached) — precedent for runtime config

### Integration Points
- `celery_app.py`: beat_schedule dict needs to be replaced with DB-bootstrapped RedBeat entries
- `app/api/v1/config.py`: PATCH endpoint needs interval-specific validation (min enforcement)
- Startup seed (app/main.py lifespan or similar): Add interval seeding alongside admin user seed
- 6 workers need their schedule entries managed by new bootstrap logic

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-interval-control-backend*
*Context gathered: 2026-03-02*
