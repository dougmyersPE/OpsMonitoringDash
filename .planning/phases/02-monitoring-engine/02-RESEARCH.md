# Phase 2: Monitoring Engine - Research

**Researched:** 2026-02-25
**Domain:** Event ID matching (fuzzy + temporal), distributed locking with Redis, Celery polling workers, idempotent status-update actions, append-only audit log with PostgreSQL REVOKE, liquidity monitoring
**Confidence:** HIGH for core patterns; MEDIUM for ProphetX write API; LOW for ProphetX status enum values (must be confirmed from live API)

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CORE-03 | Event ID matching layer links ProphetX events to SportsDataIO games by sport + teams + scheduled start time, with confidence scoring (≥0.90 required for auto-actions; below threshold flagged for manual review) | rapidfuzz token_sort_ratio for team names + start time window; EventIDMapping table; Redis cache of confirmed matches; confidence algorithm documented in Architecture Patterns |
| SYNC-01 | System auto-updates ProphetX event status Upcoming→Live→Ended when real-world game state changes (only when match confidence ≥0.90 and distributed lock acquired) | redis-py Lock (sync, non-blocking) in Celery worker; idempotent task pattern with before-state check; ProphetX `/mm/update_event_status` endpoint (unconfirmed — see Open Questions) |
| SYNC-02 | System detects postponed/cancelled events and flags them with alert + dashboard indicator; manual operator resolution required | SportsDataIO statuses Postponed/Canceled confirmed; flag-only action writes to audit log + notification; no ProphetX write call |
| SYNC-03 | Operator can manually trigger status sync for any event via the dashboard (POST endpoint) | `POST /api/v1/events/{id}/sync-status` endpoint; calls the same idempotent action worker path as automated sync |
| LIQ-01 | Admin can configure per-market liquidity thresholds with a global default fallback | system_config key `default_min_liquidity`; per-market threshold on Market model with None = use global fallback |
| LIQ-02 | System detects when market liquidity falls below configured threshold and alerts (no auto top-up in v1) | Liquidity monitor in poll_prophetx task; compare market.current_liquidity vs threshold; write to notifications table + enqueue send_alerts stub |
| AUDIT-01 | All automated and manual actions logged append-only: timestamp, actor, entity, action type, before/after state — no deletions permitted | audit_log table; PostgreSQL REVOKE UPDATE, DELETE, TRUNCATE FROM app_user; SQLAlchemy INSERT-only ORM model |
| AUDIT-02 | Operator can view the full audit log in the dashboard with basic pagination | `GET /api/v1/audit-log?page=1&per_page=50` endpoint; ORDER BY timestamp DESC; AsyncSession query |
</phase_requirements>

---

## Summary

Phase 2 is the core value of the entire system. It builds on Phase 1's skeleton (Celery Beat + API clients + PostgreSQL) to produce a continuously running monitoring engine with three primary behaviors: matching ProphetX events to SportsDataIO games with confidence scoring, detecting status mismatches and liquidity breaches on every 30-second poll cycle, and executing idempotent write actions protected by distributed locks with every action written to an append-only audit log.

The hardest technical problem is the event ID matching layer (CORE-03). ProphetX uses its own internal event IDs; SportsDataIO uses completely different identifiers. The matching strategy is multi-factor: fuzzy team name matching (rapidfuzz `token_sort_ratio` ≥ 85 for home + away teams) combined with sport equality and a ±15-minute start time window, producing a composite confidence score. A Redis cache of confirmed matches eliminates redundant fuzzy computation on subsequent polls. An `event_id_mappings` table persists confirmed matches and flags low-confidence ones for manual review.

The distributed lock (SYNC-01) uses redis-py's built-in `Lock` class in non-blocking mode within the Celery sync worker. The lock key is `lock:update_event_status:{prophetx_event_id}` with a 60-second TTL. If two workers detect the same mismatch simultaneously, one acquires the lock and proceeds; the other returns immediately without duplicate action. The action worker checks the current ProphetX status before writing (idempotency guard) — if the status is already what we'd set it to, the task exits cleanly without an API call. Every action — automated or manual — is written to the audit log before the API call returns, and the DB user is explicitly denied UPDATE/DELETE/TRUNCATE on the `audit_log` table via PostgreSQL REVOKE.

**Primary recommendation:** Build CORE-03 (event matcher) first and validate confidence scores against real ProphetX + SportsDataIO data before wiring the action workers. The 0.90 threshold is a hypothesis — it must be calibrated against actual data. Until ProphetX's event write endpoint is confirmed, the update_event_status task can be stubbed to log-only and switched to live with a single line change.

---

## Standard Stack

### Core — Phase 2 Additions

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| rapidfuzz | 3.14.3 | Fuzzy string matching for team/event name comparison | C++ implementation, 5-100x faster than thefuzz; `token_sort_ratio` handles word-order variants; scores 0–100; Python 3.10+ |
| redis-py | 5.x (already installed) | Distributed lock via `redis.lock.Lock`; Redis cache for matches | Built-in Lock class handles SET NX PX + Lua-script release; no extra dependency needed |
| SQLAlchemy 2.x | 2.x (already installed) | New ORM models: Event, Market, EventIDMapping, AuditLog, Notification | Already in pyproject.toml; Phase 2 adds 4 new models + Alembic migration |

