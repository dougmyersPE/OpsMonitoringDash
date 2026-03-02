---
phase: 06-apiusagepage
status: passed
verified: 2026-03-02
requirements: [USAGE-02, USAGE-03, USAGE-04, FREQ-01]
---

# Phase 6: ApiUsagePage - Verification

## Phase Goal

Operators and Admins can open the API Usage tab and immediately see provider quota status, per-worker call volume today and over the past 7 days, projected monthly burn rate, and — for Admins — live-updating interval controls per worker.

## Requirements Verification

### USAGE-02: Operator can see provider-reported quota

**Status: VERIFIED**

Evidence from `06-01-SUMMARY.md` and `06-02-SUMMARY.md`:
- **Backend** (`06-01`): `backend/app/clients/odds_api.py` captures `x-requests-remaining` and `x-requests-used` response headers from each Odds API call; `backend/app/clients/sports_api.py` captures `x-ratelimit-requests-remaining` and `x-ratelimit-requests-limit` per sport family (Basketball, Hockey, Baseball, American Football, Soccer). Both write to Redis with 25h TTL.
- **Frontend** (`06-02`): `OddsApiQuotaCard` renders a progress bar (green/amber/red at 50%/80% thresholds) with used/remaining/limit numbers. `SportsApiQuotaCard` shows an aggregate summary with an expandable per-sport breakdown via useState toggle. Null values from Redis display as "—" (not 0).
- Quota data flows through the extended `GET /api/v1/usage` endpoint in the `quota` section.

### USAGE-03: Operator can see a 7-day call volume history chart

**Status: VERIFIED**

Evidence from `06-01-SUMMARY.md` and `06-02-SUMMARY.md`:
- **Backend** (`06-01`): `ApiUsageSnapshot` SQLAlchemy model (`backend/app/models/api_usage_snapshot.py`) with `UNIQUE(worker_name, snapshot_date)` constraint stores daily per-worker call counts. Alembic migration 006 creates the `api_usage_snapshots` table with a date index. Nightly rollup worker (`backend/app/workers/rollup_api_usage.py`) runs at 02:00 UTC and persists yesterday's Redis counters to PostgreSQL using idempotent INSERT ON CONFLICT UPDATE.
- **Frontend** (`06-02`): `CallVolumeChart` uses Recharts v3.7.0 (React 19 compatible) stacked bar chart with per-worker color coding: ProphetX=indigo, SportsDataIO=green, Odds API=amber, Sports API=blue, ESPN=pink. XAxis dates formatted via date-fns. Empty state shows "Collecting data" message rather than a blank chart frame.
- Today's data is appended from live Redis counters, ensuring the chart is not blank on day one.

### USAGE-04: Operator can see projected monthly call volume

**Status: VERIFIED**

Evidence from `06-01-SUMMARY.md` and `06-02-SUMMARY.md`:
- **Backend** (`06-01`): Extended `GET /api/v1/usage` endpoint returns a `projections` section with monthly total and per-worker projected call counts. Projections are computed from current poll intervals retrieved from system_config.
- **Frontend** (`06-02`): `ProjectionCard` component shows the monthly total and per-worker projected call count breakdown with the current interval displayed alongside each worker. The page uses `useQuery(["usage"])` with a 30-second `refetchInterval`, so projections update within 30 seconds when an Admin changes a poll interval.

### FREQ-01: Admin can adjust poll frequency per worker, changes take effect within 5 seconds

**Status: VERIFIED**

Evidence from `06-02-SUMMARY.md` (interval controls) combined with Phase 5 backend (RedBeat propagation):
- `IntervalSection` component renders an admin-only table (role check in `ApiUsagePage.tsx`) with inline Edit/Save/Cancel controls for each worker's poll interval.
- Uses `useMutation` to call `PATCH /api/v1/config/{key}`. Client-side minimum validation runs before the server call. Server 422 errors display inline as red text. Success shows a green checkmark flash (1500ms via setTimeout).
- Backend `_propagate_to_redbeat()` in `backend/app/api/v1/config.py` writes the new interval to Redis (RedBeat) immediately after DB commit, using `run_in_executor` (sync StrictRedis client wrapped for async). Beat picks up the new interval within ~5 seconds.
- IntervalSection is hidden for Operator and Read-Only users — only visible when `user.role === 'admin'`.

## Success Criteria Check

