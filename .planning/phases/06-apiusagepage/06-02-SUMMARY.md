---
phase: 06-apiusagepage
plan: 02
status: complete
started: 2026-03-02
completed: 2026-03-02
requirements_completed: [USAGE-02, USAGE-03, USAGE-04, FREQ-01]
---

# Plan 06-02 Summary: Frontend ApiUsagePage

## What Was Built
Complete frontend API Usage page with three main sections:

1. **Provider Quotas** -- OddsApiQuotaCard with progress bar (green/amber/red thresholds at 50%/80%) and SportsApiQuotaCard with expandable per-sport breakdown (Basketball, Hockey, Baseball, American Football, Soccer). Null data renders as dashes, not zeros.

2. **Call Volume** -- 7-day stacked bar chart (Recharts) with per-worker color coding (ProphetX=indigo, SportsDataIO=green, Odds API=amber, Sports API=blue, ESPN=pink). Includes a ProjectionCard sidebar showing monthly total and per-worker projected call counts computed from current intervals.

3. **Poll Intervals** (admin-only) -- Table with inline Edit/Save/Cancel controls. Uses useMutation for PATCH /config/{key}, with client-side minimum validation, inline red error text on failure, and green checkmark flash (1500ms) on success.

## Key Files

### Created
- `frontend/src/pages/ApiUsagePage.tsx` -- Main page with useQuery(["usage"]) at 30s refetchInterval, role-gated IntervalSection
- `frontend/src/api/usage.ts` -- TypeScript interfaces (OddsQuota, SportQuota, IntervalInfo, HistoryEntry, UsageData) + fetchUsageData/updateInterval functions
- `frontend/src/components/usage/QuotaSection.tsx` -- Section wrapper rendering both quota cards in 2-col grid
- `frontend/src/components/usage/OddsApiQuotaCard.tsx` -- Progress bar with color shift + used/remaining/limit numbers
- `frontend/src/components/usage/SportsApiQuotaCard.tsx` -- Aggregate summary + expandable per-sport breakdown via useState toggle
- `frontend/src/components/usage/CallVolumeSection.tsx` -- Chart + ProjectionCard layout with empty-data fallback message
- `frontend/src/components/usage/CallVolumeChart.tsx` -- Recharts BarChart with stacked bars, dark theme, XAxis date formatting via date-fns
- `frontend/src/components/usage/ProjectionCard.tsx` -- Monthly projection total + per-worker breakdown with interval display
- `frontend/src/components/usage/IntervalSection.tsx` -- Admin-only table with inline editing, useMutation, validation, success flash

### Modified
- `frontend/src/App.tsx` -- Added /usage route with ProtectedRoute wrapper
- `frontend/src/components/Layout.tsx` -- Added "API Usage" nav item with Gauge icon as third sidebar entry

## Decisions Made
- Used Recharts v3.7.0 (compatible with React 19) for stacked bar chart
- Sports API quota card uses expandable pattern (collapsed by default) to avoid visual overload with 5 sport families
- Interval validation is done client-side first (minimum check) before server call, with server 422 errors shown inline
- Success flash uses setTimeout(1500ms) with local state rather than a toast library to keep dependencies minimal
- Empty chart shows centered "Collecting data" message rather than an empty chart frame

## Self-Check: PASSED
- [x] TypeScript compilation clean (npx tsc --noEmit)
- [x] /usage route wired in App.tsx with ProtectedRoute
- [x] "API Usage" nav item in Layout.tsx sidebar
- [x] QuotaSection renders both Odds API and Sports API cards
- [x] Null quota values display dashes not zeros
- [x] CallVolumeChart uses Recharts with worker color map
- [x] ProjectionCard shows monthly total and per-worker breakdown
- [x] IntervalSection hidden for non-admin users (role check in ApiUsagePage)
- [x] IntervalSection has Edit/Save/Cancel with mutation, validation, and success flash
