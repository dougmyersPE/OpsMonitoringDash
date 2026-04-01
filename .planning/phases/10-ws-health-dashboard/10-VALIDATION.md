---
phase: 10
slug: ws-health-dashboard
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-01
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (backend) / vitest (frontend) |
| **Config file** | `backend/pytest.ini` / `frontend/vitest.config.ts` |
| **Quick run command** | `cd backend && python -m pytest tests/ -x -q --timeout=10` |
| **Full suite command** | `cd backend && python -m pytest tests/ -q --timeout=30 && cd ../frontend && npx vitest run` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/ -x -q --timeout=10`
- **After every plan wave:** Run `cd backend && python -m pytest tests/ -q --timeout=30 && cd ../frontend && npx vitest run`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | WSHLT-01 | unit | `python -m pytest tests/test_health.py -x -q` | ✅ | ⬜ pending |
| 10-01-02 | 01 | 1 | WSHLT-01 | unit | `python -m pytest tests/test_ws_diagnostics.py -x -q` | ✅ | ⬜ pending |
| 10-02-01 | 02 | 2 | WSHLT-02 | component | `npx vitest run` | ❌ W0 | ⬜ pending |
| 10-02-02 | 02 | 2 | WSHLT-03 | component | `npx vitest run` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Frontend test setup if not present — vitest config and component test utilities
- [ ] `tests/test_health.py` — add `TestWorkerHealthWsProphetX` test class stubs for WSHLT-01
- [ ] `tests/test_ws_diagnostics.py` — extend with `ws:connection_state_since` key assertions

*Existing backend infrastructure covers most requirements. Frontend component tests may need setup.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| WS badge visual appearance matches worker badges | WSHLT-02 | CSS styling verification | Inspect dashboard, confirm green/red pill matches existing worker badges |
| Tooltip shows state + relative time | WSHLT-03 | Browser tooltip rendering | Hover WS badge, verify "ProphetX WS: {state}\nSince: {time}" format |
| Badge updates within 30s of state change | WSHLT-03 | Timing-dependent behavior | Toggle WS connection, observe badge update within poll cycle |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
