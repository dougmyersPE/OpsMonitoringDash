# Phase 14: Dashboard and Health - Research

**Researched:** 2026-04-03
**Domain:** React frontend (TypeScript), FastAPI backend (Python) — incremental UI additions
**Confidence:** HIGH

## Summary

Phase 14 is a pure presentation phase — no new data is produced, no new infrastructure is needed. The backend health endpoint already returns `opticodds_consumer` with the correct `{connected, state, since}` shape (confirmed in `health.py` line 54-58). The Event DB model already has `opticodds_status` (confirmed in `event.py` line 34). Phase 13 already extended `compute_is_critical` and `compute_status_match` to accept `opticodds_status` as a 6th argument.

The work is four surgical edits: (1) add `opticodds_status` to `EventResponse` and update its `compute_is_critical` call, (2) add `opticodds_status: string | null` to the `EventRow` TypeScript interface, (3) add the OpticOdds badge inline in `SystemHealth.tsx`, and (4) add the `opticodds_status` column to `EventsTable.tsx`. All patterns are directly established by prior phases; nothing novel is required.

**Primary recommendation:** Mirror Phase 10 WS badge pattern exactly for the health badge; mirror the OddsBlaze column pattern exactly for the events table column.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Health Badge (DASH-01)**
- D-01: OpticOdds badge mirrors the WS badge rendering pattern — dedicated inline block after the WS badge in `SystemHealth.tsx`, not added to the `WORKERS` array. Uses the same `{connected, state, since}` object shape already returned by the backend.
- D-02: Green/red binary: `connected` = green, everything else = red.
- D-03: State detail via native `title` attribute tooltip: `"OpticOdds: {state}\nSince: {relative_time}"`. Use `formatDistanceToNow` from date-fns (already imported). Create `opticOddsTitle()` helper mirroring `wsTitle()`.
- D-04: Badge label: "OpticOdds" (full name).

**Events Table Column (DASH-02)**
- D-05: Add `opticodds_status` column using the existing `SourceStatus` component. Special statuses (walkover/retired/suspended) display in amber via `SourceStatus`'s fallback path. Non-tennis events with null `opticodds_status` show "Not Listed".
- D-06: Column position: after OddsBlaze, before Flag. Column header: "OpticOdds".
- D-07: Column is sortable — add `opticodds_status` to `SortCol` type and `STATUS_COLS` set.

**Schema & API Plumbing**
- D-08: Add `opticodds_status: str | None` to `EventResponse` Pydantic schema in `backend/app/schemas/event.py`.
- D-09: Update `compute_is_critical` call in `EventResponse.is_critical` to pass `self.opticodds_status` as 6th argument.
- D-10: Add `opticodds_status: string | null` to `EventRow` TypeScript interface in `frontend/src/api/events.ts`.

**Frontend Type Updates**
- D-11: Extend `WorkerHealth` interface with `opticodds_consumer?: WsProphetXHealth` (reuse existing `WsProphetXHealth` type — same shape).

### Claude's Discretion
- Whether to rename `WsProphetXHealth` to a generic `ConsumerHealth` interface or keep it and reuse as-is.
- `colSpan` updates on the empty-state row (currently 11, needs to be 12).
- Any minor TypeScript type refinements needed for the new column.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DASH-01 | Health endpoint includes OpticOdds consumer connection state; SystemHealth shows OpticOdds badge with connection state tooltip | Backend already returns `opticodds_consumer`; frontend badge is direct mirror of `ws_prophetx` badge pattern in lines 78-100 of SystemHealth.tsx |
| DASH-02 | Events table shows OpticOdds status column alongside existing source columns | Backend needs `opticodds_status` added to EventResponse; frontend column mirrors OddsBlaze pattern; `SourceStatus` component already handles null + special statuses |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React + TypeScript | 18.x / 5.x | Frontend component and type system | Established project stack |
| @tanstack/react-query | 5.x | Data fetching + 30s polling for worker health | Already configured in project |
| date-fns | 3.x | `formatDistanceToNow` for tooltip "since" display | Already imported in SystemHealth.tsx |
| FastAPI + Pydantic v2 | 0.115 / 2.x | Backend schema definition | Established project stack |

No new packages needed. All libraries already installed.

**Installation:** None required.

## Architecture Patterns

