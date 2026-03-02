# Phase 4: Stabilization + Counter Foundation - Research

**Researched:** 2026-03-01
**Domain:** Bug fixes (Sports API false positives, broken health endpoint), confidence threshold validation, Redis call counters
**Confidence:** HIGH (all four requirements diagnosed directly from live codebase inspection)

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| STAB-01 | Sports API false-positive alerts eliminated by using actual game start times instead of noon-UTC proxy and tightening time-distance guard | Root cause confirmed: `poll_sports_api.py` lines 307-309 construct `game_start_utc` always from noon UTC, ignoring `date_str` which contains actual ISO datetime. Fix: use `game_dt` (already parsed from `date_str` earlier in the same function) for the time guard. Also tighten threshold from `>12h` to `>6h`. |
| STAB-02 | Worker health endpoint (`/api/v1/health/workers`) returns correct response instead of 404 | Root cause confirmed: route exists in `backend/app/api/v1/health.py` and is registered in `main.py` but the deployed Docker image on the Hetzner server is stale (code baked into images, not bind-mounted). Fix: rebuild backend image and redeploy. |
| STAB-03 | Event matching confidence threshold validated against real ProphetX + source data and tuned if needed | `EventMatcher` uses rapidfuzz `token_sort_ratio`, weights 0.35/0.35/0.30 (home/away/time), threshold 0.90. Known issue: "LA Lakers" vs "Los Angeles Lakers" scores 0.8574 — below threshold. Fix approach: run test data from live DB through scorer, document before/after, tune threshold or weights if match rate is unacceptable. |
| USAGE-01 | Operator can see total API calls made per worker per day via `/api/v1/usage` | No counter logic exists in any worker. Add `r.incrby(f"api_calls:{worker_name}:{today_date}", 1)` at the end of each worker's `run()` function, plus a new `/api/v1/usage` endpoint that reads all 5 counter keys via Redis MGET. Key resets automatically each day because the date suffix changes. Set 8-day TTL on first write. |
</phase_requirements>

## Summary

Phase 4 is four targeted fixes and additions to an already-deployed system. All four requirements have been fully diagnosed from direct codebase inspection — no exploratory research required.

**STAB-01** has a clear, one-function fix: the time guard in `poll_sports_api.py` computes `game_start_utc` from `game_date` at noon UTC (lines 307-309) instead of using `game_dt` (the actual ISO datetime already parsed from `date_str` at lines 270-272 of the same function). The api-sports.io API confirms it returns full ISO datetimes for non-soccer sports (`"date": "2019-11-23T00:30:00+00:00"`), so actual start times are available. The guard should also be tightened from `>12h` to `>6h` per the STATE.md diagnosis. The ESPN worker has the same noon-proxy pattern and should be fixed consistently.

**STAB-02** is a deployment issue, not a code issue. The `/health/workers` endpoint is correctly implemented in `health.py` and registered in `main.py`. The 404 occurs because the server runs a stale Docker image built before the `feat(03-02)` commit that added this endpoint. The fix is: `docker compose build backend && docker compose up -d backend` on the Hetzner server. A regression test for this endpoint should be added to `test_health.py` to prevent future silent breakage.

**STAB-03** is a validation task: run real ProphetX events and SDIO games through `compute_confidence()` and observe the match rates. The known problem case (abbreviated vs. full team names like "LA Lakers" scoring 0.8574) suggests either lowering the threshold slightly (0.85?) or accepting that time-proximity scoring (0.30 weight) compensates when timestamps align. The decision must be documented with before/after match rates to satisfy the success criterion.

**USAGE-01** adds Redis `INCRBY` call counters to all 5 poll workers and exposes them via a new `/api/v1/usage` endpoint. The Redis `incr()` / `incrby()` methods are already available via the existing `redis` library. The counter key pattern is `api_calls:{worker_name}:{YYYY-MM-DD}` with an 8-day TTL (set on first write using `expire()` if key did not previously exist). The counter must go at the END of the worker run function (after the external fetch) so that only successful poll cycles are counted, not failures that trigger retry.

**Primary recommendation:** Fix all four items in a single plan. STAB-02 (image rebuild + test) can be done first in minutes. STAB-01 and USAGE-01 are parallel code changes to different workers. STAB-03 is a validation step that requires live DB data and should be done last (after the server is running the fixed images).

