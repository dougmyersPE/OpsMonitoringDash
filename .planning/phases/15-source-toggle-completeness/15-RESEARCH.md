# Phase 15: Source Toggle Completeness - Research

**Researched:** 2026-04-07
**Domain:** FastAPI backend toggle wiring + React/TypeScript frontend component extension
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01** ProphetX WS toggle — per-message check: call `is_source_enabled('prophetx_ws')` at the top of `_upsert_event()` in `ws_prophetx.py`. If disabled, return early (skip all DB writes). Connection stays alive for health monitoring.

**D-02** Do NOT clear existing `prophetx_status` data when WS is disabled. ProphetX status is the primary source of truth — clearing it would leave events with no status. Only stop writing new updates; existing statuses remain valid. This differs from the OddsBlaze/OpticOdds pattern (which clear their columns) because ProphetX is the authoritative source.

**D-03** When ProphetX WS toggle is off, `poll_prophetx` should ignore the WS authority window and write statuses freely. This ensures events still get status updates from the REST API when the operator has disabled WS writes.

**D-04** OddsBlaze toggle: backend already implemented. Phase 15 work is frontend-only — add to `SOURCE_DISPLAY` and `sources_enabled` response.

**D-05** OpticOdds toggle: backend already implemented. Phase 15 work is frontend-only — add to `SOURCE_DISPLAY` and `sources_enabled` response.

**D-06** Add `source_enabled_opticodds` and `source_enabled_prophetx_ws` to `SOURCE_ENABLED_DEFAULTS` in `seed.py`. No Alembic migration needed — `system_config` is a key-value table; the seed script is idempotent.

**D-07** Both new toggles default to `"true"` (enabled). No behavioral change on deploy.

**D-08** Add `oddsblaze`, `opticodds`, and `prophetx_ws` to the `source_toggle_keys` list in `usage.py`.

**D-09** Add `oddsblaze`, `opticodds`, and `prophetx_ws` to `SOURCE_DISPLAY` in `SourceToggleSection.tsx` with display names "OddsBlaze", "OpticOdds", "ProphetX WS".

### Claude's Discretion

- UI ordering of the 6 sources in the toggle table (logical grouping preferred)
- Whether to add source type labels (poll/stream) as metadata — not required
- Log message format when WS writes are skipped due to toggle

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TOGL-01 | OddsBlaze appears in the Data Sources toggle section on the API Usage page with enable/disable control | Frontend-only: add `oddsblaze` to `SOURCE_DISPLAY` and `source_toggle_keys` |
| TOGL-02 | OpticOdds appears in the Data Sources toggle section on the API Usage page with enable/disable control | Frontend-only: add `opticodds` to `SOURCE_DISPLAY` and `source_toggle_keys` |
| TOGL-03 | ProphetX WS appears in the Data Sources toggle section on the API Usage page with enable/disable control | Frontend + seed: add `prophetx_ws` to `SOURCE_DISPLAY`, `source_toggle_keys`, and `SOURCE_ENABLED_DEFAULTS` |
| TOGL-04 | When ProphetX WS is disabled via toggle, the WS consumer skips status writes to DB (connection stays alive) | Backend: add `is_source_enabled('prophetx_ws')` check in `_upsert_event()` and authority bypass in `poll_prophetx` |
| TOGL-05 | When OddsBlaze is disabled via toggle, poll_oddsblaze skips polling and clears stale data (already implemented — verify wiring) | Verification task: confirm `poll_oddsblaze` toggle check + frontend + usage API wiring is end-to-end |
| TOGL-06 | When OpticOdds is disabled via toggle, poll_opticodds skips polling and clears stale data (already implemented — verify wiring) | Verification task: confirm `poll_opticodds` toggle check + frontend + usage API wiring is end-to-end |
</phase_requirements>

---

## Summary

Phase 15 completes the source toggle system by wiring three new sources — OddsBlaze, OpticOdds, and ProphetX WS — into the existing Data Sources UI on the API Usage page. The work divides cleanly into two categories: frontend-only wiring (OddsBlaze, OpticOdds) and a new backend behavior (ProphetX WS).

