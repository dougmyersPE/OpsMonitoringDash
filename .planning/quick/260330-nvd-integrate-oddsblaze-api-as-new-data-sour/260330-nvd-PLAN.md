---
phase: quick
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  # Backend
  - backend/app/core/config.py
  - backend/app/clients/oddsblaze_api.py
  - backend/app/workers/poll_oddsblaze.py
  - backend/app/workers/celery_app.py
  - backend/app/workers/beat_bootstrap.py
  - backend/app/workers/source_toggle.py
  - backend/app/models/event.py
  - backend/app/schemas/event.py
  - backend/app/monitoring/mismatch_detector.py
  - backend/app/seed.py
  - backend/alembic/versions/007_add_oddsblaze_status.py
  - .env.example
  # Frontend
  - frontend/src/api/events.ts
  - frontend/src/components/EventsTable.tsx
autonomous: true
requirements: []
must_haves:
  truths:
    - "OddsBlaze schedule data is fetched periodically for all leagues that have active events in DB"
    - "Fetched OddsBlaze statuses are fuzzy-matched to ProphetX events and stored in oddsblaze_status column"
    - "OddsBlaze status participates in mismatch detection and is_critical computation"
    - "Dashboard displays OddsBlaze status column between ESPN and Flag columns"
    - "OddsBlaze source can be toggled on/off like other sources"
  artifacts:
    - path: "backend/app/clients/oddsblaze_api.py"
      provides: "OddsBlaze API client extending BaseAPIClient"
    - path: "backend/app/workers/poll_oddsblaze.py"
      provides: "Celery poll task following poll_odds_api.py pattern"
    - path: "backend/alembic/versions/007_add_oddsblaze_status.py"
      provides: "DB migration adding oddsblaze_status column to events"
  key_links:
    - from: "backend/app/workers/poll_oddsblaze.py"
      to: "backend/app/clients/oddsblaze_api.py"
      via: "OddsBlazeClient import"
    - from: "backend/app/workers/poll_oddsblaze.py"
      to: "backend/app/monitoring/mismatch_detector.py"
      via: "compute_status_match call including oddsblaze_status"
    - from: "backend/app/workers/beat_bootstrap.py"
      to: "backend/app/workers/poll_oddsblaze.py"
      via: "WORKER_TASK_MAP entry for oddsblaze"
---

<objective>
Integrate OddsBlaze as the 6th real-world data source in the OpsMonitoringDash, following the
exact patterns established by the 5 existing sources (SDIO, Odds API, Sports API, ESPN, ProphetX).

Purpose: OddsBlaze provides schedule/live status data for NBA, MLB, NFL, NCAAF, UFC, WNBA, MLS,
EPL, Ligue 1, La Liga — broadening status cross-referencing coverage.

Output: Complete end-to-end integration: API client, Celery poller, DB column, mismatch detector
participation, frontend column, beat scheduling, source toggle support.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@backend/app/clients/base.py
@backend/app/clients/odds_api.py
@backend/app/workers/poll_odds_api.py
@backend/app/workers/poll_espn.py
@backend/app/workers/celery_app.py
@backend/app/workers/beat_bootstrap.py
@backend/app/workers/source_toggle.py
@backend/app/models/event.py
@backend/app/schemas/event.py
@backend/app/monitoring/mismatch_detector.py
@backend/app/seed.py
@backend/app/core/config.py
@frontend/src/api/events.ts
@frontend/src/components/EventsTable.tsx
@.env.example

<interfaces>
<!-- OddsBlaze API details (from docs.oddsblaze.com) -->

Schedule endpoint: GET https://api.oddsblaze.com/v2/schedule/{league_id}.json?key={api_key}
- Optional params: date (YYYY-MM-DD), live (true/false), team, id
- Response: { updated, league: {id, name, sport}, events: [{id, teams: {away: {id, name, abbreviation}, home: {id, name, abbreviation}}, date, live}] }
- `live` field is a boolean: true = in progress, false = not started / completed
- No "completed" field — derive from context (past start time + not live = ended)

Leagues endpoint: GET https://api.oddsblaze.com/v2/leagues.json (no auth needed)
- Returns: [{id, name, sport}]
- Available leagues: cfl, england-premier-league, france-ligue-1, mlb, nba, ncaaf, nfl, spain-laliga, ufc, usa-mls, wnba