## Standard Stack

### Core (all existing — no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| redis (sync) | 5.x | `r.incrby()` for atomic call counters | Already in all workers; `incr` is atomic O(1) |
| FastAPI | 0.115.x | New `/api/v1/usage` endpoint | Existing API framework |
| rapidfuzz | 3.14.x | `fuzz.token_sort_ratio()` for event matching | Already used in `event_matcher.py`; handles abbreviations better than SequenceMatcher |
| pytest | 8.x | Test for STAB-02 health/workers endpoint | Existing test framework; pyproject.toml configured |

### No New Dependencies
Phase 4 requires zero new packages. All changes are in existing Python files.

**Installation:**
```bash
# No new packages needed
```

## Architecture Patterns

### Recommended Project Structure
No structural changes needed. All changes are within existing files:
```
backend/app/
├── workers/
│   ├── poll_sports_api.py   # STAB-01: fix time guard (lines 307-314)
│   ├── poll_espn.py         # STAB-01: fix time guard (lines 245-246) for consistency
│   ├── poll_prophetx.py     # USAGE-01: add INCRBY counter
│   ├── poll_sports_data.py  # USAGE-01: add INCRBY counter
│   ├── poll_odds_api.py     # USAGE-01: add INCRBY counter
│   ├── poll_sports_api.py   # USAGE-01: add INCRBY counter (same file as STAB-01)
│   └── poll_espn.py         # USAGE-01: add INCRBY counter (same file as STAB-01)
├── api/v1/
│   ├── health.py            # STAB-02: no change needed (route already correct)
│   └── usage.py             # USAGE-01: new file — /api/v1/usage endpoint
├── main.py                  # USAGE-01: register usage router
└── monitoring/
    └── event_matcher.py     # STAB-03: possibly tune CONFIDENCE_THRESHOLD or weights
tests/
└── test_health.py           # STAB-02: add worker health regression test
```

### Pattern 1: Sports API Time Guard Fix (STAB-01)

**What:** Replace the noon-UTC proxy with the actual game datetime already parsed from `date_str`

**Current broken code (poll_sports_api.py ~lines 307-314):**
```python
# BUG: always uses noon UTC, ignores actual game start time
game_start_utc = datetime(
    game_date.year, game_date.month, game_date.day,
    12, 0, tzinfo=timezone.utc,
)
hours_apart = abs(
    (best_match.scheduled_start - game_start_utc).total_seconds()
) / 3600
if hours_apart > 12:
```

**Fixed code:**
```python
# FIX: use actual parsed game datetime (game_dt was parsed from date_str above)
# game_dt is already a timezone-aware datetime from fromisoformat(date_str)
# Fallback to noon UTC only if date_str parse failed
guard_dt = game_dt  # game_dt: set at line ~270, already handles both soccer and non-soccer
hours_apart = abs(
    (best_match.scheduled_start - guard_dt).total_seconds()
) / 3600
if hours_apart > 6:  # Tightened from 12h to 6h per STATE.md diagnosis
```

**Note:** `game_dt` at line ~270 is set via `datetime.fromisoformat(date_str.replace("Z", "+00:00"))` and falls back to noon UTC only if parsing fails. api-sports.io returns `"date": "2019-11-23T00:30:00+00:00"` for basketball — confirmed from their OpenAPI spec. So `game_dt` will have the actual game time for virtually all games.

**Same fix for poll_espn.py:** Replace `guard_midday = datetime(record_date.year, ...)` with the `record_dt` already computed at line ~209. Change threshold from `>12` to `>6`.

### Pattern 2: Redis INCRBY Call Counter (USAGE-01)

**What:** Atomic increment of a date-keyed Redis counter at the end of each poll worker's `run()` function

**When to use:** After the external API fetch succeeds and DB writes are committed — not at task start, not in `except` blocks

