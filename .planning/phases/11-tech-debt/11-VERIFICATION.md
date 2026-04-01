---
phase: 11-tech-debt
verified: 2026-04-01T20:00:00Z
status: passed
score: 7/7 must-haves verified
human_verification:
  - test: "Load Events table in browser and confirm Sports API column is absent"
    expected: "Table shows ProphetX, Odds API, SDIO, ESPN, OddsBlaze columns only"
    why_human: "Column rendering is visual; grep confirms TSX structure is correct but visual confirmation is fastest assurance"
  - test: "Load API Usage page and confirm no Sports API toggle, interval slider, quota card, or chart line"
    expected: "Only active sources (Odds API, SportsDataIO, ESPN) appear"
    why_human: "Component removal verified in code; runtime rendering and interaction not testable via grep"
---

# Phase 11: Tech Debt Verification Report

**Phase Goal:** Sports API integration fully removed — client, worker, DB column, and all references eliminated
**Verified:** 2026-04-01T20:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Sports API client and poll worker no longer exist in the codebase | VERIFIED | `backend/app/clients/sports_api.py` and `backend/app/workers/poll_sports_api.py` confirmed absent; `test ! -f` checks pass |
| 2 | Event model has no sports_api_status column | VERIFIED | `backend/app/models/event.py` — grep for `sports_api_status` returns no match; migration 009 drops the column |
| 3 | Mismatch detector does not reference Sports API in any function | VERIFIED | `mismatch_detector.py` contains no `sports_api` string; `_SPORTS_API_FLAG_STATUSES`, `_SPORTS_API_CANONICAL`, and `_sports_api_to_canonical()` are all absent |
| 4 | Health endpoint does not check poll_sports_api heartbeat | VERIFIED | `health.py` result indices are `[0]`–`[3]` for 4 workers (prophetx, sports_data, odds_api, espn); ws_state at `[4]`, ws_since at `[5]` — no poll_sports_api key present |
| 5 | Usage endpoint does not track Sports API quota or calls | VERIFIED | `usage.py` has no `SPORTS_API_FAMILIES`, no `poll_sports_api` in WORKER_NAMES or INTERVAL_KEYS, no sports_api quota section |
| 6 | Celery does not register or schedule poll_sports_api | VERIFIED | `celery_app.py` include list and `beat_bootstrap.py` WORKER_TASK_MAP, BEAT_NAME_MAP, and _FALLBACK_INTERVALS have no sports_api entries |
| 7 | All compute_status_match calls pass 4 source args (odds_api, sdio, espn, oddsblaze) not 5 | VERIFIED | Every call site verified: ws_prophetx (3 calls), poll_prophetx (5 calls), poll_odds_api (1), poll_espn (1), poll_oddsblaze (1), poll_sports_data (1), source_toggle (1), poll_critical_check uses compute_is_critical with same 5-param form — all pass exactly (px, odds_api, sdio, espn, oddsblaze) |