### Current SystemHealth.tsx Structure
```
SystemHealth.tsx
├── WsProphetXHealth interface  (lines 6-10)
├── WorkerHealth interface      (lines 12-18) — add opticodds_consumer?
├── WORKERS array               (lines 25-30) — boolean workers, do NOT add here
├── wsTitle() helper            (lines 32-37) — clone as opticOddsTitle()
└── JSX: WORKERS.map badges → ws_prophetx inline block → [NEW: opticodds inline block]
```

### Current EventsTable.tsx Column Order
```
PX ID | Event | Sport | Starts | ProphetX | Odds API | SDIO | ESPN | OddsBlaze | [NEW: OpticOdds] | Flag | Checked
```
Column count goes from 11 to 12. The empty-state `<TableCell colSpan={11}>` must become `colSpan={12}`.

### Pattern 1: Non-Boolean Health Badge (from Phase 10)
**What:** Inline IIFE render block after the `WORKERS.map()` loop, guarded by `data.ws_prophetx &&`
**When to use:** Any consumer with `{connected, state, since}` shape — not a simple boolean heartbeat
**Example (existing ws_prophetx block, lines 78-100):**
```typescript
// Source: frontend/src/components/SystemHealth.tsx lines 78-100
{data.ws_prophetx && (() => {
  const active = data.ws_prophetx.connected;
  return (
    <span
      key="ws_prophetx"
      title={wsTitle(data.ws_prophetx)}
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border",
        active
          ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
          : "bg-red-500/10 text-red-400 border-red-500/20"
      )}
    >
      <span className={cn(
        "h-1.5 w-1.5 rounded-full shrink-0",
        active ? "bg-emerald-400 animate-pulse" : "bg-red-500"
      )} />
      WS
    </span>
  );
})()}
```
**OpticOdds badge:** Identical structure. Key = `"opticodds_consumer"`. Label = `"OpticOdds"`. Title helper = `opticOddsTitle()`.

### Pattern 2: Source Status Column (from existing OddsBlaze column)
**What:** `SortableHead` in `<TableHeader>` + `<SourceStatus status={event.X_status} />` in `<TableBody>`
**Example (existing oddsblaze column):**
```typescript
// Source: frontend/src/components/EventsTable.tsx
// Header (line 510):
<SortableHead col="oddsblaze_status" sortCol={sortCol} sortDir={sortDir} onSort={handleSort}>OddsBlaze</SortableHead>

// Body (line 558):
<TableCell><SourceStatus status={event.oddsblaze_status} /></TableCell>
```
**OpticOdds column:** Same pattern. After `oddsblaze_status` entries. Before `is_flagged` entries.

### Pattern 3: SortCol Extension
**What:** Add literal to union type, add to STATUS_COLS set
**Current SortCol** (lines 215-227): union of 11 string literals
**Current STATUS_COLS** (lines 229-235): set of 5 status keys
**Change:**
```typescript
// Add to SortCol union:
| "opticodds_status"

// Add to STATUS_COLS:
"opticodds_status",
```

### Pattern 4: EventResponse Schema + compute_is_critical (from prior source columns)
**Current `EventResponse` fields** (event.py lines 9-27): all source statuses except `opticodds_status`
**Current `compute_is_critical` call** (lines 29-38): 5 args — no `opticodds_status`
**`compute_is_critical` signature** (mismatch_detector.py lines 264-271): already accepts 6th arg `opticodds_status: str | None = None`

**Required changes to `backend/app/schemas/event.py`:**
```python
# Add field after oddsblaze_status:
opticodds_status: str | None

# Update compute_is_critical call:
return compute_is_critical(
    self.prophetx_status,
    self.odds_api_status,
    self.sdio_status,
    self.espn_status,
    self.oddsblaze_status,
    self.opticodds_status,   # ← add this
)
```

### Anti-Patterns to Avoid
- **Adding opticodds_consumer to WORKERS array:** The WORKERS array is for simple boolean heartbeat workers. The `opticodds_consumer` key is an object with `{connected, state, since}` — it must be rendered inline like `ws_prophetx`.
- **Forgetting colSpan update:** The empty-state row `colSpan={11}` must become `colSpan={12}` or the empty state will not span the full table width.
- **Omitting the 6th arg to compute_is_critical:** The schema's `is_critical` computed field currently calls with 5 args. The function already accepts 6 but without passing `opticodds_status`, tennis events with opticodds data won't contribute to critical detection.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Status display with null/special handling | Custom status renderer | `SourceStatus` component (already in EventsTable.tsx) | Handles null → "Not Listed", Live, Ended, Not Started, amber fallback for special statuses |
| Relative time formatting | Custom time delta | `formatDistanceToNow` from date-fns | Already imported; handles edge cases, localization |
| Badge styling | Custom CSS classes | Existing `cn()` Tailwind pattern from ws_prophetx block | Consistency across all badges |
| Sortable column header | Custom sort UI | `SortableHead` component (already in EventsTable.tsx) | Chevron icons, active state, click handler wired |