| Criterion | Status |
|-----------|--------|
| Operator can see used/remaining/limit quota for Odds API and per-sport Sports API; null fields show "—" | VERIFIED -- OddsApiQuotaCard + SportsApiQuotaCard render quota with null guard |
| Operator can see 7-day bar chart of call volume per worker; chart is not blank on day one | VERIFIED -- ApiUsageSnapshot DB model + today's Redis data appended to history array |
| Operator can see projected monthly call volume computed from current polling rate; projection updates when Admin changes interval | VERIFIED -- projections section in /usage endpoint + ProjectionCard + 30s refetch |
| Admin can enter new poll interval, save it, and change takes effect within 5 seconds without container restart | VERIFIED -- IntervalSection + PATCH /config + _propagate_to_redbeat() via run_in_executor |

## Must-Haves Verification

### Plan 06-01 Must-Haves

| Truth | Verified |
|-------|----------|
| Odds API client captures x-requests-remaining/used to Redis | YES -- override _capture_quota_headers() in odds_api.py |
| Sports API client captures per-sport quota headers to Redis | YES -- per sport family (basketball, hockey, baseball, football, soccer) |
| ApiUsageSnapshot model exists with UNIQUE(worker_name, snapshot_date) | YES -- backend/app/models/api_usage_snapshot.py |
| Alembic migration 006 creates api_usage_snapshots table with date index | YES -- backend/alembic/versions/006_api_usage_snapshots.py |
| Nightly rollup worker registered in celery_app with crontab at 02:00 UTC | YES -- backend/app/workers/rollup_api_usage.py |
| GET /api/v1/usage returns quota, history (DB + today), intervals, and projections | YES -- full rewrite of backend/app/api/v1/usage.py |
| Today's data appended from Redis to history array | YES -- seamless chart experience before first rollup |

### Plan 06-02 Must-Haves

| Truth | Verified |
|-------|----------|
| OddsApiQuotaCard renders progress bar with green/amber/red thresholds | YES -- frontend/src/components/usage/OddsApiQuotaCard.tsx |
| SportsApiQuotaCard has expandable per-sport breakdown | YES -- useState toggle, collapsed by default |
| Null quota values render as "—" not 0 | YES -- null guard in both quota cards |
| CallVolumeChart uses Recharts stacked bars with per-worker colors | YES -- frontend/src/components/usage/CallVolumeChart.tsx |
| ProjectionCard shows monthly total and per-worker projections | YES -- frontend/src/components/usage/ProjectionCard.tsx |
| IntervalSection visible only to admin users | YES -- role check in ApiUsagePage.tsx |
| IntervalSection uses useMutation with validation and success flash | YES -- frontend/src/components/usage/IntervalSection.tsx |
| /usage route added with ProtectedRoute wrapper | YES -- frontend/src/App.tsx |
| "API Usage" nav item added to sidebar | YES -- frontend/src/components/Layout.tsx with Gauge icon |

## Key Artifacts

| Artifact | Path |
|----------|------|
| Odds API quota header capture | backend/app/clients/odds_api.py |
| Sports API quota header capture | backend/app/clients/sports_api.py |
| Base client quota hook | backend/app/clients/base.py |
| Daily snapshot model | backend/app/models/api_usage_snapshot.py |
| DB migration 006 | backend/alembic/versions/006_api_usage_snapshots.py |
| Nightly rollup worker | backend/app/workers/rollup_api_usage.py |
| Extended usage endpoint | backend/app/api/v1/usage.py |
| Main ApiUsagePage component | frontend/src/pages/ApiUsagePage.tsx |
| Usage API client + types | frontend/src/api/usage.ts |
| Quota display components | frontend/src/components/usage/OddsApiQuotaCard.tsx, SportsApiQuotaCard.tsx |
| 7-day chart component | frontend/src/components/usage/CallVolumeChart.tsx |
| Projection card | frontend/src/components/usage/ProjectionCard.tsx |
| Admin interval controls | frontend/src/components/usage/IntervalSection.tsx |
| App routing | frontend/src/App.tsx |
| Sidebar nav | frontend/src/components/Layout.tsx |

## Notes

- The integration checker (run 2026-03-02 as part of v1.1 milestone audit) confirmed all 10 E2E flows pass and all 22 cross-phase wiring checks pass. This VERIFICATION.md was created after that audit to close the documentation gap identified — the code was already confirmed correct before this file was written.
- FREQ-01 depends on Phase 5 backend (FREQ-03 + FREQ-02): RedBeat propagation and server-side minimum enforcement were built in Phase 5 and consumed by the Phase 6 IntervalSection frontend.
- Recharts v3.7.0 is used (not v2); Phase 6 Plan 02 fixed Recharts v3 Tooltip type signatures for strict TypeScript mode (commit 7a3bc0e).
