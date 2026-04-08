# Phase 15: Source Toggle Completeness - Context

**Gathered:** 2026-04-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Operators can enable/disable OddsBlaze, OpticOdds, and ProphetX WS from the Data Sources section on the API Usage page. Each source respects its enabled state at runtime. This completes the toggle section — all 6 data sources become visible and controllable.

Requirements: TOGL-01, TOGL-02, TOGL-03, TOGL-04, TOGL-05, TOGL-06

</domain>

<decisions>
## Implementation Decisions

### ProphetX WS Toggle Behavior (TOGL-04)
- **D-01:** Per-message check — call `is_source_enabled('prophetx_ws')` at the top of `_upsert_event()` in `ws_prophetx.py`. If disabled, return early (skip all DB writes). Connection stays alive for health monitoring.
- **D-02:** Do NOT clear existing `prophetx_status` data when WS is disabled. ProphetX status is the primary source of truth — clearing it would leave events with no status. Only stop writing new updates; existing statuses remain valid. This differs from the OddsBlaze/OpticOdds pattern (which clear their columns) because ProphetX is the authoritative source.
- **D-03:** When ProphetX WS toggle is off, `poll_prophetx` should ignore the WS authority window and write statuses freely. This ensures events still get status updates from the REST API when the operator has disabled WS writes.

### OddsBlaze Toggle Wiring (TOGL-05)
- **D-04:** Backend toggle already implemented — `poll_oddsblaze.py` calls `is_source_enabled('oddsblaze')` and `clear_source_and_recompute('oddsblaze')`. Phase 15 work is frontend-only: add to `SOURCE_DISPLAY` and `sources_enabled` response.

### OpticOdds Toggle Wiring (TOGL-06)
- **D-05:** Backend toggle already implemented — `poll_opticodds.py` calls `is_source_enabled('opticodds')` and `clear_source_and_recompute('opticodds')`. Phase 15 work is frontend-only: add to `SOURCE_DISPLAY` and `sources_enabled` response.

### Seed Data
- **D-06:** Add `source_enabled_opticodds` and `source_enabled_prophetx_ws` to `SOURCE_ENABLED_DEFAULTS` in `seed.py`. No Alembic migration needed — `system_config` is a key-value table and the seed script is idempotent (skips existing keys).
- **D-07:** Both new toggles default to `"true"` (enabled). Matches all existing sources. No behavioral change on deploy.

### Backend API (usage.py)
- **D-08:** Add `oddsblaze`, `opticodds`, and `prophetx_ws` to the `source_toggle_keys` list in `usage.py` so the `/usage` response includes their enabled state in `sources_enabled`.

### Frontend (SourceToggleSection.tsx)
- **D-09:** Add `oddsblaze`, `opticodds`, and `prophetx_ws` to `SOURCE_DISPLAY` map with display names: "OddsBlaze", "OpticOdds", "ProphetX WS".

### Claude's Discretion
- UI ordering of the 6 sources in the toggle table (logical grouping preferred)
- Whether to add source type labels (poll/stream) as metadata — not required
- Log message format when WS writes are skipped due to toggle

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source Toggle System (primary pattern)
- `backend/app/workers/source_toggle.py` — `is_source_enabled()`, `clear_source_and_recompute()`, `SOURCE_COLUMN_MAP` (already includes oddsblaze + opticodds entries)
- `backend/app/workers/poll_oddsblaze.py` — Toggle check pattern at top of task function (lines 106-107)
- `backend/app/workers/poll_opticodds.py` — Toggle check pattern (lines 146-147)

### ProphetX WS Consumer (modify in this phase)
- `backend/app/workers/ws_prophetx.py` — `_upsert_event()` function where toggle check goes; `_handle_broadcast_event()` dispatcher

### WS Authority Model (affects D-03)
- `backend/app/workers/poll_prophetx.py` — Authority window logic that must be bypassed when WS toggle is off

### API Usage Endpoint (modify in this phase)
- `backend/app/api/v1/usage.py` — `source_toggle_keys` list (line 137) and `sources_enabled` response section

### Seed Script (modify in this phase)
- `backend/app/seed.py` — `SOURCE_ENABLED_DEFAULTS` dict (line 43-48), `seed_intervals()` function

### Frontend Toggle Component (modify in this phase)
- `frontend/src/components/usage/SourceToggleSection.tsx` — `SOURCE_DISPLAY` map, toggle mutation, table rendering
- `frontend/src/api/usage.ts` — API client types
- `frontend/src/pages/ApiUsagePage.tsx` — Page layout passing `sourcesEnabled` prop

### Config Endpoint (no changes expected)
- `backend/app/api/v1/config.py` — PATCH endpoint already handles `source_enabled_*` keys generically (line 98-100)

### Requirements
- `.planning/REQUIREMENTS.md` §Source Toggle UI — TOGL-01, TOGL-02, TOGL-03
- `.planning/REQUIREMENTS.md` §Source Toggle Backend — TOGL-04, TOGL-05, TOGL-06

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `source_toggle.py` — Complete toggle check + clear + recompute pattern. Already has oddsblaze and opticodds in `SOURCE_COLUMN_MAP`. `is_source_enabled()` is the standard check function used by all workers.
- `SourceToggleSection.tsx` — Fully functional toggle component. Just needs 3 more entries in `SOURCE_DISPLAY`.
- `config.py` PATCH endpoint — Generically handles any `source_enabled_*` key. No backend API changes needed for new toggles.

### Established Patterns
- Toggle check at top of worker task: `if not is_source_enabled("key"): clear_source_and_recompute("key"); return`
- Config upsert via PATCH `/api/v1/config/{key}` with value `"true"` or `"false"`
- Frontend mutation via `updateInterval(key, value)` reused for toggle updates
- Seed script idempotent: skips keys that already exist in DB

### Integration Points
- `ws_prophetx.py:_upsert_event()` — Add `is_source_enabled('prophetx_ws')` check at top
- `poll_prophetx.py` — Bypass WS authority window when `is_source_enabled('prophetx_ws')` is false
- `usage.py` — Extend `source_toggle_keys` list with 3 new sources
- `seed.py` — Extend `SOURCE_ENABLED_DEFAULTS` with 2 new entries
- `SourceToggleSection.tsx` — Extend `SOURCE_DISPLAY` with 3 new entries

</code_context>

<specifics>
## Specific Ideas

- ProphetX WS toggle is unique: it does NOT clear data (D-02) and it unlocks poll_prophetx authority (D-03). This differs from all other source toggles which clear their column. The reason is ProphetX status is the primary/authoritative source — clearing it would be destructive.
- TOGL-05 and TOGL-06 are primarily verification tasks. The backend wiring already exists. The work is adding them to the frontend and the usage API response.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 15-source-toggle-completeness*
*Context gathered: 2026-04-07*
