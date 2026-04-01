---
phase: 08-ws-diagnostics-and-instrumentation
plan: "01"
subsystem: workers
tags: [websocket, redis, celery, diagnostics, instrumentation, pysher]

requires:
  - phase: prior-phases
    provides: ws_prophetx.py WS consumer, poll_prophetx.py Celery task, mismatch_detector.py compute_status_match

provides:
  - WSREL-02 fix: WS-created events get status_match=True instead of NULL
  - WSREL-01 fix: every WS reconnect queues immediate poll_prophetx with trigger='ws_reconnect'
  - Redis diagnostic keys: ws:connection_state, ws:last_message_at, ws:last_sport_event_at, ws:sport_event_count
  - poll_prophetx.run trigger kwarg (default 'scheduled') with structured logging
  - Three new test files + one updated test file (19 tests total)

affects:
  - phase: 08 Phase 9 gate — ws:sport_event_count > 0 in production confirms WS receives sport_event messages
  - phase: 09-ws-status-authority — will rely on instrumentation and reconciliation from this plan

tech-stack:
  added: []
  patterns:
    - WS reconnect reconciliation via celery_app.send_task in _on_connect callback
    - Redis diagnostic keys with self-expiring TTL for connection health (ws:connection_state, ws:last_message_at)
    - Persistent Redis counter/timestamp for production gate (ws:sport_event_count, ws:last_sport_event_at)
    - TDD approach for WS consumer tests using pysher mock with connect() side_effect to short-circuit blocking loop

key-files:
  created:
    - backend/tests/test_ws_upsert.py
    - backend/tests/test_ws_reconnect.py
    - backend/tests/test_ws_diagnostics.py
  modified:
    - backend/app/workers/ws_prophetx.py
    - backend/app/workers/poll_prophetx.py
    - backend/tests/test_mismatch_detector.py

key-decisions:
  - "WSREL-02: All external source statuses are None for newly WS-created events, so compute_status_match returns True (no disagreement) — correct and simple"
  - "WSREL-01: Fire reconciliation immediately in _on_connect with no stabilization delay (D-03 from research) — simpler and correct"
  - "Broker failures in _on_connect are caught by try/except — WS connection must never crash due to Celery broker issues"
  - "Test strategy for _on_connect inner function: mock pusher.connect() to fire callback synchronously then raise RuntimeError to exit blocking while loop — allows testing inside patch context"
  - "ws:last_message_at and ws:connection_state have 120s TTL (self-expire if consumer dies); ws:sport_event_count and ws:last_sport_event_at have no TTL (accumulate for production gate)"

patterns-established:
  - "Pattern: WS inner function testing — patch pysher.Pusher, have connect() fire callback then raise RuntimeError to short-circuit blocking while loop; all assertions inside patch context"
  - "Pattern: celery_app.send_task for cross-worker dispatch from WS consumer — try/except prevents broker failures from crashing connection"

requirements-completed: [WSREL-01, WSREL-02]

duration: 17min
completed: "2026-04-01"
---

# Phase 08 Plan 01: WS Diagnostics and Instrumentation Summary

**Fixed two WS consumer bugs (WSREL-01 reconnect reconciliation, WSREL-02 status_match NULL on create) and added four Redis ws:* diagnostic keys observable without DB access**

## Performance

- **Duration:** 17 min
- **Started:** 2026-04-01T02:07:04Z
- **Completed:** 2026-04-01T02:23:58Z
- **Tasks:** 3
- **Files modified:** 5 (2 production, 1 updated test, 3 new test files)

## Accomplishments

