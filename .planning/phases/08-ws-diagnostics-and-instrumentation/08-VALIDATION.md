---
phase: 8
slug: ws-diagnostics-and-instrumentation
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-31
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `backend/pyproject.toml` |
| **Quick run command** | `cd backend && python -m pytest tests/ -x -q --timeout=10` |
| **Full suite command** | `cd backend && python -m pytest tests/ -v --timeout=30` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/ -x -q --timeout=10`
- **After every plan wave:** Run `cd backend && python -m pytest tests/ -v --timeout=30`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Test File | Status |
|---------|------|------|-------------|-----------|-------------------|-----------|--------|
| 08-01-01 | 01 | 1 | WSREL-02 | unit | `pytest tests/test_ws_upsert.py tests/test_mismatch_detector.py -x -q` | test_ws_upsert.py, test_mismatch_detector.py | ⬜ pending |
| 08-01-02 | 01 | 1 | WSREL-01 | unit | `pytest tests/test_ws_reconnect.py -x -q` | test_ws_reconnect.py | ⬜ pending |
| 08-01-03 | 01 | 1 | WSREL-01 | unit | `pytest tests/test_ws_diagnostics.py -x -q` | test_ws_diagnostics.py | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

All test files are created by their respective tasks (TDD red-green cycle). No separate Wave 0 needed.

- Task 1 creates `backend/tests/test_ws_upsert.py` and extends `backend/tests/test_mismatch_detector.py`
- Task 2 creates `backend/tests/test_ws_reconnect.py`
- Task 3 creates `backend/tests/test_ws_diagnostics.py`

*Existing pytest infrastructure and conftest.py cover framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `ws:sport_event_count > 0` in production | WSREL-01 (gate) | Requires live ProphetX WS feed with active game windows | `docker compose exec redis redis-cli get ws:sport_event_count` after 24-48h covering live games |
| Redis keys updating during live WS session | WSREL-01 | Requires live WS connection | `docker compose exec redis redis-cli mget ws:connection_state ws:last_message_at ws:last_sport_event_at ws:sport_event_count` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands (pytest invocations)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covered — each task creates its own test file via TDD
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