### Supporting — Phase 2

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| rapidfuzz | 3.14.3 | Fuzzy name matching (event matcher only) | Only in `app/monitoring/event_matcher.py`; do NOT use in hot path of polling loop |
| (no new libraries required beyond rapidfuzz) | | | |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| rapidfuzz `token_sort_ratio` | `WRatio` | WRatio is a weighted hybrid — slightly more accurate for edge cases but slower; token_sort_ratio is sufficient and more predictable for team-name matching |
| redis-py built-in Lock | celery-once or celery_singleton | celery-once prevents duplicate task scheduling; for this use case we want to prevent duplicate *execution* of a task with the same event_id — built-in redis-py Lock is simpler and more transparent |
| Manual SQLAlchemy INSERT-only | postgresql-audit library | postgresql-audit adds a separate `activity` table with triggers — overkill for a simple append-only log; hand-building with REVOKE is cleaner and verifiable |

**Installation (only new dependency):**
```bash
cd /Users/doug/Prophet\ API\ Monitoring/backend
uv add rapidfuzz
```

---

## Architecture Patterns

### Recommended Project Structure — Phase 2 Additions

```
backend/app/
├── monitoring/                  # NEW — Phase 2 monitoring engine
│   ├── __init__.py
│   ├── event_matcher.py         # EventMatcher class: fuzzy match + confidence scoring + Redis cache
│   ├── mismatch_detector.py     # compare_statuses(): ProphetX status → SportsDataIO status mapping
│   └── liquidity_monitor.py     # check_liquidity(): compare market liquidity vs threshold
├── workers/
│   ├── celery_app.py            # EXISTING — add update_event_status + send_alerts to include
│   ├── poll_prophetx.py         # REPLACE stub — full poll: fetch events + markets, write DB, detect liquidity
│   ├── poll_sports_data.py      # REPLACE stub — full poll: fetch games by date, write DB, detect mismatches
│   ├── update_event_status.py   # NEW — idempotent action: acquire lock, check state, call ProphetX API, write audit
│   └── send_alerts.py           # NEW — stub: log alert; Phase 3 adds Slack webhook
├── models/
│   ├── user.py                  # EXISTING
│   ├── config.py                # EXISTING
│   ├── event.py                 # NEW — Event model (prophetx_event_id, statuses, match fields)
│   ├── market.py                # NEW — Market model (liquidity, threshold, event FK)
│   ├── event_id_mapping.py      # NEW — EventIDMapping (px_event_id ↔ sdio_game_id, confidence, sport)
│   ├── audit_log.py             # NEW — AuditLog (append-only; no update/delete from app user)
│   └── notification.py          # NEW — Notification (for Phase 3 SSE + in-app center; created here)
├── api/v1/
│   ├── events.py                # NEW — GET /events, POST /events/{id}/sync-status
│   ├── markets.py               # NEW — GET /markets, PATCH /markets/{id}/config
│   └── audit.py                 # NEW — GET /audit-log (paginated)
└── schemas/
    ├── event.py                 # NEW — EventResponse, EventListResponse
    ├── market.py                # NEW — MarketResponse, MarketConfigUpdate
    └── audit.py                 # NEW — AuditLogEntry, AuditLogPage
```

```
alembic/versions/
├── 001_initial_schema.py        # EXISTING — users, system_config
└── 002_monitoring_schema.py     # NEW — events, markets, event_id_mappings, audit_log, notifications
                                 #       + REVOKE statements for audit_log
```

### Pattern 1: Event ID Matching with Confidence Scoring

**What:** EventMatcher computes a composite confidence score from three factors: home team name similarity, away team name similarity, and start time proximity. A match requires confidence ≥ 0.90 to be "confirmed". Below 0.90 it is flagged for manual review. Confirmed matches are cached in Redis (key: `match:px:{px_event_id}`) with a 24-hour TTL to avoid re-running fuzzy matching on every 30-second poll.

**When to use:** Called once per ProphetX event per poll, only when no Redis cache hit exists for that event's ID.

**Algorithm:**
```python
# Source: research-derived algorithm; rapidfuzz docs at https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html
from rapidfuzz import fuzz
from datetime import datetime, timedelta

TEAM_MATCH_WEIGHT = 0.35        # home team contribution
TEAM_MATCH_WEIGHT_AWAY = 0.35   # away team contribution
TIME_WINDOW_WEIGHT = 0.30       # start time proximity contribution
CONFIDENCE_THRESHOLD = 0.90     # minimum to trigger auto-action
TIME_WINDOW_MINUTES = 15        # ± minutes for start time match

def compute_confidence(
    px_home: str, px_away: str, px_start: datetime,
    sdio_home: str, sdio_away: str, sdio_start: datetime,
    px_sport: str, sdio_sport: str,
) -> float:
    """Returns confidence in [0.0, 1.0]. 0.0 if sports don't match."""
    if px_sport.upper() != sdio_sport.upper():
        return 0.0

    # Normalize: lowercase, strip punctuation
    def norm(s: str) -> str:
        return s.lower().strip()

    home_score = fuzz.token_sort_ratio(norm(px_home), norm(sdio_home)) / 100.0
    away_score = fuzz.token_sort_ratio(norm(px_away), norm(sdio_away)) / 100.0

    # Time proximity: full score if within window, linear decay to 0 at 2x window
    delta_minutes = abs((px_start - sdio_start).total_seconds()) / 60
    if delta_minutes <= TIME_WINDOW_MINUTES:
        time_score = 1.0
    elif delta_minutes <= TIME_WINDOW_MINUTES * 2:
        time_score = 1.0 - ((delta_minutes - TIME_WINDOW_MINUTES) / TIME_WINDOW_MINUTES)
    else:
        time_score = 0.0

    return (
        home_score * TEAM_MATCH_WEIGHT
        + away_score * TEAM_MATCH_WEIGHT_AWAY
        + time_score * TIME_WINDOW_WEIGHT
    )
```

