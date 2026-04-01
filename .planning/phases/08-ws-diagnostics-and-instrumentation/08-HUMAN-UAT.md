---
status: partial
phase: 08-ws-diagnostics-and-instrumentation
source: [08-VERIFICATION.md]
started: 2026-03-31T00:00:00Z
updated: 2026-03-31T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Reconnect reconciliation fires after actual WS reconnect
expected: In staging/production, disconnect the WS consumer (kill -9 or network drop) and watch Celery logs for `poll_prophetx_started trigger=ws_reconnect`. Within seconds of pysher re-establishing the connection, the task log line should appear.
result: [pending]

### 2. Redis ws:* keys visible and updating during a live WS session
expected: In production (or staging with a live WS connection), run `redis-cli KEYS 'ws:*'` — all four keys exist and are non-empty. `ws:connection_state` is `"connected"`. `ws:last_message_at` is a recent ISO timestamp. `ws:sport_event_count` is an integer >= 0.
result: [pending]

### 3. Production gate — ws:sport_event_count increments on sport_event messages
expected: After deploying to production and waiting 24-48h covering live game windows, `redis-cli GET ws:sport_event_count` returns > 0, confirming ProphetX broadcasts sport_event change-type messages. If zero, escalate to ProphetX support.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
