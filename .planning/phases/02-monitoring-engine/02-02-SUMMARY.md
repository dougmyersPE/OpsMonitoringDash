---
phase: 02-monitoring-engine
plan: "02"
subsystem: monitoring
tags: [celery, sqlalchemy, structlog, redis, rapidfuzz, mismatch-detection, liquidity-monitoring, prophetx, sportsdataio]

# Dependency graph
requires:
  - phase: 02-monitoring-engine
    plan: "01"
    provides: Event, Market, EventIDMapping ORM models, EventMatcher, monitoring package skeleton

provides:
  - mismatch_detector.py: SdioStatus enum, FLAG_ONLY_STATUSES, SDIO_TO_PX_STATUS mapping, is_mismatch(), is_flag_only(), get_expected_px_status() — all pure functions, no network/DB deps
  - liquidity_monitor.py: get_effective_threshold() with per-market -> global default -> 0 fallback; is_below_threshold() with safe zero-threshold default
  - poll_prophetx.py: Full Celery task — fetches events+markets, logs ProphetX status enum values, upserts to DB, detects liquidity breaches
  - poll_sports_data.py: Full Celery task — fetches SDIO games (today+yesterday, 4 sports), runs EventMatcher, upserts event_id_mappings, detects mismatches and flag-only events
  - 30 unit tests for mismatch_detector and liquidity_monitor

affects:
  - 02-03-remediation
  - 02-04-alerting

# Tech tracking
tech-stack:
  added:
    - pytest>=8.0 added to pyproject.toml dependency-groups.dev
  patterns:
    - Sync Celery tasks using asyncio.run() for async HTTP clients (ProphetXClient, SportsDataIOClient)
    - SELECT then INSERT/UPDATE upsert pattern (avoids ON CONFLICT dialect-specific syntax)
    - Pure-function monitoring modules with no network/DB side effects (testable in isolation)
    - asyncio.run(_fetch()) inner-function pattern for async-in-sync context
    - ProphetX API response shape handled defensively (list or dict with "data" key)
    - SDIO game normalization: GameID/HomeTeam/AwayTeam/DateTime field mapping

key-files:
  created:
    - backend/app/monitoring/mismatch_detector.py
    - backend/app/monitoring/liquidity_monitor.py
    - backend/tests/test_mismatch_detector.py
    - backend/tests/test_liquidity_monitor.py
  modified:
    - backend/app/workers/poll_prophetx.py
    - backend/app/workers/poll_sports_data.py
    - backend/pyproject.toml

key-decisions:
  - "SDIO_TO_PX_STATUS all ProphetX values marked UNCONFIRMED — must update with observed values from prophetx_status_values_observed log before Plan 02-03"
  - "poll_sports_data polls NBA/MLB/NHL/Soccer only — NFL/NCAAB/NCAAF excluded per RESEARCH.md 404 finding"
  - "SELECT then INSERT/UPDATE upsert pattern — avoids ON CONFLICT do_update which requires insert_statement from sqlalchemy.dialects"
  - "is_below_threshold returns False when threshold=0 (not configured) — safe default, no spurious alerts"
  - "pytest added to pyproject.toml dependency-groups.dev; container install via uv sync --extra dev"

patterns-established:
  - "Pure-function monitoring modules: no imports of DB session or HTTP clients at module level; session passed as argument"
  - "asyncio.run() inner _fetch() pattern for ProphetX/SDIO clients in sync Celery tasks"
  - "Defensive API response handling: check isinstance(raw, list) vs isinstance(raw, dict) with .get('data', ...) fallback"

requirements-completed:
  - SYNC-01
  - SYNC-02
  - LIQ-01
  - LIQ-02

# Metrics
duration: 5min
completed: 2026-02-25
---

# Phase 2 Plan 02: Monitoring Engine Workers Summary

