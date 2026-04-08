---
gsd_state_version: 1.0
milestone: v1.4
milestone_name: Source Toggle Completeness
status: "Ready for /gsd:plan-phase 15"
stopped_at: Phase 15 context gathered
last_updated: "2026-04-08T01:08:01.124Z"
last_activity: 2026-04-03 — v1.4 roadmap created
progress:
  total_phases: 15
  completed_phases: 7
  total_plans: 12
  completed_plans: 12
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-07)

**Core value:** Operators always know the true health of their ProphetX platform — stale event statuses and low-liquidity markets are caught and resolved before they impact bettors.
**Current focus:** v1.4 Phase 15 — Source Toggle Completeness

## Current Position

Phase: 15 — Source Toggle Completeness
Plan: Not started
Status: Ready for /gsd:plan-phase 15
Last activity: 2026-04-03 — v1.4 roadmap created

## Performance Metrics

**Velocity:**

- Total plans completed: 20 (v1.0–v1.3)
- Average duration: ~30 min/plan (estimated from v1.2 actuals)
- Total execution time: ~10 hours

**By Phase:**

| Phase | Plans | Avg/Plan |
|-------|-------|----------|
| v1.0 (Phases 1-3) | 11 | ~27 min |
| v1.1 (Phases 4-7) | 7 | ~21 min |
| v1.2 (Phases 8-11) | 6 | ~13 min |
| v1.3 (Phases 12-14) | 6 | ~30 min |

*Updated after each plan completion*
| Phase 12 P03 | 15 | 2 tasks | 3 files |
| Phase 12-consumer-foundation P02 | 4 | 2 tasks | 2 files |
| Phase 13-status-processing-and-matching P01 | 10 | 2 tasks | 10 files |
| Phase 13 P02 | 7 | 2 tasks | 2 files |
| Phase 14-dashboard-and-health P01 | 15 | 2 tasks | 5 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Phase 11]: compute_status_match reduced to 5-param signature (px + odds_api, sdio, espn, oddsblaze) — Phase 13 extends to 6-param with opticodds
- [Phase 10]: ws_prophetx health returned as nested object with connected/state/since — opticodds_consumer should follow same shape
- [v1.3 research]: Standalone Docker service only — pika BlockingConnection blocks indefinitely; Celery incompatible
- [Phase 12-01]: OpticOdds credentials use str|None=None defaults so deployments without credentials do not fail on startup
- [Phase 12]: opticodds-consumer Docker service mirrors ws-consumer exactly (128m memory, restart: unless-stopped, standalone service per D-06)
- [Phase 13-status-processing-and-matching]: compute_status_match extended to 6-param (opticodds_status); NULL-safe design means non-tennis events are unaffected; all 13 call sites updated in poll workers + ws consumer + source_toggle
- [Phase 13]: FUZZY_THRESHOLD=0.75 for tennis — player names are abbreviated/transliterated more, requiring looser threshold
- [Phase 14-dashboard-and-health]: Reused WsProphetXHealth interface for opticodds_consumer field (same connected/state/since shape)
- [v1.4 context]: OddsBlaze + OpticOdds toggle backend already implemented (source_toggle.py) — v1.4 work is primarily frontend wiring for those two + new ProphetX WS toggle backend behavior

### Pending Todos

(none)

### Blockers/Concerns

- SDIO NFL/NCAAB/NCAAF endpoints 404 (off-season; deferred until seasons resume)
- ProphetX write endpoint still stubbed (log-only until PATCH path confirmed)
- TOGL-05/TOGL-06: verify OddsBlaze and OpticOdds toggle wiring is live end-to-end before marking complete

### Resolved

- Phase 8 gate (critical): ws:sport_event_count > 0 confirmed in production — Phase 9 unblocked
- Sports API fully removed (Phase 11)
- WS health badge deployed (Phase 10)
- ProphetX base URL: `https://cash.api.prophetx.co/partner` — production, switched from sandbox 2026-03-02
- v1.3 shipped: OpticOdds tennis integration complete (Phases 12-14)

## Session Continuity

Last session: 2026-04-08T01:08:01.116Z
Stopped at: Phase 15 context gathered
Resume file: .planning/phases/15-source-toggle-completeness/15-CONTEXT.md