**Code to add to each worker's `_write_heartbeat()` helper or as a new `_increment_call_counter()` function:**
```python
def _increment_call_counter(worker_name: str) -> None:
    """Atomically increment the call counter for this worker for today (UTC).

    Key: api_calls:{worker_name}:{YYYY-MM-DD}
    TTL: 8 days (set only on first write — expire is a no-op if key already has TTL)
    This is safe under --concurrency=6 because Redis INCRBY is atomic.
    """
    from app.core.config import settings
    from datetime import date, timezone
    today = date.today().isoformat()  # YYYY-MM-DD, resets naturally at UTC midnight
    key = f"api_calls:{worker_name}:{today}"
    r = _sync_redis.from_url(settings.REDIS_URL)
    # INCRBY is atomic — safe under 6-worker concurrency (no GET/SET race)
    count = r.incr(key)
    if count == 1:
        # First write today — set 8-day TTL so old keys expire automatically
        r.expire(key, 8 * 86400)
```

**Worker names (must match keys in /api/v1/usage response):**
- `poll_prophetx`
- `poll_sports_data`
- `poll_odds_api`
- `poll_sports_api`
- `poll_espn`

**Placement in each worker:** Call `_increment_call_counter("poll_{name}")` immediately before (or after) `_write_heartbeat()` at the end of each `run()` function. Specifically: after the external API fetch has succeeded and DB commit has happened, but before returning.

**Exception for early-return paths:** Workers have multiple early-return paths (e.g., `if not settings.SPORTS_API_KEY: return`, `if not events_in_db: return`). These early exits should NOT increment the counter — only successful full-cycle polls count.

### Pattern 3: /api/v1/usage Endpoint (USAGE-01)

**What:** New read-only endpoint serving today's call counts for all 5 workers

**File:** `backend/app/api/v1/usage.py` (new file)

```python
from fastapi import APIRouter, Depends
from datetime import date
from app.db.redis import get_redis_client
from app.core.security import require_role
from app.core.constants import RoleEnum

router = APIRouter()

WORKER_NAMES = [
    "poll_prophetx",
    "poll_sports_data",
    "poll_odds_api",
    "poll_sports_api",
    "poll_espn",
]

@router.get("/usage")
async def get_usage(
    _: None = Depends(require_role(RoleEnum.readonly)),
):
    """Return today's API call counts per worker.

    Counts come from Redis INCRBY counters incremented each poll cycle.
    Key format: api_calls:{worker_name}:{YYYY-MM-DD}
    Returns 0 (not null) for workers that have not run today.
    """
    today = date.today().isoformat()
    redis = await get_redis_client()
    keys = [f"api_calls:{name}:{today}" for name in WORKER_NAMES]
    values = await redis.mget(*keys)
    return {
        "date": today,
        "calls_today": {
            name: int(val or 0)
            for name, val in zip(WORKER_NAMES, values)
        },
    }
```

**Register in main.py:**
```python
from app.api.v1 import ..., usage
app.include_router(usage.router, prefix="/api/v1")
```

### Pattern 4: Confidence Threshold Validation (STAB-03)

**What:** Extract real ProphetX events and their matched SDIO games from the live DB, run them through `compute_confidence()`, and determine whether the 0.90 threshold causes unacceptable false negatives.

**Approach:**
```python
# Run as a one-time script against the live DB (or via docker exec on server)
# Query: SELECT e.home_team, e.away_team, e.scheduled_start, e.sport,
#               m.sdio_game_id, m.confidence, m.is_confirmed
# FROM events e JOIN event_id_mappings m ON e.id = m.px_event_id
# WHERE m.updated_at > NOW() - INTERVAL '3 days'
# ORDER BY m.confidence ASC
# Examine rows with confidence 0.80-0.95 — are they correct matches?
```

**Decision tree:**
- If all correct matches are at ≥0.90: threshold is fine, document as validated
- If correct matches cluster at 0.85-0.90: lower threshold to 0.85 (acceptable risk given time component guards against cross-match)
- If threshold change: update `CONFIDENCE_THRESHOLD` in `event_matcher.py`, clear Redis match cache (`DEL match:px:*`), document before/after match rates

