# Architecture Research

**Domain:** Real-time external API monitoring system with background workers and live dashboard
**Researched:** 2026-03-01 (v1.1 update — API usage monitoring + per-worker frequency controls)
**Confidence:** HIGH (v1.0 codebase directly inspected; all integration patterns verified against live code)

---

## v1.1 Milestone Focus

This document covers both the existing v1.0 architecture (for reference) and the specific integration points for new v1.1 features. The v1.1 milestone adds:

1. **API call volume tracking** — how many HTTP requests each worker makes per day
2. **Quota monitoring** — remaining quota from Odds API and Sports API response headers
3. **Per-worker poll frequency controls** — Admin can change intervals from the UI without restarting containers
4. **API Usage tab** — new frontend page surfacing all of the above

**The critical constraint for v1.1:** Poll intervals are currently baked into `celery_app.conf.beat_schedule` at container startup from env vars. Changing them at runtime requires writing directly to RedBeat's Redis keys via `RedBeatSchedulerEntry`. The `system_config` table and `/api/v1/config` endpoint already exist and handle the persistence side — v1.1 extends this pattern.

---

## System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        External APIs                                  │
│  ProphetX WS   SDIO (main+soccer)   Odds API   Sports API   ESPN     │
└──────────┬───────────────┬──────────────┬──────────┬──────────┬──────┘
           │               │              │          │          │
           │               │  response headers:      │          │
           │               │  (SDIO: none known)     │          │
           │               │  (OddsAPI: x-requests-  │          │
           │               │   remaining)            │          │
           │               │  (SportsAPI: x-         │          │
           │               │   ratelimit-requests-   │          │
           │               │   remaining)            │          │
           │               │                         │          │
┌──────────▼───────────────▼──────────────▼──────────▼──────────▼──────┐
│                     Celery Worker Container                           │
│  ┌────────────┐ ┌─────────────────┐ ┌──────────┐ ┌────────────────┐  │
│  │poll_prophet│ │poll_sports_data │ │poll_espn │ │poll_sports_api │  │
│  │x (WS+REST) │ │                 │ │          │ │poll_odds_api   │  │
│  └─────┬──────┘ └────────┬────────┘ └────┬─────┘ └───────┬────────┘  │
│        │   [v1.1: each worker increments Redis call counter]          │
│        └──────────────────┬──────────────┘               │           │
└───────────────────────────┼──────────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────────┐
│                        Redis                                          │
│  db=0: Celery broker + RedBeat schedules                             │
│  db=1: Celery results (TTL 1h)                                       │
│  Shared keys (existing):                                             │
│    worker:heartbeat:{name}            (TTL, liveness)                │
│    sdio:team_names:{sport}            (24h cache)                    │
│    sdio:soccer_competitions           (24h cache)                    │
│    prophet:updates                    (pub/sub channel)              │
│  New keys (v1.1):                                                    │
│    api_calls:{worker}:{YYYY-MM-DD}    (daily call counter, INCR)     │
│    api_quota:{provider}:remaining     (from response headers, 25h TTL)│
│    api_quota:{provider}:used          (from response headers, 25h TTL)│
│    api_quota:{provider}:limit         (from response headers, 25h TTL)│
│    api_quota:{provider}:updated_at    (ISO timestamp, 25h TTL)       │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────────┐
│                     PostgreSQL                                        │
│  events, markets, users, audit_log, notifications, event_id_mappings │
│  system_config (key/value — runtime config, existing)                │
│    Existing keys: alert_only_mode                                    │
│    New keys (v1.1): poll_interval_{worker}                           │
│  api_usage_snapshots (new table — nightly rollup of call counts)     │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────────┐
│                     FastAPI Backend                                   │
│  Existing endpoints:                                                 │
│    /api/v1/health/workers  — worker liveness (Redis heartbeat TTL)  │
│    /api/v1/config          — GET/PATCH system_config key/value       │
│    /api/v1/stream          — SSE pub/sub fan-out                     │
│  New endpoint (v1.1):                                                │
│    /api/v1/usage           — call volume + quota data                │
│  Modified endpoint (v1.1):                                           │
│    /api/v1/config PATCH    — when key is poll_interval_*, also       │
│                              writes to RedBeat via Redis             │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────────┐
│                     React Frontend                                    │
│  Existing pages: DashboardPage, MarketsPage, LoginPage               │
│  New page (v1.1): ApiUsagePage                                       │
│    ├── UsageSummaryCards (calls today, remaining quota per provider) │
│    ├── WorkerFrequencyPanel (current interval + input + save button) │
│    └── CallVolumeChart (per-worker rolling 7-day bar chart)          │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Component Analysis: New vs. Modified