For OddsBlaze and OpticOdds (TOGL-01, TOGL-02, TOGL-05, TOGL-06), the backend toggle check already exists in each poll worker via `is_source_enabled()` and `clear_source_and_recompute()`. The only changes needed are: (1) add the three source keys to `source_toggle_keys` in `usage.py` so the `/usage` response includes them in `sources_enabled`, and (2) add the display names to `SOURCE_DISPLAY` in `SourceToggleSection.tsx`. Both tasks are additive and carry no risk of regression.

ProphetX WS (TOGL-03, TOGL-04) requires new backend behavior. The `_upsert_event()` function in `ws_prophetx.py` must gain an early-return guard when `is_source_enabled('prophetx_ws')` is false — but critically, the WS connection must stay alive (health monitoring must not be affected). Additionally, `poll_prophetx.py` must bypass the `is_ws_authoritative()` check when the WS toggle is off, so the REST poller resumes writing statuses freely. A new seed row for `source_enabled_prophetx_ws` is needed in `seed.py`.

**Primary recommendation:** Implement in three waves: (1) seed + usage API, (2) ProphetX WS backend behavior, (3) frontend toggle additions with end-to-end verification.

---

## Standard Stack

This phase uses no new libraries. All work is within the existing project stack.

### Core (already installed)
| Component | Version | Purpose | Notes |
|-----------|---------|---------|-------|
| FastAPI | >=0.115 | Backend API endpoint | `usage.py` already handles `source_toggle_keys` |
| SQLAlchemy (sync) | >=2.0 | DB reads in workers | `SyncSessionLocal` used in `source_toggle.py` and workers |
| React + TanStack Query | existing | Frontend toggle UI | `useMutation` + `updateInterval` pattern already in place |
| structlog | >=24.0 | Logging in workers | Already used in all workers |

### No New Dependencies

All patterns in this phase replicate existing code. No new packages are required.

---

## Architecture Patterns

### Pattern 1: Poll Worker Toggle Check (existing, replicate for verification)

The established pattern used by `poll_oddsblaze.py` (lines 106-111) and `poll_opticodds.py` (lines 146-152):

```python
# Source: backend/app/workers/poll_oddsblaze.py lines 106-111
from app.workers.source_toggle import is_source_enabled, clear_source_and_recompute
if not is_source_enabled("oddsblaze"):
    clear_source_and_recompute("oddsblaze")
    _write_heartbeat()
    log.info("poll_oddsblaze_skipped", reason="source disabled")
    return
```

ProphetX WS uses a modified version of this pattern: check `is_source_enabled("prophetx_ws")` but do NOT call `clear_source_and_recompute` (D-02). Return early from `_upsert_event()` only — not from the entire WS consumer process.

### Pattern 2: ProphetX WS Toggle — `_upsert_event()` Early Return (NEW)

The check goes at the very top of `_upsert_event()`, before any DB work, but after the `prophetx_event_id` extraction (so we can log it):

```python
# New behavior in backend/app/workers/ws_prophetx.py:_upsert_event()
from app.workers.source_toggle import is_source_enabled

def _upsert_event(event_data: dict, op: str | None) -> None:
    prophetx_event_id = str(
        event_data.get("event_id") or event_data.get("id") or ""
    )
    if not prophetx_event_id:
        log.warning("ws_prophetx_event_missing_id", keys=list(event_data.keys()))
        return

    # D-01: Toggle check — skip DB writes but keep connection alive
    if not is_source_enabled("prophetx_ws"):
        log.debug("ws_prophetx_write_skipped", reason="source disabled", event_id=prophetx_event_id)
        return

    # ... rest of existing function unchanged
```

Note: `_write_ws_diagnostics()` is called from `_handle_broadcast_event()` BEFORE `_upsert_event()`, so WS diagnostic keys (heartbeat, last_message_at, ws:connection_state) are unaffected by the early return. Health badge remains green.

### Pattern 3: poll_prophetx Authority Bypass (NEW, D-03)

In `poll_prophetx.py`, the authority check currently runs unconditionally:

```python
# Existing code (poll_prophetx.py line ~226)
authoritative = is_ws_authoritative(
    existing.ws_delivered_at, settings.WS_AUTHORITY_WINDOW_SECONDS
)
is_ended = (status_value or "").lower() == "ended"

if not authoritative or is_ended:
    existing.prophetx_status = status_value
    ...
```

