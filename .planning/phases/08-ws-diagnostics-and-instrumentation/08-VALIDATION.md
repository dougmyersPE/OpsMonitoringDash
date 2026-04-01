---
phase: 8
slug: ws-diagnostics-and-instrumentation
status: draft
nyquist_compliant: false
wave_0_complete: false
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

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | WSREL-02 | unit | `pytest tests/test_ws_prophetx.py -k status_match` | ❌ W0 | ⬜ pending |
| 08-01-02 | 01 | 1 | WSREL-01 | unit | `pytest tests/test_ws_prophetx.py -k reconnect_reconciliation` | ❌ W0 | ⬜ pending |
| 08-02-01 | 02 | 1 | WSREL-01 | unit | `pytest tests/test_ws_prophetx.py -k redis_diagnostics` | ❌ W0 | ⬜ pending |
| 08-02-02 | 02 | 1 | WSREL-01 | integration | `pytest tests/test_ws_prophetx.py -k ws_connection_state` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_ws_prophetx.py` — stubs for WSREL-01 and WSREL-02 verification
- [ ] `backend/tests/conftest.py` — mock Redis and Celery fixtures (extend existing)

*Existing pytest infrastructure covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `ws:sport_event_count > 0` in production | WSREL-01 (gate) | Requires live ProphetX WS feed with active game windows | `docker compose exec redis redis-cli get ws:sport_event_count` after 24-48h covering live games |
| Redis keys updating during live WS session | WSREL-01 | Requires live WS connection | `docker compose exec redis redis-cli mget ws:connection_state ws:last_message_at ws:last_sport_event_at ws:sport_event_count` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