**Redis cache pattern:**
```python
# In event_matcher.py — called by poll_sports_data after fetching SDIO games
import json
from redis import Redis  # sync redis for Celery worker context

MATCH_CACHE_TTL = 86400  # 24 hours

def get_cached_match(redis_client: Redis, px_event_id: str) -> dict | None:
    raw = redis_client.get(f"match:px:{px_event_id}")
    return json.loads(raw) if raw else None

def cache_match(redis_client: Redis, px_event_id: str, match: dict) -> None:
    redis_client.setex(
        f"match:px:{px_event_id}",
        MATCH_CACHE_TTL,
        json.dumps(match),
    )
```

### Pattern 2: Distributed Lock in Celery Worker (Sync)

**What:** The sync redis-py Lock prevents duplicate status updates when two workers detect the same mismatch simultaneously. Non-blocking acquire — if lock is already held, the worker logs "lock not acquired" and returns immediately. TTL (timeout) of 60 seconds ensures lock auto-releases if the worker crashes mid-task.

**When to use:** Any task that writes to ProphetX API. Lock key includes the ProphetX event ID so concurrent updates to *different* events don't block each other.

**Example:**
```python
# Source: redis-py lock.py — https://github.com/redis/redis-py/blob/master/redis/lock.py
# and verified from Redis official docs: https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/
import redis
import structlog

log = structlog.get_logger()

def acquire_event_lock(redis_client: redis.Redis, event_id: str, timeout: int = 60):
    """Returns a Lock object. Caller must check lock.acquire() return value."""
    return redis_client.lock(
        f"lock:update_event_status:{event_id}",
        timeout=timeout,        # auto-release TTL in seconds
        blocking=False,         # non-blocking: return False immediately if not acquired
    )

# In update_event_status.py task:
@celery_app.task(name="app.workers.update_event_status.run", bind=True, max_retries=3)
def run(self, event_id: str, target_status: str, actor: str = "system"):
    from app.db.redis import get_sync_redis
    from app.db.sync_session import SyncSessionLocal
    from app.models.event import Event

    redis_client = get_sync_redis()
    lock = redis_client.lock(
        f"lock:update_event_status:{event_id}",
        timeout=60,
        blocking=False,
    )
    acquired = lock.acquire()
    if not acquired:
        log.info("update_event_status_lock_not_acquired", event_id=event_id)
        return  # Another worker is handling this — exit cleanly

    try:
        with SyncSessionLocal() as session:
            event = session.get(Event, event_id)
            if event is None:
                log.warning("update_event_status_event_not_found", event_id=event_id)
                return
            # Idempotency guard: check if already at target status
            if event.prophetx_status == target_status:
                log.info("update_event_status_already_at_target",
                         event_id=event_id, status=target_status)
                return

            before_state = event.prophetx_status
            # Call ProphetX API here (see Open Questions for endpoint confirmation)
            _call_prophetx_update_status(event.prophetx_event_id, target_status)

            # Update local DB
            event.prophetx_status = target_status
            session.commit()

            # Write audit log
            _write_audit_log(session, actor=actor, entity_id=event_id,
                             action_type="status_update",
                             before_state=before_state, after_state=target_status)
    except Exception as exc:
        log.error("update_event_status_failed", event_id=event_id, error=str(exc))
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    finally:
        try:
            lock.release()
        except Exception:
            pass  # Lock may have expired — that's acceptable
```

### Pattern 3: Status Mapping — SportsDataIO → ProphetX

**What:** SportsDataIO game statuses must be mapped to ProphetX event statuses. This mapping lives in `monitoring/mismatch_detector.py` as a pure function so it can be unit tested independently of network calls.

**SportsDataIO statuses (confirmed from official docs):**
- `Scheduled` → ProphetX "upcoming" equivalent
- `InProgress` → ProphetX "live" equivalent
- `Final`, `F/OT`, `F/SO` → ProphetX "ended" equivalent
- `Postponed` → Flag for manual review; no auto-action
- `Canceled` → Flag for manual review; no auto-action
- `Suspended`, `Delayed` → Flag for monitoring; no auto-action
- `Forfeit`, `NotNecessary` → Treat as Canceled

**ProphetX statuses (UNCONFIRMED — from PRD speculation and Medium article references):**
- PRD suggests: `"upcoming"`, `"live"`, `"ended"`, `"cancelled"`, `"suspended"` — must be confirmed
- Phase 1 sandbox verified connectivity but ProphetX status enum values were NOT confirmed in logs
- See Open Questions #1