When ProphetX WS is disabled, `is_ws_authoritative()` must be treated as False so the poll worker writes freely. The modification:

```python
# Modified: bypass authority window when prophetx_ws toggle is off
from app.workers.source_toggle import is_source_enabled as _is_source_enabled

ws_toggle_enabled = _is_source_enabled("prophetx_ws")
authoritative = ws_toggle_enabled and is_ws_authoritative(
    existing.ws_delivered_at, settings.WS_AUTHORITY_WINDOW_SECONDS
)
is_ended = (status_value or "").lower() == "ended"

if not authoritative or is_ended:
    existing.prophetx_status = status_value
    ...
```

This is a short-circuit: if WS toggle is off, authority is always False, poll writes freely. If WS toggle is on, existing authority logic is unchanged.

### Pattern 4: `usage.py` source_toggle_keys Extension (additive)

```python
# backend/app/api/v1/usage.py line 137 — extend to include 3 new sources
source_toggle_keys = ["odds_api", "sports_data", "espn", "oddsblaze", "opticodds", "prophetx_ws"]
```

The loop on lines 138-141 already handles missing keys gracefully (`config_map.get(f"source_enabled_{src}", "true")`), so the new keys work even before seed rows exist in DB.

### Pattern 5: `seed.py` SOURCE_ENABLED_DEFAULTS Extension (additive)

```python
# backend/app/seed.py — add 2 new entries to SOURCE_ENABLED_DEFAULTS
SOURCE_ENABLED_DEFAULTS = {
    "source_enabled_odds_api":      ("true", "Enable Odds API polling source"),
    "source_enabled_sports_data":   ("true", "Enable SportsDataIO polling source"),
    "source_enabled_espn":          ("true", "Enable ESPN polling source"),
    "source_enabled_oddsblaze":     ("true", "Enable OddsBlaze polling source"),
    # NEW — Phase 15
    "source_enabled_opticodds":     ("true", "Enable OpticOdds polling source"),
    "source_enabled_prophetx_ws":   ("true", "Enable ProphetX WS status writes"),
}
```

`source_enabled_oddsblaze` already exists in the dict. Only `opticodds` and `prophetx_ws` are new additions (D-06). Seed script is idempotent — skips existing keys.

### Pattern 6: `SourceToggleSection.tsx` SOURCE_DISPLAY Extension (additive)

```typescript
// frontend/src/components/usage/SourceToggleSection.tsx
const SOURCE_DISPLAY: Record<string, string> = {
  odds_api:     "Odds API",
  sports_data:  "SportsDataIO",
  espn:         "ESPN",
  oddsblaze:    "OddsBlaze",    // NEW TOGL-01
  opticodds:    "OpticOdds",   // NEW TOGL-02
  prophetx_ws:  "ProphetX WS", // NEW TOGL-03
};
```

Object key order determines display order. Logical grouping: existing poll sources first (Odds API, SportsDataIO, ESPN), then new poll sources (OddsBlaze, OpticOdds), then WS source (ProphetX WS). This is within Claude's discretion.

### Anti-Patterns to Avoid

- **Calling `clear_source_and_recompute("prophetx_ws")` when WS is disabled:** ProphetX WS does NOT have an entry in `SOURCE_COLUMN_MAP` and should not get one. Clearing `prophetx_status` would remove the primary status data. D-02 explicitly forbids this.
- **Placing the toggle check outside `_upsert_event()`:** The toggle must live inside `_upsert_event()`, not in `_handle_broadcast_event()`. Diagnostic writes (`_write_ws_diagnostics`, `_write_heartbeat`) must still execute for health monitoring.
- **Adding `prophetx_ws` to `SOURCE_COLUMN_MAP` in `source_toggle.py`:** There is no column to clear. Adding it would cause `clear_source_and_recompute()` to silently do nothing (returns 0 for unknown keys), but it's still wrong to add.
- **DB call per WS message in the hot path:** `is_source_enabled()` opens a sync DB session on every call. For poll workers this is called once per task run. For WS, it's called on every broadcast message. This is a potential performance concern — see Open Questions.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Toggle state check | Custom config reads | `is_source_enabled(key)` from `source_toggle.py` | Already handles missing key → True default |
| Clearing stale data | Custom NULL loop | `clear_source_and_recompute(key)` | Also recomputes status_match for all events |
| Frontend config PATCH | New API client method | `updateInterval(key, value)` from `usage.ts` | Already used for interval changes; generic enough for toggle keys |
| WS authority bypass | New authority module | Short-circuit `is_ws_authoritative()` at call site | One-liner: `ws_toggle_enabled and is_ws_authoritative(...)` |

