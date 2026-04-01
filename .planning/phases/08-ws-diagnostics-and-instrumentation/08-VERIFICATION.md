---
phase: 08-ws-diagnostics-and-instrumentation
verified: 2026-03-31T00:00:00Z
status: passed
score: 4/4 must-haves verified
re_verification: false
---

# Phase 08: WS Diagnostics and Instrumentation Verification Report

**Phase Goal:** WS consumer emits observable health signals and pre-existing bugs are fixed before authority logic is built
**Verified:** 2026-03-31
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1   | New events created by the WS consumer have a non-NULL status_match value | ✓ VERIFIED | `ws_prophetx.py` line 217: `status_match=compute_status_match(status_value, None, None, None, None, None)` in `if existing is None:` block |
| 2   | poll_prophetx task accepts a trigger kwarg and logs it | ✓ VERIFIED | `poll_prophetx.py` line 64: `def run(self, trigger: str = "scheduled"):` and line 66: `log.info("poll_prophetx_started", trigger=trigger)` |
| 3   | Reconnect reconciliation fires poll_prophetx via send_task on every WS connect | ✓ VERIFIED | `ws_prophetx.py` lines 358-362: `celery_app.send_task("app.workers.poll_prophetx.run", kwargs={"trigger": "ws_reconnect"})` inside `_on_connect` |
| 4   | Four Redis ws:* diagnostic keys are written by the WS consumer | ✓ VERIFIED | `ws:connection_state` (line 123), `ws:last_message_at` (line 111), `ws:last_sport_event_at` (line 113), `ws:sport_event_count` (line 114) |

**Score:** 4/4 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `backend/app/workers/ws_prophetx.py` | WSREL-02 fix + WSREL-01 reconnect + Redis diagnostics | ✓ VERIFIED | Contains `compute_status_match` in create path, `celery_app.send_task` in `_on_connect`, `_write_ws_diagnostics` and `_write_ws_connection_state` helpers wired to their call sites |
| `backend/app/workers/poll_prophetx.py` | trigger kwarg on run task | ✓ VERIFIED | `def run(self, trigger: str = "scheduled"):` at line 64, logged at line 66 |
| `backend/tests/test_ws_upsert.py` | Unit tests for WS event create path status_match | ✓ VERIFIED | 3 tests: `test_create_path_sets_status_match_not_none`, `test_create_path_status_match_is_true_when_all_sources_none`, `test_update_path_still_calls_compute_status_match` |
| `backend/tests/test_ws_reconnect.py` | Unit tests for reconnect reconciliation dispatch | ✓ VERIFIED | 5 tests: on_connect dispatches poll_prophetx, error resilience, callback registration, trigger kwarg signature, default |
| `backend/tests/test_ws_diagnostics.py` | Unit tests for Redis diagnostic key wiring | ✓ VERIFIED | 8 tests covering all four key writes, TTL, non-sport_event path, and wiring to `_handle_broadcast_event` and `_on_connect` |

---

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `ws_prophetx.py` | `celery_app.py` | `from app.workers.celery_app import celery_app` | ✓ WIRED | Line 38 in ws_prophetx.py |
| `ws_prophetx.py` | `mismatch_detector.py` | `compute_status_match` call in create path | ✓ WIRED | Line 37 (import) + line 217 (create path call with `status_match=`) |
| `ws_prophetx.py (_handle_broadcast_event)` | Redis ws:* keys | `_write_ws_diagnostics(change_type)` | ✓ WIRED | Line 281: called immediately after `change_type = wrapper.get("change_type")`, before any return |
| `ws_prophetx.py (_on_connect)` | Redis `ws:connection_state` | `_write_ws_connection_state("connected")` | ✓ WIRED | Line 356: called inside `_on_connect` after `connection_ready.set()` |

---

### Data-Flow Trace (Level 4)

Not applicable — this phase produces worker-side instrumentation (Redis writes, Celery dispatch) rather than components that render dynamic data. The "data" flows from code to Redis/Celery, verified at Level 3 (wiring) above.

---

### Behavioral Spot-Checks

| Behavior | Check | Result | Status |
| -------- | ----- | ------ | ------ |
| `_write_ws_diagnostics("sport_event")` sets all 3 keys | `test_ws_diagnostics.py::TestWriteWsDiagnostics::test_sport_event_sets_all_three_keys` | PASSED | ✓ PASS |
| `_write_ws_diagnostics("odds")` sets only `ws:last_message_at` | `test_ws_diagnostics.py::TestWriteWsDiagnostics::test_non_sport_event_sets_only_last_message_at` | PASSED | ✓ PASS |
| `_on_connect` dispatches `poll_prophetx` with `trigger="ws_reconnect"` | `test_ws_reconnect.py::TestWsReconnectReconciliation::test_on_connect_dispatches_poll_prophetx` | PASSED | ✓ PASS |
| Broker failure in `_on_connect` does not raise | `test_ws_reconnect.py::TestWsReconnectReconciliation::test_on_connect_resilient_to_broker_failure` | PASSED | ✓ PASS |
| WS create path sets `status_match` not None | `test_ws_upsert.py::TestWsUpsertCreatePath::test_create_path_sets_status_match_not_none` | PASSED | ✓ PASS |