**Score:** 7/7 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/alembic/versions/009_drop_sports_api_status.py` | Migration dropping sports_api_status column | VERIFIED | Exists; `op.drop_column("events", "sports_api_status")` in upgrade(); `down_revision = "008"` correctly chains from migration 008 |
| `backend/app/clients/sports_api.py` | DELETED | VERIFIED | File does not exist |
| `backend/app/workers/poll_sports_api.py` | DELETED | VERIFIED | File does not exist |
| `frontend/src/components/usage/SportsApiQuotaCard.tsx` | DELETED | VERIFIED | File does not exist |
| `backend/app/monitoring/mismatch_detector.py` | Mismatch detection without Sports API | VERIFIED | 274 lines; `compute_status_match` has 5-param signature `(px_status, odds_api_status, sdio_status, espn_status=None, oddsblaze_status=None)`; `compute_is_critical` has same 5-param form; `compute_is_flagged` has 1-param form `(sdio_status)`; no Sports API canonical dict or flag set present |
| `frontend/src/components/EventsTable.tsx` | Events table without Sports API column | VERIFIED | No `sports_api_status` in SortCol union, STATUS_COLS set, headers, or body cells; colSpan updated to 10 |
| `frontend/src/components/SystemHealth.tsx` | Health badges without Sports API worker | VERIFIED | No `poll_sports_api` in WorkerHealth interface or WORKERS array |
| `frontend/src/api/events.ts` | EventRow type without sports_api_status | VERIFIED | EventRow has 5 status fields: prophetx_status, odds_api_status, sdio_status, espn_status, oddsblaze_status — no sports_api_status |
| `.planning/ROADMAP.md` | Phase 11 goal updated to removal language | VERIFIED | Goal reads: "Sports API integration fully removed — client, worker, DB column, and all references eliminated" |
| `.planning/REQUIREMENTS.md` | DEBT-01 updated to removal language | VERIFIED | DEBT-01 reads: "Sports API integration fully removed (client, worker, DB column, config, frontend references)"; traceability table shows Complete |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `backend/app/monitoring/mismatch_detector.py` | All poll workers | `compute_status_match` signature change | VERIFIED | All 7 worker call sites pass 5 args — px + 4 sources; no 6th sports_api_status arg anywhere |
| `frontend/src/api/events.ts` | `frontend/src/components/EventsTable.tsx` | EventRow type | VERIFIED | EventRow has no `sports_api_status`; EventsTable imports EventRow and renders no Sports API column |

---

### Data-Flow Trace (Level 4)

Not applicable for this phase. The work is removal, not new data rendering. The relevant data flows (4-source mismatch detection) are verified via signature checks at all call sites.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Migration 009 has correct drop_column call | `grep "op.drop_column" .../009_drop_sports_api_status.py` | `op.drop_column("events", "sports_api_status")` | PASS |
| Migration 009 chains from 008 | `grep down_revision .../009_drop_sports_api_status.py` | `down_revision = "008"` | PASS |
| Backend grep returns zero sports_api matches | `grep -r "sports_api" backend/app/ --include="*.py" --exclude-dir=__pycache__` | No matches | PASS |
| Frontend grep returns zero sports_api matches | `grep -r "sports_api" frontend/src/ --include="*.ts" --include="*.tsx"` | No matches | PASS |
| compute_status_match signature | Direct file read of mismatch_detector.py lines 204–210 | `(px_status, odds_api_status, sdio_status, espn_status=None, oddsblaze_status=None)` — 5 params | PASS |
| compute_is_flagged signature | Direct file read of mismatch_detector.py line 140 | `(sdio_status: str \| None)` — 1 param | PASS |
| health.py ws result indices | `grep "results\[" health.py` | ws_state at `results[4]`, ws_since at `results[5]`, 4 workers at `[0]`–`[3]` | PASS |
| source_toggle SOURCE_COLUMN_MAP | `grep SOURCE_COLUMN_MAP source_toggle.py` | Contains odds_api, sports_data, espn, oddsblaze — no sports_api | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DEBT-01 | 11-01-PLAN.md, 11-02-PLAN.md | Sports API integration fully removed (client, worker, DB column, config, frontend references) | SATISFIED | Client and worker deleted; migration 009 drops column; config keys removed; all frontend references removed; mismatch functions reduced to 4-source signatures |

No orphaned requirements: DEBT-01 is the only requirement mapped to Phase 11 in REQUIREMENTS.md, and it is claimed by both plans.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `frontend/src/lib/statusDisplay.ts` | 31–61 | Comments label status codes (ns, tbd, 1h, ht, 2h, etc.) as "Sports API (api-sports.io)"; the codes remain in the mapping | Info | These status codes will never be populated in the DB since the Sports API source is gone — they are dead mapping entries. The `normalizeStatus` function is a pure display utility; no data flows through these entries. Not a blocker. This file was not in scope for 11-01 or 11-02 task lists. |
| `backend/alembic/versions/004_rename_api_football_to_sports_api.py` | 1–20 | Historical migration referencing sports_api in column rename | Info | This is a historical migration file that must remain to preserve migration chain integrity. The column it created is dropped by 009. Not a defect. |

No blockers found.

---

### Human Verification Required

#### 1. Events Table Column Layout

**Test:** Open the dashboard Events table in a browser.
**Expected:** Table shows exactly 5 source status columns — ProphetX, Odds API, SDIO, ESPN, OddsBlaze. No Sports API column present. colSpan on empty-state row shows 10 (not 11).
**Why human:** Column rendering is visual; TSX structure is verified correct but a browser render confirms the full layout.

#### 2. API Usage Page — Active Sources Only

**Test:** Open the API Usage page in a browser and inspect the Quota section, Interval section, Source Toggles section, Call Volume chart, and Projection card.
**Expected:** Sports API quota card, interval slider, source toggle, chart line, and projection entry are all absent. Only Odds API, SportsDataIO, and ESPN appear.
**Why human:** Each component's code is verified clean, but runtime rendering confirms no residual references appear through any conditional paths.

---

### Gaps Summary

No gaps. All 7 observable truths are verified, all required artifacts exist in their expected state, all key links are confirmed wired, and no blocker anti-patterns were found.

The only notes of record are:
- `statusDisplay.ts` retains dead status code entries with stale "Sports API" comments — cosmetic, not functional. These codes will never appear in data since the source is removed.
- Migration 004 historically references `sports_api` in its name and body — this is correct and must not be altered.

Both 11-01 (backend) and 11-02 (frontend + docs) plans are complete and DEBT-01 is satisfied.

---

_Verified: 2026-04-01T20:00:00Z_
_Verifier: Claude (gsd-verifier)_
