---
phase: quick
plan: 260330-nvd
subsystem: data-sources
tags: [oddsblaze, polling, celery, frontend, mismatch-detection]
depends_on: []
provides: [oddsblaze-source-integration]
affects: [mismatch-detector, event-model, dashboard, beat-scheduler, source-toggle]
tech_stack:
  added: [OddsBlazeClient, poll_oddsblaze Celery task, Alembic migration 007]
  patterns: [BaseAPIClient extension, fuzzy-match team names, canonical status mapping]
key_files:
  created:
    - backend/app/clients/oddsblaze_api.py
    - backend/app/workers/poll_oddsblaze.py
    - backend/alembic/versions/007_add_oddsblaze_status.py
  modified:
    - backend/app/core/config.py
    - backend/app/models/event.py
    - backend/app/schemas/event.py
    - backend/app/monitoring/mismatch_detector.py
    - backend/app/seed.py
    - backend/app/workers/celery_app.py
    - backend/app/workers/beat_bootstrap.py
    - backend/app/workers/source_toggle.py
    - backend/app/workers/poll_odds_api.py
    - backend/app/workers/poll_espn.py
    - backend/app/workers/poll_sports_api.py
    - backend/app/workers/poll_sports_data.py
    - backend/app/workers/poll_prophetx.py
    - backend/app/workers/ws_prophetx.py
    - backend/app/workers/poll_critical_check.py
    - frontend/src/api/events.ts
    - frontend/src/components/EventsTable.tsx
    - .env.example
decisions:
  - OddsBlaze status derived from `live` boolean + start time offset: live/scheduled/final (3 values map cleanly to canonical)
  - Poll interval set to 120s (no published rate limits from OddsBlaze)
  - Minimum floor set to 30s (conservative — can loosen per OddsBlaze ToS)
  - compute_status_match/compute_is_critical extended with optional oddsblaze_status param to preserve backward compatibility with existing call sites that only pass 4-5 args
metrics:
  duration: "~25 minutes"
  completed: "2026-03-30"
  tasks: 2
  files_changed: 19
---

# Quick Task 260330-nvd: Integrate OddsBlaze API as New Data Source

**One-liner:** OddsBlaze integrated as 6th real-world data source with schedule fetching, fuzzy team-name matching, canonical status mapping (live/scheduled/final), mismatch detector participation, beat scheduling, source toggle support, and dashboard column.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Backend — API client, DB migration, config, all wiring | c5cdb68 | 19 files (3 new, 16 modified) |
| 2 | Frontend — OddsBlaze status column in dashboard | 1e9fae6 | 2 files modified |

## What Was Built

### Backend

**OddsBlazeClient** (`backend/app/clients/oddsblaze_api.py`)
- Extends `BaseAPIClient` with `get_schedule(league_id)` method
- `LEAGUE_MAP` maps ProphetX sport names to OddsBlaze league IDs (nba, wnba, mlb, nfl, ncaaf, ufc, usa-mls, england-premier-league, france-ligue-1, spain-laliga)

**poll_oddsblaze Celery task** (`backend/app/workers/poll_oddsblaze.py`)
- Named `app.workers.poll_oddsblaze.run`, bind=True, max_retries=3
- Early exit if `ODDSBLAZE_API_KEY` not set
- Checks `is_source_enabled("oddsblaze")`, clears column if disabled
- Queries active sports from DB, maps to relevant OddsBlaze leagues via LEAGUE_MAP
- Derives status: `live=true` -> "live"; `live=false + >3h past start` -> "final"; else -> "scheduled"
- Fuzzy-matches by team names + date (same SequenceMatcher approach as poll_odds_api.py)
- 12-hour guard against cross-day mismatches
- Calls `compute_status_match()` with all 6 source statuses
- Writes heartbeat to `worker:heartbeat:poll_oddsblaze`
- Calls `_increment_call_counter("poll_oddsblaze")`
- Publishes SSE updates via Redis `prophet:updates` channel

**Alembic migration 007** — adds nullable `oddsblaze_status String(50)` column to events table

**Mismatch detector** — `_ODDSBLAZE_CANONICAL` dict added; both `compute_status_match` and `compute_is_critical` extended with `oddsblaze_status: str | None = None` parameter

**All 9 call sites updated** to pass `oddsblaze_status`:
- poll_odds_api.py (1 call)
- poll_espn.py (1 call)
- poll_sports_api.py (1 call)
- poll_sports_data.py (1 call)
- poll_prophetx.py (3 calls)
- ws_prophetx.py (2 calls)
- poll_critical_check.py (compute_is_critical, 1 call)

**source_toggle.py** — `"oddsblaze": "oddsblaze_status"` added to `SOURCE_COLUMN_MAP`; `clear_source_and_recompute` passes oddsblaze_status conditionally

**beat_bootstrap.py** — oddsblaze entries added to `WORKER_TASK_MAP`, `BEAT_NAME_MAP`, `_FALLBACK_INTERVALS` (120s)

**seed.py** — `poll_interval_oddsblaze` (120s default), `poll_interval_oddsblaze_min` (30s floor), `source_enabled_oddsblaze` ("true") added

**config.py** — `ODDSBLAZE_API_KEY: str | None = None` and `POLL_INTERVAL_ODDSBLAZE: int = 120` added

**.env.example** — `ODDSBLAZE_API_KEY=your-oddsblaze-api-key` added

### Frontend

**EventRow interface** — `oddsblaze_status: string | null` added

**EventsTable** — `"oddsblaze_status"` added to `SortCol` union, `STATUS_COLS` Set; sortable "OddsBlaze" header column placed after ESPN column; `SourceStatus` cell in each row; empty-state `colSpan` updated from 11 to 12

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all data flows wired end-to-end. The `oddsblaze_status` column will show "Not Listed" in the dashboard until `ODDSBLAZE_API_KEY` is set and the poller runs. This is expected behavior matching all other optional sources.

## Activation

Set in `.env`:
```
ODDSBLAZE_API_KEY=4a41989d-e7bb-4333-99ac-100bc93e96d4
```

Then run the DB migration and restart services:
```bash
docker compose exec backend alembic upgrade head
docker compose restart worker beat
```

## Self-Check: PASSED

- backend/app/clients/oddsblaze_api.py: FOUND
- backend/app/workers/poll_oddsblaze.py: FOUND
- backend/alembic/versions/007_add_oddsblaze_status.py: FOUND
- Commits c5cdb68 and 1e9fae6: FOUND
- All backend assertions: PASSED
- Frontend grep checks: PASSED