### Anti-Patterns to Avoid
- **Counter at task start:** Increments even if the external API call fails. Count only successful cycles.
- **GET/SET counter pattern:** `r.get(key); count = int(val)+1; r.set(key, count)` — race condition under `--concurrency=6`. Always use `r.incr()` (which is INCRBY 1).
- **Separate Redis connection per worker call:** Each `_write_heartbeat()` call already creates `_sync_redis.from_url(settings.REDIS_URL)`. The counter should reuse the same connection within the same call (or the pattern is consistent with existing worker code — one new connection per counter write is acceptable since workers fire every 30s-10m, not per-request).
- **Lowering threshold without testing:** Don't lower CONFIDENCE_THRESHOLD speculatively — test against real data first. A threshold that's too low causes false-positive auto-status-updates (worse than false-negative mismatches).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic daily call counter | GET current value, add 1, SET back | `r.incr(key)` / `r.incrby(key, 1)` | GET/SET is not atomic; two concurrent workers can read the same value and both write count+1 instead of count+2. Redis INCR is documented as O(1) and atomic. |
| Date-keyed counter reset | Cron job to zero counters at midnight | Key suffix is `{YYYY-MM-DD}` — new day = new key automatically | No reset mechanism needed. Old keys expire after 8-day TTL. |
| Worker health via Celery inspect | `celery_app.control.inspect().active()` | Redis heartbeat TTL (already in place) | Celery inspect has race conditions and is unreliable under burst load. The existing heartbeat pattern is already deployed and tested. |

**Key insight:** Redis INCR is atomic precisely because Redis is single-threaded for command processing. No locking, no transactions, no retries needed.

## Common Pitfalls

### Pitfall 1: Counter on early-return paths
**What goes wrong:** Placing the `_increment_call_counter()` call at the top of `run()` or in a try/finally block increments the counter even when the worker exits early (no API key, no matching events, network failure).
**Why it happens:** Defensive placement to "always count the attempt."
**How to avoid:** Place the counter call only after the external API call has succeeded and DB writes are committed. In each worker, this is immediately before (or after) `_write_heartbeat()` at the successful-completion path.
**Warning signs:** Counter shows 2880 calls/day for poll_prophetx (every 30s = 2880/day) but only 1200 for poll_sports_api (every 30min = 48/day) — if the numbers are equal or counter doesn't reflect actual poll interval, placement is wrong.

### Pitfall 2: Stale CONFIDENCE_THRESHOLD after cache clear
**What goes wrong:** Lowering `CONFIDENCE_THRESHOLD` in `event_matcher.py` and rebuilding the image, but Redis still contains cached match results from before the change. The cache key `match:px:{px_event_id}` has a 24h TTL — old matches persist and skip recomputation.
**Why it happens:** Redis match cache is checked before scoring (`cached = get_cached_match(...)`).
**How to avoid:** After any threshold change, flush the match cache: `redis-cli -h localhost KEYS "match:px:*" | xargs redis-cli DEL` (or run from a docker exec on the server).
**Warning signs:** Match rates look unchanged immediately after deploying the threshold fix.

### Pitfall 3: STAB-02 rebuild order
**What goes wrong:** Rebuilding the backend image but not restarting all dependent services. The Beat and Worker containers import from the same `app/` module — a stale worker container can return incorrect behavior even after the backend is updated.
**Why it happens:** `docker compose build backend && docker compose up -d backend` only updates the API server, not worker/beat.
**How to avoid:** After code changes to `app/workers/` or `app/api/`, rebuild and restart all services: `docker compose build && docker compose up -d`.
**Warning signs:** `/api/v1/health/workers` returns 200 after the API rebuild but the call counters don't appear — worker image is still stale.

### Pitfall 4: game_dt fallback case still uses noon UTC
**What goes wrong:** The `date_str` parse at line 270 can fail (except clause assigns noon UTC fallback). If the fallback triggers, `game_dt` is noon UTC and the "fixed" time guard still uses noon UTC — no behavior change in the fallback case.
**Why it happens:** The fallback exists for malformed `date_str` values.
**How to avoid:** The fallback case is correct behavior — if we don't know the actual game time, noon UTC is a reasonable midpoint. The fix for STAB-01 is correct: using `game_dt` instead of reconstructing `game_start_utc` eliminates the bug for all cases where `date_str` parses correctly (which is all real api-sports.io responses).
**Warning signs:** Not a problem — this is intended behavior.

