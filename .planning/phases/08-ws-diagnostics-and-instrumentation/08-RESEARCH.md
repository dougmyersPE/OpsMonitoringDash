# Phase 8: WS Diagnostics and Instrumentation - Research

**Researched:** 2026-03-31
**Domain:** Python WebSocket consumer instrumentation, Celery cross-service task dispatch, Redis key design
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Fire `poll_prophetx` on every reconnect — both error recovery and token-refresh cycles. No distinction needed; poll_prophetx is cheap (single API call).
- **D-02:** Use `celery_app.send_task('poll_prophetx')` from the WS consumer service. This enqueues via the Redis broker without importing the task module — standard Celery cross-service pattern.
- **D-03:** Fire immediately on reconnect, no stabilization delay. The Celery task runs independently of WS connection state.
- **D-04:** Tag reconciliation runs with `trigger='ws_reconnect'` kwarg so poll_prophetx logs distinguish reconnect-triggered runs from scheduled runs. Useful during Phase 8 observation window.

### Claude's Discretion

- Redis health key design: TTLs, value formats, update frequency for `ws:connection_state`, `ws:last_message_at`, `ws:last_sport_event_at`, `ws:sport_event_count`. Sensible defaults based on existing `worker:heartbeat` patterns (90s TTL, written on each event/heartbeat cycle).
- WSREL-02 fix: Add `status_match=compute_status_match(...)` to the new-event creation path in `_upsert_event()` (line ~177). Straightforward — the update path already does this.
- Production gate observation: Manual check of `ws:sport_event_count` in Redis after 24-48h covering live game windows. No automated alerting needed for the gate itself.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WSREL-01 | System detects WS disconnection gaps and triggers immediate poll_prophetx reconciliation run on reconnect | D-01 through D-04 specify the full implementation: `celery_app.send_task` at connection establishment in `_connect_and_run()` with `trigger='ws_reconnect'` kwarg; `poll_prophetx` task signature updated to accept and log the kwarg |
| WSREL-02 | WS consumer computes status_match when creating new events (fix NULL bug) | The bug is a missing `status_match=compute_status_match(...)` call in the `if existing is None:` branch of `_upsert_event()`. The update path (lines 213-220) already does this correctly. Fix is a direct copy pattern. |
</phase_requirements>

---

## Summary

Phase 8 makes two targeted code changes to `ws_prophetx.py` and one change to `poll_prophetx.py`, then adds four Redis diagnostic keys. The code is well-understood from source reading — all patterns exist in the codebase already. The only uncertainty is empirical: whether ProphetX actually sends `sport_event` change-type messages in production. The production gate (`ws:sport_event_count > 0`) resolves that uncertainty before Phase 9 begins.

**WSREL-02 (status_match NULL bug):** The create path in `_upsert_event()` (line 176-197) constructs an `Event` object but never calls `compute_status_match()`. The update path immediately below (lines 213-220) does call it. Fix: add `status_match=compute_status_match(status_value, None, None, None, None, None)` to the `Event(...)` constructor call. The external source statuses are NULL for new WS-created events, so all arguments after `status_value` are `None` — this is correct and safe.

**WSREL-01 (reconnect reconciliation):** The correct insertion point is immediately after `connection_ready.set()` in `_on_connect()` inside `_connect_and_run()`. The `_on_connect` callback fires on every connection establishment — both the initial connect and any pysher-internal reconnects. For the token-refresh reconnect (clean `_connect_and_run()` exit/re-enter), this also fires. `celery_app.send_task('app.workers.poll_prophetx.run', kwargs={'trigger': 'ws_reconnect'})` enqueues without importing the task.

**Redis diagnostics:** Four new `ws:*` keys follow the same pattern as `worker:heartbeat:ws_prophetx`. The counter (`ws:sport_event_count`) uses Redis INCR (atomic, no TTL) so it accumulates across restarts. The timestamp keys use TTLs to self-clean if the consumer dies.

**Primary recommendation:** All three files need edits. Keep changes minimal and isolated — no refactoring adjacent code.

---

## Standard Stack