**Example mapping function:**
```python
# monitoring/mismatch_detector.py

from enum import Enum

class SdioStatus(str, Enum):
    SCHEDULED = "Scheduled"
    IN_PROGRESS = "InProgress"
    FINAL = "Final"
    FINAL_OT = "F/OT"
    FINAL_SO = "F/SO"
    POSTPONED = "Postponed"
    CANCELED = "Canceled"
    SUSPENDED = "Suspended"
    DELAYED = "Delayed"
    FORFEIT = "Forfeit"
    NOT_NECESSARY = "NotNecessary"

# PROVISIONAL — must be updated after ProphetX status enum is confirmed
SDIO_TO_PX_STATUS = {
    "Scheduled":     "upcoming",   # UNCONFIRMED ProphetX value
    "InProgress":    "live",       # UNCONFIRMED ProphetX value
    "Final":         "ended",      # UNCONFIRMED ProphetX value
    "F/OT":          "ended",
    "F/SO":          "ended",
}

FLAG_ONLY_STATUSES = {"Postponed", "Canceled", "Suspended", "Delayed", "Forfeit", "NotNecessary"}

def get_expected_px_status(sdio_status: str) -> str | None:
    """Returns the expected ProphetX status, or None if flag-only (no auto-action)."""
    if sdio_status in FLAG_ONLY_STATUSES:
        return None
    return SDIO_TO_PX_STATUS.get(sdio_status)

def is_mismatch(px_status: str, sdio_status: str) -> bool:
    """True if ProphetX status does not match what we expect from SportsDataIO."""
    expected = get_expected_px_status(sdio_status)
    if expected is None:
        return False  # Flag-only — not an auto-correctable mismatch
    return px_status != expected
```

### Pattern 4: Append-Only Audit Log with PostgreSQL REVOKE

**What:** The `audit_log` table uses only INSERT operations from the application. The PostgreSQL role `prophet_monitor` (app DB user) is explicitly denied UPDATE, DELETE, and TRUNCATE on `audit_log`. This enforces append-only at the database level, not just application level — even a code bug cannot delete audit entries.

**When to use:** For every automated and manual action logged to `audit_log`.

**Alembic migration snippet:**
```python
# In 002_monitoring_schema.py upgrade():

# Create audit_log table
op.create_table(
    "audit_log",
    sa.Column("id", sa.UUID(), nullable=False),
    sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False,
              server_default=sa.text("now()"), index=True),
    sa.Column("action_type", sa.String(50), nullable=False),
    sa.Column("actor", sa.String(255), nullable=False),  # "system" or user email/id
    sa.Column("entity_type", sa.String(50), nullable=True),
    sa.Column("entity_id", sa.UUID(), nullable=True),
    sa.Column("before_state", sa.JSON(), nullable=True),
    sa.Column("after_state", sa.JSON(), nullable=True),
    sa.Column("result", sa.String(20), nullable=False, server_default="success"),
    sa.Column("error_message", sa.Text(), nullable=True),
    sa.Column("metadata", sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint("id"),
)
op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"])
op.create_index("ix_audit_log_entity_id", "audit_log", ["entity_id"])

# ENFORCE APPEND-ONLY: revoke UPDATE, DELETE, TRUNCATE from the app DB user
# This is a database-level enforcement that survives application bugs
op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM prophet_monitor")
# Note: replace 'prophet_monitor' with the value of settings.POSTGRES_USER
```

**SQLAlchemy model — INSERT only:**
```python
# models/audit_log.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, JSON, Text, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    before_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ORM-level guard: no update() or delete() methods should be called on this model.
    # Database-level enforcement via REVOKE is the primary control.
```

**Sync helper for Celery workers:**
```python
# In workers/update_event_status.py (and all other action workers)
def write_audit_log(session, *, actor: str, action_type: str, entity_type: str,
                    entity_id, before_state: dict | None, after_state: dict | None,
                    result: str = "success", error_message: str | None = None) -> None:
    entry = AuditLog(
        actor=actor,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        before_state=before_state,
        after_state=after_state,
        result=result,
        error_message=error_message,
    )
    session.add(entry)
    session.flush()  # flush immediately; commit is caller's responsibility
```

### Pattern 5: Celery Worker to FastAPI Endpoint Bridge (Manual Sync — SYNC-03)

**What:** The manual sync endpoint (`POST /api/v1/events/{id}/sync-status`) enqueues the same `update_event_status` Celery task that automated polling uses. This ensures the same idempotency guarantees, distributed lock, and audit logging apply to manual operator actions.

**Example:**
```python
# api/v1/events.py
from fastapi import APIRouter, Depends, HTTPException
from app.api.deps import require_role
from app.core.constants import RoleEnum
from app.workers.update_event_status import run as update_status_task

router = APIRouter(prefix="/events", tags=["events"])

@router.post("/{event_id}/sync-status",
             dependencies=[Depends(require_role(RoleEnum.operator, RoleEnum.admin))])
async def manual_sync_status(event_id: str, current_user: dict = Depends(get_current_user)):
    """Manually trigger a status sync for an event. Enqueues the same worker path as auto-sync."""
    # The worker reads current SDIO status from DB and calls ProphetX accordingly
    update_status_task.delay(
        event_id=event_id,
        target_status=None,          # None means: read current SDIO state from DB and derive
        actor=current_user["sub"],   # user ID as actor (vs "system" for automated)
    )
    return {"queued": True, "event_id": event_id}
```

