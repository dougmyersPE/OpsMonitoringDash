---
phase: 10
slug: ws-health-dashboard
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-01
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (backend) / TypeScript compiler (frontend) |
| **Config file** | `backend/pytest.ini` / `frontend/tsconfig.json` |
| **Quick run command** | `cd backend && uv run pytest tests/ -x -q --timeout=10` |
| **Full suite command** | `cd backend && uv run pytest tests/ -q --timeout=30 && cd frontend && npx tsc --noEmit` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run pytest tests/ -x -q --timeout=10`
- **After every plan wave:** Run `cd backend && uv run pytest tests/ -q --timeout=30 && cd frontend && npx tsc --noEmit`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | WSHLT-01 | unit | `uv run pytest tests/test_health.py tests/test_ws_diagnostics.py -x -q` | Yes | pending |
| 10-01-02 | 01 | 1 | WSHLT-02, WSHLT-03 | compile | `cd frontend && npx tsc --noEmit` | Yes | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

None — all test infrastructure is already in place:
- pytest is configured and working for backend tests
- TypeScript compiler serves as the frontend verification (no vitest needed; this phase adds no frontend test files, only production code verified by `tsc --noEmit`)
- `test_health.py` and `test_ws_diagnostics.py` already exist and will be extended in Task 1

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| WS badge visual appearance matches worker badges | WSHLT-02 | CSS styling verification | Inspect dashboard, confirm green/red pill matches existing worker badges |
| Tooltip shows state + relative time | WSHLT-03 | Browser tooltip rendering | Hover WS badge, verify "ProphetX WS: {state}\nSince: {time}" format |
| Badge updates within 30s of state change | WSHLT-03 | Timing-dependent behavior | Toggle WS connection, observe badge update within poll cycle |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none needed)
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready
