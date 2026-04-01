# Phase 10: WS Health Dashboard - Research

**Researched:** 2026-04-01
**Domain:** FastAPI health endpoint extension + React badge component + Redis diagnostic keys
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** WS badge sits in the same row as existing poll worker badges, using identical pill styling (green dot + label). No visual separation — it's a peer badge.
- **D-02:** Green/red binary only — `connected` = green, everything else (connecting/reconnecting/unavailable/missing) = red. Matches existing worker badge behavior exactly.
- **D-03:** Pusher state detail shown via native HTML `title` attribute tooltip on the WS badge. Pattern: `"ProphetX WS: {state}\nSince: {relative_time}"`. Consistent with existing badge `title` attributes.
- **D-04:** No styled tooltip component — use the same native title approach already on worker badges. Zero new dependencies.

### Claude's Discretion

- Health endpoint response shape for `ws_prophetx` — can be a richer object (state + timestamps) even though frontend only needs boolean + state + transition time.
- How to compute "since" relative time on the frontend — existing patterns may already have a utility or it can be computed inline.
- Whether to read `ws:sport_event_count` and `ws:last_message_at` in the health endpoint even though they aren't displayed (future-proofing vs YAGNI). Claude decides.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WSHLT-01 | GET /api/v1/health/workers response includes a `ws_prophetx` key with connection status | Add `ws:connection_state` to existing Redis mget in `health.py`; return `ws_prophetx` as a nested object with `connected` bool + `state` string + `since` timestamp |
| WSHLT-02 | Dashboard displays a ProphetX WS health badge alongside existing worker badges | Extend `WORKERS` array in `SystemHealth.tsx` with a custom WS entry; re-use existing pill CSS classes |
| WSHLT-03 | Dashboard shows Pusher connection state detail (connected/connecting/reconnecting/unavailable) with last transition time | Enrich tooltip from `ws_prophetx.state` + `ws_prophetx.since`; use `date-fns formatDistanceToNow` for relative time |
</phase_requirements>

---

## Summary

Phase 10 is a targeted surface operation with two independent touch points: a backend endpoint extension and a frontend badge addition. All infrastructure was built in Phase 8. The Redis key `ws:connection_state` already exists in production (written by `_write_ws_connection_state("connected")` in `ws_prophetx.py`). The health endpoint already uses an async Redis `mget` pattern. The frontend already has the `WORKERS` array pattern, the `cn()` utility, and `@tanstack/react-query` with a 30s refetch interval. The `date-fns` package is already installed in the frontend.

The only design decision requiring judgment is the backend response shape for `ws_prophetx`. The current `ws:connection_state` key stores only a plain string state value (e.g. `"connected"`). There is no separate timestamp key recording when the state last transitioned. To satisfy WSHLT-03's "last transition time" requirement, the implementation must either: (a) add a companion `ws:connection_state_since` key written alongside `ws:connection_state`, or (b) store the value as a JSON object. Option (a) is more consistent with existing patterns (flat Redis keys) and allows independent TTL control.

The 30s `refetchInterval` on the frontend already satisfies success criteria #4 ("reflects current state within 30 seconds") because the 120s TTL on `ws:connection_state` self-expires after the consumer dies, so the next poll will see the key absent and render red.

**Primary recommendation:** Add `ws:connection_state_since` as a companion key in `_write_ws_connection_state()`. Return a nested `ws_prophetx: {connected: bool, state: str | null, since: str | null}` object from the health endpoint. Extend `SystemHealth.tsx` with a separate render path for the WS badge. Use `date-fns formatDistanceToNow` for the tooltip relative time.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| redis.asyncio (aioredis) | ≥5.0 (already installed) | Async Redis reads in health endpoint | Already used via `get_redis_client()` in `health.py` |
| FastAPI | ≥0.115 (already installed) | Endpoint definition | Project standard |
| @tanstack/react-query | ^5.90.21 (already installed) | 30s polling of health endpoint | Already wires `SystemHealth.tsx` |
| date-fns | ^4.1.0 (already installed) | `formatDistanceToNow` for relative timestamp in tooltip | Already used in `NotificationCenter.tsx` and `CallVolumeChart.tsx` |
| tailwind + cn() | already installed | Conditional pill class application | Already in `SystemHealth.tsx` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| TypeScript interface extension | N/A | Extend `WorkerHealth` with `ws_prophetx` field | Required: frontend type must match new endpoint shape |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `formatDistanceToNow` (date-fns) | Inline `Math.floor((Date.now() - new Date(since)) / 60000) + "m ago"` | Inline is simpler, zero import cost; date-fns is cleaner and handles edge cases. Either is acceptable given date-fns is already installed. |
| Separate `ws:connection_state_since` Redis key | JSON-encode state+timestamp as `ws:connection_state` value | JSON value breaks the existing `_write_ws_connection_state` tests (they assert exact string value). Separate key is safer. |

**No installation required** — all dependencies already present.

---

## Architecture Patterns

### Backend: Response Shape for `ws_prophetx`

Recommendation: return a **nested object** for `ws_prophetx` (not a flat boolean), so the frontend can render the tooltip without a second API call.

```python
# Source: health.py — extend existing mget pattern
{
    "poll_prophetx":    True,          # existing — bool
    "poll_sports_data": False,         # existing — bool
    # ... other workers ...
    "ws_prophetx": {                   # new — richer object
        "connected": True,             # bool: state == "connected"
        "state":     "connected",      # str | None: raw Pusher state, None if key missing
        "since":     "2026-04-01T14:00:00+00:00",  # ISO str | None: transition time
    }
}
```

**Why nested object, not boolean:** The frontend needs `state` for the tooltip text and `since` for the relative time. A separate WS-specific endpoint would add round-trip overhead. A nested object is a minimal, non-breaking extension.

**Why not add `ws:last_message_at` or `ws:sport_event_count`:** YAGNI. Those keys are for production gate observation (Phase 8). Including them in the health response adds complexity with no current consumer.

### Backend: Companion Redis Key

Add `ws:connection_state_since` written alongside `ws:connection_state` in `_write_ws_connection_state()`:

```python
# Source: backend/app/workers/ws_prophetx.py — extend _write_ws_connection_state
def _write_ws_connection_state(state: str) -> None:
    r = _sync_redis.from_url(settings.REDIS_URL)
    now_iso = datetime.now(timezone.utc).isoformat()
    r.set("ws:connection_state", state, ex=120)
    r.set("ws:connection_state_since", now_iso, ex=120)  # same TTL
```

**TTL rationale:** Same 120s TTL as `ws:connection_state`. Both keys self-expire together if the consumer dies. The `since` timestamp refers to the last known state; if the key is absent, state is effectively "unknown/disconnected".

### Backend: Health Endpoint Extension

Extend the existing `mget` call to include both new keys:

```python
# Source: backend/app/api/v1/health.py
keys = [
    "worker:heartbeat:poll_prophetx",
    "worker:heartbeat:poll_sports_data",
    "worker:heartbeat:poll_odds_api",
    "worker:heartbeat:poll_sports_api",
    "worker:heartbeat:poll_espn",
    "ws:connection_state",        # new
    "ws:connection_state_since",  # new
]
results = await redis.mget(*keys)
ws_state = results[5]  # str | None
ws_since = results[6]  # ISO str | None

return {
    "poll_prophetx":    results[0] is not None,
    "poll_sports_data": results[1] is not None,
    "poll_odds_api":    results[2] is not None,
    "poll_sports_api":  results[3] is not None,
    "poll_espn":        results[4] is not None,
    "ws_prophetx": {
        "connected": ws_state == "connected",
        "state":     ws_state,
        "since":     ws_since,
    },
}
```

### Frontend: TypeScript Interface Extension

```typescript
// Source: frontend/src/components/SystemHealth.tsx — extend WorkerHealth
interface WsProphetXHealth {
  connected: boolean;
  state: string | null;
  since: string | null;
}

interface WorkerHealth {
  poll_prophetx:    boolean;
  poll_sports_data: boolean;
  poll_odds_api:    boolean;
  poll_sports_api:  boolean;
  poll_espn:        boolean;
  ws_prophetx:      WsProphetXHealth;
}
```

### Frontend: WS Badge Rendering

The WS badge cannot use the generic `WORKERS.map()` because it needs a custom tooltip. Render it separately after the `WORKERS.map()` output:

```tsx
// Source: frontend/src/components/SystemHealth.tsx — after existing WORKERS.map block
import { formatDistanceToNow } from "date-fns";

function wsTitle(ws: WsProphetXHealth): string {
  const state = ws.state ?? "unknown";
  if (!ws.since) return `ProphetX WS: ${state}`;
  const sinceStr = formatDistanceToNow(new Date(ws.since), { addSuffix: true });
  return `ProphetX WS: ${state}\nSince: ${sinceStr}`;
}

// In JSX, after WORKERS.map(…):
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
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full shrink-0",
          active ? "bg-emerald-400 animate-pulse" : "bg-red-500"
        )}
      />
      WS
    </span>
  );
})()}
```

**Label choice:** "WS" is short and consistent with the pill format. Alternatively "ProphetX WS" but it's longer. Either works; "WS" avoids redundancy since "ProphetX" already appears in the tooltip.

### Anti-Patterns to Avoid

- **Don't add `ws_prophetx` to the `WORKERS` array** with `key: "ws_prophetx"` — the array is typed to `keyof WorkerHealth` expecting `boolean` values; `ws_prophetx` is now an object. This would require a union type and complicate the generic map loop.
- **Don't use a styled tooltip library** — D-04 is locked: native `title` attribute only.
- **Don't omit the `ws:connection_state_since` key from the TTL** — if `connection_state` expires but `since` does not, the `since` value becomes stale and misleading.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Relative time formatting | Custom `"X minutes ago"` formatter | `date-fns formatDistanceToNow` | Already installed; handles plurals, edge cases (just now, yesterday, etc.) |
| Redis mget | Sequential `redis.get()` calls per key | `redis.mget(*keys)` | Already established pattern in `health.py`; one round-trip |
| Conditional CSS | Manual string concatenation | `cn()` from `@/lib/utils` | Already used in `SystemHealth.tsx` |

---

## Common Pitfalls

### Pitfall 1: `ws:connection_state` TTL race — badge flickers green/red during token refresh
**What goes wrong:** During the planned token refresh cycle (~every 20min), `_connect_and_run()` returns, the old `ws:connection_state` key expires after 120s, and then a new connection writes `"connected"` again. During that window, the badge shows red.
**Why it happens:** `_write_ws_connection_state` is only called in `_on_connect`. If reconnect takes more than 120s (unlikely but possible under backoff), the key self-expires.
**How to avoid:** This is the intended behavior per Phase 8 design — self-expiry is the disconnection signal. No special handling needed. Document it as "by design."
**Warning signs:** Badge oscillates red/green on a ~20min cycle in production. If observed, it confirms the heartbeat pattern is working.

### Pitfall 2: `ws_prophetx` field missing — frontend crashes if backend is older than Phase 10
**What goes wrong:** If the backend hasn't been deployed yet, `/health/workers` returns the old shape without `ws_prophetx`. TypeScript interface now requires it.
**How to avoid:** Use optional field in the interface: `ws_prophetx?: WsProphetXHealth`. The badge render block already guards with `{data.ws_prophetx && ...}`.

### Pitfall 3: Existing `test_health.py` breaks — assertion requires exact worker keys
**What goes wrong:** `test_worker_health_returns_200` asserts exactly 5 workers: `["poll_prophetx", ..., "poll_espn"]`. After Phase 10, `ws_prophetx` is a 6th key with an object value, not a boolean. The test would pass on the 5 keys but the shape check `isinstance(data[worker], bool)` does not cover `ws_prophetx` — so the existing test does NOT break. However, it also doesn't verify the new key.
**How to avoid:** Add a new test class `TestWorkerHealthWsProphetX` that verifies: (1) `ws_prophetx` key present, (2) it's a dict with `connected`, `state`, `since` keys, (3) `connected` is bool.

### Pitfall 4: `formatDistanceToNow` called on `null` or invalid ISO string
**What goes wrong:** If `ws_prophetx.since` is `null` (key missing from Redis), passing it to `new Date(null)` produces epoch time, resulting in "56 years ago."
**How to avoid:** The `wsTitle()` helper guards: `if (!ws.since) return \`ProphetX WS: ${state}\`;`

### Pitfall 5: `ws:connection_state_since` not written on initial connection
**What goes wrong:** The `ws:connection_state` key is first written in `_on_connect`. If `_write_ws_connection_state` is extended to also write `ws:connection_state_since`, both keys are written atomically in the same function — no gap. But if the companion key is added elsewhere (e.g., a separate function), there's a window where `state` exists but `since` doesn't.
**How to avoid:** Write both keys inside `_write_ws_connection_state()` in a single Redis connection.

---

## Code Examples

### mget with 7 keys (existing pattern extended)
```python
# Source: backend/app/api/v1/health.py (current pattern at line 28-42)
results = await redis.mget(*keys)  # returns list[str | None] in key order
ws_state = results[5]              # None if key doesn't exist (TTL expired or never written)
ws_since = results[6]
```

### date-fns formatDistanceToNow (verified usage in project)
```typescript
// Source: frontend/src/components/NotificationCenter.tsx (existing usage)
import { format } from "date-fns";
// For relative time:
import { formatDistanceToNow } from "date-fns";
formatDistanceToNow(new Date(isoString), { addSuffix: true })
// Returns e.g.: "3 minutes ago", "just now", "about 2 hours ago"
```

### Existing badge pill CSS (exact classes from SystemHealth.tsx lines 48-53)
```tsx
// Active (green):
"bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
// Inactive (red):
"bg-red-500/10 text-red-400 border-red-500/20"
// Dot active: "h-1.5 w-1.5 rounded-full shrink-0 bg-emerald-400 animate-pulse"
// Dot inactive: "h-1.5 w-1.5 rounded-full shrink-0 bg-red-500"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No WS health visibility | Redis `ws:connection_state` key with 120s TTL | Phase 8 (2026-04-01) | Key exists and is ready to read |
| Flat boolean-only worker health response | Extend with nested object for WS | Phase 10 | Non-breaking: new key is additive |

---

## Open Questions

1. **WS badge label: "WS" vs "ProphetX WS"**
   - What we know: existing labels are short ("ProphetX", "SDIO", "ESPN") — "WS" is consistent
   - What's unclear: whether "WS" alone is clear to operators without context
   - Recommendation: Use "WS" — tooltip text already says "ProphetX WS: {state}" which provides the full context on hover

2. **YAGNI: Include `ws:last_message_at` in health response?**
   - What we know: key exists, no current frontend consumer
   - What's unclear: future use case timeline
   - Recommendation: YAGNI — do not include. Adding it later is a two-line change.

---

## Environment Availability

> Step 2.6: SKIPPED — Phase 10 is a code-only change extending existing infrastructure. All runtime dependencies (Redis, FastAPI, React) are pre-existing project services with no new external tools required.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0 + pytest-asyncio 0.23 |
| Config file | `backend/pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `cd backend && uv run pytest tests/test_health.py tests/test_ws_diagnostics.py -x -q` |
| Full suite command | `cd backend && uv run pytest tests/ -x -q` |

**Note:** All tests require Docker services running (`docker compose up -d postgres redis backend`). There is no unit-testable mock layer for the health endpoint (it uses real Redis via `get_redis_client()`). The Phase 8 WS diagnostic tests use `unittest.mock.patch` to avoid real Redis — same pattern should be used for new tests.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WSHLT-01 | `/health/workers` returns `ws_prophetx` key with `connected`, `state`, `since` fields | unit (mock Redis) + integration | `uv run pytest tests/test_health.py -x -q` | ✅ (needs new test class) |
| WSHLT-01 | `ws_prophetx.connected` is `True` when `ws:connection_state == "connected"` | unit (mock Redis mget) | `uv run pytest tests/test_health.py::TestWorkerHealthWsProphetX -x -q` | ❌ Wave 0 |
| WSHLT-01 | `ws_prophetx.connected` is `False` when key absent | unit (mock Redis mget returns None) | `uv run pytest tests/test_health.py::TestWorkerHealthWsProphetX -x -q` | ❌ Wave 0 |
| WSHLT-02 | WS badge rendered (visual) | manual | N/A | N/A — frontend only |
| WSHLT-03 | `wsTitle()` returns correct format when `state="connected"` and `since` is ISO string | unit (pure TS function — not easily pytest-able) | manual visual test | ❌ — frontend logic, tested manually |

**Frontend testing:** No frontend test framework is configured (no `jest.config.*` or `vitest.config.*` found). Frontend correctness is validated by manual visual inspection per project convention.

### Sampling Rate
- **Per task commit:** `cd backend && uv run pytest tests/test_health.py -x -q`
- **Per wave merge:** `cd backend && uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_health.py` — add `TestWorkerHealthWsProphetX` class with 3 tests for new `ws_prophetx` key shape (mock Redis mget)
- [ ] `backend/tests/test_ws_diagnostics.py` — add `TestWriteWsConnectionStateSince` class verifying `ws:connection_state_since` is written alongside `ws:connection_state` with same TTL

*(All other test infrastructure exists — conftest.py, pytest config, existing test_health.py.)*

---

## Sources

### Primary (HIGH confidence)
- Direct file read: `backend/app/api/v1/health.py` — current endpoint structure, mget pattern, exact Redis keys
- Direct file read: `backend/app/workers/ws_prophetx.py` — `_write_ws_connection_state()` implementation, TTL decisions
- Direct file read: `frontend/src/components/SystemHealth.tsx` — `WORKERS` array pattern, pill CSS, react-query polling
- Direct file read: `backend/tests/test_health.py` — existing test coverage and assertions
- Direct file read: `frontend/package.json` — confirmed `date-fns ^4.1.0` already installed
- Direct file read: `frontend/src/components/NotificationCenter.tsx` — confirms `date-fns format` import pattern in project
- Direct file read: `backend/pyproject.toml` — confirmed `pytest 8.0 + pytest-asyncio 0.23` in dev deps

### Secondary (MEDIUM confidence)
- Direct file read: `backend/tests/test_ws_diagnostics.py` — Phase 8 mock pattern for `_write_ws_connection_state` tests; informs new companion key test structure

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified by direct file inspection; no new dependencies
- Architecture: HIGH — patterns read directly from existing source files
- Pitfalls: HIGH — identified from direct code analysis (TTL values, TypeScript interface shape, existing test assertions)

**Research date:** 2026-04-01
**Valid until:** 2026-05-01 (stable stack; all dependencies pinned in project files)