---

## Common Pitfalls

### Pitfall 1: ProphetX WS Diagnostic Keys Not Written When Toggle Off

**What goes wrong:** If the toggle check is placed in `_handle_broadcast_event()` instead of `_upsert_event()`, then `_write_ws_diagnostics()` never fires when WS is disabled. The health endpoint sees no `ws:last_message_at` key and reports the connection as dead — but the toggle requirement says the connection stays alive.

**Why it happens:** `_write_ws_diagnostics()` is called at the top of `_handle_broadcast_event()` before the `_upsert_event()` call. Moving the check up intercepts both the diagnostic write and the DB write.

**How to avoid:** Place the `is_source_enabled("prophetx_ws")` check at the top of `_upsert_event()` only. Verified by reading the call stack: `_handle_broadcast_event()` → `_write_ws_diagnostics()` → `_upsert_event()`.

**Warning signs:** After toggling ProphetX WS off, the WS health badge turns red (not green as specified in TOGL-04).

### Pitfall 2: poll_prophetx Authority Window Still Active When WS Disabled

**What goes wrong:** If `poll_prophetx.py` is not modified (D-03 ignored), then when WS is disabled, newly arriving events can still have `ws_delivered_at` set from before the toggle was flipped. `is_ws_authoritative()` returns True for the next 10 minutes (WS_AUTHORITY_WINDOW_SECONDS=600), so poll writes are still blocked. Events won't get updated statuses for up to 10 minutes even after the operator disables WS.

**Why it happens:** `ws_delivered_at` is a DB column that persists across toggle state changes. The authority window runs on wall-clock time from the last WS delivery, not from the toggle state.

**How to avoid:** Check `is_source_enabled("prophetx_ws")` before evaluating `is_ws_authoritative()`. Short-circuit: if WS toggle is off, authority is False unconditionally.

**Warning signs:** After toggling ProphetX WS off, `poll_prophetx_authority_window_skip` log entries continue to appear for up to 10 minutes.

### Pitfall 3: `is_source_enabled()` Called Per-Message in WS Hot Path

**What goes wrong:** The WS consumer processes every Pusher broadcast message. If there are hundreds of events, `is_source_enabled("prophetx_ws")` opens a new DB session for every message. Under sustained load this could exhaust the connection pool.

**Why it happens:** `is_source_enabled()` uses `SyncSessionLocal()` which creates a new connection each call. Poll workers call it once per task run (every 2-5 minutes) — this is fine. WS calls it on every broadcast message.

**How to avoid:** Cache the toggle result with a short TTL (e.g., module-level variable refreshed every 30 seconds) OR simply call `is_source_enabled()` each time and rely on the connection pool (the pool is the same used by the existing DB upsert, which also runs per-message). Given that the WS consumer processes events at low frequency in practice and the DB call is fast, the simpler approach of calling per-message is acceptable and consistent with the established pattern. Flag as a known tradeoff rather than blocking the implementation.

**Warning signs:** DB connection pool exhaustion errors in ws-consumer Docker logs under high-volume WS traffic.

### Pitfall 4: Seed Script Idempotency — `source_enabled_oddsblaze` Already Exists

**What goes wrong:** `source_enabled_oddsblaze` is already in `SOURCE_ENABLED_DEFAULTS` (line 47 of `seed.py`). Adding it again would cause a key collision in the dict literal (Python silently uses the last definition). This is not a runtime error but would be confusing.

**Why it happens:** The existing dict already seeded `source_enabled_oddsblaze`. Phase 15 only needs to add `source_enabled_opticodds` and `source_enabled_prophetx_ws`.

**How to avoid:** Add only the two new entries. Do not modify the existing `source_enabled_oddsblaze` entry.

### Pitfall 5: TOGL-05/TOGL-06 Verification Gap

**What goes wrong:** The backend toggle for OddsBlaze and OpticOdds is implemented but the `sources_enabled` API response currently does NOT include `oddsblaze` or `opticodds` keys (confirmed: `usage.py` line 137 only has `["odds_api", "sports_data", "espn"]`). The frontend cannot display what the API doesn't return.

