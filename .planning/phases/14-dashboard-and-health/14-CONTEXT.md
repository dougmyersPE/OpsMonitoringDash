# Phase 14: Dashboard and Health - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Surface OpticOdds consumer health alongside other worker badges on the dashboard and add an OpticOdds status column to the events table. The backend health endpoint already returns `opticodds_consumer` data (Phase 12); the consumer already writes `opticodds_status` to the DB (Phase 13). This phase is purely frontend presentation + schema plumbing to expose existing data.

Requirements: DASH-01, DASH-02

</domain>

<decisions>
## Implementation Decisions

### Health Badge (DASH-01)
- **D-01:** OpticOdds badge mirrors the WS badge rendering pattern — dedicated inline block after the WS badge in `SystemHealth.tsx`, not added to the `WORKERS` array (which handles simple boolean workers). Uses the same `{connected, state, since}` object shape already returned by the backend.
- **D-02:** Green/red binary: `connected` = green, everything else = red. Matches Phase 10 D-02 decision for WS badge.
- **D-03:** State detail via native `title` attribute tooltip: `"OpticOdds: {state}\nSince: {relative_time}"`. Matches Phase 10 D-03/D-04 — use `formatDistanceToNow` from date-fns (already imported). Create `opticOddsTitle()` helper mirroring `wsTitle()`.
- **D-04:** Badge label: "OpticOdds" (full name, clear to operators).

### Events Table Column (DASH-02)
- **D-05:** Add `opticodds_status` column using the existing `SourceStatus` component — consistent with Odds API, SDIO, ESPN, OddsBlaze columns. Special statuses (walkover/retired/suspended) display in amber via `SourceStatus`'s fallback path. Non-tennis events with null `opticodds_status` show "Not Listed" (existing `SourceStatus` null behavior).
- **D-06:** Column position: after OddsBlaze, before Flag — last source column in the row. Column header: "OpticOdds".
- **D-07:** Column is sortable — add `opticodds_status` to `SortCol` type and `STATUS_COLS` set.

### Schema & API Plumbing
- **D-08:** Add `opticodds_status: str | None` to `EventResponse` Pydantic schema in `backend/app/schemas/event.py`. The Event model already has the column (Phase 12 migration 010).
- **D-09:** Update `compute_is_critical` call in `EventResponse.is_critical` to pass `self.opticodds_status` as 6th argument — `compute_is_critical` was already extended in Phase 13.
- **D-10:** Add `opticodds_status: string | null` to `EventRow` TypeScript interface in `frontend/src/api/events.ts`.

### Frontend Type Updates
- **D-11:** Extend `WorkerHealth` interface with `opticodds_consumer?: WsProphetXHealth` (reuse existing `WsProphetXHealth` type — same shape: `{connected, state, since}`). Alternatively, rename the interface to something generic or create an alias — Claude's discretion.

### Claude's Discretion
- Whether to rename `WsProphetXHealth` to a generic `ConsumerHealth` interface or keep it and reuse as-is
- `colSpan` updates on the empty-state row (currently 11, needs to be 12)
- Any minor TypeScript type refinements needed for the new column

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Frontend — SystemHealth Badge
- `frontend/src/components/SystemHealth.tsx` — Current WS badge rendering pattern (lines 78-100); `wsTitle()` helper; `WorkerHealth` and `WsProphetXHealth` interfaces. Mirror for OpticOdds badge.

### Frontend — Events Table
- `frontend/src/components/EventsTable.tsx` — `SourceStatus` component, `SortCol` type, `STATUS_COLS` set, `SortableHead` usage, column order in table header/body
- `frontend/src/api/events.ts` — `EventRow` interface; add `opticodds_status` field

### Backend — Schema
- `backend/app/schemas/event.py` — `EventResponse` Pydantic schema; add `opticodds_status` field and update `compute_is_critical` call
- `backend/app/models/event.py` — Event model with `opticodds_status` column (already exists from Phase 12)

### Backend — Health Endpoint
- `backend/app/api/v1/health.py` — Already returns `opticodds_consumer` with `{connected, state, since}` shape (Phase 12). No backend changes needed.

### Mismatch Detection
- `backend/app/monitoring/mismatch_detector.py` — `compute_is_critical()` already accepts 6 params including `opticodds_status` (Phase 13)

### Requirements
- `.planning/REQUIREMENTS.md` §Health & Dashboard — DASH-01 (health badge), DASH-02 (events table column)

### Prior Phase Context
- `.planning/phases/10-ws-health-dashboard/10-CONTEXT.md` — WS badge design decisions (D-01 through D-04) that Phase 14 mirrors
- `.planning/phases/12-consumer-foundation/12-CONTEXT.md` — Consumer health endpoint shape, Redis key design
- `.planning/phases/13-status-processing-and-matching/13-CONTEXT.md` — Status writing, special status handling, compute_status_match extension

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `SystemHealth.tsx:wsTitle()` — Tooltip helper for `{state, since}` object; clone as `opticOddsTitle()`
- `SystemHealth.tsx` WS badge block (lines 78-100) — Complete inline rendering pattern with green/red styling
- `EventsTable.tsx:SourceStatus` — Status display component already handles null, Live, Ended, Not Started, and flag-worthy statuses
- `EventsTable.tsx:SortableHead` — Sortable column header component
- `date-fns:formatDistanceToNow` — Already imported in SystemHealth.tsx

### Established Patterns
- Health badges: `WsProphetXHealth` interface with `{connected, state, since}` — `opticodds_consumer` uses identical shape
- Source columns: Each source gets a `SortableHead` + `SourceStatus` cell in the table
- Type extension: `SortCol` union type + `STATUS_COLS` set for sortable status columns
- React Query: 30s polling on worker health; events query auto-refreshes

### Integration Points
- `WorkerHealth` interface — Add `opticodds_consumer` optional field
- `SortCol` type — Add `"opticodds_status"` literal
- `STATUS_COLS` set — Add `"opticodds_status"`
- Table header — Add `SortableHead` after OddsBlaze
- Table body — Add `SourceStatus` cell after OddsBlaze
- Empty row `colSpan` — Increment from 11 to 12

</code_context>

<specifics>
## Specific Ideas

- Backend health endpoint already returns `opticodds_consumer` in the right shape — zero backend health changes needed
- The only backend change is adding `opticodds_status` to the `EventResponse` schema and updating the `compute_is_critical` call
- Frontend is the primary work: SystemHealth badge + EventsTable column + TypeScript types
- Phase 10 established the exact pattern for adding a non-boolean health badge — this is a near-copy

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 14-dashboard-and-health*
*Context gathered: 2026-04-03*