### Pattern 6: Liquidity Threshold Resolution (LIQ-01)

**What:** Per-market threshold stored on the Market model as a nullable Decimal. When None, the system reads `default_min_liquidity` from `system_config`. This fallback logic is a single helper function shared by poll_prophetx and any future admin UI.

**Example:**
```python
# monitoring/liquidity_monitor.py
from decimal import Decimal
from app.models.market import Market
from app.db.sync_session import SyncSessionLocal

def get_effective_threshold(market: Market, session) -> Decimal:
    """Return market-specific threshold, falling back to global default."""
    if market.min_liquidity_threshold is not None:
        return market.min_liquidity_threshold
    # Read global default from system_config
    from sqlalchemy import select
    from app.models.config import SystemConfig
    row = session.execute(
        select(SystemConfig).where(SystemConfig.key == "default_min_liquidity")
    ).scalar_one_or_none()
    if row is None:
        return Decimal("0")  # No threshold = no alert (safe fallback)
    return Decimal(row.value)

def is_below_threshold(market: Market, session) -> bool:
    threshold = get_effective_threshold(market, session)
    return market.current_liquidity < threshold
```

### Anti-Patterns to Avoid

- **Running fuzzy matching inside the 30-second poll loop without caching:** rapidfuzz is fast but O(N×M) over all ProphetX events × all SDIO games adds up. Cache confirmed matches in Redis for 24 hours; re-run matching only on cache miss or when ProphetX event identity changes.
- **Using `asyncio.run()` inside Celery workers:** Celery workers are sync. Use the sync SQLAlchemy engine and sync redis-py client. Do not call `await` inside Celery task functions.
- **Using non-blocking lock and silently swallowing duplicate work:** If `lock.acquire()` returns False, log the skip explicitly so it's visible in monitoring — otherwise duplicate mismatch counts are hidden.
- **Writing audit log AFTER API call:** If the ProphetX API call succeeds but audit log INSERT fails, the action is unrecorded. Write audit log in the same transaction as the DB state update, before (or immediately after) the API call returns.
- **Deleting or updating audit_log rows from application code:** REVOKE prevents this at DB level but application code should never attempt it. No `session.delete()` on AuditLog; no `update()` queries against audit_log.
- **Storing ProphetX status enum values as free-text strings without a defined enum:** If ProphetX returns a status value you don't recognize, the mismatch detector silently fails. Validate against the known enum on ingest; log unknown values as warnings.
- **Querying SportsDataIO `GamesByDate` for only today:** Games near midnight can span two calendar dates. Query today AND tomorrow; cache results; dedup by game ID.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Fuzzy string matching | Levenshtein distance implementation | rapidfuzz | C++ implementation; handles token reordering with token_sort_ratio; battle-tested for sports name matching |
| Distributed lock | Custom Redis SETNX + TTL + ownership check | redis-py built-in Lock | Lock class handles random token ownership, Lua-script release (atomic check + delete), and lock extension; hand-rolling misses the ownership check |
| Task deduplication | Custom "already running" Redis flag | redis-py Lock + idempotency guard (before-state check) | Lock prevents concurrent execution; before-state check handles retry after crash; both together cover the full deduplication space |
| Append-only enforcement | Application-layer delete prevention | PostgreSQL REVOKE at DB level | Application bugs can bypass application-layer checks; REVOKE enforces at DB engine level |
| Status mapping logic | Inline conditionals in polling task | `mismatch_detector.py` pure functions | Pure functions are independently unit-testable; inline logic makes the poll task untestable in isolation |

**Key insight:** The distributed lock and idempotency guard are two separate concerns and both are needed. The lock prevents concurrent writes; the before-state check handles the case where a lock expires and the same task retries.

---

## Common Pitfalls

### Pitfall 1: ProphetX Status Enum Values Unconfirmed

**What goes wrong:** Phase 2 builds comparison logic against assumed ProphetX status values (`"upcoming"`, `"live"`, `"ended"`). When the live ProphetX API returns different values (`"UPCOMING"`, `"IN_PROGRESS"`, `"CLOSED"` — or anything else), all mismatch detection produces false positives or silently misses real mismatches.

**Why it happens:** Phase 1 verified connectivity to the ProphetX sandbox (`api-ss-sandbox.betprophet.co/partner`) but the test returned tournaments, not events with status values. STATE.md explicitly flags this as unconfirmed.

**How to avoid:** The first task in Plan 02-01 must call `ProphetXClient().get_events_raw()` on the sandbox, log the full response, and define the ProphetX status enum from the actual API response before writing any comparison logic. The status mapping in `mismatch_detector.py` must not be hardcoded until this is done.

**Warning signs:** Mismatch detector reports 100% mismatch rate or 0% mismatch rate on first run; `event.prophetx_status` values in DB contain values not in the defined enum.