**Why it happens:** Phase 15 is specifically the phase that adds these sources to the API response and frontend.

**How to avoid:** The `usage.py` change (D-08) MUST happen before the frontend change is useful. They are in the same phase — sequence: backend API first, then frontend.

---

## Code Examples

### `_upsert_event()` toggle guard placement (ws_prophetx.py)

The function currently opens `if not prophetx_event_id: return` as its first guard. The toggle check goes immediately after that check, so we have the event_id for logging:

```python
# Source: backend/app/workers/ws_prophetx.py (existing structure, new guard added)
def _upsert_event(event_data: dict, op: str | None) -> None:
    """Write a Pusher sport_event payload to the database and publish SSE."""
    prophetx_event_id = str(
        event_data.get("event_id") or event_data.get("id") or ""
    )
    if not prophetx_event_id:
        log.warning("ws_prophetx_event_missing_id", keys=list(event_data.keys()))
        return

    # TOGL-04: Skip DB writes when prophetx_ws source is disabled.
    # Connection stays alive — diagnostics written before this in _handle_broadcast_event.
    from app.workers.source_toggle import is_source_enabled
    if not is_source_enabled("prophetx_ws"):
        log.debug("ws_prophetx_write_skipped", reason="source_disabled", event_id=prophetx_event_id)
        return

    now = datetime.now(timezone.utc)
    # ... rest of existing function unchanged
```

### poll_prophetx authority bypass (D-03)

Only the single `authoritative = ...` line changes inside the update branch of the event upsert loop:

```python
# Source: backend/app/workers/poll_prophetx.py (inside the else: branch for existing events)
# D-03: bypass WS authority when prophetx_ws toggle is off
from app.workers.source_toggle import is_source_enabled as _is_prophetx_ws_enabled

ws_toggle_on = _is_prophetx_ws_enabled("prophetx_ws")
authoritative = ws_toggle_on and is_ws_authoritative(
    existing.ws_delivered_at, settings.WS_AUTHORITY_WINDOW_SECONDS
)
is_ended = (status_value or "").lower() == "ended"

if not authoritative or is_ended:
    existing.prophetx_status = status_value
    existing.status_source = "poll"
    existing.ws_delivered_at = None
    existing.status_match = compute_status_match(...)
else:
    # WS still authoritative — log discrepancy if needed
    ...
```

---

## Runtime State Inventory

> This phase involves no rename or refactor. No runtime state migration is required.

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | `source_enabled_oddsblaze` row already exists in `system_config` table (seeded in earlier phase). `source_enabled_opticodds` and `source_enabled_prophetx_ws` do NOT exist yet. | Seed script inserts the two new rows on next deploy (idempotent) |
| Live service config | ws-consumer Docker service has no toggle awareness; config change is handled at runtime via `is_source_enabled()` DB check | No service restart needed; toggle takes effect on next WS message |
| OS-registered state | None — no OS-level registrations | None |
| Secrets/env vars | No new env vars; toggle state lives in `system_config` DB table | None |
| Build artifacts | None | None |

---

## Environment Availability

