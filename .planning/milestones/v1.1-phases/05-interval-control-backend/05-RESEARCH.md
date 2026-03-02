# Phase 5: Interval Control Backend - Research

**Researched:** 2026-03-02
**Domain:** RedBeat scheduler bootstrap, FastAPI config endpoint extension, DB-seeded runtime configuration
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Minimum intervals per worker** (DB-configurable, initial values):
- ProphetX: 60s
- SportsDataIO: 15s
- Odds API: 600s (10 min) — hard floor due to 500 calls/month free tier
- Sports API: 600s (10 min) — floor due to per-sport daily quotas
- ESPN: 60s
- Critical Check: 15s

PATCH request below minimum returns HTTP 422 with clear error message.

**Default values and seeding:**
- Seed from env vars on first boot: startup hook reads POLL_INTERVAL_* env vars and inserts as initial DB rows (if no row exists yet)
- Consistent with existing admin user seed pattern (runs on every boot, checks if rows exist, inserts if missing)
- Current production defaults: ProphetX=300s, SDIO=30s, Odds=600s, Sports API=1800s, ESPN=600s
- Critical Check default lowered from 60s to 30s (DB query is cheap)
- DB is sole source of truth after initial seed — env vars are ignored for intervals once DB rows exist

**Critical check task:**
- poll_critical_check becomes configurable (same pattern as other workers)
- Minimum: 15s, Default: 30s

### Claude's Discretion

- RedBeat integration approach (bootstrap from DB vs `from_key` API)
- Change propagation mechanism (how quickly DB changes reach running Beat)
- DB key naming convention for interval config rows
- Whether minimums are stored in same system_config table or separate

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| FREQ-02 | Server enforces minimum poll interval per worker to prevent API abuse (HTTP 422 on violation) | PATCH /api/v1/config/{key} endpoint extended with interval-specific validation; minimum values seeded to DB from constants |
| FREQ-03 | Poll interval settings persist across Beat restarts (DB-backed, not overwritten by static config) | beat_schedule dict removed from celery_app.py; startup seed writes DB rows on first boot; Beat bootstrap function reads DB rows and calls RedBeatSchedulerEntry.save() before Beat loop starts |
</phase_requirements>

## Summary

The root of FREQ-03 is a confirmed RedBeat behavior: `RedBeatScheduler.setup_schedule()` calls `update_from_dict()` on every Beat startup, which calls `entry.save()` for every entry in `beat_schedule`. The `save()` method writes the full `definition` hash to Redis, including the `schedule` interval. This overwrites whatever interval an operator set at runtime. `last_run_at` is preserved (the meta field), but the interval is not. As long as `beat_schedule` in `celery_app.py` contains hardcoded or env-var-derived intervals, Beat restart will always revert to those values.

The fix is two-part: (1) remove the `beat_schedule` dict from `celery_app.py` entirely, and (2) bootstrap RedBeat entries from the DB at startup. The bootstrap must happen before Beat starts its tick loop. The correct hook is the Beat `setup_schedule()` method via a startup function called in the API's `seed.py`-equivalent for Beat, OR (simpler) a standalone bootstrap script called from the Beat container command before `celery beat` starts. The `RedBeatSchedulerEntry` class provides a clean `save()` API for writing entries with arbitrary intervals to Redis.