### Pitfall 5: /api/v1/usage endpoint authorization level
**What goes wrong:** Applying `require_role(RoleEnum.admin)` instead of `require_role(RoleEnum.readonly)` (or `operator`) to the usage endpoint, making call counts invisible to operators who are not admins.
**Why it happens:** New endpoints default to admin guard for safety.
**How to avoid:** Per REQUIREMENTS.md USAGE-01: "Operator can see total API calls." Use `require_role(RoleEnum.readonly)` (which accepts read_only, operator, AND admin roles). Follow the pattern from `events.py` and `markets.py`.

## Code Examples

Verified patterns from codebase inspection:

### INCRBY Counter (atomic, date-keyed)
```python
# Source: redis library docs + existing worker pattern in poll_prophetx.py
def _increment_call_counter(worker_name: str) -> None:
    from app.core.config import settings
    from datetime import date
    today = date.today().isoformat()  # "2026-03-01" — key auto-resets each day
    key = f"api_calls:{worker_name}:{today}"
    r = _sync_redis.from_url(settings.REDIS_URL)
    count = r.incr(key)          # INCRBY 1 — atomic under --concurrency=6
    if count == 1:
        r.expire(key, 8 * 86400) # 8-day TTL on first write only
```

### Time Guard Fix (use actual game datetime)
```python
# Source: Direct inspection of poll_sports_api.py lines 270-314
# game_dt is already computed above this block via:
#   game_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
#   except: game_dt = datetime(game_date.year, ..., 12, 0, tzinfo=utc)  # noon fallback

# BEFORE (broken — always noon UTC):
game_start_utc = datetime(game_date.year, game_date.month, game_date.day, 12, 0, tzinfo=timezone.utc)
hours_apart = abs((best_match.scheduled_start - game_start_utc).total_seconds()) / 3600
if hours_apart > 12:

# AFTER (correct — uses actual parsed game time):
hours_apart = abs((best_match.scheduled_start - game_dt).total_seconds()) / 3600
if hours_apart > 6:  # tightened from 12 per STATE.md diagnosis
```

### /api/v1/usage Response Shape
```json
{
  "date": "2026-03-01",
  "calls_today": {
    "poll_prophetx": 2847,
    "poll_sports_data": 2847,
    "poll_odds_api": 142,
    "poll_sports_api": 48,
    "poll_espn": 48
  }
}
```

### Confidence Validation Script Pattern
```python
# Run via: docker exec <backend_container> python -c "..."
# Or as a temporary endpoint during validation phase
from app.db.sync_session import SyncSessionLocal
from app.models.event_id_mapping import EventIDMapping
from sqlalchemy import select, and_
from datetime import datetime, timedelta, timezone

with SyncSessionLocal() as session:
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    rows = session.execute(
        select(EventIDMapping).where(EventIDMapping.updated_at > cutoff)
        .order_by(EventIDMapping.confidence.asc())
    ).scalars().all()
    # Print rows with confidence 0.70-0.95 for manual inspection
    for row in rows:
        if 0.70 <= row.confidence < 0.95:
            print(f"confidence={row.confidence:.3f} confirmed={row.is_confirmed} "
                  f"px={row.px_event_id} sdio={row.sdio_game_id}")
```