### Core (no new dependencies needed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| redis (sync) | >=5.0 (already installed) | `_sync_redis.from_url()` for all Redis writes | Already used in `ws_prophetx.py` — `_write_heartbeat()` and `_publish_update()` use it |
| celery | >=5.4 (already installed) | `celery_app.send_task()` for cross-service task dispatch | `celery_app` already imported in `poll_prophetx.py`; D-02 specifies this exact approach |
| structlog | >=24.0 (already installed) | Structured logging for `trigger` kwarg | Already used throughout workers |

No new packages needed. All required libraries are in `pyproject.toml`.

**Installation:** None required.

---

## Architecture Patterns

### Reconnect Trigger Pattern (WSREL-01)

The `_on_connect` callback in `_connect_and_run()` is the correct hook. It fires every time pysher establishes a connection — both initial connect and all reconnects. The token-refresh cycle exits `_connect_and_run()` and re-enters it from `run()`, which calls `_connect_and_run()` again → `_on_connect` fires again. Error reconnects are handled internally by pysher (`reconnect_interval=5`), which also fires `_on_connect`.

The `celery_app` instance is not imported in `ws_prophetx.py` today. Two valid approaches:

**Option A (import celery_app):** Add `from app.workers.celery_app import celery_app` to `ws_prophetx.py`. Works because `celery_app` only imports config/settings — no circular dependency risk. Cleanest approach.

**Option B (send_task via fresh Celery instance):** Create a minimal Celery app with just the broker URL. More verbose, no benefit in this case.

**Recommendation:** Option A. The `celery_app` module is already used by all worker tasks; `ws_prophetx.py` is a worker-adjacent service and importing it creates no circular dependency.

```python
# In ws_prophetx.py — add to imports
from app.workers.celery_app import celery_app

# In _on_connect callback inside _connect_and_run()
def _on_connect(data: str) -> None:
    log.info("ws_prophetx_connected")
    connection_ready.set()
    # WSREL-01: trigger immediate reconciliation on every reconnect
    celery_app.send_task(
        "app.workers.poll_prophetx.run",
        kwargs={"trigger": "ws_reconnect"},
    )
    log.info("ws_prophetx_reconnect_reconciliation_queued")
```

### poll_prophetx trigger kwarg (D-04)

The `run` task currently accepts no kwargs. Add `trigger: str = "scheduled"` so the task accepts and logs the trigger source:

```python
@celery_app.task(name="app.workers.poll_prophetx.run", bind=True, max_retries=3)
def run(self, trigger: str = "scheduled"):
    log.info("poll_prophetx_started", trigger=trigger)
    ...
```

No behavior change — `trigger` is purely a logging label.

### WSREL-02 Fix Pattern

The `Event(...)` constructor call is at line 177-191. Add `status_match=` as a keyword argument:

```python
# Source: ws_prophetx.py _upsert_event() create path
event = Event(
    prophetx_event_id=prophetx_event_id,
    sport=...,
    ...
    prophetx_status=status_value,
    last_prophetx_poll=now,
    status_match=compute_status_match(   # <-- add this
        status_value,
        None,   # odds_api_status — not known at WS create time
        None,   # sports_api_status
        None,   # sdio_status
        None,   # espn_status
        None,   # oddsblaze_status
    ),
)
```

`compute_status_match()` returns `True` when `px_status` is set and all source statuses are `None` (the function treats missing sources as "no disagreement"). This is the correct starting value for a newly-created WS event — not NULL.

### Redis Diagnostic Keys Design

Four new keys in the `ws:` namespace, distinct from `worker:heartbeat:*`:

| Key | Value | TTL | Update Point | Notes |
|-----|-------|-----|-------------|-------|
| `ws:connection_state` | `"connected"` or `"disconnected"` | 120s | Set to "connected" in `_on_connect`; set to "disconnected" on clean disconnect/expiry | TTL acts as implicit "disconnected" after 2x heartbeat interval |
| `ws:last_message_at` | ISO timestamp string | 120s | Every message received in `_handle_broadcast_event` (all change_types) | Covers all Pusher traffic, not just sport_events |
| `ws:last_sport_event_at` | ISO timestamp string | None (permanent until overwritten) | Only when `change_type == "sport_event"` in `_handle_broadcast_event` | No TTL — persists across reconnects for observability |
| `ws:sport_event_count` | integer (INCR) | None (permanent, accumulates) | INCR only when `change_type == "sport_event"` | Production gate key — must be > 0 before Phase 9 |