**Key insight:** Every required UI element already exists. This phase is assembly, not construction.

## Common Pitfalls

### Pitfall 1: TypeScript narrowing with optional interface field
**What goes wrong:** `data.opticodds_consumer` is typed as `WsProphetXHealth | undefined`. Accessing `data.opticodds_consumer.connected` without a guard causes a type error.
**Why it happens:** D-11 makes the field optional (`opticodds_consumer?: WsProphetXHealth`) to match `ws_prophetx?`'s existing pattern.
**How to avoid:** Use the same IIFE-with-guard pattern: `{data.opticodds_consumer && (() => { ... })()}`. TypeScript narrows correctly inside the guard.
**Warning signs:** TS error "Object is possibly undefined" on `data.opticodds_consumer.connected`.

### Pitfall 2: opticodds_status absent from API response until schema is patched
**What goes wrong:** Frontend adds the column but the field is undefined in API responses until `EventResponse` is updated.
**Why it happens:** Pydantic serializes only declared fields. `opticodds_status` exists in the DB model but is not yet in `EventResponse`.
**How to avoid:** Backend schema change (D-08) must be deployed before or alongside the frontend column change. In this project both are in the same phase — plan them in the same wave or deploy together.
**Warning signs:** All cells show "Not Listed" even for tennis events known to have opticodds data.

### Pitfall 3: compute_is_critical call remains at 5 args
**What goes wrong:** `is_critical` computed field in `EventResponse` does not include `opticodds_status`, so tennis events with opticodds data showing "live" never contribute to critical detection.
**Why it happens:** The function signature already accepts 6 args with a default, so there's no runtime error — the bug is silent.
**How to avoid:** D-09 explicitly requires updating the call. Include this as a required task, not a nice-to-have.
**Warning signs:** No runtime error; only detectable by testing critical detection logic with opticodds live data.

### Pitfall 4: WsProphetXHealth rename creates unnecessary diff
**What goes wrong:** Renaming to `ConsumerHealth` touches more code than necessary and increases review surface.
**Why it happens:** Temptation to "clean up" the type name.
**How to avoid:** Per D-11 / Claude's Discretion — reusing `WsProphetXHealth` as-is is the simpler choice. Only rename if it aids clarity without spreading changes.
**Warning signs:** Git diff touches lines unrelated to the feature.

## Code Examples

### opticOddsTitle() helper (mirrors wsTitle())
```typescript
// Source: mirrors SystemHealth.tsx:32-37
function opticOddsTitle(oo: WsProphetXHealth): string {
  const state = oo.state ?? "unknown";
  if (!oo.since) return `OpticOdds: ${state}`;
  const sinceStr = formatDistanceToNow(new Date(oo.since), { addSuffix: true });
  return `OpticOdds: ${state}\nSince: ${sinceStr}`;
}
```

### WorkerHealth interface extension (D-11)
```typescript
// Source: mirrors SystemHealth.tsx:12-18
interface WorkerHealth {
  poll_prophetx: boolean;
  poll_sports_data: boolean;
  poll_odds_api: boolean;
  poll_espn: boolean;
  ws_prophetx?: WsProphetXHealth;
  opticodds_consumer?: WsProphetXHealth;   // ← add this
}
```

### EventRow interface extension (D-10)
```typescript
// Source: frontend/src/api/events.ts
export interface EventRow {
  // ... existing fields ...
  oddsblaze_status: string | null;
  opticodds_status: string | null;   // ← add after oddsblaze_status
  status_match: boolean;
  // ...
}
```

