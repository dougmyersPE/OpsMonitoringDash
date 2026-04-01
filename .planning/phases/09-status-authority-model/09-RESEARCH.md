# Phase 9: Status Authority Model - Research

**Researched:** 2026-03-31
**Domain:** SQLAlchemy ORM column additions, Alembic migrations, authority-window logic, poll worker conditional writes
**Confidence:** HIGH

## Summary

Phase 9 introduces two new columns on the `events` table (`status_source` and `ws_delivered_at`) and modifies two workers (`ws_prophetx.py` and `poll_prophetx.py`) to implement a WS-leads, poll-defers model. The work is entirely within the Python backend — no frontend changes, no new external dependencies, no new services. Every file to be touched has been read and the exact insertion points are known.

The authority window logic is a simple datetime comparison. When `ws_delivered_at` is set and `(now - ws_delivered_at) < threshold`, poll skips the `prophetx_status` write but proceeds with the metadata-only update path. The "ended" status is a deliberate exception: poll can always mark a stale event ended regardless of WS authority, preventing events from being stranded as live forever.

The Alembic migration is migration number 008 (next after the existing 007 series). No third-party libraries are needed beyond what is already installed. The test pattern is established — mock-based unit tests in `backend/tests/` following the pattern already used in `test_ws_upsert.py` and `test_ws_reconnect.py`.

**Primary recommendation:** Add columns and write the authority check function in a shared helper, then call it from both workers. Keep the logic pure/testable — no DB access inside the authority gate predicate.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** Authority window duration is 10 minutes, configurable. After WS delivers a status, poll_prophetx will not overwrite `prophetx_status` for 10 minutes. Configurable via environment variable or settings.

**D-02:** Authority is tracked by a `ws_delivered_at` timestamp column on the events table. If `ws_delivered_at` is not null and `now - ws_delivered_at < threshold`, the event is "WS-authoritative."

**D-03:** Add `status_source` column directly on the events table (String, values: "ws", "poll", "manual"). Updated on every `prophetx_status` write. No separate audit table — keep it simple.

**D-04:** `ws_delivered_at` column (DateTime, nullable) on events table. Set when WS writes status, cleared/ignored when poll is allowed to overwrite after window expires.

**D-05:** Authority window does NOT protect against poll marking events "ended." The "ended" status is terminal — if poll sees an event gone from the API, it can always mark it ended regardless of WS authority.

**D-06:** When poll detects a different status than WS delivered, and the event is within the authority window: log the discrepancy (structured log with both statuses) but do NOT overwrite `prophetx_status`. The WS-delivered status wins.

**D-07:** When WS is authoritative, poll_prophetx still updates: `home_team`, `away_team`, `scheduled_start`, `league`, `last_prophetx_poll`, and recomputes `status_match`. Only `prophetx_status` and `status_source` are protected.

### Claude's Discretion

- Migration numbering: next available (008)
- Alembic migration for `status_source` and `ws_delivered_at` columns
- Structured log format for authority-window skip events
- Whether to add an index on `ws_delivered_at` (likely not needed at this scale)
- Test structure: extend existing test files or create new ones for authority logic

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTH-01 | Events table tracks status_source (ws/poll/manual) for each prophetx_status write | New `status_source` String column on events; set in ws_prophetx._upsert_event (both paths) and poll_prophetx (create + update paths) and update_event_status.run |
| AUTH-02 | poll_prophetx skips prophetx_status overwrite when WS delivered the status recently (within configurable threshold) | New `ws_delivered_at` DateTime column; authority check function in update path of poll_prophetx; 10-min threshold from settings |
| AUTH-03 | poll_prophetx updates only metadata (teams, scheduled_start, league) when WS is authoritative for an event | Metadata-only write path already exists structurally in poll_prophetx update block; just split the status assignment behind the authority guard |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | >=2.0 (already installed) | ORM mapped_column additions | Already used throughout; `Mapped` + `mapped_column` pattern established |
| Alembic | >=1.13 (already installed) | DB migration 008 | Migration chain 001–007 already exists; next is 008 |
| structlog | >=24.0 (already installed) | Structured authority-window skip logs | Already used in both workers |
| pydantic-settings | >=2.0 (already installed) | `WS_AUTHORITY_WINDOW_SECONDS` env var | Already used in `config.py` Settings class |