### Pitfall 2: Event ID Matching Threshold 0.90 Is a Hypothesis

**What goes wrong:** The 0.90 confidence threshold (REQUIREMENTS.md CORE-03) was chosen before any real ProphetX + SportsDataIO data was observed. Team names may use abbreviations, city vs. nickname variations, or special characters that cause systematic underscoring (e.g., ProphetX: "LA Lakers" vs SDIO: "Los Angeles Lakers" → token_sort_ratio ≈ 62, which would miss all NBA matches with the 0.90 threshold).

**Why it happens:** The matching algorithm was designed without access to real API data.

**How to avoid:** In Plan 02-01, after calling both APIs, log a sample of raw ProphetX event names alongside corresponding SportsDataIO game names. Manually compute `token_sort_ratio` for 5–10 pairs. Adjust weights and threshold to ensure known correct matches score ≥ 0.90. Document the calibration in code comments.

**Warning signs:** `event_id_mappings` table has zero rows after first polling cycle; or all mappings score exactly 1.0 (too loose) or none score above 0.50 (too strict).

### Pitfall 3: Celery Task Lock TTL Too Short

**What goes wrong:** `update_event_status` task acquires a 60-second lock but ProphetX API with retry logic takes up to 4+8+16 = 28 seconds minimum (if all 3 retries max out). The lock expires mid-task; a second worker picks up the same work; both update the same event simultaneously.

**Why it happens:** Lock TTL chosen arbitrarily without calculating worst-case task duration.

**How to avoid:** Lock TTL = max expected task duration × safety factor. For update_event_status: 3 retries × 4 second max wait (tenacity) + DB write overhead = ~15 seconds realistic. Set lock TTL = 120 seconds (safe margin). Never set lock TTL shorter than the retry backoff of the underlying operation.

**Warning signs:** Duplicate audit log entries for the same event_id at nearly the same timestamp; ProphetX API returns 409 Conflict errors on status updates.

### Pitfall 4: SportsDataIO `GamesByDate` Returns Empty During Overnight Hours

**What goes wrong:** Polling workers query `GamesByDate/{today}` at midnight UTC. Many NBA and NHL games that started yesterday PST are still in progress but appear on "yesterday's" date. The worker finds 0 games → computes 0 mismatches → does nothing. All live games become stale.

**Why it happens:** `GamesByDate` is keyed on game *start* date, not current calendar date.

**How to avoid:** Query both today and yesterday when polling. Alternatively, use SportsDataIO's `ScoresBasic` or `Scores` endpoint which returns "in progress" games regardless of date. Dedup results by game ID. This is a critical correctness issue for any games that span midnight.

**Warning signs:** Dashboard shows all events as "upcoming" during late-night hours even though games are live; poll_sports_data log shows 0 games returned.

### Pitfall 5: Audit Log REVOKE Fails If App DB User Is the Table Owner

**What goes wrong:** `REVOKE UPDATE ON audit_log FROM prophet_monitor` has no effect if `prophet_monitor` is the table owner. PostgreSQL owners always retain full privileges on their own tables; REVOKE does not reduce owner privileges.

**Why it happens:** Docker Compose creates the database with the same user that runs the application (e.g., `POSTGRES_USER=prophet_monitor`), making that user the table owner for all tables.

**How to avoid:** Two options: (1) Create a separate privileged `migration_user` that owns the tables, grant SELECT/INSERT on audit_log to the app user `prophet_monitor`, then REVOKE removes what the app user was granted. (2) Simpler alternative: leave REVOKE in place as defense-in-depth; add an ORM-level guard that raises an error if `session.delete()` is called on `AuditLog`; document in code that the DB user is the owner and REVOKE is a no-op in this config. Both approaches provide layered protection. Note this as a known limitation in the code comment.

**Warning signs:** `REVOKE` statement in migration runs without error but manual testing via psql shows UPDATE/DELETE still succeed.

### Pitfall 6: Redis Match Cache Serves Stale Matches After Rematch

**What goes wrong:** ProphetX creates a new tournament with the same teams and start time as a previous event (e.g., rescheduled game). The Redis cache for `match:px:{old_event_id}` is already gone, but the new event gets the same ID — cache returns the previous season's SportsDataIO game ID.

**Why it happens:** ProphetX event IDs are assumed stable per event; if IDs are reused or recycled, the 24-hour Redis TTL is not sufficient protection.

**How to avoid:** Cache key includes ProphetX event ID AND the event's scheduled_start timestamp. When an event's start time changes (detected during polling), invalidate the cache key explicitly. Store the SportsDataIO game date in the cache so the cache hit can be validated against the current date range before being used.

---

## Code Examples

### New DB Models Overview

```python
# models/event.py
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base

class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prophetx_event_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    sport: Mapped[str] = mapped_column(String(50), nullable=False)
    league: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    home_team: Mapped[str | None] = mapped_column(String(255), nullable=True)
    away_team: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prophetx_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    real_world_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status_match: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_prophetx_poll: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_real_world_poll: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))

# models/market.py
from sqlalchemy import Numeric, ForeignKey
class Market(Base):
    __tablename__ = "markets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prophetx_market_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    current_liquidity: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), default=Decimal("0"))
    min_liquidity_threshold: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=2), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    last_polled: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

# models/event_id_mapping.py
class EventIDMapping(Base):
    __tablename__ = "event_id_mappings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prophetx_event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sdio_game_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sport: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)  # True when confidence >= 0.90
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False)    # True when below threshold
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))
```