> Step 2.6: SKIPPED — phase is purely code/config changes to existing running services. No new external tools, services, or CLIs are introduced.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.23 |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `cd backend && python -m pytest tests/test_ws_upsert.py tests/test_mismatch_detector.py -x -q` |
| Full suite command | `cd backend && python -m pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TOGL-01 | OddsBlaze key appears in `sources_enabled` API response | Integration (mock) | `pytest tests/test_source_toggle.py::test_usage_response_includes_oddsblaze -x` | Wave 0 |
| TOGL-02 | OpticOdds key appears in `sources_enabled` API response | Integration (mock) | `pytest tests/test_source_toggle.py::test_usage_response_includes_opticodds -x` | Wave 0 |
| TOGL-03 | ProphetX WS key appears in `sources_enabled` API response | Integration (mock) | `pytest tests/test_source_toggle.py::test_usage_response_includes_prophetx_ws -x` | Wave 0 |
| TOGL-04 | `_upsert_event()` returns early when prophetx_ws disabled; no DB write | Unit | `pytest tests/test_ws_upsert.py::TestWsToggle -x` | Wave 0 |
| TOGL-04 | poll_prophetx writes status when WS toggle off (authority bypassed) | Unit | `pytest tests/test_source_toggle.py::test_poll_prophetx_bypasses_authority_when_ws_disabled -x` | Wave 0 |
| TOGL-05 | OddsBlaze toggle off → poll_oddsblaze skips poll + clears column | Unit (existing pattern) | `pytest tests/test_source_toggle.py::test_oddsblaze_toggle_skips_and_clears -x` | Wave 0 |
| TOGL-06 | OpticOdds toggle off → poll_opticodds skips poll + clears column | Unit (existing pattern) | `pytest tests/test_source_toggle.py::test_opticodds_toggle_skips_and_clears -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `cd backend && python -m pytest tests/test_ws_upsert.py tests/test_source_toggle.py -x -q`
- **Per wave merge:** `cd backend && python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `backend/tests/test_source_toggle.py` — new test file covering TOGL-01/02/03/04/05/06 with mocked DB sessions
- [ ] New test class `TestWsToggle` in existing `backend/tests/test_ws_upsert.py` — covers TOGL-04 WS early-return behavior

*(Existing test infrastructure: `conftest.py`, `test_ws_upsert.py`, `test_status_authority.py` are all present and cover adjacent behavior)*

---

## Open Questions

1. **`is_source_enabled()` call frequency in WS hot path**
   - What we know: `is_source_enabled()` opens a `SyncSessionLocal()` DB connection per call. Poll workers call it once per task run. WS calls it on every broadcast message.
   - What's unclear: Under high WS message volume (many concurrent events), could this exhaust the connection pool?
   - Recommendation: Implement as per-message call first (consistent with established pattern). The connection pool is shared with `_upsert_event()` DB work which also runs per-message — the toggle check adds one extra checkout per message. If performance issues arise post-deploy, add a module-level cache with 30s TTL. For Phase 15, the simple approach is correct.

2. **`source_enabled_oddsblaze` row in production DB**
   - What we know: `seed.py` `SOURCE_ENABLED_DEFAULTS` already contains `source_enabled_oddsblaze` (line 47). The seed runs on deploy.
   - What's unclear: Whether the production DB already has this row (from a prior deploy) or not.
   - Recommendation: Seed script is idempotent — it skips existing keys. Either way is safe. No action needed.

---

## Sources

### Primary (HIGH confidence)

All findings are based on direct code inspection of the project repository. No external library research was needed — this phase uses no new dependencies.

- `backend/app/workers/source_toggle.py` — `is_source_enabled()`, `clear_source_and_recompute()`, `SOURCE_COLUMN_MAP`
- `backend/app/workers/ws_prophetx.py` — `_upsert_event()`, `_handle_broadcast_event()`, call stack
- `backend/app/workers/poll_prophetx.py` — authority window logic (`is_ws_authoritative()` call site)
- `backend/app/workers/poll_oddsblaze.py` lines 106-111 — established toggle check pattern
- `backend/app/workers/poll_opticodds.py` lines 146-152 — established toggle check pattern
- `backend/app/api/v1/usage.py` lines 136-141 — `source_toggle_keys` list (confirmed: missing oddsblaze/opticodds/prophetx_ws)
- `backend/app/seed.py` lines 43-48 — `SOURCE_ENABLED_DEFAULTS` (confirmed: oddsblaze present, opticodds/prophetx_ws absent)
- `frontend/src/components/usage/SourceToggleSection.tsx` — `SOURCE_DISPLAY`, toggle mutation pattern
- `frontend/src/api/usage.ts` — `UsageData` interface, `updateInterval()` function
- `frontend/src/pages/ApiUsagePage.tsx` — page layout, `sourcesEnabled` prop passing
- `backend/app/monitoring/authority.py` — `is_ws_authoritative()` signature
- `backend/pyproject.toml` — pytest configuration, asyncio_mode=auto

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all code directly inspected; no new dependencies
- Architecture patterns: HIGH — patterns extracted from existing working code; modifications are minimal and localized
- Pitfalls: HIGH — identified by tracing actual call paths in code; not speculative

**Research date:** 2026-04-07
**Valid until:** Stable (no external APIs; only internal code patterns — valid until project code changes)
