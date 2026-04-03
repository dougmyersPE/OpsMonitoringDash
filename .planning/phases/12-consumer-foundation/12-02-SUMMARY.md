---
phase: 12-consumer-foundation
plan: "02"
subsystem: amqp-consumer
tags: [amqp, rabbitmq, pika, consumer, opticodds, health-keys, slack-alerts, unit-tests]
dependency_graph:
  requires: ["12-01"]
  provides: ["opticodds_consumer.py standalone AMQP consumer with queue lifecycle, reconnect, health keys, Slack alerts"]
  affects: ["backend/app/workers/opticodds_consumer.py", "backend/tests/test_opticodds_consumer.py"]
tech_stack:
  added: ["pika>=1.3.2 (AMQP consumer, already in pyproject.toml)"]
  patterns:
    - "pika BlockingConnection with heartbeat=30, auto_ack=False, prefetch_count=10"
    - "Exponential backoff reconnect 5s-60s with jitter (mirrors ws_prophetx.py)"
    - "Redis health keys: worker:heartbeat:opticodds_consumer (90s TTL), opticodds:connection_state (120s TTL), opticodds:last_message_at (90s TTL)"
    - "Slack alerting via slack_sdk WebhookClient with Redis SETNX dedup (mirrors poll_critical_check.py)"
    - "Status mapping via explicit dict _OPTICODDS_CANONICAL (15 statuses, no default fallthrough)"
key_files:
  created:
    - "backend/app/workers/opticodds_consumer.py (302 lines)"
    - "backend/tests/test_opticodds_consumer.py (375 lines)"
  modified: []
decisions:
  - "D-01 to D-10 all implemented: self-managing queue lifecycle, pika BlockingConnection with heartbeat=30 and manual ack, exponential backoff with jitter, Redis health keys, SIGTERM cleanup, raw message logging, and Slack alerts for unknown statuses via slack_sdk with Redis SETNX dedup"
  - "Phase 12 scope boundary respected: consumer receives, acks, logs — DB writes (opticodds_status column) deferred to Phase 13 (TNNS-02 fuzzy matching)"
  - "pika installed into .venv via uv pip install pika (already in pyproject.toml dependencies)"
metrics:
  duration: "~4 minutes"
  completed_date: "2026-04-03"
  tasks_completed: 2
  files_changed: 2
---

# Phase 12 Plan 02: OpticOdds AMQP Consumer Summary

**One-liner:** Standalone pika BlockingConnection consumer with self-managing queue lifecycle (REST start/stop), exponential backoff reconnect, Redis health keys, and Slack alerts for unknown tennis statuses via WebhookClient with SETNX dedup.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create opticodds_consumer.py | 3e5e681 | backend/app/workers/opticodds_consumer.py |
| 2 | Unit tests for opticodds_consumer | 6131a48 | backend/tests/test_opticodds_consumer.py |

## What Was Built

### opticodds_consumer.py (302 lines)

Standalone AMQP consumer module mirroring `ws_prophetx.py` architecture with 8 sections:

1. **Imports and state** — `_message_count` counter for D-10 raw logging, `UNKNOWN_STATUS_DEDUP_TTL = 300`
2. **`_OPTICODDS_CANONICAL`** — 15 status mappings: not_started/scheduled/delayed/start_delayed/postponed → not_started; in_progress/live/suspended/interrupted → live; finished/complete/retired/walkover/cancelled/abandoned → ended
3. **Queue lifecycle** — `_start_queue()` POSTs to `settings.OPTICODDS_BASE_URL`, caches queue_name in Redis, calls `sys.exit(1)` on failure; `_stop_queue()` calls stop URL (best-effort, never raises)
4. **Slack alert helper** — `_alert_unknown_status()` with Redis SETNX dedup at `opticodds_unknown_status:{raw_status}` key; skips silently if already alerted within 5 minutes
5. **Redis health helpers** — `_write_heartbeat()` (90s), `_write_connection_state()` (120s), `_write_last_message_at()` (90s)
6. **`_on_message()`** — raw body DEBUG logging (first 5 messages), status mapping, unknown status WARNING + Slack alert, manual ack/nack
7. **`run()`** — `_start_queue()` then infinite loop with pika BlockingConnection, heartbeat=30, blocked_connection_timeout=300, auto_ack=False, prefetch=10, exponential backoff with jitter
8. **Entry point** — `__main__` sets up SIGTERM/SIGINT handlers calling `_stop_queue()` before exit

### test_opticodds_consumer.py (375 lines, 13 tests)

All tests mock external dependencies (httpx, pika, redis, slack_sdk) — no running services needed:

- `TestStartQueueSuccess` — verifies POST URL, X-Api-Key header, Redis cache, return value
- `TestStartQueueFailure` — verifies `sys.exit(1)` on HTTPStatusError
- `TestStopQueueNoRaise` — verifies ConnectionError doesn't propagate
- `TestOnMessageAck` — verifies `basic_ack` called on valid JSON message
- `TestOnMessageNack` — verifies `basic_nack(requeue=True)` on invalid JSON
- `TestRawLoggingCounter` — verifies exactly 5 `opticodds_raw_message` debug logs for 6 messages
- `TestCanonicalMapping` — verifies in_progress→live, finished→ended, not_started→not_started, walkover/retired→ended, 15+ total entries
- `TestUnknownStatusWarning` — verifies WARNING log with `raw_status` kwarg
- `TestWriteConnectionStateRedis` — verifies both connection_state keys (120s TTL) and heartbeat key (90s TTL)
- `TestUnknownStatusSlackAlert` — verifies WebhookClient instantiated, `.send()` called with status; dedup test verifies WebhookClient NOT called when Redis returns False; no-webhook-URL test verifies early return

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pika not installed in .venv**
- **Found during:** Task 2 test execution
- **Issue:** `pika` was listed in `pyproject.toml` dependencies but not installed in the `.venv`
- **Fix:** `uv pip install pika` — installed pika 1.3.2
- **Files modified:** None (dependency installation only)
- **Commit:** N/A (environment fix)

## Decisions Made

1. **Phase 12 scope boundary enforced:** The consumer receives, acks, and logs messages but does NOT write to `opticodds_status` DB column. DB writes require fuzzy matching to identify which event row to update — that is Phase 13 scope (TNNS-02). The `_write_opticodds_status()` function will be added in Phase 13.

2. **Slack alert via WebhookClient (not Celery):** The consumer is a standalone process (not Celery), so it cannot use `send_alerts.run.delay()`. Uses `slack_sdk.webhook.WebhookClient` with Redis SETNX dedup directly, mirroring the `poll_critical_check.py` pattern.

## Known Stubs

None — the consumer is complete for Phase 12 scope. The only intentional non-implementation is DB writes, which are explicitly deferred to Phase 13 per the plan boundary documented in the file's module docstring.

## Self-Check: PASSED

- [x] `backend/app/workers/opticodds_consumer.py` exists (302 lines)
- [x] `backend/tests/test_opticodds_consumer.py` exists (375 lines, 13 tests)
- [x] Commit `3e5e681` exists (feat: opticodds_consumer.py)
- [x] Commit `6131a48` exists (test: unit tests)
- [x] All 13 tests pass with 0 failures
- [x] All 26 acceptance criteria from plan verified