### STAB-02 Regression Test Pattern
```python
# Add to tests/test_health.py
@pytest.mark.asyncio
async def test_worker_health_returns_200(client):
    """Regression test for STAB-02: /health/workers must return 200, not 404."""
    response = await client.get("/api/v1/health/workers")
    assert response.status_code == 200
    data = response.json()
    # All 5 workers present (values can be True or False depending on test Redis state)
    assert "poll_prophetx" in data
    assert "poll_sports_data" in data
    assert "poll_odds_api" in data
    assert "poll_sports_api" in data
    assert "poll_espn" in data
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Noon-UTC proxy for time guard | Actual ISO datetime from api-sports.io response | STAB-01 fix | Eliminates false positives when same teams play consecutive days |
| No call counters | Redis INCRBY per worker per day | USAGE-01 | Provides real usage data for Phase 6 ApiUsagePage; one week of history before frontend is built |
| Confidence threshold unvalidated (0.90) | Threshold validated against real data, documented | STAB-03 | Operator trust in auto-status-sync decisions |

**Deprecated/outdated:**
- `game_start_utc = datetime(game_date.year, ..., 12, 0)` in `poll_sports_api.py`: replaced by `game_dt` (actual parsed time)
- `guard_midday = datetime(record_date.year, ..., 12, 0)` in `poll_espn.py`: replaced by `record_dt` (actual parsed time) for consistency

## Open Questions

1. **STAB-03: What threshold adjustment (if any) is warranted?**
   - What we know: threshold is 0.90; "LA Lakers" vs "Los Angeles Lakers" scores 0.8574; test data from Phase 2 research exists but was synthetic
   - What's unclear: actual false-negative rate against real ProphetX + SDIO data from live DB; whether the time component (0.30 weight) fully compensates for abbreviated team names
   - Recommendation: Query `event_id_mappings` on the server for the past 3 days; inspect all rows with `confidence < 0.95`; if confirmed correct matches cluster at 0.85-0.90, lower to 0.85 and document; if all correct matches are ≥0.90, document threshold as validated with no change

2. **STAB-01: Should poll_espn.py be updated with the same fix?**
   - What we know: ESPN worker has identical noon-UTC proxy issue (`guard_midday` at lines 245-246); ESPN records only return date-level strings (no time component), so `record_dt` is already noon UTC and the fix is a no-op for ESPN
   - What's unclear: Whether ESPN records ever contain actual datetimes (the `_extract_date` function returns `event_date = datetime.fromisoformat(date_str).date().isoformat()` — strips time component)
   - Recommendation: Update the ESPN time guard threshold from `>12` to `>6` for consistency with Sports API, but keep the noon proxy since ESPN doesn't provide actual start times at the record level

3. **USAGE-01: Should the `/api/v1/usage` endpoint require a login or be public?**
   - What we know: All other data endpoints require auth; the requirements say "Operator can see..."
   - What's unclear: Nothing — this is clearly an authenticated endpoint
   - Recommendation: Use `require_role(RoleEnum.readonly)` (same as events/markets endpoints) to allow read-only, operator, and admin roles

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: `backend/app/workers/poll_sports_api.py` — time guard logic at lines 270-314, confirmed noon-UTC proxy bug
- Direct codebase inspection: `backend/app/workers/poll_espn.py` — same noon-UTC proxy pattern at lines 209, 245-246
- Direct codebase inspection: `backend/app/api/v1/health.py` — `/health/workers` endpoint correctly defined
- Direct codebase inspection: `backend/app/main.py` — `health.router` registered with `/api/v1` prefix
- Direct codebase inspection: `backend/app/monitoring/event_matcher.py` — CONFIDENCE_THRESHOLD=0.90, weights 0.35/0.35/0.30
- Direct codebase inspection: `backend/app/db/redis.py` — sync and async Redis client patterns
- api-sports.io OpenAPI spec (`basketball-v1.yaml`) — confirmed `date` field format: `"2019-11-23T00:30:00+00:00"` (full ISO datetime, not date-only)
- Redis INCR docs (https://redis.io/docs/latest/commands/incr/) — atomic O(1), confirmed thread-safe

### Secondary (MEDIUM confidence)
- `.planning/phases/03-dashboard-and-alerts/.continue-here.md` — post-deployment context confirming server is live at Hetzner, code is baked into images, and Sports API false positives are the active concern
- `STATE.md` — diagnosis: "Sports API false-positive root cause: using noon-UTC proxy instead of actual start time, time-distance guard too loose (>12h)" — confirmed by code inspection

### Tertiary (LOW confidence)
- None — all required findings are HIGH confidence from codebase inspection and official docs

## Metadata

**Confidence breakdown:**
- STAB-01 fix approach: HIGH — root cause confirmed from code; api-sports.io date format confirmed from official spec
- STAB-02 fix approach: HIGH — route exists and is registered; stale image is only plausible explanation for 404
- STAB-03 validation approach: HIGH — scoring mechanics confirmed; actual threshold decision is LOW confidence until real data is examined
- USAGE-01 counter pattern: HIGH — Redis INCR atomicity confirmed from official docs; pattern consistent with existing worker code

**Research date:** 2026-03-01
**Valid until:** 2026-03-30 (stack is stable; no dependencies on external APIs that could change)