Auth: query param `key` on all authenticated endpoints.

<!-- Existing patterns from codebase -->

From backend/app/clients/base.py:
  class BaseAPIClient:
    def __init__(self, base_url: str, timeout: float = 10.0)
    async def _get(self, path: str, **kwargs) -> dict | list

From backend/app/models/event.py:
  class Event(Base):
    odds_api_status, sports_api_status, sdio_status, espn_status: Mapped[str | None]

From backend/app/monitoring/mismatch_detector.py:
  def compute_status_match(px, odds_api, sports_api, sdio, espn=None) -> bool
  def compute_is_critical(px, odds_api, sports_api, sdio, espn) -> bool
  # Both need a new oddsblaze_status parameter

From backend/app/workers/source_toggle.py:
  SOURCE_COLUMN_MAP = { "odds_api": "odds_api_status", ... }
  # Needs "oddsblaze": "oddsblaze_status" entry
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Backend — API client, DB migration, config, and all wiring</name>
  <files>
    backend/app/core/config.py
    backend/app/clients/oddsblaze_api.py
    backend/app/workers/poll_oddsblaze.py
    backend/app/workers/celery_app.py
    backend/app/workers/beat_bootstrap.py
    backend/app/workers/source_toggle.py
    backend/app/models/event.py
    backend/app/schemas/event.py
    backend/app/monitoring/mismatch_detector.py
    backend/app/seed.py
    backend/alembic/versions/007_add_oddsblaze_status.py
    .env.example
  </files>
  <action>
    Follow the exact patterns from poll_odds_api.py and odds_api.py. Every step below references
    the specific existing file to mirror.

    **1. config.py** — Add to Settings class:
    ```python
    ODDSBLAZE_API_KEY: str | None = None
    POLL_INTERVAL_ODDSBLAZE: int = 120  # 2 min — OddsBlaze has no published rate limits
    ```

    **2. .env.example** — Add line:
    ```
    ODDSBLAZE_API_KEY=your-oddsblaze-api-key
    ```

    **3. backend/app/clients/oddsblaze_api.py** — New file. Extend BaseAPIClient:
    ```python
    BASE_URL = "https://api.oddsblaze.com/v2"

    # ProphetX sport name (lowercase) -> OddsBlaze league IDs
    LEAGUE_MAP: dict[str, list[str]] = {
        "basketball": ["nba", "wnba"],
        "baseball": ["mlb"],
        "american football": ["nfl", "ncaaf"],
        "mma": ["ufc"],
        "soccer": ["usa-mls", "england-premier-league", "france-ligue-1", "spain-laliga"],
    }

    class OddsBlazeClient(BaseAPIClient):
        def __init__(self, api_key: str | None = None):
            super().__init__(base_url=BASE_URL)
            self._api_key = api_key or settings.ODDSBLAZE_API_KEY

        async def get_schedule(self, league_id: str) -> list[dict]:
            """Fetch schedule for a league. Returns list of event dicts."""
            raw = await self._get(
                f"/schedule/{league_id}.json",
                params={"key": self._api_key},
            )
            events = raw.get("events", []) if isinstance(raw, dict) else []
            log.info("oddsblaze_schedule_fetched", league=league_id, count=len(events))
            return events
    ```

    **4. backend/app/models/event.py** — Add column after `espn_status`:
    ```python
    oddsblaze_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ```

    **5. Alembic migration** — Create `backend/alembic/versions/007_add_oddsblaze_status.py`.
    Follow the pattern from 005_add_espn_status.py. Add nullable String(50) column `oddsblaze_status`
    to `events` table. Revision ID should be auto-generated. Down migration drops the column.

    **6. backend/app/schemas/event.py** — Add `oddsblaze_status: str | None` field to EventResponse.
    Update `is_critical` computed field to pass `self.oddsblaze_status` to compute_is_critical.

    **7. backend/app/monitoring/mismatch_detector.py**:
    - Add `_ODDSBLAZE_CANONICAL` dict mapping OddsBlaze statuses to canonical form:
      ```python
      _ODDSBLAZE_CANONICAL: dict[str, str] = {
          "live": "inprogress",      # live=true in schedule response
          "scheduled": "scheduled",   # live=false, event in future
          "final": "final",           # live=false, event in past
      }
      ```
    - Update `compute_status_match()` signature: add `oddsblaze_status: str | None = None` parameter.
      Add it to the `sources` list alongside the others: `(oddsblaze_status, _ODDSBLAZE_CANONICAL)`.
    - Update `compute_is_critical()` signature: add `oddsblaze_status: str | None` parameter.
      Add it to the `sources` list.
    - IMPORTANT: Update ALL callers of compute_status_match and compute_is_critical across the
      codebase to pass the new parameter. Search for all call sites:
      - poll_odds_api.py: pass `best_match.oddsblaze_status`
      - poll_espn.py: pass `event.oddsblaze_status`
      - poll_sports_api.py (if exists): pass the oddsblaze_status
      - poll_sports_data.py (if exists): pass the oddsblaze_status
      - poll_critical_check.py: pass the oddsblaze_status
      - source_toggle.py clear_source_and_recompute: pass oddsblaze_status (conditionally None if clearing oddsblaze)

    **8. backend/app/workers/poll_oddsblaze.py** — New file. Follow poll_odds_api.py pattern exactly:
    - Celery task named `app.workers.poll_oddsblaze.run` with `bind=True, max_retries=3`
    - Early exit if `ODDSBLAZE_API_KEY` not set
    - Check `is_source_enabled("oddsblaze")`, call `clear_source_and_recompute("oddsblaze")` if disabled
    - Query active sports from DB, map to OddsBlaze league IDs via LEAGUE_MAP
    - Fetch schedule for each relevant league
    - Derive status from each event:
      - If `live` is True -> "live"
      - If `live` is False and event `date` is in the past (> 3 hours ago) -> "final"
      - Otherwise -> "scheduled"
    - Fuzzy-match by team names + date (same SequenceMatcher approach as poll_odds_api.py)
    - Set `event.oddsblaze_status` on matched events
    - Call `compute_status_match()` with all 6 source statuses (including oddsblaze)
    - Write heartbeat to `worker:heartbeat:poll_oddsblaze`
    - Call `_increment_call_counter("poll_oddsblaze")`
    - Publish SSE update via Redis `prophet:updates` channel

    **9. backend/app/workers/celery_app.py** — Add to `include` list:
    ```python
    "app.workers.poll_oddsblaze",
    ```

    **10. backend/app/workers/beat_bootstrap.py** — Add entries:
    ```python
    WORKER_TASK_MAP["oddsblaze"] = "app.workers.poll_oddsblaze.run"
    BEAT_NAME_MAP["oddsblaze"] = "poll-oddsblaze"
    _FALLBACK_INTERVALS["oddsblaze"] = 120.0
    ```

    **11. backend/app/workers/source_toggle.py** — Add to SOURCE_COLUMN_MAP:
    ```python
    "oddsblaze": "oddsblaze_status",
    ```
    Also update `clear_source_and_recompute` to pass oddsblaze_status to compute_status_match
    (the function now takes the new parameter — ensure it's conditionally None when clearing oddsblaze).

    **12. backend/app/seed.py** — Add to INTERVAL_DEFAULTS:
    ```python
    "poll_interval_oddsblaze": str(settings.POLL_INTERVAL_ODDSBLAZE),  # 120
    ```
    Add to INTERVAL_MINIMUMS:
    ```python
    "poll_interval_oddsblaze_min": "30",
    ```
    Add to SOURCE_ENABLED_DEFAULTS:
    ```python
    "source_enabled_oddsblaze": ("true", "Enable OddsBlaze polling source"),
    ```
  </action>
  <verify>
    <automated>cd /Users/doug/OpsMonitoringDash/backend && python -c "
from app.clients.oddsblaze_api import OddsBlazeClient, LEAGUE_MAP
from app.models.event import Event
from app.schemas.event import EventResponse
from app.monitoring.mismatch_detector import compute_status_match, compute_is_critical, _ODDSBLAZE_CANONICAL
from app.workers.source_toggle import SOURCE_COLUMN_MAP
from app.workers.beat_bootstrap import WORKER_TASK_MAP, BEAT_NAME_MAP
from app.core.config import Settings
import inspect
# Verify new column exists on model
assert hasattr(Event, 'oddsblaze_status'), 'Missing oddsblaze_status on Event model'
# Verify schema has it
assert 'oddsblaze_status' in EventResponse.model_fields, 'Missing oddsblaze_status in schema'
# Verify mismatch detector has canonical map
assert 'live' in _ODDSBLAZE_CANONICAL
# Verify compute_status_match accepts oddsblaze param
sig = inspect.signature(compute_status_match)
assert 'oddsblaze_status' in sig.parameters, 'compute_status_match missing oddsblaze_status param'
# Verify source toggle
assert 'oddsblaze' in SOURCE_COLUMN_MAP
# Verify beat bootstrap
assert 'oddsblaze' in WORKER_TASK_MAP
assert 'oddsblaze' in BEAT_NAME_MAP
# Verify config has the key
assert 'ODDSBLAZE_API_KEY' in Settings.model_fields
print('All backend checks passed')
"</automated>
  </verify>
  <done>
    - OddsBlazeClient class exists extending BaseAPIClient with get_schedule method
    - poll_oddsblaze.py Celery task fetches schedules, fuzzy-matches, updates oddsblaze_status
    - Event model has oddsblaze_status column with Alembic migration
    - compute_status_match and compute_is_critical include oddsblaze_status in calculations
    - Beat bootstrap, source toggle, seed all include oddsblaze entries
    - All existing callers of compute_status_match/compute_is_critical updated with new param
    - ODDSBLAZE_API_KEY in config.py and .env.example
  </done>
</task>

<task type="auto">
  <name>Task 2: Frontend — Add OddsBlaze status column to dashboard</name>
  <files>
    frontend/src/api/events.ts
    frontend/src/components/EventsTable.tsx
  </files>
  <action>
    **1. frontend/src/api/events.ts** — Add to EventRow interface:
    ```typescript
    oddsblaze_status: string | null;
    ```

    **2. frontend/src/components/EventsTable.tsx** — Three changes:

    a) Add `"oddsblaze_status"` to the `SortCol` type union (after `"espn_status"`).

    b) Add `"oddsblaze_status"` to the `STATUS_COLS` Set.

    c) Add a new sortable header column and data cell for OddsBlaze. Place it AFTER the ESPN
       column and BEFORE the Flag column. The header should read "OddsBlaze":

       In TableHeader, after the ESPN SortableHead:
       ```tsx
       <SortableHead col="oddsblaze_status" sortCol={sortCol} sortDir={sortDir} onSort={handleSort}>OddsBlaze</SortableHead>
       ```

       In each TableRow, after the ESPN SourceStatus cell:
       ```tsx
       <TableCell><SourceStatus status={event.oddsblaze_status} /></TableCell>
       ```

    d) Update the empty-state colSpan from 11 to 12 to account for the new column.
  </action>
  <verify>
    <automated>cd /Users/doug/OpsMonitoringDash/frontend && grep -q "oddsblaze_status" src/api/events.ts && grep -q "oddsblaze_status" src/components/EventsTable.tsx && grep -q "OddsBlaze" src/components/EventsTable.tsx && echo "Frontend checks passed"</automated>
  </verify>
  <done>
    - EventRow type includes oddsblaze_status field
    - EventsTable displays OddsBlaze column between ESPN and Flag
    - Column is sortable like other source status columns
    - colSpan updated for empty state row
  </done>
</task>

</tasks>

<verification>
1. Backend imports validate: `python -c "from app.workers.poll_oddsblaze import run; from app.clients.oddsblaze_api import OddsBlazeClient"`
2. Alembic migration generates correctly: `cd backend && alembic heads` shows new migration
3. Frontend grep confirms OddsBlaze column present in EventsTable
4. All existing compute_status_match callers pass oddsblaze_status (grep for call sites)
</verification>

<success_criteria>
- OddsBlaze client, poller, migration, config, seed, beat bootstrap, source toggle all wired
- Mismatch detector includes OddsBlaze in status comparison and critical detection
- Frontend shows OddsBlaze status column in the events table
- No regressions to existing 5 source integrations
- Setting ODDSBLAZE_API_KEY=4a41989d-e7bb-4333-99ac-100bc93e96d4 in .env enables polling
</success_criteria>

<output>
After completion, create `.planning/quick/260330-nvd-integrate-oddsblaze-api-as-new-data-sour/260330-nvd-SUMMARY.md`
</output>
