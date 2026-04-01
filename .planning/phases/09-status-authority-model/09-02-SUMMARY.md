---
phase: 09-status-authority-model
plan: "02"
subsystem: workers
tags: [celery, websocket, poll, status-authority, authority-window, integration-tests]

# Dependency graph
requires:
  - phase: 09-status-authority-model
    plan: "01"
    provides: is_ws_authoritative(), WS_AUTHORITY_WINDOW_SECONDS, status_source + ws_delivered_at columns
provides:
  - ws_prophetx sets status_source='ws' and ws_delivered_at on all three write paths (create, update, op=d)
  - poll_prophetx authority-aware update path: defers to WS within 10-min window, always writes metadata
  - poll_prophetx create path sets status_source='poll' and status_match
  - poll_prophetx stale-ended loop sets status_source='poll' and clears ws_delivered_at
  - update_event_status sets status_source='manual' and clears ws_delivered_at on write
  - 17-test suite covering all authority behaviors (TestAuthorityHelper + TestWsAuthorityColumns + TestPollAuthorityColumns + TestManualStatusSource)
affects:
  - 09-03-authority-api-endpoint (can now expose status_source in event responses)
  - 10-ws-health-dashboard (status_source column now populated by all workers)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Authority-aware write: if not authoritative or is_ended: write / else: log discrepancy + recompute match only"
    - "Metadata-unconditional / status-gated split: home_team/away_team/league/scheduled_start/last_prophetx_poll always update"
    - "AsyncMock for ProphetXClient async context manager in Celery worker tests"
    - "call_count side-effect pattern for session.execute() to control bulk query return values"

key-files:
  created: []
  modified:
    - backend/app/workers/ws_prophetx.py
    - backend/app/workers/poll_prophetx.py
    - backend/app/workers/update_event_status.py
    - backend/tests/test_status_authority.py
    - backend/tests/test_update_event_status.py

key-decisions:
  - "Metadata always updates (unconditional): home_team, away_team, league, scheduled_start, last_prophetx_poll written even when WS is authoritative (AUTH-03)"
  - "ended bypasses authority window: poll status 'ended' always writes regardless of WS authority (D-05)"
  - "ws_delivered_at cleared on poll/manual write: any non-WS write clears the WS authority timestamp to prevent stale authority"
  - "status_match recomputed in both branches: whether poll writes or defers, status_match is always refreshed against current status"
  - "AuditLog after_state includes status_source='manual' for manual actions traceability"

requirements-completed: [AUTH-01, AUTH-02, AUTH-03]

# Metrics
duration: 10min
completed: 2026-04-01
---

# Phase 9 Plan 02: Status Authority Worker Wiring Summary

**Authority wiring into all three workers: ws_prophetx sets status_source='ws'+ws_delivered_at on 3 code paths; poll_prophetx checks is_ws_authoritative() with metadata-unconditional split; update_event_status sets status_source='manual'; 17 integration tests covering all behaviors**

## Performance

- **Duration:** 10 min
- **Started:** 2026-04-01T03:03:19Z
- **Completed:** 2026-04-01T03:20:52Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

### Task 1: Wire status_source and ws_delivered_at into ws_prophetx.py

- Added `existing.status_source = "ws"` + `existing.ws_delivered_at = now` to op=d path (before `session.commit()`)
- Added `status_source="ws"` + `ws_delivered_at=now` kwargs to Event() create constructor
- Added `existing.status_source = "ws"` + `existing.ws_delivered_at = now` to existing event update path
- Added `_make_session_mock()` helper function to `test_status_authority.py` (shared across all new test classes)
- Added `TestWsAuthorityColumns` class (3 tests): create path, update path, op=d path — all pass

### Task 2: Wire authority check into poll_prophetx.py and manual source into update_event_status.py

- Added module-level imports: `from app.core.config import settings` and `from app.monitoring.authority import is_ws_authoritative` to poll_prophetx
- Poll create path: added `status_source="poll"` and `status_match=compute_status_match(...)` to Event() constructor (was missing status_match — minor gap fixed)
- Poll update path: replaced unconditional status write with authority-aware split:
  - Metadata writes (sport, league, name, home_team, away_team, scheduled_start, last_prophetx_poll) remain unconditional (AUTH-03)
  - `is_ws_authoritative()` called with `existing.ws_delivered_at` and `settings.WS_AUTHORITY_WINDOW_SECONDS`
  - If not authoritative OR status is "ended": writes prophetx_status, status_source="poll", clears ws_delivered_at, recomputes status_match
  - If authoritative: logs `poll_prophetx_authority_window_skip` when status differs, recomputes status_match against WS-authoritative status
- Stale-ended loop: added `event.status_source = "poll"` + `event.ws_delivered_at = None` after `event.prophetx_status = "ended"`
- update_event_status: added `event.status_source = "manual"` + `event.ws_delivered_at = None` after status write; added `"status_source": "manual"` to AuditLog `after_state` dict
- Added `TestPollAuthorityColumns` (8 tests) and `TestManualStatusSource` (1 test) to test_status_authority.py

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire status_source='ws' and ws_delivered_at into ws_prophetx** - `6fe572b` (feat)
2. **Task 2: Wire authority check into poll_prophetx and manual source into update_event_status** - `4d84b5e` (feat)

