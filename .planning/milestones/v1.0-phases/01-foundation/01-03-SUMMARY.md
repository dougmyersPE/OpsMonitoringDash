---
phase: 01-foundation
plan: "03"
subsystem: infra
tags: [celery, redbeat, redis, httpx, tenacity, structlog, fastapi]

# Dependency graph
requires:
  - phase: 01-01
    provides: Docker Compose skeleton with worker/beat service stubs, Redis, settings with CELERY_BROKER_URL and REDBEAT_REDIS_URL

provides:
  - Celery worker container running poll_prophetx and poll_sports_data stub tasks every 30 seconds
  - Celery Beat container using RedBeat scheduler (Redis-backed, not file-based)
  - BaseAPIClient with async httpx + tenacity retry
  - ProphetXClient with Bearer auth header (base URL unconfirmed — see Decisions)
  - SportsDataIOClient with Ocp-Apim-Subscription-Key header auth (never query param)
  - Admin-only GET /api/v1/probe/clients endpoint for live API connectivity testing
  - 5 passing unit tests confirming header auth patterns on both clients

affects:
  - 02-polling: ProphetXClient.get_events_raw() is the entry point for Phase 2 poll logic; base URL must be confirmed before Phase 2 starts
  - 02-polling: SportsDataIO subscription coverage result (401 per sport with placeholder key) tells Phase 2 which sports endpoint paths are reachable
  - 02-polling: ProphetX status enum values remain unconfirmed (DNS failure with placeholder base URL)

# Tech tracking
tech-stack:
  added:
    - celery[redis]>=5.4 (already in pyproject.toml from Plan 01-01)
    - celery-redbeat>=2.0 (already in pyproject.toml from Plan 01-01)
    - httpx>=0.27 (already in pyproject.toml)
    - tenacity>=8.0 (already in pyproject.toml)
  patterns:
    - Celery 5 lowercase config keys (not Celery 3 uppercase compatibility mode)
    - RedBeat scheduler with redbeat_redis_url — Beat stores schedule state in Redis not on disk
    - startup assertion pattern: assert celery_app.conf.beat_scheduler == "redbeat.RedBeatScheduler" — fail loudly if misconfigured
    - BaseAPIClient context manager pattern (async with client as c: ...) for guaranteed connection cleanup
    - tenacity @retry decorator on _get() — 3 attempts, exponential backoff 1-4s, reraises on final failure
    - Header-only API auth: Authorization: Bearer (ProphetX) and Ocp-Apim-Subscription-Key (SportsDataIO) — API key never in URL

key-files:
  created:
    - backend/app/workers/__init__.py
    - backend/app/workers/celery_app.py
    - backend/app/workers/poll_prophetx.py
    - backend/app/workers/poll_sports_data.py
    - backend/app/clients/__init__.py
    - backend/app/clients/base.py
    - backend/app/clients/prophetx.py
    - backend/app/clients/sportsdataio.py
    - backend/app/api/v1/probe.py
    - backend/tests/test_clients.py
  modified:
    - backend/app/main.py (added probe router)
    - docker-compose.yml (fixed worker queue: -Q celery,default)

key-decisions:
  - "Worker command uses -Q celery,default — Celery routes tasks to 'celery' queue by default; -Q default alone causes tasks to queue but never execute"
  - "ProphetX base URL (api.prophetx.co) is unconfirmed — DNS failure in probe confirms it needs to be validated with Doug before Phase 2"
  - "SportsDataIO uses Ocp-Apim-Subscription-Key header (not query param) — query param auth would log API key in Nginx access logs"
  - "beat_scheduler startup assertion added to celery_app.py — prevents silent fallback to file-based scheduler on misconfiguration"

patterns-established:
  - "BaseAPIClient subclass pattern: __init__ sets base_url + headers; methods call self._get(path, headers=self._headers)"
  - "Probe endpoint pattern: Admin-only router instantiates clients via async context manager, catches all exceptions, returns structured summary"
  - "Stub task pattern: @celery_app.task(bind=True, max_retries=3) + log.info(event_name, task_id=self.request.id)"

requirements-completed: [CORE-01, CORE-02]

# Metrics
duration: 20min
completed: 2026-02-25
---

# Phase 1 Plan 03: Celery Workers and API Clients Summary