### New Components

#### 1. Redis Call Counter (per poll worker)
**Where:** Added inside every `poll_*.py` worker body, after each batch of external API calls.
**What:** `INCR api_calls:{worker_name}:{YYYY-MM-DD}` after each poll cycle. One counter per worker per calendar day.
**Why Redis not DB:** Workers run every 30–1800 seconds. A DB write per poll cycle adds unnecessary load and latency. Redis INCR is atomic, sub-millisecond, and handles concurrent Celery fork processes naturally (no transaction needed). Daily rollup to PostgreSQL handles long-term retention separately.

```python
def _record_api_calls(worker_name: str, count: int) -> None:
    """Increment the daily call counter for this worker in Redis."""
    r = _sync_redis.from_url(settings.REDIS_URL)
    date_key = f"api_calls:{worker_name}:{date.today().isoformat()}"
    r.incrby(date_key, count)
    r.expire(date_key, 8 * 86400)  # 8-day TTL — covers weekly rollup window
```

What counts as one "call": each HTTP request to an external API. The SDIO worker already computes `sport_counts` per cycle — sum these for total calls per run.

#### 2. Quota Header Capture (API client layer)
**Where:** `clients/base.py` gets a new optional method; `clients/odds_api.py` and `clients/sports_api.py` override it.
**What:** After each successful response, extract quota headers and write to Redis with a 25-hour TTL.
**Why client layer, not worker:** Workers are already complex. Keeping quota awareness in the client maintains separation of concerns. A new worker added in the future automatically gets quota tracking if it uses the shared client.

Confirmed header names (HIGH confidence, verified from official documentation):
- **Odds API:** `x-requests-remaining`, `x-requests-used`, `x-requests-last`
- **Sports API (api-sports.io / api-football):** `x-ratelimit-requests-remaining`, `x-ratelimit-requests-limit`
- **SDIO:** No quota headers known. Paid plans are described as "unlimited." SDIO usage is tracked by call count only until header presence is confirmed from a live response inspection.

```python
# clients/base.py — additive change
class BaseAPIClient:
    def _capture_quota_headers(self, headers, provider: str | None = None) -> None:
        """Subclass override to capture provider-specific quota headers."""
        pass  # default: no-op

    async def _get(self, path: str, **kwargs) -> dict | list:
        response = await self._client.get(path, **kwargs)
        response.raise_for_status()
        self._capture_quota_headers(response.headers)  # hook
        return response.json()
```

```python
# clients/odds_api.py — override
def _capture_quota_headers(self, headers, provider: str = "odds_api") -> None:
    remaining = headers.get("x-requests-remaining")
    used = headers.get("x-requests-used")
    limit_last = headers.get("x-requests-last")
    if remaining is None:
        return
    r = _sync_redis.from_url(settings.REDIS_URL)
    pipe = r.pipeline()
    pipe.set(f"api_quota:odds_api:remaining", remaining, ex=25*3600)
    pipe.set(f"api_quota:odds_api:used", used or "", ex=25*3600)
    pipe.set(f"api_quota:odds_api:updated_at", datetime.utcnow().isoformat(), ex=25*3600)
    pipe.execute()
```

Note: `SportsApiClient` does not extend `BaseAPIClient` (it manages its own per-sport `httpx.AsyncClient` instances). The quota header capture for Sports API must be added directly to `SportsApiClient.get_games()`.

#### 3. `api_usage_snapshots` Table (new DB table)
**Schema:**
```sql
CREATE TABLE api_usage_snapshots (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_name   VARCHAR(50) NOT NULL,
    snapshot_date DATE NOT NULL,
    call_count    INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(worker_name, snapshot_date)
);
```
**Purpose:** Durable record of daily call counts per worker. Redis counters have an 8-day TTL; this table enables the 7-day trend chart in the UI.
**Who writes:** Nightly rollup worker only. API reads from it.
**Migration:** New Alembic migration `006_api_usage_snapshots.py`.

