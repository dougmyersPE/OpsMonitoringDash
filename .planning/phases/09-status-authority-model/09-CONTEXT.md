# Phase 9: Status Authority Model - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Elevate WS-delivered event status to authoritative source. Add `status_source` tracking (ws/poll/manual) to every `prophetx_status` write. Implement authority window logic so `poll_prophetx` cannot overwrite a WS-delivered status within a configurable threshold. Ensure poll still updates metadata (teams, scheduled_start, league) even when WS is authoritative. This phase transforms the relationship between WS and poll from "both write freely" to "WS leads, poll defers within window."

</domain>

<decisions>
## Implementation Decisions

### Authority Window (AUTH-02)
- **D-01:** Authority window duration is 10 minutes, configurable. After WS delivers a status, poll_prophetx will not overwrite `prophetx_status` for 10 minutes. Configurable via environment variable or settings.
- **D-02:** Authority is tracked by a `ws_delivered_at` timestamp column on the events table. If `ws_delivered_at` is not null and `now - ws_delivered_at < threshold`, the event is "WS-authoritative."

### status_source Storage (AUTH-01)
- **D-03:** Add `status_source` column directly on the events table (String, values: "ws", "poll", "manual"). Updated on every `prophetx_status` write. No separate audit table — keep it simple.
- **D-04:** `ws_delivered_at` column (DateTime, nullable) on events table. Set when WS writes status, cleared/ignored when poll is allowed to overwrite after window expires.

### Stale Event Handling
- **D-05:** Authority window does NOT protect against poll marking events "ended." The "ended" status is terminal — if poll sees an event gone from the API, it can always mark it ended regardless of WS authority. This prevents events from staying artificially "live" after ProphetX removes them.

### Reconciliation Behavior (AUTH-02, AUTH-03)
- **D-06:** When poll detects a different status than WS delivered, and the event is within the authority window: log the discrepancy (structured log with both statuses) but do NOT overwrite `prophetx_status`. The WS-delivered status wins.
- **D-07:** When WS is authoritative, poll_prophetx still updates: `home_team`, `away_team`, `scheduled_start`, `league`, `last_prophetx_poll`, and recomputes `status_match`. Only `prophetx_status` and `status_source` are protected.

### Claude's Discretion
- Migration numbering: next available (008)
- Alembic migration for `status_source` and `ws_delivered_at` columns
- Structured log format for authority-window skip events
- Whether to add an index on `ws_delivered_at` (likely not needed at this scale)
- Test structure: extend existing test files or create new ones for authority logic

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### WS Consumer & Poll Workers
- `backend/app/workers/ws_prophetx.py` — WS consumer; needs to set `status_source="ws"` and `ws_delivered_at=now` on every status write
- `backend/app/workers/poll_prophetx.py` — Poll worker; needs authority check before `prophetx_status` overwrite, metadata-only update path (AUTH-03)
- `backend/app/models/event.py` — Event model; needs `status_source` and `ws_delivered_at` columns

### Requirements
- `.planning/REQUIREMENTS.md` §Status Authority — AUTH-01, AUTH-02, AUTH-03

### Phase 8 Context (predecessor)
- `.planning/phases/08-ws-diagnostics-and-instrumentation/08-CONTEXT.md` — WS diagnostic decisions, Redis key patterns
- `.planning/phases/08-ws-diagnostics-and-instrumentation/08-01-SUMMARY.md` — What was built in Phase 8

### Existing Patterns
- `backend/alembic/versions/` — Migration numbering pattern (001-007 exist)
- `backend/app/monitoring/mismatch_detector.py:compute_status_match()` — Status comparison logic
- `backend/app/core/constants.py` — Status lifecycle constants (ACTIVE_STATUSES etc.)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `compute_status_match()` in `mismatch_detector.py` — already called after every status write; no changes needed
- `_upsert_event()` in `ws_prophetx.py` — both create and update paths write `prophetx_status`; both need `status_source="ws"` and `ws_delivered_at=now`
- Redis diagnostic keys from Phase 8 — `ws:connection_state`, `ws:last_message_at` — can inform dashboard but are separate from authority logic

### Established Patterns
- Both `poll_prophetx.py` and `ws_prophetx.py` use the same `Event` model and `SessionLocal` for DB writes
- `poll_prophetx.py` has distinct create path (line ~195) and update path (line ~215) — authority check goes in update path only
- `ws_prophetx.py` has create path (line ~208) and update path (line ~230) — both set `status_source="ws"`

### Integration Points
- `poll_prophetx.py` update path: add authority window check before `existing.prophetx_status = status_value`
- `poll_prophetx.py` create path: set `status_source="poll"` (new events from poll are always poll-sourced)
- `ws_prophetx.py` update path: set `ws_delivered_at=now` and `status_source="ws"`
- `ws_prophetx.py` create path: set `ws_delivered_at=now` and `status_source="ws"`
- `update_event_status.py` (manual sync): set `status_source="manual"` if it writes `prophetx_status`

</code_context>

<specifics>
## Specific Ideas

- ROADMAP success criteria #2: "poll_prophetx running within 10 minutes does not overwrite prophetx_status" — the 10-minute window is the explicit success criterion
- ROADMAP success criteria #4: "A stale REST status arriving after a WS live delivery does not regress the event status" — this is enforced by the authority window + lifecycle guard (no backward transitions)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 09-status-authority-model*
*Context gathered: 2026-03-31*
