---
phase: 09
slug: status-authority-model
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-31
---

# Phase 09 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.23 |
| **Config file** | `backend/pyproject.toml` (`[tool.pytest.ini_options]`, asyncio_mode="auto") |
| **Quick run command** | `cd backend && python -m pytest tests/test_status_authority.py -x -q` |
| **Full suite command** | `cd backend && python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/test_status_authority.py -x -q`
- **After every plan wave:** Run `cd backend && python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | AUTH-01 | unit | `pytest tests/test_status_authority.py::TestWsAuthorityColumns -x` | ❌ W0 | ⬜ pending |
| 09-01-02 | 01 | 1 | AUTH-02 | unit | `pytest tests/test_status_authority.py::TestAuthorityHelper -x` | ❌ W0 | ⬜ pending |
| 09-01-03 | 01 | 1 | AUTH-02 | unit | `pytest tests/test_status_authority.py::TestPollAuthorityColumns -x` | ❌ W0 | ⬜ pending |
| 09-01-04 | 01 | 1 | AUTH-03 | unit | `pytest tests/test_status_authority.py::TestPollAuthorityColumns::test_poll_updates_metadata_inside_window -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_status_authority.py` — stubs for AUTH-01, AUTH-02, AUTH-03
- [ ] Authority helper fixtures in test file

*Existing infrastructure (pytest, conftest) covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| WS authority window observed in production | AUTH-02 | Requires live ProphetX WS connection | Deploy, wait for WS status delivery, verify poll_prophetx log shows `authority_window_skip` within 10 minutes |
| status_source visible in DB via admin query | AUTH-01 | Database inspection | `SELECT prophetx_event_id, prophetx_status, status_source, ws_delivered_at FROM events WHERE status_source IS NOT NULL LIMIT 10` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
