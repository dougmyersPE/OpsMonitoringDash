---
phase: 13
slug: status-processing-and-matching
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-03
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | backend/pyproject.toml |
| **Quick run command** | `cd backend && source .venv/bin/activate && set -a && source ../.env && set +a && python -m pytest tests/test_opticodds_consumer.py tests/test_mismatch_detector.py -q --tb=short` |
| **Full suite command** | `cd backend && source .venv/bin/activate && set -a && source ../.env && set +a && python -m pytest tests/ -q --tb=short` |
| **Estimated runtime** | ~5 seconds (unit tests only) |

---

## Sampling Rate

- **After every task commit:** Run quick run command
- **After every plan wave:** Run full suite command
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 1 | MISM-01 | unit | `pytest tests/test_mismatch_detector.py -q` | ✅ | ⬜ pending |
| 13-01-02 | 01 | 1 | MISM-01 | unit | `pytest tests/test_mismatch_detector.py -q` | ✅ | ⬜ pending |
| 13-02-01 | 02 | 2 | TNNS-02 | unit | `pytest tests/test_opticodds_consumer.py -q` | ✅ | ⬜ pending |
| 13-02-02 | 02 | 2 | TNNS-03 | unit | `pytest tests/test_opticodds_consumer.py -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. pytest, test fixtures, and mock patterns are already established from Phase 12.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| OpticOdds fixture matched to correct ProphetX event | TNNS-02 | Requires live OpticOdds messages with real fixture data | Deploy, observe logs for match hits/misses |
| Slack alert fires for walkover/retired/suspended | TNNS-03 | Requires Slack webhook + live message flow | Simulate or wait for tennis special status, check Slack channel |
| Redis connection state keys present | AMQP-03 | Requires running consumer | `redis-cli GET opticodds:connection_state` after deploy |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
