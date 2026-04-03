---
phase: 14
slug: dashboard-and-health
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-03
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (backend) / vitest or manual (frontend) |
| **Config file** | `backend/pyproject.toml` |
| **Quick run command** | `cd backend && python -m pytest tests/ -x -q --timeout=30` |
| **Full suite command** | `cd backend && python -m pytest tests/ -q --timeout=60` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/ -x -q --timeout=30`
- **After every plan wave:** Run `cd backend && python -m pytest tests/ -q --timeout=60`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 1 | DASH-01 | unit | `python -m pytest tests/test_health.py -q` | ✅ | ⬜ pending |
| 14-01-02 | 01 | 1 | DASH-02 | unit | `python -m pytest tests/test_events.py -q` | ✅ | ⬜ pending |
| 14-01-03 | 01 | 1 | DASH-01 | manual | Browser: check SystemHealth badge | N/A | ⬜ pending |
| 14-01-04 | 01 | 1 | DASH-02 | manual | Browser: check events table column | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| OpticOdds badge renders green/red with tooltip | DASH-01 | Visual verification | Open dashboard, check SystemHealth row for OpticOdds badge |
| OpticOdds column shows status for tennis events | DASH-02 | Visual verification | Open events table, verify tennis events show opticodds_status |
| Non-tennis events show dash in OpticOdds column | DASH-02 | Visual verification | Open events table, verify non-tennis events show "Not Listed" |
| Badge updates within 30s of state change | DASH-01 | Timing verification | Toggle consumer, wait 30s, verify badge reflects new state |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