#### 4. Daily Rollup Worker
**Where:** New `workers/rollup_api_usage.py`, added to `celery_app.py` Beat schedule.
**Schedule:** Once per day (e.g., `crontab(hour=2, minute=0)` UTC).
**What:** Reads all `api_calls:*:yesterday` Redis keys, upserts one row per worker into `api_usage_snapshots`, logs summary.
**Why a separate task:** Keeps the per-poll-cycle workers fast and simple. The rollup is cheap — one Redis MGET + one DB insert per worker per night.

```python
@celery_app.task(name="app.workers.rollup_api_usage.run")
def run():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    r = get_sync_redis()
    worker_names = [
        "poll_prophetx", "poll_sports_data", "poll_odds_api",
        "poll_sports_api", "poll_espn",
    ]
    with SyncSessionLocal() as session:
        for name in worker_names:
            key = f"api_calls:{name}:{yesterday}"
            val = r.get(key)
            count = int(val) if val else 0
            # UPSERT — safe to re-run
            session.execute(
                insert(ApiUsageSnapshot)
                .values(worker_name=name, snapshot_date=yesterday, call_count=count)
                .on_conflict_do_update(
                    index_elements=["worker_name", "snapshot_date"],
                    set_={"call_count": count}
                )
            )
        session.commit()
```

#### 5. `/api/v1/usage` Endpoint
**Where:** New `api/v1/usage.py` router, registered in `main.py`.
**Auth:** `require_role(RoleEnum.read_only)` — all authenticated users can see usage data.
**What:** Reads live Redis counters (today) + DB history (last 7 days) + Redis quota keys.

```python
@router.get("")
async def get_usage(
    session: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis_client),
    _user = Depends(require_role(RoleEnum.read_only)),
):
    today = date.today().isoformat()
    worker_names = [
        "poll_prophetx", "poll_sports_data", "poll_odds_api",
        "poll_sports_api", "poll_espn",
    ]

    # Live today counts from Redis
    today_keys = [f"api_calls:{w}:{today}" for w in worker_names]
    today_vals = await redis.mget(*today_keys)
    today_counts = {w: int(v or 0) for w, v in zip(worker_names, today_vals)}

    # 7-day history from DB
    rows = await session.execute(
        select(ApiUsageSnapshot)
        .where(ApiUsageSnapshot.snapshot_date >= date.today() - timedelta(days=7))
        .order_by(ApiUsageSnapshot.snapshot_date)
    )
    # ... aggregate per worker

    # Quota from Redis
    quota_providers = ["odds_api", "sports_api"]
    quota_data = {}
    for provider in quota_providers:
        remaining = await redis.get(f"api_quota:{provider}:remaining")
        used = await redis.get(f"api_quota:{provider}:used")
        updated_at = await redis.get(f"api_quota:{provider}:updated_at")
        quota_data[provider] = {
            "remaining": int(remaining) if remaining else None,
            "used": int(used) if used else None,
            "updated_at": updated_at,
        }

    return {"workers": ..., "quota": quota_data}
```

**Response shape:**
```json
{
  "workers": {
    "poll_sports_data": {
      "calls_today": 1440,
      "calls_7d": [{"date": "2026-02-23", "count": 1350}, ...],
      "interval_seconds": 30
    }
  },
  "quota": {
    "odds_api": {
      "remaining": 420,
      "used": 80,
      "updated_at": "2026-03-01T14:22:00"
    },
    "sports_api": {
      "remaining": 450,
      "updated_at": "2026-03-01T14:22:00"
    },
    "sdio": {
      "calls_today": 1440,
      "note": "No quota header — call-count tracking only"
    }
  }
}
```

