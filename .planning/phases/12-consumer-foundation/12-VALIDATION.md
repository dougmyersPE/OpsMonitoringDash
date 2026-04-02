---
phase: 12
slug: consumer-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-02
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | `backend/pytest.ini` |
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
| 12-01-01 | 01 | 1 | TNNS-01 | migration | `cd backend && alembic upgrade head && alembic check` | ❌ W0 | ⬜ pending |
| 12-02-01 | 02 | 1 | AMQP-01 | unit | `cd backend && python -m pytest tests/test_opticodds_consumer.py -x -q` | ❌ W0 | ⬜ pending |
| 12-02-02 | 02 | 1 | AMQP-02 | unit | `cd backend && python -m pytest tests/test_opticodds_consumer.py::test_reconnect -x -q` | ❌ W0 | ⬜ pending |
| 12-03-01 | 03 | 2 | AMQP-01 | integration | `docker compose ps opticodds-consumer --format json` | ❌ W0 | ⬜ pending |
| 12-03-02 | 03 | 2 | AMQP-02 | integration | `docker compose logs opticodds-consumer 2>&1 \| grep -c "backoff"` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_opticodds_consumer.py` — stubs for AMQP-01, AMQP-02, TNNS-01
- [ ] `backend/tests/conftest.py` — shared fixtures (already exists, may need pika/mock additions)

*Existing pytest infrastructure covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Docker container restart recovery | AMQP-01 | Requires `docker kill` + wait for restart | `docker kill opticodds-consumer && sleep 5 && docker compose ps opticodds-consumer` |
| RabbitMQ reconnect with backoff | AMQP-02 | Requires live broker connection drop | Stop RabbitMQ, watch consumer logs for backoff delays, restart RabbitMQ |
| Queue start REST call on startup | AMQP-01 | Requires live OpticOdds API | Check consumer startup logs for queue name + Redis cache entry |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
