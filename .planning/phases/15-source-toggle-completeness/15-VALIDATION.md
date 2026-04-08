---
phase: 15
slug: source-toggle-completeness
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-07
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | backend/pytest.ini |
| **Quick run command** | `cd backend && python -m pytest tests/ -x -q --timeout=30` |
| **Full suite command** | `cd backend && python -m pytest tests/ -v --timeout=60` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/ -x -q --timeout=30`
- **After every plan wave:** Run `cd backend && python -m pytest tests/ -v --timeout=60`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 15-01-01 | 01 | 1 | TOGL-05 | unit | `pytest tests/test_usage.py -k source_toggle` | ❌ W0 | ⬜ pending |
| 15-01-02 | 01 | 1 | TOGL-01 | unit | `pytest tests/test_usage.py -k oddsblaze` | ❌ W0 | ⬜ pending |
| 15-02-01 | 02 | 1 | TOGL-02 | unit | `pytest tests/test_poll_oddsblaze.py -k disabled` | ❌ W0 | ⬜ pending |
| 15-02-02 | 02 | 1 | TOGL-03 | unit | `pytest tests/test_poll_opticodds.py -k disabled` | ❌ W0 | ⬜ pending |
| 15-03-01 | 03 | 2 | TOGL-04 | unit | `pytest tests/test_prophetx_ws.py -k disabled` | ❌ W0 | ⬜ pending |
| 15-04-01 | 04 | 2 | TOGL-06 | integration | `pytest tests/test_toggle_e2e.py -k reenable` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Test stubs created during plan execution (no separate Wave 0 needed — tests co-created with implementation)

*Existing test infrastructure covers framework needs. Test files created alongside implementation tasks.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ProphetX WS health badge stays green when disabled | TOGL-04 | Requires live WS connection | 1. Disable prophetx_ws toggle 2. Check health endpoint shows green 3. Verify no new ws-sourced audit entries |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