#### 6. `ApiUsagePage` (Frontend)
**Where:** New `pages/ApiUsagePage.tsx`, new route `/usage` in `App.tsx`, new nav entry in `Layout.tsx`.
**Components:**
- **UsageSummaryCards:** One card per provider showing calls today + remaining quota. Polls `/api/v1/usage` with `refetchInterval: 60_000` (TanStack Query). Show "unavailable" if Redis quota key has expired.
- **WorkerFrequencyPanel:** Table of workers with current interval (from `/api/v1/usage` response) + number input + save button. PATCH to `/api/v1/config/poll_interval_{worker}`. Admin-only: hide/disable for non-Admin roles.
- **CallVolumeChart:** 7-day bar chart using `recharts` (already a common dep in the React ecosystem; confirm it's in `package.json` or add it). One bar per day per worker.

---

### Modified Components

#### `clients/base.py` — Add header capture hook
**Change:** Add `_capture_quota_headers(headers)` method (no-op default). Call it inside `_get()` after `response.raise_for_status()`.
**Risk:** LOW. Additive. The no-op default means all existing clients are unaffected until they override.

#### `clients/odds_api.py` — Override quota capture
**Change:** Override `_capture_quota_headers` to write `x-requests-remaining`, `x-requests-used` to Redis.
**Risk:** LOW. New method addition. No existing logic touched.
**Note:** `OddsAPIClient.get_scores()` uses `await self._get(...)` via `BaseAPIClient`, so the hook fires automatically on every `get_scores()` call.

#### `clients/sports_api.py` — Add quota capture
**Change:** `SportsApiClient` does not extend `BaseAPIClient`. Add a `_capture_quota_headers(headers)` call inside `get_games()` after `resp.raise_for_status()`.
**Risk:** LOW. Additive. Single location (`get_games()` method is the only HTTP call this client makes).

#### Each `poll_*.py` worker — Add call counter
**Change:** Call `_record_api_calls(worker_name, count)` at the end of each successful poll cycle. The count is the number of HTTP requests made during that cycle.
- `poll_sports_data.py`: Sum `sport_counts` dict (already computed).
- `poll_odds_api.py`: `len(relevant_keys)` (one request per sport key).
- `poll_sports_api.py`: `len(db_sports) * 3` (3 dates × per sport).
- `poll_espn.py`: `len(needed_endpoints) * 3` (3 dates × per endpoint).
- `poll_prophetx.py`: Count ProphetX REST calls (1 per reconciliation cycle).
**Risk:** LOW. Purely additive. Wrap in `try/except` to prevent counter failure from disrupting the poll cycle.

#### `celery_app.py` — Read intervals from system_config at startup
**Change:** Before building `beat_schedule`, query PostgreSQL for `system_config` rows with `poll_interval_*` keys. Use DB value if present, fall back to env var default.
**Risk:** MEDIUM. This is Beat's startup path. A DB connection failure would block Beat from starting. Must use a sync connection with a short timeout (3 seconds) and fall back to env vars on any DB error.

```python
def _load_intervals_from_db() -> dict[str, float]:
    """Load poll intervals from system_config. Falls back to env defaults on any DB error."""
    defaults = {
        "poll-prophetx":    float(settings.POLL_INTERVAL_PROPHETX),
        "poll-sports-data": float(settings.POLL_INTERVAL_SPORTS_DATA),
        "poll-odds-api":    float(settings.POLL_INTERVAL_ODDS_API),
        "poll-sports-api":  float(settings.POLL_INTERVAL_SPORTS_API),
        "poll-espn":        float(settings.POLL_INTERVAL_ESPN),
    }
    try:
        with SyncSessionLocal() as session:
            rows = session.execute(
                select(SystemConfig).where(SystemConfig.key.like("poll_interval_%"))
            ).scalars().all()
            for row in rows:
                # "poll_interval_sports_data" → "poll-sports-data"
                task_key = row.key.replace("poll_interval_", "poll-").replace("_", "-")
                if task_key in defaults:
                    defaults[task_key] = float(row.value)
    except Exception as e:
        log.warning("beat_interval_db_load_failed", error=str(e), using="env_defaults")
    return defaults
```

Also add the rollup task to `beat_schedule`:
```python
"rollup-api-usage": {
    "task": "app.workers.rollup_api_usage.run",
    "schedule": crontab(hour=2, minute=0),  # 02:00 UTC nightly
},
```

#### `api/v1/config.py` — Add RedBeat write for interval keys
**Change:** When the key being PATCHed matches `poll_interval_*`, also update the live RedBeat schedule.
**Risk:** MEDIUM. Requires a Celery app import in the API process. The `celery_app` module is already importable from the API (it's in the same codebase). `RedBeatSchedulerEntry.from_key()` only needs a configured Celery app and Redis access — both are available in the API container.

```python
from redbeat import RedBeatSchedulerEntry as Entry
from celery.schedules import schedule as celery_schedule
from app.workers.celery_app import celery_app as _celery_app

INTERVAL_KEY_TO_TASK = {
    "poll_interval_prophetx":    "poll-prophetx",
    "poll_interval_sports_data": "poll-sports-data",
    "poll_interval_odds_api":    "poll-odds-api",
    "poll_interval_sports_api":  "poll-sports-api",
    "poll_interval_espn":        "poll-espn",
}

INTERVAL_MINIMUMS = {
    "poll_interval_prophetx":    60,
    "poll_interval_sports_data": 30,
    "poll_interval_odds_api":    300,
    "poll_interval_sports_api":  600,
    "poll_interval_espn":        300,
}

@router.patch("/{key}", response_model=ConfigItem, dependencies=[Depends(require_role(RoleEnum.admin))])
async def update_config(key: str, body: ConfigUpdateRequest, session: AsyncSession = Depends(...)):
    # ... existing DB upsert logic ...

    # v1.1: if this is an interval key, also update RedBeat live schedule
    if key in INTERVAL_KEY_TO_TASK:
        new_interval = float(body.value)
        minimum = INTERVAL_MINIMUMS.get(key, 30)
        if new_interval < minimum:
            raise HTTPException(status_code=422, detail=f"Minimum interval for {key} is {minimum}s")
        task_name = INTERVAL_KEY_TO_TASK[key]
        try:
            redbeat_key = f"redbeat:{task_name}"
            entry = Entry.from_key(redbeat_key, app=_celery_app)
            entry.schedule = celery_schedule(new_interval)
            entry.save()
            log.info("redbeat_interval_updated", task=task_name, interval=new_interval)
        except Exception as e:
            # DB write succeeded — don't rollback. Beat will pick up on restart.
            log.warning("redbeat_interval_update_failed", task=task_name, error=str(e))

    return ConfigItem(...)
```

#### `main.py` — Register new router
**Change:** Add `app.include_router(usage.router, prefix="/api/v1")`.
**Risk:** NONE.

#### `App.tsx` + `Layout.tsx` — Add API Usage page and nav
**Change:** New route `/usage` → `ApiUsagePage`. New nav entry "API Usage" in `Layout.tsx` sidebar.
**Risk:** NONE.

---

## Data Flow Changes

### Call Volume Tracking Flow (new)

```
Poll cycle fires (Beat → worker via Redis queue)
    ↓
Worker calls external API (N HTTP requests)
    ↓
BaseAPIClient._get() response hook:
    → captures quota headers
    → writes api_quota:{provider}:* keys to Redis (25h TTL)
    ↓
Worker counts calls made this cycle (N)
    ↓
_record_api_calls(worker_name, N)
    → Redis INCRBY api_calls:{worker}:{today} N
    → EXPIRE 8 days
    ↓
[nightly, 02:00 UTC]
rollup_api_usage reads api_calls:*:{yesterday}
    → UPSERT into api_usage_snapshots (PostgreSQL)
```

### Interval Change Flow (new)

```
Admin opens /usage page → sees WorkerFrequencyPanel
    ↓
Admin changes Odds API interval from 600s to 300s, clicks Save
    ↓
Frontend: PATCH /api/v1/config/poll_interval_odds_api {"value": "300"}
    ↓
Config endpoint:
  1. Validates new_interval >= 300 (minimum for odds_api)
  2. Upserts system_config row: poll_interval_odds_api = "300"
  3. Loads RedBeatSchedulerEntry.from_key("redbeat:poll-odds-api")
  4. entry.schedule = celery_schedule(300.0); entry.save()
    ↓
Beat picks up updated schedule on next tick (within 5 seconds)
Odds API worker now fires every 300s instead of 600s
    ↓
On next container restart:
  celery_app.py calls _load_intervals_from_db()
  → reads system_config.poll_interval_odds_api = "300"
  → uses 300s for beat_schedule initialization
  → interval persists across restarts
```

### Usage Data Read Flow (new)

```
Browser navigates to /usage
    ↓
TanStack Query: GET /api/v1/usage (refetchInterval: 60s)
    ↓
FastAPI /usage handler:
  Parallel reads:
  ├── Redis MGET api_calls:{worker}:{today} × 5 workers
  ├── PostgreSQL SELECT api_usage_snapshots WHERE date > today-7d
  └── Redis MGET api_quota:{provider}:* × 2 providers
    ↓
Returns combined JSON (< 50ms typical)
    ↓
Frontend renders:
  ├── UsageSummaryCards (calls today + quota remaining)
  ├── WorkerFrequencyPanel (current interval + controls)
  └── CallVolumeChart (7-day bar chart per worker)
```

---

## Component Boundaries

| Concern | Owner | Rule |
|---------|-------|------|
| API call counting | Poll workers | Each worker counts its own calls. Workers do not import from each other. |
| Quota header capture | API clients (clients/) | Client layer owns header parsing. Workers call `client.get_scores()` — quota capture is transparent. |
| Interval persistence across restarts | system_config (DB) | Single source of truth for desired interval. Written by config endpoint. Read by celery_app.py at startup. |
| Live interval update (no restart) | RedBeat via config endpoint | Config endpoint writes to both DB and RedBeat Redis. Beat picks up within 5 seconds. |
| Historical call data | api_usage_snapshots (DB) | Rollup worker owns all writes. API reads only. |
| Live call data (today) | Redis INCR keys | Poll workers own all writes (INCR). API reads only. |
| Quota snapshot data | Redis quota keys | Client layer owns all writes. API reads only. |

**Boundary that must not be crossed:** Workers should not query system_config at task-start time to read their own poll interval. This would add a synchronous DB query to every poll cycle. Workers execute on the schedule Beat gives them — they don't need to know their own interval. Beat reads from system_config at startup; the config endpoint updates Beat's live schedule directly.

---

## Build Order

Dependencies determine the order. Each step unblocks the next.

### Step 1: Call Counter Infrastructure (no dependencies)
**What:** Add `_record_api_calls()` helper. Call it in each poll worker after the external API fetch.
**Why first:** No schema changes, no new endpoints, no frontend changes. Starts accumulating real data immediately so the chart has something to show when the UI is built.
**Files:** `workers/poll_sports_data.py`, `workers/poll_odds_api.py`, `workers/poll_sports_api.py`, `workers/poll_espn.py`, `workers/poll_prophetx.py`

### Step 2: Quota Header Capture (depends on Step 1 pattern established)
**What:** Add `_capture_quota_headers()` hook to `clients/base.py`. Implement for `odds_api.py` and `sports_api.py`.
**Why second:** Defines what quota data is available before the DB schema is written. Confirms whether SDIO provides any headers (inspect live response before writing code).
**Files:** `clients/base.py`, `clients/odds_api.py`, `clients/sports_api.py`

### Step 3: DB Schema for Snapshots (depends on Steps 1-2 data shape being known)
**What:** Alembic migration `006_api_usage_snapshots.py` for `api_usage_snapshots` table.
**Why third:** Schema must be stable before the rollup worker or API endpoint references it.
**Files:** `backend/alembic/versions/006_api_usage_snapshots.py`

### Step 4: Daily Rollup Worker (depends on Step 3 schema)
**What:** `workers/rollup_api_usage.py` + add entry to `celery_app.py` beat_schedule.
**Why fourth:** Requires DB schema. Provides historical data for the trend chart. Can be deployed and run overnight before the frontend is built.
**Files:** `workers/rollup_api_usage.py`, `workers/celery_app.py`

### Step 5: Usage API Endpoint (depends on Steps 1-3)
**What:** `api/v1/usage.py` + register in `main.py`.
**Why fifth:** Can serve live Redis data (today counts + quota) immediately. DB history is available once Step 3-4 have run. Useful for curl-based debugging before the frontend exists.
**Files:** `api/v1/usage.py`, `main.py`

### Step 6: Interval Control Backend (depends on existing system_config and RedBeat)
**What:** Extend `api/v1/config.py` PATCH endpoint to write to RedBeat when key is `poll_interval_*`. Modify `celery_app.py` to read intervals from DB at startup.
**Why sixth:** Independent of Steps 1-5 (different concern). Requires RedBeat to be working (it is). The existing `system_config` + config endpoint pattern is extended, not replaced.
**Files:** `api/v1/config.py`, `workers/celery_app.py`
**Risk note:** Test the `celery_app.py` DB read at startup with a disconnected DB to confirm it falls back to env var defaults without blocking Beat startup.

### Step 7: Frontend ApiUsagePage (depends on Steps 5 and 6)
**What:** `pages/ApiUsagePage.tsx`, new route in `App.tsx`, new nav entry in `Layout.tsx`. Confirm `recharts` is available or add it.
**Why last:** Frontend integrates all backend steps. Build after the API returns real data.
**Files:** `pages/ApiUsagePage.tsx`, `App.tsx`, `components/Layout.tsx`

---

## Architectural Patterns (Existing — Preserved for Reference)

### Pattern 1: Celery Beat + Worker Separation

Beat is a separate process (separate Docker container) that schedules tasks by publishing to the Redis queue. Workers consume from that queue and execute. Beat never executes tasks itself. This is why changing a Beat schedule from the API must write to Redis (where Beat reads its schedule from) — not to the in-memory `celery_app.conf` of the API process.

### Pattern 2: system_config as Runtime Override
The `system_config` table stores key/value pairs that override env var defaults at runtime. The existing `alert_only_mode` key uses this pattern. The v1.1 `poll_interval_*` keys extend the same pattern. This is the correct location for "admin-configurable values that must survive container restarts."

### Pattern 3: Redis for Hot Data, PostgreSQL for Durable Data
Redis handles high-frequency writes (call counters, heartbeat TTLs, quota snapshots) without DB write pressure. PostgreSQL handles durable long-term storage (daily snapshots, event data, audit log). The API reads from both sources and merges them. This is the existing pattern for heartbeat TTLs and will be extended for usage data.

### Pattern 4: SSE Push via Redis Pub/Sub
Workers publish to `prophet:updates` channel after state changes. FastAPI SSE endpoint subscribes and fans out to connected browsers. TanStack Query cache is invalidated on each SSE event. The v1.1 features do not require any new SSE events — usage data is polled by the frontend (60-second interval is fine for this use case; no operator urgency requires sub-second updates).

---

## Anti-Patterns to Avoid (v1.1 Specific)

### Anti-Pattern 1: DB Query Per Poll Cycle for Interval

**What people do:** `run()` task starts, reads `system_config` to get its own poll interval.
**Why it's wrong:** SDIO runs every 30s = 2880 DB queries/day just to read a value that almost never changes. Adds latency to the task critical path.
**Do this instead:** Intervals are Beat's concern. Workers execute on the schedule Beat assigns — they never need to know their own interval. Beat reads from `system_config` once at startup; the config endpoint updates Beat directly via RedBeat.

### Anti-Pattern 2: Writing Call Counts Per-Cycle to PostgreSQL

**What people do:** `INSERT INTO api_usage_snapshots (worker, timestamp, count) VALUES (...)` every poll cycle.
**Why it's wrong:** Creates thousands of rows per day. The `events` table already has write contention from 5 workers. High-frequency inserts amplify connection pool pressure.
**Do this instead:** Redis INCR for live counts (atomic, O(1), no connection overhead). Nightly rollup task writes one row per worker to PostgreSQL for durable history.

### Anti-Pattern 3: Mutating `celery_app.conf.beat_schedule` at Runtime from FastAPI

**What people do:** `celery_app.conf.beat_schedule["poll-odds-api"]["schedule"] = 300.0` from the config endpoint.
**Why it's wrong:** The `celery_app` imported in the FastAPI process is a different object instance than the one running in the Beat container. Mutating it has no effect on the running scheduler.
**Do this instead:** Use `RedBeatSchedulerEntry.from_key(key, app=celery_app).save()` to write directly to the Redis keys that the Beat container reads. This is how RedBeat is designed to support runtime schedule changes.

### Anti-Pattern 4: Quota Data Without TTL

**What people do:** Write quota data to Redis with no expiry. Value persists forever.
**Why it's wrong:** If the provider stops returning quota headers (outage, plan change, API version change), the UI shows a stale value that is potentially weeks old, misleading operators.
**Do this instead:** 25-hour TTL on all quota keys. If the key expires, the API returns `null` for that provider's quota. The frontend shows "unavailable" rather than stale data. The next successful API call refreshes the key.

### Anti-Pattern 5: Minimum Interval Enforcement Only in Frontend

**What people do:** Client-side validation prevents setting an interval below the minimum. No server-side check.
**Why it's wrong:** A direct API call bypasses the frontend. An operator could set SDIO to 1 second and exhaust the subscription in minutes.
**Do this instead:** Enforce minimum intervals in the config endpoint server-side. Return HTTP 422 with a clear error message if the submitted value is below the minimum.

---

## Scaling Considerations

This is an internal ops tool deployed on a single Hetzner CX23 VPS. v1.1 features add negligible load.

| Concern | After v1.1 | Notes |
|---------|-----------|-------|
| Redis memory | +~5KB for all usage/quota keys | 5 workers × 8 daily counters + quota keys per provider. Negligible against 256MB Redis limit. |
| PostgreSQL writes | +5 rows per night (rollup) | No meaningful impact on write throughput. |
| Beat startup time | +DB query (≤3s timeout) | Beat total startup becomes ≤5s. Acceptable. |
| API endpoint latency | New /usage: ~1 Redis MGET + 1 DB SELECT | Expected < 50ms. No caching needed at this scale. |
| Worker memory | +~1KB per cycle for counter logic | Negligible against 400MB per-child limit. |
| Frontend load | +1 TanStack Query (60s interval) | One additional 60-second polling query per open tab. Negligible. |

---

## Open Questions

1. **SDIO quota headers:** SDIO documentation does not publish quota header names for paid plans (described as "unlimited calls"). Inspect an actual SDIO response header before building the quota capture for SDIO. If no headers exist, SDIO usage monitoring is call-count-only (the Redis counter provides this). Do not hard-code "unlimited" in the UI without confirming the subscription terms.

2. **RedBeat key prefix confirmation:** The default RedBeat prefix is `redbeat:`. Beat task names in `celery_app.py` use dashes: `poll-sports-data`. Full Redis key would be `redbeat:poll-sports-data`. Confirm this against the live Redis instance with `redis-cli KEYS "redbeat:*"` before writing `Entry.from_key(...)` code.

3. **RedBeat key format for crontab schedule:** The rollup task uses `crontab(hour=2, minute=0)` rather than a fixed interval. RedBeat supports both interval and crontab schedules, but the `Entry.from_key()` update path tested in research used `schedule(N)` (interval type). Confirm crontab entries are also updateable via `Entry.from_key()`, or keep the rollup schedule as a static Beat schedule entry (it does not need UI control — it should always run nightly).

4. **`recharts` dependency:** The 7-day call volume chart requires a charting library. Confirm whether `recharts` or another option is already in `frontend/package.json`. If not, add it in Step 7.

5. **Celery app import in FastAPI process:** `RedBeatSchedulerEntry` requires importing `celery_app` from `workers/celery_app.py` into the API process. Confirm this import doesn't trigger Celery worker registration side effects in the API container. The `celery_app.py` module includes `include=[...]` which registers task modules — this should be safe as long as the worker modules don't have startup side effects (they currently don't).

---

## Sources

- Direct codebase inspection: `workers/celery_app.py`, `workers/poll_*.py`, `clients/base.py`, `clients/odds_api.py`, `clients/sports_api.py`, `models/config.py`, `api/v1/config.py`, `api/v1/health.py`, `db/redis.py`, `docker-compose.yml`, `core/config.py`
- Odds API documentation: `x-requests-remaining`, `x-requests-used`, `x-requests-last` headers — confirmed from the-odds-api.com (HIGH confidence)
- API-Football/api-sports.io rate limit documentation: `x-ratelimit-requests-remaining`, `x-ratelimit-requests-limit` — confirmed from api-football.com/news/post/how-ratelimit-works (HIGH confidence)
- RedBeat runtime schedule update: `Entry.from_key(key, app=app); entry.schedule = schedule(N); entry.save()` — confirmed from GitHub gist (gist.github.com/nvpmai/bd475b5d562811dadc86381a49759040) and RedBeat GitHub (github.com/sibson/redbeat) (HIGH confidence)
- SDIO quota headers: not found in public documentation — treat as call-count-only until confirmed from live response (LOW confidence)
- Previous v1.0 architecture research (2026-02-24) — full system overview, component boundaries, scaling considerations, anti-patterns

---
*Architecture research for: ProphetX Market Monitor — v1.1 API usage monitoring + per-worker poll frequency controls*
*Researched: 2026-03-01*