**ProphetX + SportsDataIO poll workers with full DB upsert, status mismatch detection (30 tests), and liquidity breach detection — monitoring engine core operational**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-25T23:17:26Z
- **Completed:** 2026-02-25T23:22:24Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Created `mismatch_detector.py` — pure functions: `is_mismatch()`, `is_flag_only()`, `get_expected_px_status()` with SdioStatus enum and SDIO_TO_PX_STATUS mapping (all ProphetX values marked UNCONFIRMED pending live API confirmation)
- Created `liquidity_monitor.py` — `get_effective_threshold()` with 3-level fallback (per-market -> global config -> 0); `is_below_threshold()` with safe zero-threshold default
- 30 unit tests pass (exceeds plan's 11 minimum): all required cases plus edge cases (equal-to-threshold, zero-threshold, F/OT, F/SO variants)
- Replaced Phase 1 stub `poll_prophetx.py` with full implementation: asyncio.run() fetch, critical status enum logging, event+market upsert, per-market liquidity breach detection
- Replaced Phase 1 stub `poll_sports_data.py` with full implementation: today+yesterday SDIO fetch for 4 sports, EventMatcher with Redis cache, event_id_mappings upsert, mismatch+flag-only detection (SYNC-02 compliant)

## Task Commits

Each task was committed atomically:

1. **Task 1: Mismatch Detector + Liquidity Monitor (Pure Functions + Tests)** - `970740d` (feat)
2. **Task 2: Full Poll Workers (ProphetX + SportsDataIO)** - `ce16527` (feat)

**Plan metadata:** _(docs commit follows)_

## Files Created/Modified

- `backend/app/monitoring/mismatch_detector.py` - SdioStatus enum, FLAG_ONLY_STATUSES, SDIO_TO_PX_STATUS mapping, is_mismatch(), is_flag_only(), get_expected_px_status()
- `backend/app/monitoring/liquidity_monitor.py` - get_effective_threshold() with fallback chain; is_below_threshold() with zero-threshold safety
- `backend/tests/test_mismatch_detector.py` - 21 tests covering mismatch detection, flag-only statuses, status mapping
- `backend/tests/test_liquidity_monitor.py` - 9 tests covering threshold resolution and breach detection with mock session
- `backend/app/workers/poll_prophetx.py` - Full ProphetX poll: asyncio fetch, status enum logging, event+market upsert, liquidity check
- `backend/app/workers/poll_sports_data.py` - Full SDIO poll: today+yesterday fetch, dedup, EventMatcher, mapping upsert, mismatch+flag detection
- `backend/pyproject.toml` - pytest added to dependency-groups.dev

## Decisions Made

- SDIO_TO_PX_STATUS values all marked `# UNCONFIRMED ProphetX value` — the `prophetx_status_values_observed` log in `poll_prophetx.py` will emit actual ProphetX status strings on first successful fetch; those values must replace the placeholders before Plan 02-03 can perform accurate mismatch detection.
- SUPPORTED_SPORTS in `poll_sports_data.py` set to `["nba", "mlb", "nhl", "soccer"]` — NFL/NCAAB/NCAAF return 404 from SportsDataIO (different endpoint format per RESEARCH.md); included sports need subscription validation.
- Used SELECT then INSERT/UPDATE upsert pattern instead of `on_conflict_do_update` — more portable across SQLAlchemy sessions and avoids needing dialect-specific INSERT statement construction.
- `is_below_threshold()` returns False when threshold resolves to Decimal("0") — prevents spurious alerts when no threshold is configured. Operators must explicitly set a threshold (per-market or global) to enable breach detection.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pytest not installed in container**
- **Found during:** Task 1 (running tests)
- **Issue:** `uv sync --frozen` in Dockerfile only installs main dependencies; pytest was in `project.optional-dependencies.dev` but the container's `uv sync --extra dev` command was needed to install it
- **Fix:** Added `pytest>=8.0` and `pytest-asyncio>=0.23` to `[dependency-groups] dev` in pyproject.toml; used `uv sync --extra dev` in the running container for test run; rebuilt image to bake in the updated pyproject.toml
- **Files modified:** backend/pyproject.toml, backend/uv.lock
- **Verification:** 30 tests pass in container after `uv sync --extra dev`
- **Committed in:** 970740d (Task 1 commit)

**2. [Rule 3 - Blocking] monitoring package and event_matcher.py not present in container**
- **Found during:** Task 1 (test run) and Task 2 (worker import verification)
- **Issue:** Phase 02-01 built the monitoring package and event_matcher.py, but the backend container was not rebuilt after that plan — so `/app/app/monitoring/` directory didn't exist
- **Fix:** Created `/app/app/monitoring/` directory in running container, copied files; rebuilt backend image after Task 2 to bake in all new files permanently
- **Files modified:** None (Docker operational fix)
- **Verification:** `python -c "from app.workers.poll_prophetx import run; from app.workers.poll_sports_data import run"` exits 0 in fresh container from rebuilt image
- **Committed in:** ce16527 (Task 2 commit triggers docker build --target production)

---

**Total deviations:** 2 auto-fixed (both Rule 3 - Blocking)
**Impact on plan:** Both fixes required for test execution and worker import verification. No scope creep. Docker rebuild ensures the new image contains all Phase 2 monitoring modules.

## Issues Encountered

- Container had stale image from Phase 1 — missing monitoring package and pytest. Required `docker compose build backend` after completing both tasks to bake new files into image.
- ProphetX base URL remains unresolved (known Phase 2 blocker from STATE.md) — `poll_prophetx` will log a connection error on its first execution, but the max_retries=3 with exponential backoff handles this gracefully. The `prophetx_status_values_observed` log cannot be captured until the URL is resolved.

## IMPORTANT: Operator Action Required Before Plan 02-03

**ProphetX status values are UNCONFIRMED.** Once `poll_prophetx.run` executes successfully against the live API, look for this log line:

```
prophetx_status_values_observed statuses=[...]
```

The actual ProphetX status strings in that log must replace the `# UNCONFIRMED` placeholders in `SDIO_TO_PX_STATUS` inside `backend/app/monitoring/mismatch_detector.py` before mismatch detection will be accurate.

## Next Phase Readiness

- Poll workers registered in Celery Beat schedule (30-second interval)
- `is_mismatch()` and `is_flag_only()` unit-tested and integrated into poll workers
- `is_below_threshold()` called per market in ProphetX poll — logs WARNING on breach
- Plan 02-03 (remediation) can proceed; it will wire up the alert dispatch that these workers intentionally skip
- SDIO_TO_PX_STATUS calibration still required — ProphetX URL must be resolved first

---
*Phase: 02-monitoring-engine*
*Completed: 2026-02-25*