**TTL rationale:** `worker:heartbeat:ws_prophetx` uses 90s TTL written every 10s. The new connection-state key uses 120s (2x the 60s health-check loop) so it survives brief polling gaps. Timestamp keys use 120s for the same reason. The count key is permanent — it's a cumulative counter, not a health signal.

**Update frequency:** `ws:last_message_at` writes on every Pusher message (both sport_event and other change_types). This adds one Redis SET per message, which is negligible. The `_write_heartbeat()` function already shows the project is comfortable with per-event Redis writes.

**Implementation helper:**

```python
# Add to ws_prophetx.py Redis helpers section
def _write_ws_diagnostics(event_type: str) -> None:
    """Write ws:* diagnostic keys. Called from _handle_broadcast_event."""
    from app.core.config import settings
    r = _sync_redis.from_url(settings.REDIS_URL)
    now_iso = datetime.now(timezone.utc).isoformat()
    r.set("ws:last_message_at", now_iso, ex=120)
    if event_type == "sport_event":
        r.set("ws:last_sport_event_at", now_iso)
        r.incr("ws:sport_event_count")

def _write_ws_connection_state(state: str) -> None:
    """Write ws:connection_state. Called on connect/disconnect."""
    from app.core.config import settings
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.set("ws:connection_state", state, ex=120)
```

### Anti-Patterns to Avoid

- **Don't pipeline multiple Redis commands:** The existing pattern uses a single `r.set()` per call, creating a new connection per write. This matches the rest of the codebase. Do not change to pipeline or connection pooling — that's a separate concern.
- **Don't filter reconnect trigger by type:** D-01 is explicit — fire on every reconnect, no distinction between error recovery and token-refresh. The implementation must not add conditional logic around the `send_task` call.
- **Don't import task functions directly:** D-02 specifies `send_task` by name string. Never `from app.workers.poll_prophetx import run` and call `run.delay()` — that would import the full task module and all its dependencies into the WS consumer process.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic counter | Custom Redis counter with GET+SET | `r.incr("ws:sport_event_count")` | Redis INCR is atomic; GET+SET has a race condition in theory (though WS consumer is single-threaded, INCR is still the correct idiom) |
| Cross-service task dispatch | Direct function import | `celery_app.send_task("task.name", ...)` | Avoids import coupling; task runs independently of WS connection state (per D-02, D-03) |

---

## Common Pitfalls

### Pitfall 1: `_on_connect` fires only on initial connect in some pysher versions

**What goes wrong:** Pysher's internal reconnect handling fires `pusher:connection_established` on initial connect but may not re-fire it on pysher-internal reconnects in all versions.

**Why it happens:** pysher reconnect behavior depends on version. The `reconnect_interval=5` parameter means pysher manages brief reconnects internally without calling `_connect_and_run()` again.

**How to avoid:** Verify by checking if pysher fires `pusher:connection_established` on reconnect. If it does not, a fallback is to also call `send_task` on the token-refresh reconnect path (at the top of `_connect_and_run()` after `connection_ready.wait()` succeeds on a re-entry). The token-refresh cycle is reliable because `run()` explicitly calls `_connect_and_run()` again.

**Recommended approach:** Bind `_on_connect` to `pusher:connection_established` as specified. The token-refresh path (every ~20 min) provides a reliable floor of reconciliation. If pysher internal reconnects don't re-fire `_on_connect`, document the limitation — it only affects brief network interruptions that pysher handles without a full disconnect cycle.

**Warning signs:** Celery logs show `trigger=ws_reconnect` only every ~20 minutes (token refresh interval) but never more frequently despite observed network blips.

### Pitfall 2: NULL status_match persists on existing rows after WSREL-02 fix

**What goes wrong:** Fixing the create path prevents future NULL status_match values but does not backfill existing rows with NULL.

**Why it happens:** Events already in the database from before the fix have `status_match = NULL`. The `poll_prophetx` task's final loop (lines 278-291) recomputes `status_match` for all events each run — this will naturally backfill NULL rows within the next poll cycle after deploy.

**How to avoid:** No migration needed. The existing `poll_prophetx` recompute pass covers backfill automatically. Verify by checking for NULL values after the first poll run post-deploy.

**Warning signs:** NULL status_match values persist more than 5-10 minutes after deploy (the poll interval).

### Pitfall 3: `ws:sport_event_count` stays at 0 despite active WS connection

