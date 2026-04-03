# Phase 13: Status Processing and Matching - Research

**Researched:** 2026-04-03
**Domain:** AMQP consumer DB integration, fuzzy event matching, mismatch detection extension
**Confidence:** HIGH

## Summary

Phase 13 is almost entirely about wiring an already-running consumer (`opticodds_consumer.py`) into the existing DB-write and mismatch-detection patterns that every other source worker already uses. The codebase has a complete, working template in `poll_oddsblaze.py` and `poll_espn.py`. The fuzzy matching algorithm (SequenceMatcher + date-window index + time-proximity bonus + 12-hour guard) is identical for all three sources. The mismatch detector (`mismatch_detector.py`) has already been extended to a 6-parameter signature with `opticodds_status` in place — the function signature change is done. The `opticodds_status` column is already in the `Event` model (added in Phase 12).

The primary work of this phase is: (1) add `_write_opticodds_status()` logic inside `_on_message()` in the consumer, reusing `SyncSessionLocal` exactly like `poll_oddsblaze.py`; (2) add a `_alert_special_status()` function for walkover/retired/suspended, reusing the `_alert_unknown_status()` dedup pattern already present; (3) update all 5-param callers of `compute_status_match` to pass `opticodds_status` as the 6th argument (currently 8 call sites pass only 5 args); and (4) add `opticodds_status` to `source_toggle.py`'s `SOURCE_COLUMN_MAP` so the toggle system works correctly.

**Primary recommendation:** Mirror `poll_oddsblaze.py` exactly for the fuzzy-match and DB-write pattern. Use `FUZZY_THRESHOLD = 0.75` (ESPN tennis threshold — individual athlete names vary more than team names). The mismatch detector already has the 6-param signature; the only remaining work there is updating call sites that still pass 5 args.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Mirror `poll_oddsblaze.py` matching pattern — competitor name token overlap + 24h date window
- **D-02:** Match logic lives in the consumer's `_on_message` callback path
- **D-03:** No match found → log at WARNING level (not an error); do NOT create new events
- **D-04:** On successful match, write the mapped canonical status from `_OPTICODDS_CANONICAL` to `opticodds_status` column; use async DB session from within consumer following `poll_oddsblaze.py` pattern
- **D-05:** After writing `opticodds_status`, call `compute_status_match()` and update `status_match` on the same event row — triggers SSE push via existing flow
- **D-06:** `walkover`, `retired`, and `suspended` statuses are written verbatim (raw value) to `opticodds_status`. They are also mapped through `_OPTICODDS_CANONICAL` for canonical comparison (walkover→ended, retired→ended, suspended→live)
- **D-07:** These three special statuses trigger a Slack alert with event context (event name, teams, raw status) using existing `SLACK_WEBHOOK_URL` + dedup pattern from Phase 12
- **D-08:** Keep `opticodds:connection_state` and `opticodds:last_message_at` prefix from Phase 12 — already deployed, already wired. AMQP-03 satisfied by existing keys. No change needed
- **D-09:** Add `opticodds_status: str | None = None` parameter to `compute_status_match()` in `mismatch_detector.py`. Add `_OPTICODDS_CANONICAL` dict to the same file. NULL-safe: None = skipped
- **D-10:** Also add `opticodds_status` parameter to `compute_is_critical()` following the same pattern
- **D-11:** All callers of `compute_status_match` must be updated to pass `opticodds_status` — grep all call sites
- **D-12:** Consumer uses synchronous SQLAlchemy sessions (not async) — pika BlockingConnection runs synchronously; follow `poll_oddsblaze.py` pattern with `SyncSessionLocal`

### Claude's Discretion
- Exact fuzzy match threshold (0.5-0.9 range — look at what `poll_oddsblaze` uses and match it)
- DB session lifecycle details (per-message vs batched)
- Logging verbosity for match hits/misses
- Test structure for fuzzy matching unit tests