### Audit Log Endpoint (AUDIT-02)

```python
# api/v1/audit.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import require_role, get_async_session
from app.core.constants import RoleEnum
from app.models.audit_log import AuditLog
from app.schemas.audit import AuditLogPage

router = APIRouter(prefix="/audit-log", tags=["audit"])

@router.get("", response_model=AuditLogPage,
            dependencies=[Depends(require_role(RoleEnum.operator, RoleEnum.admin))])
async def get_audit_log(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_async_session),
):
    """Paginated audit log, newest first."""
    offset = (page - 1) * per_page
    total_q = await session.execute(select(func.count()).select_from(AuditLog))
    total = total_q.scalar_one()

    rows_q = await session.execute(
        select(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(per_page)
    )
    rows = rows_q.scalars().all()
    return AuditLogPage(total=total, page=page, per_page=per_page, entries=rows)
```

### Poll Workers — Phase 2 Structure

```python
# workers/poll_prophetx.py — Phase 2 (replaces stub)
from app.workers.celery_app import celery_app
from app.clients.prophetx import ProphetXClient
from app.db.sync_session import SyncSessionLocal
from app.db.redis import get_sync_redis
from app.monitoring.liquidity_monitor import is_below_threshold
from app.models.event import Event
from app.models.market import Market
import structlog

log = structlog.get_logger()

@celery_app.task(name="app.workers.poll_prophetx.run", bind=True)
def run(self):
    """
    Poll ProphetX for current event statuses and market liquidity.
    Writes results to DB. Enqueues send_alerts for liquidity breaches.
    """
    import asyncio
    # NOTE: ProphetXClient is async; run in a new event loop for Celery sync context
    # This is the ONE acceptable use of asyncio.run() — for the API call only;
    # all DB writes use the sync engine.
    async def _fetch():
        async with ProphetXClient() as px:
            events = await px.get_events_raw()
            markets = await px.get_markets_raw()
            return events, markets

    raw_events, raw_markets = asyncio.run(_fetch())

    with SyncSessionLocal() as session:
        redis_client = get_sync_redis()
        _upsert_events(session, raw_events)
        _check_markets_liquidity(session, redis_client, raw_markets)
        session.commit()
    log.info("poll_prophetx_complete", task_id=self.request.id)
```

**Important note on `asyncio.run()` in Celery:** Using `asyncio.run()` for the ProphetX async HTTP client inside a Celery sync worker IS acceptable because the async call is isolated (not using the SQLAlchemy async engine or any shared async resource). The async event loop is created, used for the HTTP call only, and destroyed. This is the documented pattern for using async HTTP clients in sync Celery workers when no async-native Celery support is needed.

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|-----------------|--------|
| FuzzyWuzzy for string matching | rapidfuzz (C++ backed, 5-100x faster) | Same API, drop-in replacement; significantly better for high-frequency matching |
| Custom Redis SETNX + TTL | redis-py built-in Lock class | Lock handles ownership token + atomic Lua-script release; built into redis-py 5.x already installed |
| Application-level DELETE prevention | PostgreSQL REVOKE at DB level | Database-level enforcement survives application bugs; provides defense-in-depth |
| Separate Celery task for lock acquisition | redis-py Lock used inside the action task | Simpler: lock is acquired at the top of the task function; no separate coordination task needed |

**Deprecated/outdated:**
- `thefuzz` (formerly FuzzyWuzzy): replaced by rapidfuzz; same API but significantly slower; do not use for new code
- `aioredlock`: separate library for async Redis locks — unnecessary since redis-py 5.x includes `redis.asyncio.Lock`

---

## Open Questions

1. **ProphetX event write endpoint for status updates (SYNC-01 blocker)**
   - What we know: Phase 1 confirmed sandbox reads: `GET /mm/get_tournaments`, `GET /mm/get_sport_events`, `GET /mm/get_markets`. Auth flow confirmed (OAuth2 token exchange).
   - What's unclear: The write endpoint for updating event status. PRD speculates `PATCH /events/{id}` but actual ProphetX Partner API may use a different path (e.g., `POST /mm/update_sport_event_status` or similar). Medium articles returned 403.
   - Recommendation: The first task in Plan 02-01 must probe ProphetX sandbox for available write endpoints. Until confirmed, `update_event_status` task should be implemented as log-only stub with a clear `# TODO: wire ProphetX write endpoint` comment. The idempotency + audit log logic can be built and tested with the stub.

2. **ProphetX status enum values (CORE-03 blocker)**
   - What we know: PRD speculates `"upcoming"`, `"live"`, `"ended"`, `"cancelled"`, `"suspended"`. STATE.md explicitly flags as unconfirmed. Phase 1 sandbox call returned tournaments, not events with status fields.
   - What's unclear: Exact string values; whether they are lowercase, uppercase, or mixed case; whether there are additional values.
   - Recommendation: Plan 02-01 Task 1 must call `get_events_raw()` and log the full response. The `mismatch_detector.py` status mapping MUST NOT be finalized until enum values are confirmed from the actual API response. Placeholder values in the code must be clearly marked `# UNCONFIRMED`.