Full run: `python -m pytest tests/test_ws_upsert.py tests/test_ws_reconnect.py tests/test_ws_diagnostics.py --noconftest` — **16/16 PASSED**

Note: The full conftest requires a running Postgres + FastAPI stack (not available in this environment). `--noconftest` was used because all phase 08 test files are self-contained with `unittest.mock` and do not require the session-scoped fixtures in conftest.py.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| WSREL-01 | 08-01-PLAN.md | System detects WS disconnection gaps and triggers immediate poll_prophetx reconciliation run on reconnect | ✓ SATISFIED | `_on_connect` in ws_prophetx.py (line 353-365) calls `celery_app.send_task("app.workers.poll_prophetx.run", kwargs={"trigger": "ws_reconnect"})` on every connection event; broker errors caught silently |
| WSREL-02 | 08-01-PLAN.md | WS consumer computes status_match when creating new events (fix NULL bug) | ✓ SATISFIED | `_upsert_event` create path (line 203-218) includes `status_match=compute_status_match(status_value, None, None, None, None, None)` in the `Event()` constructor |

Both requirements are marked Complete in REQUIREMENTS.md. No orphaned requirements found for Phase 8.

---

### Anti-Patterns Found

No anti-patterns found in any phase 08 modified files. No TODO/FIXME/placeholder comments, no stub returns, no empty handlers.

**Pre-existing issue (out of scope for Phase 08):** `poll_prophetx.py` create path (line 193-204) does not include `status_match` in the `Event()` constructor. WSREL-02 was explicitly scoped to the WS consumer only — REQUIREMENTS.md reads "WS consumer computes status_match when creating new events." The poll_prophetx create path omission predates phase 08 and is a separate concern.

**Pre-existing test failures (out of scope):** Two tests in `test_mismatch_detector.py` fail — `test_scheduled_to_upcoming_no_mismatch` and `test_get_expected_px_status_scheduled` — both introduced in phase 02 commit `970740d`. Phase 08 only appended the `TestComputeStatusMatchAllNoneSources` class (3 tests, all passing).

---

### Human Verification Required

#### 1. Reconnect reconciliation fires after actual WS reconnect

**Test:** In a staging/production environment, disconnect the WS consumer (kill -9 or network drop) and watch Celery logs for `poll_prophetx_started trigger=ws_reconnect`.
**Expected:** Within seconds of pysher re-establishing the connection, a Celery task log line appears: `poll_prophetx_started` with `trigger=ws_reconnect`.
**Why human:** Cannot simulate a live Pusher reconnect event in unit tests without a live ProphetX WS connection.

#### 2. Redis ws:* keys visible and updating during a live WS session

**Test:** In production (or staging with a live WS connection), run `redis-cli KEYS 'ws:*'` and then `redis-cli GET ws:connection_state`, `redis-cli GET ws:last_message_at`, `redis-cli GET ws:last_sport_event_at`, `redis-cli GET ws:sport_event_count`.
**Expected:** All four keys exist and are non-empty. `ws:last_message_at` is a recent ISO timestamp. `ws:connection_state` is `"connected"`. `ws:sport_event_count` is an integer >= 0.
**Why human:** Requires a live Pusher connection to a ProphetX WS endpoint.

#### 3. Production gate — ws:sport_event_count increments on sport_event messages

**Test:** After deploying to production and waiting 24-48 hours covering live game windows, check `redis-cli GET ws:sport_event_count`.
**Expected:** Counter is > 0, confirming ProphetX broadcasts sport_event change-type messages on the broadcast channel.
**Why human:** This is the explicit Phase 9 gate. A count of 0 after game windows indicates ProphetX may not be broadcasting on the configured channel and requires escalation to ProphetX support.

---

### Gaps Summary

None. All four must-have truths verified, all five artifacts confirmed substantive and wired, all four key links confirmed. All 16 phase 08 tests pass. Both WSREL-01 and WSREL-02 are satisfied by the implementation.

The only outstanding items are the three human verification checks above, which require a live ProphetX WS connection (unavailable in a local/CI environment). These do not block the automated verification status.

---

_Verified: 2026-03-31_
_Verifier: Claude (gsd-verifier)_