### Deferred Ideas (OUT OF SCOPE)
- **Dashboard OpticOdds column** — DASH-02 mapped to Phase 14
- **OpticOdds health badge** — DASH-01 mapped to Phase 14
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TNNS-02 | Consumer matches OpticOdds tennis fixtures to ProphetX events by competitor names + date window (fuzzy match) | `poll_oddsblaze.py` and `poll_espn.py` provide complete template; SequenceMatcher + `±1-day date index` + time-proximity bonus + 12-hour guard |
| TNNS-03 | Walkover, retired, and suspended statuses display their actual value in the OpticOdds column and trigger Slack alerts | `_alert_unknown_status()` in consumer provides dedup pattern; write raw value to column, alert separately |
| AMQP-03 | Redis keys track OpticOdds connection state (connected/reconnecting/disconnected) and last message timestamp | Already implemented in Phase 12 — `opticodds:connection_state`, `opticodds:connection_state_since`, `opticodds:last_message_at` all written and wired to `/health/workers` |
| MISM-01 | OpticOdds status included in `compute_status_match` for tennis events; NULL safely skipped for non-tennis events | `mismatch_detector.py` already has the 6-param signature; 8 call sites in app workers still pass 5 args and need updating |
</phase_requirements>

## Standard Stack

### Core (all pre-existing)
| Library | Version | Purpose | Notes |
|---------|---------|---------|-------|
| SQLAlchemy (sync) | already installed | Sync DB session for writes inside pika callback | `SyncSessionLocal` from `app.db.sync_session` |
| pika | >=1.3.2,<2.0 | Already in `opticodds_consumer.py` (Phase 12) | BlockingConnection pattern |
| difflib.SequenceMatcher | stdlib | Fuzzy name matching | Same as `poll_oddsblaze.py` and `poll_espn.py` |
| redis (sync) | already installed | Dedup keys for Slack alerts | `_sync_redis.from_url(settings.REDIS_URL)` |
| slack_sdk.webhook.WebhookClient | already installed | Special status alerts | Same pattern as `_alert_unknown_status()` |

No new dependencies. Everything is already installed and proven in production.