- WSREL-02 closed: WS-created events now get `status_match=True` instead of NULL — `compute_status_match(status_value, None, None, None, None, None)` called in create path
- WSREL-01 closed: `_on_connect` now dispatches `celery_app.send_task("app.workers.poll_prophetx.run", kwargs={"trigger": "ws_reconnect"})` immediately on every Pusher reconnect, broker failures caught silently
- Redis diagnostic instrumentation complete: `ws:connection_state`, `ws:last_message_at` (both 120s TTL), `ws:last_sport_event_at`, `ws:sport_event_count` (no TTL — accumulates for Phase 9 gate)
- `poll_prophetx.run` accepts `trigger: str = "scheduled"` kwarg, logs `poll_prophetx_started` with trigger value

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix WSREL-02 status_match on WS create path** - `512e2e8` (feat)
2. **Task 2: WSREL-01 reconnect reconciliation + poll_prophetx trigger kwarg** - `f272fc4` (feat)
3. **Task 3: Redis WS diagnostic keys** - `6384adc` (feat)

_Note: All tasks used TDD approach (RED → GREEN)_

## Files Created/Modified

- `backend/app/workers/ws_prophetx.py` — Added `status_match=compute_status_match(...)` to create path; added `celery_app` import + reconnect dispatch in `_on_connect`; added `_write_ws_diagnostics` and `_write_ws_connection_state` helpers; wired both into `_handle_broadcast_event` and `_on_connect`
- `backend/app/workers/poll_prophetx.py` — Added `trigger: str = "scheduled"` param to `run()` task; added `log.info("poll_prophetx_started", trigger=trigger)` as first line
- `backend/tests/test_ws_upsert.py` — New: verifies WS create path sets `status_match` and calls `compute_status_match` with all-None external sources
- `backend/tests/test_ws_reconnect.py` — New: verifies `_on_connect` dispatches poll_prophetx with `trigger="ws_reconnect"`, error resilience, and `poll_prophetx.run` trigger kwarg signature
- `backend/tests/test_ws_diagnostics.py` — New: verifies all 4 Redis ws:* key writes and wiring to `_handle_broadcast_event` and `_on_connect`
- `backend/tests/test_mismatch_detector.py` — Added `TestComputeStatusMatchAllNoneSources` class with 3 tests for all-None sources returning True

## Decisions Made

- WSREL-02 uses `compute_status_match(status_value, None, None, None, None, None)` — all external source statuses are None for newly WS-created events, always returns True (no disagreement). Semantically correct: no data = no conflict.
- WSREL-01 fires reconciliation immediately on connect (no delay) — simpler, correct per D-03 from research.
- `_on_connect` broker failures caught with bare `except Exception` + `log.exception` — WS connection must survive Celery broker being temporarily unavailable.
- Test strategy for `_on_connect` inner closure: mock `pysher.connect()` to fire the callback synchronously then raise `RuntimeError("test_exit_loop")` to break out of the blocking `while` loop. All assertions run inside the `with patch(...)` context block.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

**Test hanging issue (Task 2):** Initial test design called `_on_connect` callback OUTSIDE the `with patch(...)` context manager, causing the real `celery_app.send_task` to attempt a Redis broker connection (which hung). Fixed by having `connect()` side_effect fire the callback synchronously AND raise RuntimeError to exit the blocking loop — all assertions happen inside the patch context.

## User Setup Required

None — no external service configuration required. Phase 9 gate check (`ws:sport_event_count > 0`) requires deploying to production and waiting 24-48h for live game windows.

## Next Phase Readiness

- Phase 9 (WS Status Authority) is unblocked from a code perspective
- Production gate: deploy and confirm `ws:sport_event_count > 0` after 24-48h covering live game windows
- If gate fails (count stays 0), escalate to ProphetX on broadcast channel config — this plan's instrumentation makes the failure observable

## Self-Check: PASSED

All files confirmed present:
- backend/tests/test_ws_upsert.py — FOUND
- backend/tests/test_ws_reconnect.py — FOUND
- backend/tests/test_ws_diagnostics.py — FOUND
- .planning/phases/08-ws-diagnostics-and-instrumentation/08-01-SUMMARY.md — FOUND

All commits confirmed present:
- 512e2e8 — FOUND
- f272fc4 — FOUND
- 6384adc — FOUND

---
*Phase: 08-ws-diagnostics-and-instrumentation*
*Completed: 2026-04-01*