**What goes wrong:** Production gate fails even with a connected WS consumer. This is a known risk documented in STATE.md.

**Why it happens:** ProphetX may not be sending sport_event change_type messages to the subscribed broadcast channel. This is a channel configuration issue on ProphetX's side, not a code bug.

**How to avoid:** Distinguish between "WS connected and receiving messages" vs "WS connected but no sport_events." The `ws:last_message_at` key will update even for non-sport_event messages (market, market_line change types). If `ws:last_message_at` is updating but `ws:sport_event_count` stays at 0, the channel is active but sport_events are not flowing — escalate to ProphetX.

**Warning signs:** `ws:last_message_at` updating, `ws:last_sport_event_at` NULL, `ws:sport_event_count` = 0.

### Pitfall 4: `celery_app.send_task` silently drops if broker is unreachable

**What goes wrong:** The WS consumer starts, pysher connects, `_on_connect` fires, but the task never appears in Celery because Redis is temporarily down.

**Why it happens:** `send_task` uses the configured broker (Redis). If Redis is unavailable, Celery raises a connection error.

**How to avoid:** Wrap the `send_task` call in a try/except with a log.error — never let task dispatch failures crash the WS connection. The WS consumer's primary job is event processing; reconciliation is best-effort.

```python
try:
    celery_app.send_task(
        "app.workers.poll_prophetx.run",
        kwargs={"trigger": "ws_reconnect"},
    )
    log.info("ws_prophetx_reconnect_reconciliation_queued")
except Exception:
    log.exception("ws_prophetx_reconnect_reconciliation_dispatch_failed")
```

---

## Code Examples

### Verified: compute_status_match with all-None sources

```python
# Source: backend/app/monitoring/mismatch_detector.py lines 270-307
# When px_status is set and all source statuses are None:
# - Loop iterates but `if not source_status: continue` skips every source
# - Returns True (no disagreement found)
compute_status_match("not_started", None, None, None, None, None)  # → True
compute_status_match("live", None, None, None, None, None)          # → True
```

This confirms that `status_match=compute_status_match(status_value, None, None, None, None, None)` in the Event constructor produces `True` for any non-None `status_value`, which is the correct initial state.

### Verified: Celery send_task cross-service pattern

```python
# Source: Celery docs — standard pattern for dispatching to a named task
# without importing the task module
celery_app.send_task(
    "app.workers.poll_prophetx.run",   # exact name from @celery_app.task(name=...)
    kwargs={"trigger": "ws_reconnect"},
)
# Task name confirmed from poll_prophetx.py line 63:
# @celery_app.task(name="app.workers.poll_prophetx.run", bind=True, max_retries=3)
```

### Verified: Redis INCR pattern (existing project pattern)

```python
# Source: backend/app/workers/poll_prophetx.py lines 46-61
# _increment_call_counter() uses r.incr(key) — exact same pattern for ws:sport_event_count
count = r.incr("ws:sport_event_count")  # atomic, initializes to 1 on first call
# No TTL on the counter — accumulates permanently
```

### Verified: Existing ws_prophetx.py reconnect flow

```python
# Source: backend/app/workers/ws_prophetx.py lines 299-376
# run() loop:
#   _connect_and_run()  ← token-refresh exits here (clean)
#   retry on exception  ← error recovery exits here
# Both paths re-call _connect_and_run() → _on_connect fires again
# → reconnect reconciliation fires on both token-refresh AND error recovery paths
```

---

## Environment Availability

All services run via Docker Compose. No host-level tool dependencies for this phase.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | All services | ✓ | 29.2.1 | — |
| Redis (in container) | Redis key writes, Celery broker | ✓ | 7-alpine (docker-compose.yml) | — |
| Python 3.11+ | Backend/worker build | ✓ | 3.11.7 | — |
| Celery (in container) | Task dispatch | ✓ | >=5.4 (pyproject.toml) | — |
| pysher (in container) | WS consumer | ✓ | >=1.0 (pyproject.toml) | — |

**No missing dependencies.** All changes are to Python source files in the existing backend image.

**Production gate check:** Manual `docker exec` into the running redis container:
```bash
docker compose exec redis redis-cli get ws:sport_event_count
```

---

## Validation Architecture