## Files Created/Modified

- `backend/app/workers/ws_prophetx.py` - Added status_source='ws' + ws_delivered_at on op=d, create, and update paths
- `backend/app/workers/poll_prophetx.py` - Added is_ws_authoritative import; authority-aware update path; status_source on create + stale-ended
- `backend/app/workers/update_event_status.py` - Added status_source='manual' + ws_delivered_at=None; updated AuditLog after_state
- `backend/tests/test_status_authority.py` - Grew from 5 tests (TestAuthorityHelper) to 17 tests (added TestWsAuthorityColumns, TestPollAuthorityColumns, TestManualStatusSource + _make_session_mock helper)
- `backend/tests/test_update_event_status.py` - Updated after_state assertion to include status_source='manual' and alert_only_mode=False

## Decisions Made

- **Metadata always unconditional (AUTH-03):** home_team, away_team, league, scheduled_start, last_prophetx_poll are written regardless of WS authority. Only prophetx_status, status_source, and ws_delivered_at are gated.
- **ended bypasses authority window (D-05):** `is_ended = (status_value or "").lower() == "ended"`. If poll sees "ended", it always writes even if WS is authoritative within the window. Ensures terminal state can never be blocked.
- **ws_delivered_at cleared on poll/manual write:** When poll or manual writes prophetx_status, ws_delivered_at is set to None. This prevents a stale WS timestamp from making a future WS poll appear authoritative when it shouldn't be.
- **status_match recomputed in both branches:** In the authority-skip branch, status_match is computed against `existing.prophetx_status` (the WS-delivered value). In the write branch, against `status_value`.
- **AsyncMock for ProphetXClient:** The ProphetXClient uses `async with` / `await` — `MagicMock` doesn't support this. All test methods that exercise the poll run path use `AsyncMock` for `__aenter__`, `__aexit__`, and `get_events_raw`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Poll create path was missing status_match**
- **Found during:** Task 2, reviewing Plan action section B
- **Issue:** The plan noted "status_match was missing from poll create path (existing minor gap noted in RESEARCH.md Pattern 6)" — the original Event() constructor in poll_prophetx had no status_match kwarg
- **Fix:** Added `status_match=compute_status_match(status_value, None, None, None, None, None)` alongside `status_source="poll"` in create constructor
- **Files modified:** `backend/app/workers/poll_prophetx.py`
- **Commit:** `4d84b5e`

**2. [Rule 1 - Bug] test_update_event_status.py assertion outdated after AuditLog change**
- **Found during:** Task 2 full-suite run
- **Issue:** Existing test `test_successful_update_writes_audit_log` checked `after_state={"prophetx_status": target_status}` but we added `status_source` and `alert_only_mode` to the dict
- **Fix:** Updated assertion to `after_state={"prophetx_status": target_status, "status_source": "manual", "alert_only_mode": False}`
- **Files modified:** `backend/tests/test_update_event_status.py`
- **Commit:** `4d84b5e`

**3. [Rule 3 - Blocking] AsyncMock required for ProphetXClient in tests**
- **Found during:** Task 2 test execution
- **Issue:** ProphetXClient uses `async with` / `await` — using `MagicMock` for `__aenter__`/`__aexit__`/`get_events_raw` caused `TypeError: object list can't be used in 'await' expression`
- **Fix:** Changed all ProphetXClient mock setup in poll tests to use `AsyncMock` for async context manager methods
- **Files modified:** `backend/tests/test_status_authority.py`
- **Commit:** `4d84b5e`

**4. [Rule 3 - Blocking] _make_poll_session_mock must return empty list for bulk queries**
- **Found during:** Task 2 test execution
- **Issue:** Mock returning `[existing]` for all `scalars().all()` calls caused the stale-ended loop to pick up the test event and overwrite its status, causing test_poll_update_inside_window_skips_status to fail (event was set to "ended" by stale loop)
- **Fix:** Changed `_make_poll_session_mock` to return empty list for `scalars().all()` (bulk queries) — only `scalar_one_or_none()` returns the test event
- **Files modified:** `backend/tests/test_status_authority.py`
- **Commit:** `4d84b5e`

## Pre-existing Issues (Out of Scope)

- `test_mismatch_detector.py::TestIsMismatch::test_scheduled_to_upcoming_no_mismatch` — pre-existing failure, noted in Plan 01 SUMMARY
- `test_mismatch_detector.py::TestGetExpectedPxStatus::test_get_expected_px_status_scheduled` — pre-existing failure, noted in Plan 01 SUMMARY
- 15 test errors in test_auth.py, test_health.py, test_interval_validation.py — require running Docker/PostgreSQL environment (pre-existing)

## Known Stubs

None — all code paths write real values. ProphetX write endpoint in update_event_status remains stubbed (log-only until PATCH path confirmed) but this is a pre-existing stub from v1.0, not introduced in this plan.

## Next Phase Readiness

- AUTH-01, AUTH-02, AUTH-03 complete: all workers source-annotate every prophetx_status write
- WS-leads, poll-defers model is now fully operational
- Future phases can read `status_source` and `ws_delivered_at` to understand which authority delivered the current status
- API endpoint exposing `status_source` in event responses can now be built (phase 09-03 if planned)

---
*Phase: 09-status-authority-model*
*Completed: 2026-04-01*