3. **ProphetX market liquidity field name and units**
   - What we know: ProphetX has markets with liquidity data; Phase 1 confirmed `GET /mm/get_markets` endpoint exists.
   - What's unclear: The exact field name for current liquidity in the market response (could be `liquidity`, `total_liquidity`, `available_liquidity`, `pool_size`, etc.) and units (USD, credits, or internal units).
   - Recommendation: Log full `get_markets_raw()` response in Plan 02-02 development; identify the liquidity field and units before implementing `is_below_threshold()`. The per-market threshold in `system_config` must be set in the same units.

4. **SportsDataIO subscription sports coverage for this account**
   - What we know: Phase 1 built `probe_subscription_coverage()` in `SportsDataIOClient` but it was not run against the real API. STATE.md notes NFL/NCAAB/NCAAF returned 404 in research (different URL format).
   - What's unclear: Which sports Doug's subscription covers; whether NFL uses a different endpoint pattern.
   - Recommendation: Run `probe_subscription_coverage()` via `/probe/clients` endpoint in early Plan 02-02 development. Document which sports return 200 vs. 403 and adjust the poll_sports_data worker's sports list accordingly.

5. **Confidence threshold calibration (CORE-03)**
   - What we know: REQUIREMENTS.md specifies ≥ 0.90 confidence threshold. This was set before any real API data was observed.
   - What's unclear: Whether real ProphetX event names and SportsDataIO game names produce scores above 0.90 for correct matches. Team name normalization differences (abbreviations, city vs. full name) may cause systematic underscoring.
   - Recommendation: After Plan 02-01 has the matcher working, manually compute confidence scores for 10–20 known correct pairs from real API data. Adjust threshold and weights if needed. Document the calibration data in a comment in `event_matcher.py`.

---

## Sources

### Primary (HIGH confidence)

- [redis-py Lock class source](https://github.com/redis/redis-py/blob/master/redis/lock.py) — Constructor params, acquire(blocking=False), release(), context manager; verified current
- [Redis official distributed locks docs](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/) — SET NX PX pattern; Lua-script safe release; TTL recommendations
- [RapidFuzz official docs — fuzz module](https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html) — `token_sort_ratio` return values (0–100); confirmed for sports name matching use case
- [RapidFuzz PyPI](https://pypi.org/project/RapidFuzz/) — Version 3.14.3, Python 3.10+, pip install rapidfuzz
- [SportsDataIO NFL Workflow Guide](https://sportsdata.io/developers/workflow-guide/nfl) — Confirmed status values: Scheduled, InProgress, Final, F/OT, Postponed, Canceled, Suspended, Delayed; `Status` field name confirmed
- [PostgreSQL REVOKE docs (v18)](https://www.postgresql.org/docs/current/sql-revoke.html) — `REVOKE UPDATE, DELETE, TRUNCATE ON table FROM role` syntax confirmed
- [Celery 5 tasks docs](https://docs.celeryq.dev/en/main/userguide/tasks.html) — bind=True, self.retry(), autoretry_for, retry_backoff, acks_late

### Secondary (MEDIUM confidence)

- [Celery non-blocking lock pattern (Gist)](https://gist.github.com/Skyross/2f4c95f5df2446b71f74f4f9d9771125) — Celery task with redis lock, non-blocking acquire; pattern verified with redis-py Lock docs
- [SportsDataIO Postponed/Rescheduled guide](https://support.sportsdata.io/hc/en-us/articles/4404845580567-Postponed-and-Rescheduled-Games) — Confirmed Postponed vs Canceled distinction; search result confirmed article exists
- FastAPI + Celery idempotent task pattern (Medium, Dec 2025) — `task_acks_late` + before-state check pattern; verified against Celery official docs

### Tertiary (LOW confidence — requires validation)

- ProphetX status enum values — PRD speculation only (`"upcoming"`, `"live"`, `"ended"`); Medium article returned 403; must be confirmed from live API
- ProphetX event write endpoint path — Not publicly documented; must be confirmed from ProphetX partner docs or sandbox testing
- ProphetX market liquidity field name — Not publicly documented; must be confirmed from `get_markets_raw()` response

---

## Metadata

**Confidence breakdown:**
- Standard stack (rapidfuzz, redis-py Lock): HIGH — official docs and PyPI verified, versions confirmed
- Architecture patterns (event matcher, distributed lock, audit log): HIGH — patterns derived from verified library docs and PRD data model; confidence scoring algorithm is research-derived and requires calibration
- ProphetX write API: LOW — read endpoints confirmed from Phase 1; write endpoint path unconfirmed; status enum unconfirmed
- SportsDataIO status values: HIGH — confirmed from official workflow guide; field name `Status` confirmed
- Pitfalls: HIGH for infrastructure pitfalls (Redis lock TTL, REVOKE ownership); MEDIUM for ProphetX-specific pitfalls (threshold calibration); all drawn from direct experience patterns

**Research date:** 2026-02-25
**Valid until:** 2026-04-25 (stable libraries; 60-day validity; ProphetX items need validation before expiry is relevant)