### Supporting
No new libraries required. All needed packages are already installed.

**Installation:**
```bash
# No new packages — all dependencies already in pyproject.toml
```

## Architecture Patterns

### Recommended Project Structure

Changes are confined to these existing files:
```
backend/
├── app/
│   ├── models/
│   │   └── event.py                  # Add status_source + ws_delivered_at columns
│   ├── core/
│   │   └── config.py                 # Add WS_AUTHORITY_WINDOW_SECONDS setting
│   ├── workers/
│   │   ├── ws_prophetx.py            # Set status_source="ws" + ws_delivered_at=now
│   │   ├── poll_prophetx.py          # Authority check + metadata-only path
│   │   └── update_event_status.py    # Set status_source="manual"
│   └── monitoring/
│       └── authority.py              # NEW: pure authority-check helper function
├── alembic/
│   └── versions/
│       └── 008_add_status_authority_columns.py  # NEW migration
└── tests/
    └── test_status_authority.py      # NEW: authority logic unit tests
```

### Pattern 1: Pure Authority-Check Helper

**What:** Extract the authority window predicate into a pure function with no DB or Redis access. Takes `ws_delivered_at` (datetime or None) and `threshold_seconds` (int). Returns bool.

**When to use:** Called at the top of the poll update path before deciding whether to write `prophetx_status`.

**Example:**
```python
# backend/app/monitoring/authority.py
from datetime import datetime, timezone


def is_ws_authoritative(ws_delivered_at: datetime | None, threshold_seconds: int) -> bool:
    """Return True if a WS-delivered status is within the authority window.

    Args:
        ws_delivered_at: UTC datetime when WS last wrote prophetx_status, or None.
        threshold_seconds: Authority window duration (e.g. 600 for 10 minutes).

    Returns:
        True if event is currently WS-authoritative (poll should not overwrite).
        False if window expired, or ws_delivered_at is None (poll has free write).
    """
    if ws_delivered_at is None:
        return False
    now = datetime.now(timezone.utc)
    # Ensure ws_delivered_at is timezone-aware (DB may return naive UTC)
    if ws_delivered_at.tzinfo is None:
        ws_delivered_at = ws_delivered_at.replace(tzinfo=timezone.utc)
    elapsed = (now - ws_delivered_at).total_seconds()
    return elapsed < threshold_seconds
```

### Pattern 2: Settings Extension

**What:** Add `WS_AUTHORITY_WINDOW_SECONDS` to the existing `Settings` class in `config.py`.

**Example:**
```python
# In backend/app/core/config.py Settings class
WS_AUTHORITY_WINDOW_SECONDS: int = 600  # 10 minutes default; override via env
```

### Pattern 3: Alembic Migration (following 001–007 pattern)

```python
# backend/alembic/versions/008_add_status_authority_columns.py
revision = "008"
down_revision = "007"

def upgrade() -> None:
    op.add_column("events", sa.Column("status_source", sa.String(20), nullable=True))
    op.add_column("events", sa.Column("ws_delivered_at", sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    op.drop_column("events", "ws_delivered_at")
    op.drop_column("events", "status_source")
```

