---
phase: 11-tech-debt
plan: 02
subsystem: frontend
tags: [react, typescript, events-table, system-health, api-usage, docs]

# Dependency graph
requires:
  - phase: 11-01
    provides: Backend Sports API fully removed; sports_api_status column dropped via migration 009
provides:
  - Frontend completely free of Sports API references
  - ROADMAP, REQUIREMENTS, architecture.md updated to reflect removal
affects: [deployment, docs]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "4-source events table: Odds API, SDIO, ESPN, OddsBlaze (Sports API column removed)"
    - "4-worker health badges: ProphetX, SDIO, Odds API, ESPN (Sports API badge removed)"
    - "3-source usage toggles: Odds API, SportsDataIO, ESPN (Sports API toggle removed)"

key-files:
  created: []
  modified:
    - frontend/src/api/events.ts
    - frontend/src/api/usage.ts
    - frontend/src/components/EventsTable.tsx
    - frontend/src/components/SystemHealth.tsx
    - frontend/src/components/usage/CallVolumeChart.tsx
    - frontend/src/components/usage/IntervalSection.tsx
    - frontend/src/components/usage/ProjectionCard.tsx
    - frontend/src/components/usage/QuotaSection.tsx
    - frontend/src/components/usage/SourceToggleSection.tsx
    - .planning/ROADMAP.md
    - .planning/REQUIREMENTS.md
    - docs/architecture.md
  deleted:
    - frontend/src/components/usage/SportsApiQuotaCard.tsx

key-decisions:
  - "D-01 follow-through: frontend mirrors backend removal — zero sports_api references remain anywhere"
  - "DEBT-01 marked complete: requirement updated from refactor to full removal"

requirements-completed: [DEBT-01]

# Metrics
duration: ~4min
completed: 2026-04-01
---

# Phase 11 Plan 02: Sports API Frontend Removal + Docs Update Summary

**Sports API fully excised from frontend and planning docs: EventsTable column removed, SystemHealth badge removed, all API Usage page references eliminated, SportsApiQuotaCard deleted, ROADMAP/REQUIREMENTS/architecture updated to reflect removal**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-04-01T19:32:03Z
- **Completed:** 2026-04-01T19:36:00Z
- **Tasks:** 2
- **Files modified:** 12 (1 deleted)

## Accomplishments

- Removed `sports_api_status` from `EventRow` type and `EventsTable` sort/column
- Removed `sports_api` from `UsageData.quota` type; removed unused `SportQuota` interface
- Deleted `SportsApiQuotaCard.tsx` entirely
- Removed `poll_sports_api` from `WorkerHealth` interface and `WORKERS` array in `SystemHealth.tsx`
- Removed `poll_sports_api` from `CallVolumeChart`, `IntervalSection`, `ProjectionCard` label/color maps
- Removed `sports_api` from `SourceToggleSection` source list
- Simplified `QuotaSection` to Odds API only (no Sports API card)
- TypeScript compiles clean — zero `sports_api` references in `frontend/src/`
- Updated ROADMAP Phase 11 goal, success criteria, and plan checkboxes to reflect removal
- Updated REQUIREMENTS.md DEBT-01 text from "refactored" to "fully removed"; marked complete
- Updated `docs/architecture.md`: removed `sports_api_status` from Event column list, updated worker/client lists, updated env var docs

## Task Commits

1. **Task 1: Remove Sports API from all frontend files** - `da5f110` (feat)
2. **Task 2: Update docs — ROADMAP, REQUIREMENTS, architecture** - `afab7fc` (feat)

## Files Created/Modified

- `frontend/src/api/events.ts` — Removed `sports_api_status: string | null` from EventRow
- `frontend/src/api/usage.ts` — Removed `sports_api: Record<string, SportQuota>` from quota type; deleted SportQuota interface
- `frontend/src/components/EventsTable.tsx` — Removed `sports_api_status` from SortCol union, STATUS_COLS set, header cell, body cell; fixed colSpan 11→10
- `frontend/src/components/SystemHealth.tsx` — Removed `poll_sports_api` from WorkerHealth and WORKERS array
- `frontend/src/components/usage/SportsApiQuotaCard.tsx` — DELETED
- `frontend/src/components/usage/QuotaSection.tsx` — Removed SportsApiQuotaCard import, sports_api prop type, and JSX element
- `frontend/src/components/usage/CallVolumeChart.tsx` — Removed `poll_sports_api` from WORKER_COLORS and WORKER_DISPLAY_NAMES
- `frontend/src/components/usage/IntervalSection.tsx` — Removed `poll_sports_api` from WORKER_DISPLAY_NAMES and WORKER_CONFIG_KEYS
- `frontend/src/components/usage/SourceToggleSection.tsx` — Removed `sports_api` from SOURCE_DISPLAY
- `frontend/src/components/usage/ProjectionCard.tsx` — Removed `poll_sports_api` from WORKER_DISPLAY_NAMES
- `.planning/ROADMAP.md` — Phase 11 goal/criteria/plan checkboxes updated to removal language; progress table updated
- `.planning/REQUIREMENTS.md` — DEBT-01 updated to "fully removed"; marked complete; traceability table updated
- `docs/architecture.md` — Removed sports_api_status from Event description; updated client list, worker count, config vars, tech debt section

## Decisions Made

- Followed D-01 (full removal from 11-01): frontend matches backend — no partial stubs, no dead code left
- DEBT-01 requirement text updated to accurately describe what was done (removal, not refactor)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing] Fixed colSpan for removed column**
- **Found during:** Task 1
- **Issue:** Removing the Sports API column from EventsTable reduced column count from 11 to 10; the empty-state `colSpan={11}` would have spanned one extra column
- **Fix:** Updated colSpan from 11 to 10
- **Files modified:** frontend/src/components/EventsTable.tsx
- **Committed in:** da5f110 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 2 — colSpan correctness)
**Impact on plan:** Minimal — single number update to keep table structure correct.

## Known Stubs

None.

---

*Phase: 11-tech-debt*
*Completed: 2026-04-01*