The `workflow.nyquist_validation` key is absent from `.planning/config.json` — treated as enabled.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio |
| Config file | `backend/pyproject.toml` ([tool.pytest.ini_options]) |
| Quick run command | `cd backend && python -m pytest tests/test_mismatch_detector.py -x -q` |
| Full suite command | `cd backend && python -m pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WSREL-02 | `compute_status_match` with all-None sources returns True | unit | `cd backend && python -m pytest tests/test_mismatch_detector.py -x -q` | ✅ existing file, but new test case needed |
| WSREL-02 | New event created via WS has non-NULL status_match | unit | `cd backend && python -m pytest tests/test_ws_upsert.py -x -q` | ❌ Wave 0 — create this file |
| WSREL-01 | `send_task` is called after `connection_ready.set()` in `_on_connect` | unit (mock) | `cd backend && python -m pytest tests/test_ws_reconnect.py -x -q` | ❌ Wave 0 — create this file |

**Manual-only tests:**
- Redis keys `ws:connection_state`, `ws:last_message_at`, `ws:last_sport_event_at`, `ws:sport_event_count` are present and updating — manual inspection via `docker compose exec redis redis-cli` during a live WS session. Automating this requires a running Docker environment and ProphetX connectivity — not suitable for the unit test suite.
- Production gate (`ws:sport_event_count > 0`) — manual observation window, 24-48h.

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/test_mismatch_detector.py tests/test_ws_upsert.py tests/test_ws_reconnect.py -x -q`
- **Per wave merge:** `cd backend && python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_ws_upsert.py` — unit tests for `_upsert_event()` create path: (1) new event has `status_match` not NULL; (2) new event `status_match` equals `compute_status_match(status_value, None, None, None, None, None)`
- [ ] `tests/test_ws_reconnect.py` — unit test for `_on_connect` side effects: mock `celery_app.send_task`, call `_on_connect`, assert called once with correct task name and `trigger='ws_reconnect'`
- [ ] Add test case to `tests/test_mismatch_detector.py`: `compute_status_match("not_started", None, None, None, None, None)` returns `True`

---

## Open Questions

1. **Does pysher fire `pusher:connection_established` on internal reconnects?**
   - What we know: pysher manages brief network drops via `reconnect_interval=5`; the `run()` outer loop handles full failures
   - What's unclear: Whether `_on_connect` fires on pysher-internal reconnects (short blips) or only on the first connection per `_connect_and_run()` call
   - Recommendation: Implement as specified (bind to `pusher:connection_established`). The token-refresh reconnect (every ~20 min) provides a reliable floor. Document in code comments that pysher internal reconnects may not retrigger `_on_connect`.

2. **`ws:sport_event_count` reset policy**
   - What we know: No TTL specified; counter accumulates across restarts
   - What's unclear: Whether there should be a manual reset capability (e.g., for the production gate observation window to be clean)
   - Recommendation: No reset mechanism needed now. The gate check is "any value > 0 after 24-48h" — cumulative count is sufficient. If needed, `redis-cli del ws:sport_event_count` can reset it manually.

---

## Sources

### Primary (HIGH confidence)
- Direct source read: `backend/app/workers/ws_prophetx.py` — full implementation, line-level understanding
- Direct source read: `backend/app/workers/poll_prophetx.py` — task signature, `_write_heartbeat` pattern, `_increment_call_counter` INCR pattern
- Direct source read: `backend/app/monitoring/mismatch_detector.py` — `compute_status_match()` behavior confirmed at line 270-307
- Direct source read: `backend/app/workers/celery_app.py` — task name `"app.workers.poll_prophetx.run"` confirmed at line 63
- Direct source read: `.planning/phases/08-ws-diagnostics-and-instrumentation/08-CONTEXT.md` — locked decisions

### Secondary (MEDIUM confidence)
- `docker-compose.yml` — Redis 7-alpine and service topology confirmed
- `backend/pyproject.toml` — dependency versions and pytest configuration confirmed

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; all libraries already installed and in use
- Architecture: HIGH — all patterns verified directly from source files in the codebase
- Pitfalls: HIGH for code pitfalls (verified against actual implementation); MEDIUM for pysher reconnect behavior (depends on pysher internals not directly inspected)

**Research date:** 2026-03-31
**Valid until:** 2026-05-01 (stable codebase; only risk is pysher version behavior)