### EventResponse schema patch (D-08 + D-09)
```python
# Source: backend/app/schemas/event.py
class EventResponse(BaseModel):
    # ... existing fields ...
    oddsblaze_status: str | None
    opticodds_status: str | None    # ← add after oddsblaze_status

    @computed_field
    @property
    def is_critical(self) -> bool:
        return compute_is_critical(
            self.prophetx_status,
            self.odds_api_status,
            self.sdio_status,
            self.espn_status,
            self.oddsblaze_status,
            self.opticodds_status,   # ← add 6th arg
        )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| compute_is_critical with 5 params | 6-param signature with opticodds_status default None | Phase 13 | Call site in EventResponse still uses 5 args — must be updated |
| No opticodds_consumer in /health/workers | opticodds_consumer returned with connected/state/since | Phase 12 | Frontend can read it immediately; only WorkerHealth interface needs extending |
| No opticodds_status in DB | opticodds_status column added via migration 010 | Phase 12 | Column exists and is written by Phase 13 consumer; only EventResponse schema needs it |

## Environment Availability

Step 2.6: SKIPPED — this phase is purely code/config changes to existing frontend and backend files. No new external tools, services, CLIs, runtimes, or databases are introduced.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `cd backend && python -m pytest tests/test_health.py -x -q` |
| Full suite command | `cd backend && python -m pytest tests/ -q` |

Note: No frontend test framework is configured (package.json has no test script, no vitest/jest config found). Frontend changes are validated manually or via visual inspection. This is the established project pattern.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DASH-01 | `/health/workers` response includes `opticodds_consumer` key with `connected/state/since` | integration | `cd backend && python -m pytest tests/test_health.py -x -q -k "opticodds"` | ❌ Wave 0 |
| DASH-01 | SystemHealth badge renders for OpticOdds | manual/visual | — (no frontend test framework) | N/A |
| DASH-02 | `EventResponse` serializes `opticodds_status` field | unit | `cd backend && python -m pytest tests/ -x -q -k "opticodds_status"` | ❌ Wave 0 |
| DASH-02 | Events table OpticOdds column display | manual/visual | — (no frontend test framework) | N/A |

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/test_health.py -x -q`
- **Per wave merge:** `cd backend && python -m pytest tests/ -q`
- **Phase gate:** Full backend suite green + manual visual verification of badge and column

### Wave 0 Gaps
- [ ] `tests/test_health.py` — add `TestOpticOddsConsumerHealth` class covering `opticodds_consumer` key presence, `connected` bool type, `state` string-or-null, `since` string-or-null (mirrors existing `TestWorkerHealthWsProphetX` class)
- [ ] `tests/` (any test file) — add test that `EventResponse` includes `opticodds_status` field and that it serializes correctly from the Event model

## Open Questions

1. **Whether to rename `WsProphetXHealth` to `ConsumerHealth`**
   - What we know: Both `ws_prophetx` and `opticodds_consumer` use identical `{connected, state, since}` shape
   - What's unclear: Whether future consumers will also use this shape
   - Recommendation: Keep `WsProphetXHealth` as-is and reuse; add a comment. Rename only if a third consumer appears. Fewer changed lines = lower risk for a presentation-only phase.

## Sources

### Primary (HIGH confidence)
- `frontend/src/components/SystemHealth.tsx` — read directly; WS badge pattern at lines 78-100; `wsTitle()` at lines 32-37; `WorkerHealth` and `WsProphetXHealth` interfaces at lines 6-18
- `frontend/src/components/EventsTable.tsx` — read directly; `SourceStatus` component at lines 77-90; `SortCol` union at lines 215-227; `STATUS_COLS` set at lines 229-235; `SortableHead` at lines 264-304; colSpan at line 571
- `frontend/src/api/events.ts` — read directly; `EventRow` interface at lines 3-19
- `backend/app/schemas/event.py` — read directly; `EventResponse` at lines 9-38; 5-arg `compute_is_critical` call at lines 29-38
- `backend/app/models/event.py` — read directly; `opticodds_status` column confirmed at line 34
- `backend/app/api/v1/health.py` — read directly; `opticodds_consumer` returned at lines 54-58 with `connected/state/since` shape
- `backend/app/monitoring/mismatch_detector.py` — read directly; `compute_is_critical` 6-param signature at lines 264-271 (already accepts `opticodds_status`)

### Secondary (MEDIUM confidence)
None required — all findings from direct source inspection.

### Tertiary (LOW confidence)
None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all files read directly; no ambiguity
- Architecture: HIGH — patterns extracted from existing code; no inference needed
- Pitfalls: HIGH — identified from direct code inspection of call sites and type definitions

**Research date:** 2026-04-03
**Valid until:** 2026-05-03 (stable codebase; patterns won't change unless prior phases are modified)