**Note on index:** D-01 (Claude's discretion) says index on `ws_delivered_at` likely not needed at this scale. Do not add one — keeps migration minimal.

### Pattern 4: poll_prophetx Update Path Split

**What:** In the existing update block (lines ~206–228 of poll_prophetx.py), split the update into two parts:
1. **Always:** Update metadata fields (`sport`, `league`, `name`, `home_team`, `away_team`, `scheduled_start`, `last_prophetx_poll`)
2. **Conditional:** Update `prophetx_status`, `status_source`, and recompute `status_match` — only when NOT ws-authoritative, OR when status_value is "ended"

**Example:**
```python
# In poll_prophetx.py update block — replaces the unconditional existing.prophetx_status = ...

from app.monitoring.authority import is_ws_authoritative

# Always update metadata (AUTH-03)
existing.sport = str(raw_event.get("sport") or ... or existing.sport)
if tournament_name:
    existing.league = tournament_name
existing.name = str(raw_event.get("name") or ... or existing.name)
existing.home_team = home_team or existing.home_team
existing.away_team = away_team or existing.away_team
if scheduled_start is not None:
    existing.scheduled_start = scheduled_start
existing.last_prophetx_poll = now

# Authority check — poll defers to WS except for terminal "ended" (D-05)
authoritative = is_ws_authoritative(existing.ws_delivered_at, settings.WS_AUTHORITY_WINDOW_SECONDS)
is_ended = (status_value or "").lower() == "ended"

if not authoritative or is_ended:
    existing.prophetx_status = status_value
    existing.status_source = "poll"
    existing.status_match = compute_status_match(
        status_value,
        existing.odds_api_status,
        existing.sports_api_status,
        existing.sdio_status,
        existing.espn_status,
        existing.oddsblaze_status,
    )
else:
    # WS is authoritative — log discrepancy if status differs, do not overwrite
    if status_value != existing.prophetx_status:
        log.info(
            "poll_prophetx_authority_window_skip",
            prophetx_event_id=prophetx_event_id,
            ws_status=existing.prophetx_status,
            poll_status=status_value,
            ws_delivered_at=existing.ws_delivered_at.isoformat() if existing.ws_delivered_at else None,
        )
    # Still recompute status_match against the WS-authoritative status
    existing.status_match = compute_status_match(
        existing.prophetx_status,
        existing.odds_api_status,
        existing.sports_api_status,
        existing.sdio_status,
        existing.espn_status,
        existing.oddsblaze_status,
    )
```

### Pattern 5: ws_prophetx Create and Update Path Additions

**What:** In `_upsert_event`, set `status_source="ws"` and `ws_delivered_at=now` on both create and update paths. The `now` variable is already computed at the top of the function.

```python
# Create path (Event constructor kwargs — add alongside existing fields):
status_source="ws",
ws_delivered_at=now,

# Update path (add alongside existing.prophetx_status = status_value):
existing.status_source = "ws"
existing.ws_delivered_at = now
```

**Note:** The op=d (delete → ended) path in `_upsert_event` also writes `prophetx_status`. Set `status_source="ws"` there too, since the deletion is WS-delivered.

### Pattern 6: poll_prophetx Create Path

**What:** New events created by poll (never seen by WS) get `status_source="poll"`. Also set `status_match` on create path (currently missing in poll_prophetx — a minor existing gap).

```python
# In poll_prophetx create block (Event constructor):
status_source="poll",
status_match=compute_status_match(status_value, None, None, None, None, None),
```

### Pattern 7: poll_prophetx Stale-Ended Path

**What:** The stale-event marking loop (lines ~245–274) also writes `prophetx_status = "ended"`. Per D-05, ended is always allowed. Also set `status_source="poll"`.

```python
event.prophetx_status = "ended"
event.status_source = "poll"   # poll determined this event is stale
```

### Pattern 8: update_event_status Manual Source

**What:** `update_event_status.py` (line ~155) writes `event.prophetx_status = effective_target`. Add `event.status_source = "manual"` alongside.

```python
event.prophetx_status = effective_target
event.status_source = "manual"
```

The AuditLog `after_state` dict can also include `"status_source": "manual"` for traceability — no schema change required (AuditLog stores JSON).

### Anti-Patterns to Avoid

- **Putting the authority check inside `_upsert_event`:** WS is the authority setter, not the checker. The check belongs only in the poll path.
- **Clearing `ws_delivered_at` after the window expires:** D-04 says "cleared/ignored when poll is allowed to overwrite." This means poll simply overwrites it naturally when it writes `prophetx_status`. No explicit clear needed — when poll writes `status_source="poll"`, `ws_delivered_at` naturally becomes stale. To avoid confusion, when poll does write `prophetx_status`, also clear `ws_delivered_at` (set to `None`) so the column accurately reflects the last WS delivery time, not a stale one. This is safer than leaving an old timestamp that would re-trigger the authority gate if queried.

  **Revised guidance:** When poll writes `prophetx_status` (authority window expired or "ended" exception), also set `existing.ws_delivered_at = None`. This keeps the column semantically clean.

- **Reading `settings` at module import time inside workers:** Both workers already use `from app.core.config import settings` at the top level. `WS_AUTHORITY_WINDOW_SECONDS` will be available as `settings.WS_AUTHORITY_WINDOW_SECONDS`.
- **Using `datetime.utcnow()`:** The codebase uses `datetime.now(timezone.utc)` consistently. Do not use the deprecated `utcnow()`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Authority window threshold config | Hardcoded constant | `Settings.WS_AUTHORITY_WINDOW_SECONDS` env var | Already in pydantic-settings; survives Docker redeploy without code change |
| Timezone-aware datetime comparison | Custom offset math | Standard `datetime.now(timezone.utc)` subtraction | Python timedelta handles DST/UTC correctly; no tz library needed |
| Status source tracking | Separate audit table | `status_source` column on events (D-03) | User decision; simpler query path; audit_log already tracks full state changes |

---

## Common Pitfalls

### Pitfall 1: Naive vs Timezone-Aware Datetime Comparison
**What goes wrong:** `datetime.now(timezone.utc) - existing.ws_delivered_at` raises `TypeError: can't subtract offset-naive and offset-aware datetimes` if PostgreSQL returns a naive datetime from a `DateTime(timezone=True)` column in some driver configurations.
**Why it happens:** SQLAlchemy with psycopg2 returns timezone-aware datetimes for `DateTime(timezone=True)` columns, but test mocks often use naive datetimes.
**How to avoid:** The pure helper `is_ws_authoritative` should defensively coerce `ws_delivered_at` to UTC-aware if it arrives naive (shown in Pattern 1 example above).
**Warning signs:** `TypeError` in test output when passing `datetime.now()` instead of `datetime.now(timezone.utc)`.

### Pitfall 2: Missing status_match Recompute in WS-Authoritative Path
**What goes wrong:** When poll skips `prophetx_status` write, it might also skip `status_match` recompute. The `status_match` column would then not reflect updates from real-world source workers that ran between poll cycles.
**Why it happens:** The early-return (or skip) pattern around `prophetx_status` could be applied too broadly.
**How to avoid:** Always recompute `status_match` in both branches (authority-skip branch and normal-write branch). Pattern 4 above shows this explicitly.

### Pitfall 3: poll_prophetx Create Path Missing status_source
**What goes wrong:** AUTH-01 requires every `prophetx_status` write to record `status_source`. The poll create path (new events) currently sets `prophetx_status` but not `status_source`. If omitted, newly polled events have `NULL` status_source.
**Why it happens:** The create path is separate from the update path; easy to miss.
**How to avoid:** Pattern 6 above. Include `status_source="poll"` in the `Event(...)` constructor call in poll's create block.

### Pitfall 4: Stale-Ended Loop Omitting status_source
**What goes wrong:** The stale-event marking loop writes `event.prophetx_status = "ended"` but poll_prophetx currently has no `status_source` field. After migration, omitting it leaves `status_source=NULL` on stale-ended events.
**Why it happens:** The stale loop is a secondary code path, easy to overlook.
**How to avoid:** Pattern 7 above. Add `event.status_source = "poll"` in the stale loop.

### Pitfall 5: op=d Path in ws_prophetx Not Setting status_source
**What goes wrong:** The op=d (delete → ended) path in `_upsert_event` writes `existing.prophetx_status = "ended"` but is a separate code path that returns early. If `status_source` and `ws_delivered_at` are only set in the upsert block below, the op=d path misses them.
**Why it happens:** The op=d path has an early return at line ~161 before the main upsert logic.
**How to avoid:** In the op=d block, add `existing.status_source = "ws"` (and optionally `existing.ws_delivered_at = now`) before `session.commit()`.

### Pitfall 6: Settings Import in update_event_status.py
**What goes wrong:** `update_event_status.py` does `from app.core.config import settings` as a deferred import inside the task body (line ~125: `from app.models.config import SystemConfig`). The new `WS_AUTHORITY_WINDOW_SECONDS` would be accessed via `settings.WS_AUTHORITY_WINDOW_SECONDS` — no issue since `settings` is a module-level singleton. But the `status_source = "manual"` write does not need to read settings at all.
**Why it happens:** N/A for this change — just a note to confirm no import change needed in update_event_status.py.
**How to avoid:** Simply add `event.status_source = "manual"` after `event.prophetx_status = effective_target` (line ~155).

---

## Code Examples

### Verified: Existing Event Model Column Pattern
```python
# Source: backend/app/models/event.py (read directly)
# Existing column pattern — new columns follow exactly this form:
class Event(Base):
    __tablename__ = "events"
    # ... existing columns ...
    oddsblaze_status: Mapped[str | None] = mapped_column(String(50), nullable=True)

# New columns to add (same pattern):
status_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
ws_delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

### Verified: Existing Alembic Migration Pattern
```python
# Source: backend/alembic/versions/007_add_oddsblaze_status.py (read directly)
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("events", sa.Column("oddsblaze_status", sa.String(50), nullable=True))

def downgrade() -> None:
    op.drop_column("events", "oddsblaze_status")
```

### Verified: Existing structlog Pattern in Workers
```python
# Source: backend/app/workers/ws_prophetx.py (read directly)
log.info(
    "ws_prophetx_event_updated",
    prophetx_event_id=prophetx_event_id,
    status=status_value,
)
# Authority-window skip log follows same pattern:
log.info(
    "poll_prophetx_authority_window_skip",
    prophetx_event_id=prophetx_event_id,
    ws_status=existing.prophetx_status,
    poll_status=status_value,
    ws_delivered_at=existing.ws_delivered_at.isoformat(),
)
```

### Verified: Existing Test Mock Pattern
```python
# Source: backend/tests/test_ws_upsert.py (read directly)
def _make_session_mock(existing=None):
    mock_session = MagicMock()
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = existing
    mock_session.execute.return_value = mock_execute_result
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    return mock_session
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Both workers write `prophetx_status` freely | WS sets authority window; poll checks before write | Poll cannot overwrite recent WS status |
| No source attribution | `status_source` column on every write | Audit trail for ws/poll/manual origin |
| No `status_match` on poll create path | Add `status_match` on poll create path | Fixes existing minor gap (no BC break) |

---

## Runtime State Inventory

> Phase involves adding columns to existing live table, not renaming.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Existing `events` rows will have `status_source=NULL` and `ws_delivered_at=NULL` after migration runs | NULL is valid — both columns are nullable. No data migration needed. Poll will backfill `status_source` on next write per event. |
| Live service config | No external service configuration references these new column names | None |
| OS-registered state | None — no cron/scheduler references column names | None |
| Secrets/env vars | New `WS_AUTHORITY_WINDOW_SECONDS` env var added to Settings | Add to `.env` and Docker Compose env block if non-default value desired; has safe default of 600 |
| Build artifacts | None — no compiled binaries reference column names | None |

---

## Environment Availability

Step 2.6: SKIPPED (no new external dependencies — all changes are Python code and a DB migration against the existing PostgreSQL instance)

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.23 |
| Config file | `backend/pyproject.toml` (`[tool.pytest.ini_options]`, asyncio_mode="auto") |
| Quick run command | `cd backend && python -m pytest tests/test_status_authority.py -x -q` |
| Full suite command | `cd backend && python -m pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-01 | ws_prophetx create path sets status_source="ws" and ws_delivered_at | unit | `pytest tests/test_status_authority.py::TestWsAuthorityColumns::test_create_sets_ws_source -x` | ❌ Wave 0 |
| AUTH-01 | ws_prophetx update path sets status_source="ws" and ws_delivered_at | unit | `pytest tests/test_status_authority.py::TestWsAuthorityColumns::test_update_sets_ws_source -x` | ❌ Wave 0 |
| AUTH-01 | ws_prophetx op=d path sets status_source="ws" | unit | `pytest tests/test_status_authority.py::TestWsAuthorityColumns::test_delete_sets_ws_source -x` | ❌ Wave 0 |
| AUTH-01 | poll_prophetx create path sets status_source="poll" | unit | `pytest tests/test_status_authority.py::TestPollAuthorityColumns::test_poll_create_sets_poll_source -x` | ❌ Wave 0 |
| AUTH-01 | poll_prophetx update path (window expired) sets status_source="poll" | unit | `pytest tests/test_status_authority.py::TestPollAuthorityColumns::test_poll_update_outside_window_sets_poll_source -x` | ❌ Wave 0 |
| AUTH-02 | is_ws_authoritative returns True when within window | unit | `pytest tests/test_status_authority.py::TestAuthorityHelper::test_within_window_returns_true -x` | ❌ Wave 0 |
| AUTH-02 | is_ws_authoritative returns False when window expired | unit | `pytest tests/test_status_authority.py::TestAuthorityHelper::test_expired_window_returns_false -x` | ❌ Wave 0 |
| AUTH-02 | is_ws_authoritative returns False when ws_delivered_at is None | unit | `pytest tests/test_status_authority.py::TestAuthorityHelper::test_none_delivered_at_returns_false -x` | ❌ Wave 0 |
| AUTH-02 | poll_prophetx does NOT overwrite prophetx_status within window | unit | `pytest tests/test_status_authority.py::TestPollAuthorityColumns::test_poll_update_inside_window_skips_status -x` | ❌ Wave 0 |
| AUTH-02 | poll_prophetx logs authority_window_skip when status differs | unit | `pytest tests/test_status_authority.py::TestPollAuthorityColumns::test_poll_logs_discrepancy_inside_window -x` | ❌ Wave 0 |
| AUTH-02 | "ended" always allowed even inside window (D-05) | unit | `pytest tests/test_status_authority.py::TestPollAuthorityColumns::test_ended_bypasses_authority_window -x` | ❌ Wave 0 |
| AUTH-03 | poll_prophetx updates metadata fields when WS is authoritative | unit | `pytest tests/test_status_authority.py::TestPollAuthorityColumns::test_poll_updates_metadata_inside_window -x` | ❌ Wave 0 |
| AUTH-03 | status_match recomputed even inside authority window | unit | `pytest tests/test_status_authority.py::TestPollAuthorityColumns::test_status_match_recomputed_inside_window -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/test_status_authority.py -x -q`
- **Per wave merge:** `cd backend && python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_status_authority.py` — covers AUTH-01, AUTH-02, AUTH-03 (all test cases above)
- [ ] `app/monitoring/authority.py` — pure helper needed before tests can import it

*(Existing conftest.py and mock patterns in test_ws_upsert.py provide all needed fixtures and patterns — no new conftest additions required)*

---

## Open Questions

1. **Does `update_event_status.py` need `ws_delivered_at` cleared when it writes `status_source="manual"`?**
   - What we know: D-03 says `status_source` is updated on every `prophetx_status` write. D-04 says `ws_delivered_at` is set when WS writes, cleared/ignored when poll overwrites.
   - What's unclear: Manual sync via `update_event_status` is rare (human-triggered). Should a manual write clear the WS authority window?
   - Recommendation: Yes — set `event.ws_delivered_at = None` when `update_event_status` writes `prophetx_status`. A human decision should always take precedence over the WS window.

2. **What should happen to `status_source` on the existing NULL rows?**
   - What we know: After migration, all existing events have `status_source=NULL`. No backfill migration is planned.
   - What's unclear: Will dashboard queries or log analysis break if `status_source=NULL` appears in logs?
   - Recommendation: NULL is a valid pre-Phase-9 state. Log consumers should treat NULL as "unknown (pre-authority-model)". No backfill needed; every event touched after Phase 9 ships will get the column populated.

---

## Sources

### Primary (HIGH confidence)
- Direct file reads: `backend/app/workers/ws_prophetx.py`, `backend/app/workers/poll_prophetx.py`, `backend/app/models/event.py`, `backend/app/core/config.py`, `backend/app/workers/update_event_status.py`, `backend/app/monitoring/mismatch_detector.py`, `backend/alembic/versions/007_add_oddsblaze_status.py`, `backend/tests/test_ws_upsert.py`, `backend/tests/conftest.py`, `backend/pyproject.toml`
- `.planning/phases/09-status-authority-model/09-CONTEXT.md` — locked decisions

### Secondary (MEDIUM confidence)
- `.planning/REQUIREMENTS.md` — AUTH-01, AUTH-02, AUTH-03 requirement text
- `.planning/STATE.md` — project history and phase gate context

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all dependencies already installed and in use; no new packages
- Architecture: HIGH — insertion points read directly from source files; exact line regions identified
- Pitfalls: HIGH — derived from direct code reading (op=d early-return path, create-path gaps, naive datetime risks)
- Test patterns: HIGH — existing test_ws_upsert.py provides the exact mock pattern to follow

**Research date:** 2026-03-31
**Valid until:** 2026-04-30 (stable Python backend, no fast-moving deps)