**Celery Beat with RedBeat scheduler fires poll_prophetx and poll_sports_data every 30s; ProphetX and SportsDataIO clients use header-only auth with tenacity retry; Admin probe endpoint confirms SportsDataIO reachability and documents ProphetX base URL as unconfirmed**

## Performance

- **Duration:** ~20 min (active execution; session break between Task 1 and Task 2)
- **Started:** 2026-02-25T15:54:59Z
- **Completed:** 2026-02-25T18:10:00Z
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments

- Celery worker and beat containers running — stub tasks fire every 30 seconds, confirmed in worker logs with structlog JSON entries
- RedBeat scheduler confirmed active: `redis-cli keys "redbeat:*"` returns `redbeat:poll-prophetx`, `redbeat:poll-sports-data`, `redbeat::schedule`, `redbeat::lock`, `redbeat::statics`; no `celerybeat-schedule` file in beat container
- ProphetX and SportsDataIO clients built with correct header-only auth patterns; 5 unit tests passing; probe endpoint live and Admin-gated

## Task Commits

Each task was committed atomically:

1. **Task 1: Celery app, RedBeat scheduler, and stub poll tasks** - `bdeca45` (feat)
2. **Task 2: API clients (ProphetX + SportsDataIO) and probe endpoint** - `4b66532` (feat)

**Plan metadata:** TBD (docs commit)

## Files Created/Modified

- `backend/app/workers/__init__.py` - Package marker for workers module
- `backend/app/workers/celery_app.py` - Celery app factory: RedBeat scheduler, 30s beat schedule, reliability config, startup assertion
- `backend/app/workers/poll_prophetx.py` - Stub task: logs `poll_prophetx_fired` every 30s
- `backend/app/workers/poll_sports_data.py` - Stub task: logs `poll_sports_data_fired` every 30s
- `backend/app/clients/__init__.py` - Package marker for clients module
- `backend/app/clients/base.py` - `BaseAPIClient`: async httpx client with tenacity retry (3 attempts, exp backoff 1-4s)
- `backend/app/clients/prophetx.py` - `ProphetXClient`: Bearer auth, `get_events_raw()`, `get_markets_raw()`
- `backend/app/clients/sportsdataio.py` - `SportsDataIOClient`: `Ocp-Apim-Subscription-Key` header, `get_games_by_date_raw()`, `probe_subscription_coverage()`
- `backend/app/api/v1/probe.py` - Admin-only `GET /api/v1/probe/clients` — instantiates both clients, returns response summaries
- `backend/tests/test_clients.py` - 5 unit tests: client instantiation, Bearer auth header (ProphetX), Ocp-Apim-Subscription-Key header (SportsDataIO), base URL v3 check
- `backend/app/main.py` - Added `probe.router` registration
- `docker-compose.yml` - Fixed worker queue flag to `-Q celery,default`

## Probe Endpoint Results (Phase 1 Primary Artifact)

Called with: `GET /api/v1/probe/clients` (Admin token, placeholder API keys in .env)

```json
{
    "prophetx": {
        "status": "error",
        "error": "[Errno -2] Name or service not known"
    },
    "sportsdataio": {
        "status": "ok",
        "subscription_coverage": {
            "nfl": 404,
            "nba": 401,
            "mlb": 401,
            "nhl": 401,
            "ncaab": 404,
            "ncaaf": 404,
            "soccer": 401
        }
    }
}
```

### ProphetX Result

**Status:** DNS failure — `api.prophetx.co` does not resolve.

The base URL (`https://api.prophetx.co`) is a best-guess from research. The DNS failure confirms it is incorrect or unreachable. **Action required before Phase 2:** Doug must provide the correct ProphetX API base URL and a valid API key. The `PROPHETX_BASE_URL` constant in `backend/app/clients/prophetx.py` needs to be updated.

ProphetX status enum values remain **unconfirmed** (no successful API call possible with placeholder key + wrong base URL). This is the primary Phase 2 blocker.

### SportsDataIO Result

**Status:** Server reached and auth mechanism accepted (401 = auth rejected, not connection failure).

Coverage by sport with placeholder API key:
- `nba`, `mlb`, `nhl`, `soccer` → **401** (auth rejected — endpoint exists, real key will confirm coverage)
- `nfl`, `ncaab`, `ncaaf` → **404** (endpoint path `/nfl/scores/json/GamesByDate/{date}` does not exist — NFL and college sports use different URL structure)

