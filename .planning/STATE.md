---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Stabilization + API Usage
status: shipped
last_updated: "2026-03-04"
progress:
  total_phases: 7
  completed_phases: 7
  total_plans: 18
  completed_plans: 18
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-02)

**Core value:** Operators always know the true health of their ProphetX platform — stale event statuses and low-liquidity markets are caught and resolved before they impact bettors.
**Current focus:** Ad-hoc bugfixes deployed; planning next milestone

## Current Position

Milestone: v1.1 SHIPPED (2026-03-02)
All milestones complete. Run `/gsd:new-milestone` to start next version.

Progress: [██████████] 100% (v1.1 SHIPPED)

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
Last session: 2026-03-04T21:35:25Z
Stopped at: Ad-hoc bugfixes deployed, all services running stable
What happened this session:
  - Added `restart: unless-stopped` to all 8 Docker Compose services (commit a800b0e)
  - Fixed poll_prophetx not writing `last_prophetx_poll` on upsert (commit 71f3ac8)
  - Fixed auto-sync regressing ProphetX status — lifecycle guard prevents backward moves (commit 60323b9)
  - Fixed SDIO soccer using `GamesByDateFinal` instead of `GamesByDate` (commit 03b4ef6)
  - Root-caused ProphetX `not_started` bug: SDIO worker mismatch detector was overwriting correct `live` status
  - Docker already set to start on boot (`systemctl is-enabled docker` = enabled)
  - Server has no git repo — code deployed via `scp` + `docker compose build/up`
Next: Run `/gsd:new-milestone` to start next version
