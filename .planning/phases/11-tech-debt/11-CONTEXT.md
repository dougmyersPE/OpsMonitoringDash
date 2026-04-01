# Phase 11: Tech Debt - Context

**Gathered:** 2026-04-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Remove the Sports API (api-sports.io) integration entirely — client, poll worker, DB column, usage tracking, health checks, mismatch detector references, and all related tests. This eliminates the architectural inconsistency (DEBT-01) at the source rather than refactoring it. Update roadmap and requirements to reflect removal instead of refactor.

</domain>

<decisions>
## Implementation Decisions

### Removal Strategy
- **D-01:** Full removal — drop DB column via Alembic migration, remove worker, remove from usage page, health checks, mismatch detector, config, and tests. No deprecated stubs or historical data preservation.
- **D-02:** Phase goal pivoted from "refactor SportsApiClient to use BaseAPIClient" to "remove Sports API entirely." Motivation: data is redundant with SportsDataIO + ESPN + OddsBlaze, and API cost/quota isn't worth the coverage.

### Data Source Coverage
- **D-03:** SportsDataIO + ESPN + OddsBlaze are sufficient as remaining real-world status sources. Sports API was the least reliable and added noise rather than signal.

### Roadmap & Requirements
- **D-04:** Update ROADMAP.md Phase 11 goal and REQUIREMENTS.md DEBT-01 to reflect removal instead of refactor. Keep docs honest.

### Claude's Discretion
- **D-05:** Match logic cleanup — Claude decides whether to simply remove sports_api_status from compute_status_match / compute_is_critical or recalibrate thresholds/weights. Goal: cleanest logic after removal.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Sports API Integration (to be removed)
- `backend/app/clients/sports_api.py` — SportsApiClient class and sport configs (DELETE target)
- `backend/app/workers/poll_sports_api.py` — Poll worker task (DELETE target)

### BaseAPIClient Pattern (reference for what "correct" looks like)
- `backend/app/clients/base.py` — BaseAPIClient with retry, quota hook, context manager
- `backend/app/clients/odds_api.py` — OddsAPIClient as example of proper BaseAPIClient subclass with _capture_quota_headers

### Dependent Code (must be updated)
- `backend/app/models/event.py` — Event model with sports_api_status column
- `backend/app/monitoring/mismatch_detector.py` — Uses sports_api_status in status comparison
- `backend/app/api/v1/health.py` — Health endpoint includes Sports API worker
- `backend/app/api/v1/usage.py` — API Usage endpoint tracks Sports API quota/calls
- `backend/app/workers/celery_app.py` — Worker registration
- `backend/app/workers/beat_bootstrap.py` — Beat schedule bootstrap
- `backend/app/core/config.py` — Sports API settings
- `backend/app/schemas/event.py` — Event schema with sports_api_status field
- `backend/app/workers/rollup_api_usage.py` — Usage rollup includes Sports API

### Planning Docs
- `.planning/ROADMAP.md` — Phase 11 goal to update
- `.planning/REQUIREMENTS.md` — DEBT-01 requirement to update

</canonical_refs>

<code_context>
## Existing Code Insights

### Files to Delete
- `backend/app/clients/sports_api.py` — Entire client (98-line class + helpers)
- `backend/app/workers/poll_sports_api.py` — Entire poll worker
- `backend/alembic/versions/004_rename_api_football_to_sports_api.py` — Historical migration (keep — already applied)

### Files to Modify (~26 touchpoints)
- Event model: drop `sports_api_status` column (new Alembic migration)
- Event schema: remove `sports_api_status` field
- Mismatch detector: remove sports_api_status from source comparison logic
- Health endpoint: remove Sports API worker from health checks
- Usage endpoint: remove Sports API quota display
- Config: remove SPORTS_API_KEY and related settings
- Celery app: remove poll_sports_api task registration
- Beat bootstrap: remove Sports API poll schedule
- Source toggle: remove Sports API toggle if present
- Rollup: remove Sports API from usage rollup
- Tests: remove/update tests referencing Sports API

### Established Patterns
- Other clients (SDIO, ESPN, OddsBlaze, OddsAPI) all inherit BaseAPIClient — this pattern is stable
- Alembic migrations follow sequential numbering (currently at 008+)

### Integration Points
- Frontend API Usage page likely renders Sports API quota — needs dashboard update
- Frontend mismatch highlighting may reference sports_api_status

</code_context>

<specifics>
## Specific Ideas

- User explicitly chose removal over refactoring as better use of resources
- Sports API described as "least reliable" and "adding noise, not signal"
- Both redundant data AND API cost cited as motivation

</specifics>

<deferred>
## Deferred Ideas

- **DEBT-02 (Redis MGET batching):** Still future — not bundled since Sports API quota reads will be removed entirely. Remaining providers (SDIO, Odds API) could still benefit from MGET but that's a separate concern.

</deferred>

---

*Phase: 11-tech-debt*
*Context gathered: 2026-04-01*