**Action for Phase 2:** Once a real SportsDataIO key is in `.env`, re-run `GET /probe/clients` to confirm which sports return 200. NFL/college endpoints will need path research (likely different base path format).

## Decisions Made

- **Worker queue flag fixed to `-Q celery,default`** — Celery 5 routes tasks to the `celery` queue by default. The docker-compose.yml had `-Q default` which caused tasks to queue in Redis but never be received by the worker. Fixed to listen on both queues.
- **ProphetX base URL is a placeholder** — `api.prophetx.co` does not resolve. Documented in `prophetx.py` with a NOTE comment. Must be confirmed before Phase 2.
- **SportsDataIO header auth locked** — `Ocp-Apim-Subscription-Key` in headers, never as query param. Enforced in `SportsDataIOClient.__init__` and verified by unit test.
- **Beat startup assertion** — `assert celery_app.conf.beat_scheduler == "redbeat.RedBeatScheduler"` prevents silent fallback to file-based scheduler if `REDBEAT_REDIS_URL` is misconfigured.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Worker queue flag mismatch — tasks queued but never executed**

- **Found during:** Task 1 verification (checking worker logs after beat dispatched tasks)
- **Issue:** `docker-compose.yml` had `celery worker -Q default`. Celery 5 routes tasks to the `celery` queue by default, not `default`. Tasks were accumulating in the `celery` Redis list (`redis-cli llen celery` returned 4) while the worker listened to `default` (empty).
- **Fix:** Changed worker command to `-Q celery,default` to consume from both queues.
- **Files modified:** `docker-compose.yml`
- **Verification:** Worker logs showed `poll_prophetx_fired` and `poll_sports_data_fired` every ~30 seconds after fix.
- **Committed in:** `bdeca45` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Necessary fix — without it, no tasks would ever execute. No scope creep.

## Issues Encountered

- **Dev dependencies not installed in Docker image** — `Dockerfile` uses `uv sync --frozen` (no dev extras). Running `python -m pytest` inside the container failed. Fixed by running `uv sync --extra dev` inside the container before pytest. This is expected behaviour for production Dockerfiles; not a defect.

## User Setup Required

Two items require manual action before Phase 2 can begin:

1. **ProphetX base URL** — Replace `PROPHETX_BASE_URL = "https://api.prophetx.co"` in `backend/app/clients/prophetx.py` with the real URL. Then add a valid `PROPHETX_API_KEY` to `.env` and re-run `GET /probe/clients` to confirm auth works and capture raw response structure (especially event status enum values).

2. **SportsDataIO API key** — Add a real `SPORTSDATAIO_API_KEY` to `.env` and re-run `GET /probe/clients` to confirm subscription coverage (which sports return 200). Also research correct URL patterns for NFL/college sports (404 with placeholder key).

## Next Phase Readiness

Phase 1 Foundation is **complete** (Plans 01-01, 01-02, 01-03 all done):
- All 6 services start with `docker compose up`
- GET /health returns 200
- Redis: 256mb + allkeys-lru
- JWT auth + RBAC enforced on all protected endpoints
- Beat fires stub tasks every 30 seconds (confirmed in logs)
- Both API clients have correct header-only auth patterns and unit test coverage

**Phase 2 blockers (must resolve before starting):**
- ProphetX correct base URL + valid API key (DNS failure blocks all ProphetX polling)
- ProphetX status enum values unconfirmed (critical for Phase 2 comparison logic)
- SportsDataIO key + sport endpoint path research for NFL/college sports

## Self-Check: PASSED

All claimed files verified present on disk. All task commits verified in git history.

| Check | Result |
|-------|--------|
| backend/app/workers/celery_app.py | FOUND |
| backend/app/workers/poll_prophetx.py | FOUND |
| backend/app/workers/poll_sports_data.py | FOUND |
| backend/app/clients/base.py | FOUND |
| backend/app/clients/prophetx.py | FOUND |
| backend/app/clients/sportsdataio.py | FOUND |
| backend/app/api/v1/probe.py | FOUND |
| backend/tests/test_clients.py | FOUND |
| backend/app/main.py | FOUND |
| docker-compose.yml | FOUND |
| Commit bdeca45 (Task 1) | FOUND |
| Commit 4b66532 (Task 2) | FOUND |

---
*Phase: 01-foundation*
*Completed: 2026-02-25*
