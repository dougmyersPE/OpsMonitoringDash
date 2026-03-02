---
phase: 03-dashboard-and-alerts
plan: "02"
subsystem: api
tags: [sse, redis, pubsub, slack, celery, fastapi, jwt, heartbeat, alert-dedup]

# Dependency graph
requires:
  - phase: 02-monitoring-engine
    provides: "poll_prophetx, poll_sports_data workers; send_alerts stub; update_event_status; SystemConfig model"
  - phase: 03-dashboard-and-alerts plan 01
    provides: "React SSE consumer (useSse hook) that connects to /api/v1/stream?token=<jwt>"
provides:
  - "SSE endpoint at /api/v1/stream with Redis pub/sub subscriber and query-param JWT auth"
  - "verify_token_from_query FastAPI dependency for ?token= auth"
  - "/health/workers endpoint reading worker:heartbeat:{name} Redis keys with 90s TTL"
  - "Redis pub/sub publish in both poll workers after every state change (event_updated, market_updated, mismatch_detected)"
  - "Worker heartbeat keys written at end of each successful poll task"
  - "Real Slack webhook delivery in send_alerts via WebhookClient with SETNX deduplication"
  - "alert_only_mode guard in update_event_status: reads system_config, skips ProphetX write when true"
  - "SLACK_WEBHOOK_URL optional setting in Settings"
affects: [03-dashboard-and-alerts]

# Tech tracking
tech-stack:
  added: [sse-starlette==3.2.0, slack-sdk==3.40.1]
  patterns:
    - "SSE auth via ?token= query param (EventSource cannot send Authorization headers)"
    - "Worker liveness via Redis heartbeat keys with TTL (not Celery inspect)"
    - "Redis SETNX deduplication for alerts: SET alert_dedup:{type}:{id} 1 NX EX 300"
    - "Alert-only mode read from system_config DB at task start (not cached)"

key-files:
  created:
    - backend/app/api/v1/stream.py
  modified:
    - backend/app/api/deps.py
    - backend/app/api/v1/health.py
    - backend/app/main.py
    - backend/app/workers/poll_prophetx.py
    - backend/app/workers/poll_sports_data.py
    - backend/app/workers/send_alerts.py
    - backend/app/workers/update_event_status.py
    - backend/app/core/config.py
    - backend/pyproject.toml
    - backend/uv.lock

key-decisions:
  - "SSE auth uses ?token= query param, not Authorization header — native EventSource API has no header support"
  - "Worker heartbeat uses Redis key TTL (90s) not Celery inspect — no Celery dependency; simpler health check"
  - "Alert deduplication window is 5 minutes (300s SETNX TTL) — matches plan ALERT-02 requirement"
  - "SLACK_WEBHOOK_URL is optional in settings (default None) — send_alerts logs warning and returns when not configured"
  - "alert_only_mode is read from system_config DB at task start — not cached — ensures real-time config changes take effect"
  - "Task 2 changes were absorbed into 03-01 commit 9a56a37 due to concurrent agent execution; code state is correct"

patterns-established:
  - "SSE pattern: EventSourceResponse with pubsub.get_message() loop, ping=20 keeps Nginx alive"
  - "_publish_update() and _write_heartbeat() as module-level helpers in each poll worker"
  - "Alert guard pattern: SETNX check first (skip if exists), then Slack send if configured"

requirements-completed: [ALERT-01, ALERT-02, ALERT-03, DASH-03, DASH-04]

# Metrics
duration: 4min
completed: 2026-02-26
---

# Phase 03 Plan 02: SSE Streaming + Slack Alerting Summary

**SSE endpoint streaming Redis pub/sub events to browser via sse-starlette, Slack alerts with SETNX deduplication via slack-sdk, and alert_only_mode guard in update_event_status**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-26T15:13:00Z
- **Completed:** 2026-02-26T15:17:27Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments

- SSE endpoint at `/api/v1/stream` with `EventSourceResponse` subscribing to `prophet:updates` Redis pub/sub channel, authenticated via `?token=<jwt>` query param
- `/health/workers` endpoint returning `{poll_prophetx: bool, poll_sports_data: bool}` based on Redis heartbeat keys with 90s TTL
- Both poll workers now publish to `prophet:updates` after state changes and write heartbeat keys after successful execution
- Real Slack webhook delivery in `send_alerts` using `WebhookClient.send()`, with Redis SETNX deduplication preventing duplicate alerts within 5-minute window
- `alert_only_mode` guard in `update_event_status` reads `system_config` table before ProphetX write, skips write when true but always writes audit log

## Task Commits

Each task was committed atomically:

1. **Task 1: SSE Endpoint, Query-Param Auth, Worker Heartbeats, Redis Publish** - `1181073` (feat)
2. **Task 2: Slack Alerting with Deduplication and Alert-Only Mode Guard** - `9a56a37` (feat - absorbed into 03-01 commit due to concurrent execution)

**Plan metadata:** (this commit)

## Files Created/Modified

- `backend/app/api/v1/stream.py` - SSE endpoint with EventSourceResponse, Redis pub/sub subscriber, query-param auth
- `backend/app/api/deps.py` - Added `verify_token_from_query` dependency for ?token= JWT auth
- `backend/app/api/v1/health.py` - Added `/health/workers` endpoint reading Redis heartbeat keys
- `backend/app/main.py` - Mounted stream router at `/api/v1`
- `backend/app/workers/poll_prophetx.py` - Added `_publish_update()`, `_write_heartbeat()` helpers; calls after event/market upserts and at task end
- `backend/app/workers/poll_sports_data.py` - Added same helpers; publishes after mismatch detection; writes heartbeat at task end
- `backend/app/workers/send_alerts.py` - Replaced stub with real Slack SDK WebhookClient delivery + SETNX dedup
- `backend/app/workers/update_event_status.py` - Added alert_only_mode guard reading system_config before ProphetX write
- `backend/app/core/config.py` - Added `SLACK_WEBHOOK_URL: str | None = None`
- `backend/pyproject.toml` / `backend/uv.lock` - Added sse-starlette==3.2.0, slack-sdk==3.40.1

## Decisions Made

- SSE auth uses `?token=` query param: the native `EventSource` API cannot send `Authorization` headers, so JWT must be passed as a query parameter
- Worker heartbeat pattern uses Redis key TTL (90s) rather than Celery `inspect` — eliminates Celery dependency, more reliable for detecting worker absence
- `SLACK_WEBHOOK_URL` is optional with `None` default — system operates without Slack configured; delivery skipped with structured warning log
- `alert_only_mode` read fresh from DB at each task start (not cached) — real-time config changes take effect immediately without worker restart

## Deviations from Plan

None - plan executed exactly as written. All steps followed the specified implementation.

Note: Task 2 changes were committed to the repository in commit `9a56a37` (labeled as 03-01) because a concurrent 03-01 plan agent was executing simultaneously and included the staged backend files. The code state is fully correct and all verifications pass.

## Issues Encountered

- Concurrent plan execution: 03-01 frontend plan agent staged and committed Task 2 backend changes (send_alerts.py, update_event_status.py, config.py) before the Task 2 commit ran. Files were correct; only the commit attribution was unexpected. Verified all changes are present in HEAD.

## User Setup Required

**External services require manual configuration.** To enable Slack alerts:

1. Go to Slack App Directory → Your Apps → Incoming Webhooks → Add New Webhook to Workspace
2. Copy the Webhook URL
3. Add to `.env`: `SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...`
4. Restart the API and Celery workers for the change to take effect

When `SLACK_WEBHOOK_URL` is not set, alerts log a warning but system continues operating normally.

## Next Phase Readiness

- SSE backend is complete and connected to the React `useSse` hook from Plan 03-01
- Slack alerts fire when `SLACK_WEBHOOK_URL` is configured; deduplication prevents alert storms
- `alert_only_mode` is wired and ready for operator use via the system config API
- Phase 3 Plans 01 and 02 are both complete — the dashboard and alerting backend is fully functional

---
*Phase: 03-dashboard-and-alerts*
*Completed: 2026-02-26*

## Self-Check: PASSED

- stream.py: FOUND
- deps.py: FOUND
- send_alerts.py: FOUND
- 03-02-SUMMARY.md: FOUND
- commit 1181073: FOUND
- commit 9a56a37: FOUND