FREQ-02 is straightforward: extend the existing `PATCH /api/v1/config/{key}` handler to detect interval keys by naming convention, parse the new value as an integer, compare it against the per-worker minimum (read from DB or hardcoded constant), and raise HTTP 422 if violated. After validation passes, call a helper that updates the RedBeat entry in Redis so Beat picks up the change on its next tick (typically within 5 seconds — Beat's default max_interval is 5s).

**Primary recommendation:** Remove `beat_schedule` from `celery_app.py`. Add a DB-seeded bootstrap that writes RedBeat entries via `RedBeatSchedulerEntry.save()` in a sync startup script mirroring the admin seed pattern. Extend the config PATCH endpoint with interval validation and a Redis update helper.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| celery-redbeat | 2.3.3 | RedBeat scheduler — stores Beat schedule in Redis | Already installed and configured; provides `RedBeatSchedulerEntry` API |
| SQLAlchemy (sync) | existing | DB reads in seed/bootstrap (sync context) | `SyncSessionLocal` already used in seed.py and worker tasks |
| celery.schedules.schedule | existing | Celery interval schedule object | Required by `RedBeatSchedulerEntry` constructor |
| FastAPI HTTPException | existing | HTTP 422 response | Standard FastAPI error pattern already used in the project |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| celery.schedules.schedule | existing | Wrap float seconds into a Celery schedule object | Required when constructing `RedBeatSchedulerEntry` — plain floats not accepted |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Sync bootstrap script called before Beat | Beat `setup_schedule()` override subclass | Subclassing requires shipping custom RedBeatScheduler — more fragile, harder to reason about |
| Same `system_config` table for both intervals and minimums | Separate `poll_intervals` table | New table adds migration without benefit; system_config key-value pattern handles both cleanly via naming convention |

## Architecture Patterns

### Recommended Project Structure

Changes are confined to existing files with one new utility module:

```
backend/app/
├── workers/
│   ├── celery_app.py          # MODIFIED: remove beat_schedule dict
│   └── beat_bootstrap.py      # NEW: reads DB, writes RedBeat entries
├── seed.py                    # MODIFIED: add interval seed call
└── api/v1/
    └── config.py              # MODIFIED: add interval validation + RedBeat update
docker-compose.yml             # MODIFIED: beat command gains bootstrap step
```

### Pattern 1: DB Key Naming Convention

Two sets of keys in `system_config`:

- `poll_interval_{worker}` — the operator-set interval in seconds (string-encoded integer)
- `poll_interval_{worker}_min` — the server-enforced minimum in seconds

Worker names match the task names: `prophetx`, `sports_data`, `odds_api`, `sports_api`, `espn`, `critical_check`.

Full example key set:
```
poll_interval_prophetx          = "300"
poll_interval_prophetx_min      = "60"
poll_interval_sports_data       = "30"
poll_interval_sports_data_min   = "15"
poll_interval_odds_api          = "600"
poll_interval_odds_api_min      = "600"
poll_interval_sports_api        = "1800"
poll_interval_sports_api_min    = "600"
poll_interval_espn              = "600"
poll_interval_espn_min          = "60"
poll_interval_critical_check    = "30"
poll_interval_critical_check_min = "15"
```

This approach stores everything in the existing `system_config` table (no new migration needed beyond adding rows), makes minimums DB-configurable as per the locked decision, and allows the PATCH endpoint to detect interval keys by prefix.

### Pattern 2: Beat Bootstrap Script

A new `beat_bootstrap.py` module that reads intervals from DB and writes RedBeat entries. This runs synchronously (using `SyncSessionLocal`) before Beat starts its tick loop.

```python
# backend/app/workers/beat_bootstrap.py
# Source: analysis of redbeat/schedulers.py RedBeatSchedulerEntry API

from celery.schedules import schedule as celery_schedule
from redbeat import RedBeatSchedulerEntry
from sqlalchemy import select

from app.db.sync_session import SyncSessionLocal
from app.models.config import SystemConfig
from app.workers.celery_app import celery_app

# Maps DB key suffix -> Celery task name
WORKER_TASK_MAP = {
    "prophetx":      "app.workers.poll_prophetx.run",
    "sports_data":   "app.workers.poll_sports_data.run",
    "odds_api":      "app.workers.poll_odds_api.run",
    "sports_api":    "app.workers.poll_sports_api.run",
    "espn":          "app.workers.poll_espn.run",
    "critical_check":"app.workers.poll_critical_check.run",
}

# Beat entry name (key used in RedBeat's sorted set)
BEAT_NAME_MAP = {
    "prophetx":      "poll-prophetx",
    "sports_data":   "poll-sports-data",
    "odds_api":      "poll-odds-api",
    "sports_api":    "poll-sports-api",
    "espn":          "poll-espn",
    "critical_check":"poll-critical-check",
}


def bootstrap_beat_schedule():
    """Read intervals from system_config and write RedBeat entries to Redis.

    Called before Beat starts. Safe to call multiple times — save() uses
    hsetnx for meta so last_run_at is preserved if the entry already exists.
    """
    with SyncSessionLocal() as session:
        configs = session.execute(select(SystemConfig)).scalars().all()
        config_map = {row.key: row.value for row in configs}

    for worker_key, task_name in WORKER_TASK_MAP.items():
        db_key = f"poll_interval_{worker_key}"
        interval_seconds = float(config_map.get(db_key, 60))  # fallback if seed failed
        beat_name = BEAT_NAME_MAP[worker_key]

        entry = RedBeatSchedulerEntry(
            name=beat_name,
            task=task_name,
            schedule=celery_schedule(interval_seconds),
            app=celery_app,
        )
        entry.save()


if __name__ == "__main__":
    bootstrap_beat_schedule()
```

### Pattern 3: Seed Intervals on API Startup

Extend `seed.py` (or the lifespan hook in `main.py`) to insert interval rows on first boot. Mirrors exact pattern of admin user seed: check-exists, insert-if-missing.

```python
# Added to seed.py (or as a separate seed_intervals() function called from seed())
# Source: analysis of existing seed.py pattern

from app.core.config import settings

INTERVAL_DEFAULTS = {
    "poll_interval_prophetx":           str(settings.POLL_INTERVAL_PROPHETX),   # 300
    "poll_interval_sports_data":        str(settings.POLL_INTERVAL_SPORTS_DATA), # 30
    "poll_interval_odds_api":           str(settings.POLL_INTERVAL_ODDS_API),    # 600
    "poll_interval_sports_api":         str(settings.POLL_INTERVAL_SPORTS_API),  # 1800
    "poll_interval_espn":               str(settings.POLL_INTERVAL_ESPN),        # 600
    "poll_interval_critical_check":     "30",                                    # lowered default
    # Minimum floors (DB-configurable per locked decision)
    "poll_interval_prophetx_min":       "60",
    "poll_interval_sports_data_min":    "15",
    "poll_interval_odds_api_min":       "600",
    "poll_interval_sports_api_min":     "600",
    "poll_interval_espn_min":           "60",
    "poll_interval_critical_check_min": "15",
}

def seed_intervals(session):
    for key, default_value in INTERVAL_DEFAULTS.items():
        existing = session.execute(
            select(SystemConfig).where(SystemConfig.key == key)
        ).scalar_one_or_none()
        if existing is None:
            session.add(SystemConfig(
                key=key,
                value=default_value,
                description=f"Poll interval config — seeded from env/defaults",
            ))
    session.commit()
```

### Pattern 4: PATCH Endpoint Interval Validation + Redis Update

Extend the existing `update_config` handler to detect interval keys and apply two checks: (1) parse as integer, (2) compare against minimum, (3) update RedBeat entry in Redis after DB commit.

```python
# Extended logic in app/api/v1/config.py
# Source: analysis of existing config.py pattern + redbeat schedulers.py

from fastapi import HTTPException
from celery.schedules import schedule as celery_schedule
from redbeat import RedBeatSchedulerEntry
from app.workers.celery_app import celery_app

INTERVAL_KEY_TO_BEAT_NAME = {
    "poll_interval_prophetx":      "poll-prophetx",
    "poll_interval_sports_data":   "poll-sports-data",
    "poll_interval_odds_api":      "poll-odds-api",
    "poll_interval_sports_api":    "poll-sports-api",
    "poll_interval_espn":          "poll-espn",
    "poll_interval_critical_check":"poll-critical-check",
}

INTERVAL_KEY_TO_TASK = {
    "poll_interval_prophetx":      "app.workers.poll_prophetx.run",
    "poll_interval_sports_data":   "app.workers.poll_sports_data.run",
    "poll_interval_odds_api":      "app.workers.poll_odds_api.run",
    "poll_interval_sports_api":    "app.workers.poll_sports_api.run",
    "poll_interval_espn":          "app.workers.poll_espn.run",
    "poll_interval_critical_check":"app.workers.poll_critical_check.run",
}

async def _validate_and_apply_interval(key: str, new_value: str, session: AsyncSession):
    """Validate an interval update and propagate to RedBeat if valid.

    Raises HTTP 422 if:
    - new_value is not a positive integer
    - new_value is below the per-worker minimum in DB

    After DB update, writes the new schedule to RedBeat so Beat picks
    it up on its next tick (~5s).
    """
    # Parse
    try:
        new_seconds = int(new_value)
        if new_seconds <= 0:
            raise ValueError
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"poll interval must be a positive integer (seconds), got: {new_value!r}"
        )

    # Enforce minimum from DB
    min_key = f"{key}_min"
    min_row = await session.execute(
        select(SystemConfig).where(SystemConfig.key == min_key)
    )
    min_row = min_row.scalar_one_or_none()
    if min_row is not None:
        min_seconds = int(min_row.value)
        if new_seconds < min_seconds:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"poll interval for {key!r} must be at least {min_seconds}s "
                    f"(got {new_seconds}s). Minimum enforced to prevent API abuse."
                )
            )

    # After DB commit (in caller), update RedBeat
    # Runs synchronously — RedBeat uses sync Redis client
    beat_name = INTERVAL_KEY_TO_BEAT_NAME.get(key)
    task_name = INTERVAL_KEY_TO_TASK.get(key)
    if beat_name and task_name:
        _update_redbeat_entry(beat_name, task_name, new_seconds)


def _update_redbeat_entry(beat_name: str, task_name: str, seconds: int) -> None:
    """Write updated interval to existing RedBeat entry, preserving last_run_at."""
    from redbeat.schedulers import RedBeatSchedulerEntry, get_redis
    redis_key = RedBeatSchedulerEntry.generate_key(celery_app, beat_name)
    try:
        # Load existing entry to preserve last_run_at
        entry = RedBeatSchedulerEntry.from_key(redis_key, app=celery_app)
        entry.schedule = celery_schedule(seconds)
    except KeyError:
        # Entry doesn't exist yet (first boot before bootstrap) — create it
        entry = RedBeatSchedulerEntry(
            name=beat_name,
            task=task_name,
            schedule=celery_schedule(seconds),
            app=celery_app,
        )
    entry.save()
```

**Critical note on `_update_redbeat_entry` being sync in an async handler:** RedBeat uses a sync `StrictRedis` client (`get_redis()` returns sync connection). Calling `entry.save()` from an async FastAPI handler is safe as long as it's a brief synchronous call (no I/O wait inside async context). The alternative is `asyncio.get_event_loop().run_in_executor(None, _update_redbeat_entry, ...)`. Given the simplicity and brevity of the save operation, direct sync call is acceptable; document it explicitly.

### Pattern 5: Beat Container Bootstrap Command

Modify the Beat service command to run the bootstrap before starting Beat:

```yaml
# docker-compose.yml beat service
command: >
  bash -c "python -m app.workers.beat_bootstrap && celery -A app.workers.celery_app beat --scheduler redbeat.RedBeatScheduler --loglevel=info"
```

This ensures DB-derived intervals are in Redis before Beat starts its first tick. Beat no longer has a `beat_schedule` dict to fall back to (it's removed from `celery_app.py`), so it reads all schedules from Redis only.

### Anti-Patterns to Avoid

- **Keeping `beat_schedule` dict in `celery_app.py` alongside DB bootstrap:** Even with bootstrap running first, if `beat_schedule` exists, RedBeat's `setup_schedule()` will call `update_from_dict()` on startup and overwrite the DB-derived intervals with code defaults. The dict must be completely removed.
- **Using `entry.reschedule()` to update intervals:** `reschedule()` only updates `last_run_at` and the sorted-set score; it does not update the interval. Use `entry.schedule = celery_schedule(seconds); entry.save()` instead.
- **Reading interval from DB inside each poll task:** The task should not query the DB for its own interval — that couples task logic to scheduling config. The interval lives in Beat/Redis, not the task.
- **Using async DB session in beat_bootstrap.py:** Bootstrap runs in Beat container which has no async event loop set up; use `SyncSessionLocal` (already used in seed.py and all poll workers).
- **Not calling `celery_app.conf.update()` with empty `beat_schedule`:** If the key is completely absent, RedBeat may use its `statics_key` cleanup logic to remove previously-static entries. Safest is to either explicitly set `beat_schedule={}` or remove the `beat_schedule` key from `conf.update()`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Interval persistence in Redis | Custom Redis hash structure | `RedBeatSchedulerEntry.save()` | RedBeat's format is required — Beat reads `definition` and `meta` fields of specific hash structure; custom formats will be ignored |
| Beat entry lookups | Direct `redis.hget()` calls | `RedBeatSchedulerEntry.from_key()` | Handles JSON decoding, `last_run_at` preservation, and sorted-set score update atomically |
| Min/max validation | Custom range-check middleware | Inline validation in PATCH handler | Project already has localized validation logic; no middleware layer needed at this scale |

**Key insight:** RedBeat is a thin wrapper around Redis hashes. Its entire API surface (relevant to this phase) is `save()`, `from_key()`, and `generate_key()`. Don't replicate its Redis schema manually.

## Common Pitfalls

### Pitfall 1: `beat_schedule` dict silently overwrites DB intervals on restart

**What goes wrong:** Even if the DB-bootstrap runs and writes correct intervals to Redis, Beat's `setup_schedule()` calls `update_from_dict(self.app.redbeat_conf.schedule)` — which reads from `beat_schedule` — and overwrites every entry in Redis with code-default intervals. Restart reverts all operator changes.

**Why it happens:** RedBeat was designed to layer DB-only dynamic entries on top of a static `beat_schedule`. The static entries are always authoritative on restart. This is documented behavior, not a bug.

**How to avoid:** Remove `beat_schedule` entirely from `celery_app.conf.update()`. After removal, `app.redbeat_conf.schedule` returns `{}`, so `update_from_dict` does nothing. All entries come exclusively from Redis (written by the bootstrap).

**Warning signs:** After a Beat restart, intervals snap back to env-var values despite DB having different values.

### Pitfall 2: `setup_schedule()` cleans up "removed static entries"

**What goes wrong:** RedBeat tracks which entry names were in `beat_schedule` last time in a Redis set (`redbeat::statics`). On startup, it computes the difference between the previous static names and the current `beat_schedule` keys. Entries in the difference are deleted from Redis. If `beat_schedule` is emptied, RedBeat may delete the bootstrap entries written just before Beat starts.

**Why it happens:** The `setup_schedule()` cleanup loop runs before the tick loop. Bootstrap writes entries, then Beat startup deletes them because they appear to be "removed statics."

**How to avoid:** Verify `setup_schedule()` behavior with `beat_schedule={}`. Based on source code analysis (lines 432–449 in schedulers.py): `previous` is the set of names previously stored in `statics_key`; `removed = previous.difference(self.app.redbeat_conf.schedule.keys())`. With `beat_schedule={}`, `schedule.keys()` is empty, so `removed = previous` — **all previously-static entries are deleted**.

The correct solution is one of:
  - Option A: Run bootstrap AFTER Beat has started and cleared statics (impractical — no hook).
  - Option B: Never register our entries as statics in the first place. Use a different Beat entry name prefix OR write entries to Redis without going through `update_from_dict`. Since `beat_bootstrap.py` calls `entry.save()` directly (not through `update_from_dict`), these entries are NOT added to `statics_key`. Beat's statics cleanup only removes names that ARE in `statics_key`. Bootstrap entries survive.
  - Option C: The bootstrap script clears `statics_key` in Redis before writing entries, so `previous` is empty and `removed` is empty.

**Recommendation:** Option B is already the natural behavior — `beat_bootstrap.py` calling `entry.save()` directly does NOT call `client.sadd(statics_key, ...)`. Confirm this by re-reading `update_from_dict()` vs `save()`: `save()` only writes to the entry hash and the schedule sorted set. The `statics_key` sadd happens in `setup_schedule()` / `update_from_dict()` after `entry.save()` — not inside `save()` itself. Boot sequence: (1) bootstrap writes entries without touching statics_key, (2) Beat starts, (3) `setup_schedule()` deletes entries in `statics_key` that are no longer in `beat_schedule` — but since bootstrap entries were never in `statics_key`, they are not deleted.

**Warning signs:** After Beat starts, `redis-cli KEYS "redbeat:*"` shows no task entries.

### Pitfall 3: Importing `celery_app` from FastAPI process triggers worker task registration

**What goes wrong:** The `_update_redbeat_entry` helper in `config.py` imports `celery_app`. This is flagged in STATE.md as a risk — importing `celery_app` in the API process may trigger side effects (worker registration, signal handlers).

**Why it happens:** Celery's task decorator registers tasks at import time. In some configurations, importing the Celery app in a non-worker context triggers `app_or_default()` initialization.

**How to avoid:** The project already imports `celery_app` in the Beat bootstrap (which is a separate process). For the FastAPI API process, the safest approach is to call `_update_redbeat_entry` only after the DB commit succeeds. Use `get_redis()` from `redbeat.schedulers` directly (which takes `app=celery_app`) rather than a full Celery app init. The import in the config router is a deferred import inside the function body (same pattern used in `poll_prophetx.py` for `send_alerts`), avoiding circular imports. Confirm during implementation by checking if the API process logs any task registration output after the import.

**Warning signs:** API startup logs show "Received task:" or "Registered tasks:" output from worker modules.

### Pitfall 4: `RedBeatSchedulerEntry` `schedule` parameter requires a Celery schedule object

**What goes wrong:** Passing a raw `float` or `int` as the `schedule` parameter to `RedBeatSchedulerEntry` fails or produces an unserializable object.

**Why it happens:** `RedBeatJSONEncoder` in `redbeat/decoder.py` handles `celery.schedules.schedule` objects specifically. A plain number is not recognized.

**How to avoid:** Always wrap seconds in `celery.schedules.schedule(seconds)`:
```python
from celery.schedules import schedule as celery_schedule
entry = RedBeatSchedulerEntry(
    name="poll-prophetx",
    task="app.workers.poll_prophetx.run",
    schedule=celery_schedule(300.0),  # NOT just 300.0
    app=celery_app,
)
```

**Warning signs:** `json.dumps` error in Beat logs on first tick, or entry loaded from Redis has no schedule.

### Pitfall 5: Sync RedBeat call in async FastAPI context

**What goes wrong:** `get_redis()` from RedBeat creates a synchronous `StrictRedis` connection. Calling `entry.save()` (which calls `get_redis()`) inside an async FastAPI route handler blocks the event loop during the Redis I/O operations.

**Why it happens:** RedBeat was built for the synchronous Celery/Beat process, not async web frameworks.

**How to avoid:** The blocking window is small (one pipeline with 3 Redis commands). For this use case, wrapping in `asyncio.get_event_loop().run_in_executor(None, _update_redbeat_entry, ...)` is the correct async-safe approach. Alternatively, since the async Redis client is already available (`get_redis_client()` from `app/db/redis.py`), a standalone helper that writes the RedBeat hash fields directly via async redis is viable — but requires manually constructing the JSON that RedBeat expects, which is coupling to internal format. Prefer `run_in_executor` to keep RedBeat as the interface.

**Warning signs:** API response latency spikes on PATCH /config/{interval_key} calls; event loop starvation logs.

## Code Examples

### RedBeatSchedulerEntry.save() — verified from source

```python
# Source: redbeat/schedulers.py lines 340-359
def save(self):
    definition = {
        'name': self.name,
        'task': self.task,
        'args': self.args,
        'kwargs': self.kwargs,
        'options': self.options,
        'schedule': self.schedule,
        'enabled': self.enabled,
    }
    meta = {
        'last_run_at': self.last_run_at,
    }
    with get_redis(self.app).pipeline() as pipe:
        pipe.hset(self.key, 'definition', json.dumps(definition, cls=RedBeatJSONEncoder))
        pipe.hsetnx(self.key, 'meta', json.dumps(meta, cls=RedBeatJSONEncoder))  # hsetnx: won't overwrite existing meta
        pipe.zadd(self.app.redbeat_conf.schedule_key, {self.key: self.score})
        pipe.execute()
```

Key insight: `hsetnx` for meta means `last_run_at` is preserved when an existing entry is updated via `save()`. The `definition` uses `hset` (overwrite), which is what replaces the interval.

### from_key() — preserve last_run_at when updating interval

```python
# Source: redbeat/schedulers.py lines 287-305
# Correct pattern for updating an existing entry's interval:

redis_key = RedBeatSchedulerEntry.generate_key(celery_app, "poll-prophetx")
try:
    entry = RedBeatSchedulerEntry.from_key(redis_key, app=celery_app)
    # entry.last_run_at is now set from Redis meta
    entry.schedule = celery_schedule(new_seconds)
    entry.save()  # hset definition (new interval), hsetnx meta (preserves last_run_at)
except KeyError:
    # Entry doesn't exist — create fresh
    entry = RedBeatSchedulerEntry(
        name="poll-prophetx",
        task="app.workers.poll_prophetx.run",
        schedule=celery_schedule(new_seconds),
        app=celery_app,
    )
    entry.save()
```

Wait — on re-examination: `save()` uses `hsetnx` for meta. But `from_key()` loads `last_run_at` into `entry.last_run_at`. When we call `entry.save()` after modifying the schedule, the meta dict written is `{'last_run_at': self.last_run_at}` — but with `hsetnx`, this only sets if the key doesn't exist. Since the meta key already exists in Redis, `hsetnx` is a no-op. The previously-stored `last_run_at` remains in Redis unchanged. This is the correct and safe behavior for interval updates.

### Verifying RedBeat key names in live Redis

Per STATE.md "Before Phase 5" todo: run this against live Redis before writing bootstrap code:

```bash
redis-cli KEYS "redbeat:*"
# Expected output:
# redbeat::lock
# redbeat::schedule
# redbeat::statics
# redbeat:poll-prophetx
# redbeat:poll-sports-data
# redbeat:poll-odds-api
# redbeat:poll-sports-api
# redbeat:poll-espn
# redbeat:poll-critical-check

redis-cli HGETALL "redbeat:poll-prophetx"
# Shows: definition (JSON with schedule interval) and meta (last_run_at)
```

This confirms entry name format (`redbeat:` prefix + beat entry name) and verifies the bootstrap will use the correct key names.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `beat_schedule` dict with env vars | DB-seeded, RedBeat-bootstrapped intervals | Phase 5 | Beat restart no longer reverts operator changes |
| `poll_critical_check` hardcoded at 60s | Configurable via `poll_interval_critical_check` DB key | Phase 5 | Critical check cadence tunable without code deploy |
| PATCH /config/{key} writes any string | PATCH validates interval keys against per-worker minimums | Phase 5 | FREQ-02: API abuse prevention |

**No deprecated approaches in this phase** — all changes are additive to existing patterns.

## Open Questions

1. **Statics cleanup behavior with `beat_schedule={}`**
   - What we know: `setup_schedule()` deletes entries from `statics_key` that were previously static but are no longer in `beat_schedule`. Bootstrap entries are never added to `statics_key` (they bypass `update_from_dict`).
   - What's unclear: Whether removing `beat_schedule` entirely (vs. setting it to `{}`) behaves differently in the statics cleanup path.
   - Recommendation: Set `beat_schedule={}` explicitly in `celery_app.conf.update()` rather than removing the key. Then run `redis-cli SMEMBERS "redbeat::statics"` after first boot to confirm bootstrap entries are absent from statics. If they appear there, add a `redis.srem()` call to bootstrap to clean the statics set.

2. **RedBeat entry names: must match existing names in Redis**
   - What we know: Live Redis currently has entries created by the existing `beat_schedule` dict. Entry names are the dict keys (`poll-prophetx`, `poll-sports-data`, etc.) prefixed with `redbeat:`.
   - What's unclear: Whether the bootstrap must use exactly these names or can use new ones. If different names are used, old entries remain in the sorted set and fire duplicate tasks.
   - Recommendation: The STATE.md todo explicitly says "run `redis-cli KEYS 'redbeat:*'` to confirm exact Beat key names before writing `RedBeatSchedulerEntry.from_key()`." Do this as Wave 0 task 1. Use exactly the names found. If old names exist but won't be bootstrapped, delete them via `entry.delete()`.

3. **Import safety: `celery_app` in API process**
   - What we know: STATE.md flags this as unconfirmed risk. Poll workers already import `celery_app` for task registration — that's expected in the worker process.
   - What's unclear: Whether importing `celery_app` in the FastAPI process (for `_update_redbeat_entry`) causes any registrations or side effects.
   - Recommendation: Test by adding a deferred import inside `_update_redbeat_entry` function body (not at module level). If side effects occur, refactor to write RedBeat Redis keys directly using the async Redis client.

## Validation Architecture

`nyquist_validation` is not set in `.planning/config.json` (key absent). Skipping formal validation section.

Manual verification steps that serve the same purpose:

**FREQ-03 verification:**
1. Set an interval via PATCH: `curl -X PATCH /api/v1/config/poll_interval_espn -d '{"value":"999"}'`
2. Restart Beat container: `docker compose restart beat`
3. Check interval survived: `redis-cli HGET "redbeat:poll-espn" definition | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['schedule'])"`
4. Confirm it shows 999 seconds, not the env-var default (600).

**FREQ-02 verification:**
1. PATCH with value below minimum: `curl -X PATCH /api/v1/config/poll_interval_espn -d '{"value":"30"}'`
2. Confirm HTTP 422 response with message mentioning 60s minimum.
3. Confirm DB still has previous value (not 30).

## Sources

### Primary (HIGH confidence)

- RedBeat source code at `/Users/doug/Prophet API Monitoring/backend/.venv/lib/python3.12/site-packages/redbeat/schedulers.py` — `RedBeatSchedulerEntry`, `RedBeatScheduler.setup_schedule()`, `update_from_dict()`, `save()`, `from_key()` analyzed directly. Version: celery-redbeat 2.3.3.
- Existing project source code — `celery_app.py`, `seed.py`, `config.py`, `main.py`, `sync_session.py`, `redis.py` analyzed directly. Patterns are consistent and well-established.

### Secondary (MEDIUM confidence)

- STATE.md pending todos — explicitly calls out live Redis key name verification and import safety check as pre-Phase-5 tasks. Research confirms both are real risks.

### Tertiary (LOW confidence)

- No WebSearch was required — all findings come from direct source analysis of installed packages and project code.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries are already installed; APIs verified from source
- Architecture: HIGH — patterns derived directly from RedBeat source code, not documentation
- Pitfalls: HIGH — Pitfalls 1 and 2 verified by reading `setup_schedule()` and `save()` source; Pitfalls 3-5 verified from project patterns

**Research date:** 2026-03-02
**Valid until:** 2026-04-02 (stable library — celery-redbeat 2.3.3 is installed; changes would require a package update)
