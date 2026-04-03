---
phase: 12
slug: consumer-foundation
status: draft
nyquist_compliant: true
wave_0_complete: true
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

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| 12-01-01 | 01 | 1 | TNNS-01 | migration | `cd backend && alembic upgrade head && alembic check` | pending |
| 12-01-02 | 01 | 1 | TNNS-01 | grep | `grep -q 'opticodds_status' backend/app/models/event.py` | pending |
| 12-02-01 | 02 | 2 | AMQP-01 | syntax+behavioral | `python -c "import ast; ast.parse(open('backend/app/workers/opticodds_consumer.py').read())" && grep -q 'heartbeat=30' backend/app/workers/opticodds_consumer.py && grep -q 'auto_ack=False' backend/app/workers/opticodds_consumer.py && grep -q '_stop_queue' backend/app/workers/opticodds_consumer.py && grep -q '_alert_unknown_status' backend/app/workers/opticodds_consumer.py` | pending |
| 12-02-02 | 02 | 2 | AMQP-01,AMQP-02 | unit | `cd backend && python -m pytest tests/test_opticodds_consumer.py -x -q --timeout=10` | pending |
| 12-03-01 | 03 | 2 | AMQP-01 | grep | `grep -q 'opticodds-consumer' docker-compose.yml && grep -q 'opticodds_consumer' backend/app/api/v1/health.py` | pending |
| 12-03-02 | 03 | 2 | AMQP-01 | unit | `cd backend && python -m pytest tests/test_health.py -x -v --timeout=10` | pending |

*Status: pending / green / red / flaky*

---

## Nyquist Compliance Notes

Plan 02 uses an implementation-first approach (Task 1: write consumer, Task 2: write tests). This is intentional:
- Task 1's `<automated>` verify includes **behavioral grep checks** (heartbeat=30, auto_ack=False, _stop_queue in shutdown, _alert_unknown_status for Slack, WebhookClient import) beyond basic syntax validation.
- Task 2 provides full behavioral unit test coverage immediately after Task 1.
- No 3 consecutive tasks pass without automated feedback — Task 1 has behavioral grep verification, Task 2 has pytest.
- This satisfies Nyquist: every task has automated verification; behavioral coverage arrives within 2 tasks.

---

## Wave 0 Status

Wave 0 test scaffolding is NOT required as a separate step because:
1. Plan 01 (Wave 1) is config/migration only — verified by grep and alembic commands.
2. Plan 02 Task 1 has behavioral grep checks in its `<automated>` block.
3. Plan 02 Task 2 creates the full test suite immediately after Task 1.
4. Plan 03 Task 2 extends existing `test_health.py` (already has fixtures/infrastructure).

The test file `backend/tests/test_opticodds_consumer.py` is created as part of Plan 02 Task 2, which is in the same plan as the implementation. No separate Wave 0 plan needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Docker container restart recovery | AMQP-01 | Requires `docker kill` + wait for restart | `docker kill opticodds-consumer && sleep 5 && docker compose ps opticodds-consumer` |
| RabbitMQ reconnect with backoff | AMQP-02 | Requires live broker connection drop | Stop RabbitMQ, watch consumer logs for backoff delays, restart RabbitMQ |
| Queue start REST call on startup | AMQP-01 | Requires live OpticOdds API | Check consumer startup logs for queue name + Redis cache entry |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify with behavioral checks
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Nyquist compliant: behavioral grep checks in Task 1, full pytest in Task 2
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending execution