**Fuzzy threshold decision (Claude's discretion):** Use `FUZZY_THRESHOLD = 0.75`. Rationale: `poll_espn.py` uses 0.75 for tennis/MMA (individual athlete names vary more than team names, same as OpticOdds tennis), while `poll_oddsblaze.py` uses 0.80 for team sports. Tennis player names (last name only vs full name, accents, abbreviations) make 0.80 too strict. ESPN's 0.75 is the proven threshold for this exact problem.

## Architecture Patterns

### Key Insight: What Is Already Done vs What Needs Doing

**Already done (Phase 12 + prior):**
- `mismatch_detector.py`: `compute_status_match()` already has 6-param signature with `opticodds_status: str | None = None`
- `mismatch_detector.py`: `compute_is_critical()` already has 6-param signature with `opticodds_status: str | None = None`
- `mismatch_detector.py`: `_OPTICODDS_CANONICAL` dict does NOT exist yet (confirmed by reading file — only `_ODDSBLAZE_CANONICAL` exists)
- `Event` model: `opticodds_status` column already present
- `opticodds_consumer.py`: `_OPTICODDS_CANONICAL` already defined IN THE CONSUMER FILE (lines 48-64), not in mismatch_detector.py
- `opticodds_consumer.py`: `_alert_unknown_status()` with Redis SETNX dedup already exists
- Redis health keys: all written and wired to `/health/workers`

**What Phase 13 actually needs to build:**
1. `_write_opticodds_status()` helper (or inline logic) in `opticodds_consumer.py` — fuzzy match + DB write + status_match recompute + SSE publish
2. `_alert_special_status()` function in `opticodds_consumer.py` — reuses dedup pattern from `_alert_unknown_status()`, fires for walkover/retired/suspended
3. Add `_OPTICODDS_CANONICAL` to `mismatch_detector.py` — currently only in consumer; needs to be in detector for `compute_status_match` to use (D-09). The existing dict in `opticodds_consumer.py` maps to `not_started/live/ended` but `mismatch_detector.py` canonical dicts map to `scheduled/inprogress/final` — this needs reconciliation (see Pitfall 1)
4. Update `source_toggle.py` SOURCE_COLUMN_MAP to include `opticodds` → `opticodds_status`
5. Update all 5-param `compute_status_match` callers to pass `event.opticodds_status` as 6th arg

### Call Sites That Need Updating (MISM-01 / D-11)

Grep confirmed 8 call sites in app workers that pass only 5 arguments (without `opticodds_status`):

| File | Line | Context |
|------|------|---------|
| `poll_prophetx.py` | ~207 | New event creation (passes 5 `None`s — pass `None` for opticodds too) |
| `poll_prophetx.py` | ~235 | Existing event non-authoritative update |
| `poll_prophetx.py` | ~253 | Existing event WS-authoritative recompute |
| `poll_prophetx.py` | ~298 | Stale event marked ended |
| `poll_prophetx.py` | ~314 | Full recompute pass over all events |
| `poll_sports_data.py` | ~648 | Non-flag status update |
| `ws_prophetx.py` | ~155 | Event deleted → marked ended |
| `ws_prophetx.py` | ~221 | New event creation (passes 5 `None`s) |
| `ws_prophetx.py` | ~248 | Existing event update |
| `source_toggle.py` | ~57 | Source clear and recompute |
| `poll_odds_api.py` | ~254 | Event status update |
| `poll_espn.py` | ~291 | Event status update |
| `poll_oddsblaze.py` | ~273 | Event status update |

Each of these passes 5 positional args. Since `opticodds_status` is already the 6th optional param (default `None`), these calls technically work today but do not pass the event's actual `opticodds_status`. Phase 13 must update them to pass `event.opticodds_status` (or `existing.opticodds_status` etc.) so the mismatch detector sees the real value.

### Canonical Map Location Decision

The `_OPTICODDS_CANONICAL` dict currently lives in `opticodds_consumer.py` (lines 48-64) mapping raw status → `not_started/live/ended`. The `mismatch_detector.py` canonical dicts (`_ODDSBLAZE_CANONICAL`, `_SDIO_CANONICAL`, etc.) map to `scheduled/inprogress/final`. These are DIFFERENT namespaces.

D-09 says to add `_OPTICODDS_CANONICAL` to `mismatch_detector.py`. The dict in `mismatch_detector.py` must use `scheduled/inprogress/final` terminology to match the other source dicts there. The consumer's existing `_OPTICODDS_CANONICAL` maps to `not_started/live/ended` and is used for writing to the `opticodds_status` column — that's the raw column value. The mismatch detector's version maps the same raw input to its own `scheduled/inprogress/final` canonical form.

**Conclusion:** Two separate dicts in two places for two different purposes:
- `opticodds_consumer._OPTICODDS_CANONICAL`: raw status → column value (`not_started/live/ended`) — already exists
- `mismatch_detector._OPTICODDS_CANONICAL`: raw status → detector canonical (`scheduled/inprogress/final`) — needs to be added

### Fuzzy Matching Pattern (from poll_oddsblaze.py — direct template)

```python
# Source: backend/app/workers/poll_oddsblaze.py lines 36-37, 229-256
from difflib import SequenceMatcher
from collections import defaultdict
from datetime import date, timedelta

FUZZY_THRESHOLD = 0.75  # Tennis: 0.75 (ESPN pattern for individual sports)

def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

# Build date index once — query DB for all candidate events
index: dict[tuple[str, date], list[Event]] = defaultdict(list)
for event in candidates:
    key = (_normalize_sport(event.sport), event.scheduled_start.date())
    index[key].append(event)

# Match: check ±1 day to absorb timezone differences
match_candidates = (
    index.get(("tennis", event_date), [])
    + index.get(("tennis", event_date - timedelta(days=1)), [])
    + index.get(("tennis", event_date + timedelta(days=1)), [])
)

# Score: try both orderings (home/away conventions differ)
for db_event in match_candidates:
    forward = (_similarity(db_event.home_team, home) + _similarity(db_event.away_team, away)) / 2
    reversed_ = (_similarity(db_event.home_team, away) + _similarity(db_event.away_team, home)) / 2
    name_score = max(forward, reversed_)
    # Time proximity bonus (same as poll_espn.py)
    time_bonus = 0.0
    if db_event.scheduled_start:
        delta_hours = abs((db_event.scheduled_start - event_dt).total_seconds()) / 3600
        if delta_hours <= 1: time_bonus = 0.15
        elif delta_hours <= 6: time_bonus = 0.10
        elif delta_hours <= 12: time_bonus = 0.05
    score = name_score + time_bonus
    ...

# 12-hour guard: reject cross-day mismatches even above threshold
if best_match.scheduled_start:
    hours_apart = abs((best_match.scheduled_start - event_dt).total_seconds()) / 3600
    if hours_apart > 12:
        # Reject — unmatched
```

### DB Write Pattern (from poll_oddsblaze.py)

```python
# Source: backend/app/workers/poll_oddsblaze.py lines 118-302 (sync session pattern)
from app.db.sync_session import SyncSessionLocal
from app.monitoring.mismatch_detector import compute_status_match

with SyncSessionLocal() as session:
    candidates = session.execute(
        select(Event).where(
            Event.home_team.isnot(None),
            Event.away_team.isnot(None),
            Event.scheduled_start.isnot(None),
        )
    ).scalars().all()

    # ... fuzzy match loop ...

    if best_match and best_score >= FUZZY_THRESHOLD:
        best_match.opticodds_status = raw_status  # For special: write raw verbatim
        new_status_match = compute_status_match(
            best_match.prophetx_status,
            best_match.odds_api_status,
            best_match.sdio_status,
            best_match.espn_status,
            best_match.oddsblaze_status,
            raw_status,  # opticodds_status (6th param)
        )
        best_match.status_match = new_status_match
        best_match.last_real_world_poll = now
        _publish_update(str(best_match.id))

    session.commit()
```

**Session lifecycle (Claude's discretion):** Per-message is safest for a persistent consumer — each message independently committed. `poll_oddsblaze.py` uses one session for a whole batch. For the consumer's pika callback, one session per `_on_message()` invocation is cleaner. The callback is synchronous and low-volume (tennis only).

### Special Status Alert Pattern

```python
# Reuse _alert_unknown_status() pattern — different dedup key, different message text
SPECIAL_STATUS_DEDUP_TTL = 3600  # 1-hour dedup window (these are high-signal, infrequent)
SPECIAL_STATUSES = {"walkover", "retired", "suspended"}

def _alert_special_status(raw_status: str, event_name: str, home: str, away: str) -> None:
    """Fire Slack alert for operationally significant tennis statuses (D-07)."""
    if not settings.SLACK_WEBHOOK_URL:
        return
    try:
        r = _sync_redis.from_url(settings.REDIS_URL)
        dedup_key = f"opticodds_special_status:{raw_status}:{home}:{away}"
        if not r.set(dedup_key, "1", ex=SPECIAL_STATUS_DEDUP_TTL, nx=True):
            return
        text = (
            f":tennis: *OpticOdds tennis alert: `{raw_status}`*\n"
            f"*Event:* {event_name}\n"
            f"*Players:* {home} vs {away}\n"
            f"This status is expected but operationally significant."
        )
        WebhookClient(settings.SLACK_WEBHOOK_URL).send(text=text)
    except Exception as exc:
        log.warning("opticodds_special_status_alert_failed", error=str(exc))
```

### Source Toggle Integration

`source_toggle.py` has `SOURCE_COLUMN_MAP` that maps source key → column name. Currently missing `opticodds`. Must add:

```python
SOURCE_COLUMN_MAP = {
    "odds_api": "odds_api_status",
    "sports_data": "sdio_status",
    "espn": "espn_status",
    "oddsblaze": "oddsblaze_status",
    "opticodds": "opticodds_status",  # Add this
}
```

Also, the `clear_source_and_recompute()` function currently passes 5 args to `compute_status_match` with an inline None for the cleared column. It must be updated to pass `ev.opticodds_status` when the cleared column is not `opticodds_status`.

### _OPTICODDS_CANONICAL for mismatch_detector.py

```python
# Add to mismatch_detector.py alongside _ODDSBLAZE_CANONICAL
# Maps raw OpticOdds status values → detector canonical (scheduled/inprogress/final)
_OPTICODDS_CANONICAL: dict[str, str] = {
    "not_started":   "scheduled",
    "scheduled":     "scheduled",
    "delayed":       "scheduled",
    "start_delayed": "scheduled",
    "postponed":     "scheduled",
    "in_progress":   "inprogress",
    "live":          "inprogress",
    "suspended":     "inprogress",  # D-06: suspended → live → inprogress in canonical
    "interrupted":   "inprogress",
    "finished":      "final",
    "complete":      "final",
    "retired":       "final",       # D-06: retired → ended → final in canonical
    "walkover":      "final",       # D-06: walkover → ended → final in canonical
    "cancelled":     "final",
    "abandoned":     "final",
}
```

Note: This dict uses `scheduled/inprogress/final` to match the other canonical dicts in `mismatch_detector.py`. The `opticodds_consumer._OPTICODDS_CANONICAL` uses `not_started/live/ended` for column writes — those are two different dicts for two different purposes.

### Anti-Patterns to Avoid
- **Async session in pika callback:** pika BlockingConnection is synchronous; using async SQLAlchemy here requires `asyncio.run()` per message which is inefficient and fragile. Use `SyncSessionLocal` instead (D-12).
- **Re-querying DB per message:** Build the candidate index once per DB session (load all events, index by sport+date), then match in memory. Do not query per message.
- **Creating new events from OpticOdds:** D-03 — only update existing ProphetX events. If no match, log WARNING and continue.
- **Importing opticodds_consumer._OPTICODDS_CANONICAL in mismatch_detector:** The detector must not import from workers. The dict needs to be duplicated with `scheduled/inprogress/final` values.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Fuzzy string matching | Custom token-overlap scorer | `difflib.SequenceMatcher` | Already used by all 3 poll workers; proven threshold at 0.75 |
| Redis dedup for alerts | Custom dedup logic | `r.set(key, "1", ex=TTL, nx=True)` | Already in `_alert_unknown_status()` — exact pattern to reuse |
| SSE push | Custom publish | `_publish_update(entity_id)` | Already in `poll_oddsblaze.py` — copy helper verbatim |
| DB session management | Custom connection pool | `SyncSessionLocal()` context manager | Already in sync_session.py, used by all poll workers |

## Common Pitfalls

### Pitfall 1: Two _OPTICODDS_CANONICAL Dicts With Different Value Namespaces
**What goes wrong:** The consumer file has `_OPTICODDS_CANONICAL` mapping to `not_started/live/ended` (column values). The mismatch detector's other source dicts use `scheduled/inprogress/final`. If the consumer's dict is copied verbatim into `mismatch_detector.py`, all OpticOdds statuses will fail canonical comparison silently.
**Why it happens:** Two different purposes: one is for column storage, one is for 3-way canonical comparison.
**How to avoid:** The mismatch_detector version must use `scheduled/inprogress/final`. Map `walkover/retired → final`, `suspended → inprogress` (not `ended`/`live`).
**Warning signs:** Test `compute_status_match("live", None, None, None, None, "in_progress")` returning `False` when it should return `True`.

### Pitfall 2: DB Session Per Message vs Index Build
**What goes wrong:** Opening a new session and reloading all events for every incoming AMQP message creates N full-table scans for N messages. For a persistent consumer with high-volume tennis days, this degrades DB performance.
**Why it happens:** Copying the DB write pattern without the index-build optimization.
**How to avoid:** Follow `poll_oddsblaze.py`'s pattern: load candidates once per processing batch. For the consumer's `_on_message()`, consider loading the candidate index into module-level state and refreshing it on a timer or per-N-messages, rather than per-message. Alternatively, keep per-message sessions since tennis volume is low — but document the tradeoff.
**Warning signs:** Slow message processing times in logs; DB CPU spike during active tennis days.

### Pitfall 3: Special Status Written as Canonical vs Raw
**What goes wrong:** Writing the canonical form (`ended`) to `opticodds_status` for walkover/retired instead of the raw value. D-06 explicitly requires writing the raw value verbatim (`walkover`, `retired`, `suspended`).
**Why it happens:** Normal flow writes `_OPTICODDS_CANONICAL.get(raw_status)` to the column. Special statuses need to skip the canonical mapping for the column write.
**How to avoid:** Check `if raw_status in SPECIAL_STATUSES: best_match.opticodds_status = raw_status` (not the mapped value). The Slack alert fires using the raw value. The mismatch detector uses its own canonical map internally.
**Warning signs:** DB shows `ended` in `opticodds_status` instead of `walkover` for a walkover match; dashboard in Phase 14 would show wrong value.

### Pitfall 4: compute_status_match Call Sites Not Updated
**What goes wrong:** Updating the signature but leaving 13 call sites passing only 5 args. Python won't raise an error (6th param defaults to None), but OpticOdds data is silently excluded from mismatch detection even after it's populated.
**Why it happens:** D-11 requires grepping all call sites, which is easy to partially complete.
**How to avoid:** After updating all call sites, run `grep -n "compute_status_match(" backend/app/workers/*.py` and verify every call passes 6 args where the event has an `opticodds_status` field.
**Warning signs:** MISM-01 acceptance test fails — mismatch not detected even when opticodds and prophetx statuses disagree.

### Pitfall 5: _write_heartbeat Dead Code
**What goes wrong:** Phase 12 verifier noted `_write_heartbeat()` in the consumer appears to be dead code (never called in the current `_on_message` or main loop). If this stays broken, the `worker:heartbeat:opticodds_consumer` key is never written, which may affect health checks.
**Why it happens:** The function was scaffolded but not wired into the message loop.
**How to avoid:** Call `_write_heartbeat()` at the end of each successful `_on_message()` processing (after ack), similar to how `poll_oddsblaze.py` calls it after each full poll run. The TTL is 90s so it should be refreshed on every message arrival.
**Warning signs:** `worker:heartbeat:opticodds_consumer` key missing from Redis even when consumer is running.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `cd backend && python -m pytest tests/test_opticodds_consumer.py tests/test_mismatch_detector.py -x -q` |
| Full suite command | `cd backend && python -m pytest tests/ -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TNNS-02 | Fuzzy match scores above threshold → DB write; below threshold → WARNING, no write | unit | `pytest tests/test_opticodds_consumer.py -k "match" -x` | ❌ Wave 0 |
| TNNS-02 | No-match path logs WARNING, does not create new events | unit | same file | ❌ Wave 0 |
| TNNS-03 | Walkover/retired/suspended write raw value to opticodds_status (not canonical) | unit | `pytest tests/test_opticodds_consumer.py -k "special" -x` | ❌ Wave 0 |
| TNNS-03 | Special status Slack alert fires with dedup | unit | same file | ❌ Wave 0 |
| AMQP-03 | Redis keys opticodds:connection_state + opticodds:last_message_at present | unit | `pytest tests/test_opticodds_consumer.py -k "redis" -x` | ✅ (Phase 12) |
| MISM-01 | compute_status_match returns False when opticodds disagrees with prophetx | unit | `pytest tests/test_mismatch_detector.py -x` | ❌ Wave 0 (existing file, new tests needed) |
| MISM-01 | compute_status_match returns True when opticodds_status is None (NULL-safe) | unit | same file | ✅ (passes 6 None args — already tested) |

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/test_opticodds_consumer.py tests/test_mismatch_detector.py -x -q`
- **Per wave merge:** `cd backend && python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_opticodds_consumer.py` — new test classes for fuzzy match (TNNS-02), special status write (TNNS-03), special status Slack alert (TNNS-03), _write_heartbeat wiring, _on_message DB write path
- [ ] `tests/test_mismatch_detector.py` — new test class `TestComputeStatusMatchOpticOdds` with cases: opticodds disagrees → False, opticodds agrees → True, opticodds None → True (NULL-safe per MISM-01)

*(Existing test infrastructure covers all other infrastructure. Only new behavior tests need to be added.)*

## Environment Availability

Step 2.6: SKIPPED for most tools — all dependencies already deployed and verified in Phase 12. The consumer service is already running in production.

| Dependency | Required By | Available | Notes |
|------------|------------|-----------|-------|
| SyncSessionLocal | DB writes | ✓ | `backend/app/db/sync_session.py` confirmed |
| SequenceMatcher | Fuzzy matching | ✓ | stdlib, no install needed |
| pika | AMQP consumer | ✓ | In `pyproject.toml` deps, installed in Phase 12 |
| slack_sdk | Special status alerts | ✓ | In `pyproject.toml` deps |
| redis (sync) | Alert dedup | ✓ | In `pyproject.toml` deps |

## Sources

### Primary (HIGH confidence)
- Direct code read: `backend/app/workers/poll_oddsblaze.py` — complete fuzzy match template, FUZZY_THRESHOLD=0.80, SequenceMatcher, SyncSessionLocal pattern, SSE publish
- Direct code read: `backend/app/workers/poll_espn.py` — FUZZY_THRESHOLD=0.75 for individual sports (tennis/MMA), identical time-proximity bonus
- Direct code read: `backend/app/monitoring/mismatch_detector.py` — confirmed 6-param `compute_status_match` signature already in place; `_OPTICODDS_CANONICAL` NOT yet present; only `_ODDSBLAZE_CANONICAL` exists
- Direct code read: `backend/app/workers/opticodds_consumer.py` — `_OPTICODDS_CANONICAL` present (maps to `not_started/live/ended`); `_alert_unknown_status()` dedup pattern present; `_write_heartbeat()` defined but never called in message path
- Direct code read: `backend/app/models/event.py` — `opticodds_status` column confirmed present
- Direct code read: `backend/app/workers/source_toggle.py` — SOURCE_COLUMN_MAP confirmed missing `opticodds` entry
- Grep: all 13 `compute_status_match` call sites in app workers confirmed — all pass 5 positional args without opticodds_status

### Secondary (MEDIUM confidence)
- `.planning/research/SUMMARY.md` — OpticOdds message schema field names are MEDIUM confidence; consumer logs raw messages for first 5 to validate

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all pre-existing, production-confirmed
- Architecture: HIGH — direct template in codebase, no ambiguity
- Pitfalls: HIGH — identified from direct code reading, not speculation
- Fuzzy threshold: MEDIUM-HIGH — 0.75 is ESPN's proven value for tennis; reasonable starting point, may need tuning once real messages flow

**Research date:** 2026-04-03
**Valid until:** Stable — no external dependencies changing. Valid until Phase 14.
