---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: WebSocket-Primary Status Authority
status: planning
last_updated: "2026-03-31"
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-31)

**Core value:** Operators always know the true health of their ProphetX platform — stale event statuses and low-liquidity markets are caught and resolved before they impact bettors.
**Current focus:** v1.2 — WebSocket-primary status authority

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-03-31 — Milestone v1.2 started

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

### Pending Todos

(none)

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260330-nvd | Integrate OddsBlaze API as new data source | 2026-03-30 | fd00e64 | [260330-nvd-integrate-oddsblaze-api-as-new-data-sour](./quick/260330-nvd-integrate-oddsblaze-api-as-new-data-sour/) |
| 260331-fmz | Auto-purge events older than 48h regardless of status | 2026-03-31 | 18a9d61 | [260331-fmz-auto-purge-events-older-than-48-hours-fr](./quick/260331-fmz-auto-purge-events-older-than-48-hours-fr/) |

### Blockers/Concerns

- SDIO NFL/NCAAB/NCAAF endpoints 404 (off-season; deferred to v2 when seasons resume)
- ProphetX write endpoint still stubbed (log-only until PATCH path confirmed)
- SportsApiClient bypasses BaseAPIClient (architecturally inconsistent, functional)
- SDIO data lag: some games (spring training baseball, occasional EPL) stay `Scheduled` in SDIO even when live — SDIO-side issue, not ours
- WS consumer receives zero `sport_event` change_type messages (only market_selections/matched_bet) — needs investigation with ProphetX on whether broadcast channel carries status changes

### Resolved

- ProphetX base URL: `https://cash.api.prophetx.co/partner` — production, switched from sandbox 2026-03-02
- ProphetX status enum values confirmed: `ended`, `live`, `not_started`
- Sports API false-positive root cause: fixed in Phase 4
- RedBeat restart overwrite: fixed in Phase 5 (DB-backed bootstrap)
- Login endpoint now returns role in response (was defaulting all users to "operator")
- ESPN time guard fixed: uses actual event datetime instead of fake noon UTC
- Logout button added to sidebar
- Auto-sync status regression: stale SDIO data was overwriting ProphetX's correct `live` status back to `not_started` — lifecycle guard added (2026-03-04)
- SDIO soccer endpoint: was using `GamesByDateFinal` (completed games only) instead of `GamesByDate` (all games) — fixed (2026-03-04)
- poll_prophetx was not updating `last_prophetx_poll` timestamp — fixed (2026-03-04)
- Docker Compose: all services now have `restart: unless-stopped` for server reboot resilience (2026-03-04)

## Session Continuity

Last activity: 2026-03-31 - Completed quick task 260331-fmz: Auto-purge events older than 48h regardless of status
Last session: 2026-03-31T15:15:34Z
Stopped at: Quick task 260331-fmz complete — auto-purge events older than 48h
What happened this session:
  - Quick task 260331-fmz: cleanup_old_events.py now purges ALL events >48h regardless of status (commit 18a9d61)
  - Also cleans up orphaned event_id_mappings and notifications for purged events
  - 7 unit tests added and passing
Next: Deploy to production server via rsync + docker compose rebuild
