# Phase 8: WS Diagnostics and Instrumentation - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Instrument the WS consumer (`ws_prophetx.py`) with Redis health keys so connection state and message activity are observable. Fix two pre-existing bugs: NULL `status_match` on WS-created events (WSREL-02) and missing reconnect-triggered reconciliation (WSREL-01). This phase is the gate for Phase 9 — `ws:sport_event_count > 0` must be confirmed in production before status authority logic is built.

</domain>

<decisions>
## Implementation Decisions

### Reconnect Reconciliation (WSREL-01)
- **D-01:** Fire `poll_prophetx` on every reconnect — both error recovery and token-refresh cycles. No distinction needed; poll_prophetx is cheap (single API call).
- **D-02:** Use `celery_app.send_task('poll_prophetx')` from the WS consumer service. This enqueues via the Redis broker without importing the task module — standard Celery cross-service pattern.
- **D-03:** Fire immediately on reconnect, no stabilization delay. The Celery task runs independently of WS connection state.
- **D-04:** Tag reconciliation runs with `trigger='ws_reconnect'` kwarg so poll_prophetx logs distinguish reconnect-triggered runs from scheduled runs. Useful during Phase 8 observation window.

### Claude's Discretion
- Redis health key design: TTLs, value formats, update frequency for `ws:connection_state`, `ws:last_message_at`, `ws:last_sport_event_at`, `ws:sport_event_count`. Sensible defaults based on existing `worker:heartbeat` patterns (90s TTL, written on each event/heartbeat cycle).
- WSREL-02 fix: Add `status_match=compute_status_match(...)` to the new-event creation path in `_upsert_event()` (line ~177). Straightforward — the update path already does this.
- Production gate observation: Manual check of `ws:sport_event_count` in Redis after 24-48h covering live game windows. No automated alerting needed for the gate itself.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### WS Consumer
- `backend/app/workers/ws_prophetx.py` — Current WS consumer implementation; all instrumentation changes go here
- `backend/app/workers/poll_prophetx.py` — Reconciliation target; needs `trigger` kwarg support in task signature

### Requirements
- `.planning/REQUIREMENTS.md` §WS Diagnostics & Reliability — WSREL-01 (reconnect reconciliation), WSREL-02 (status_match NULL bug)

### Existing Patterns
- `backend/app/workers/poll_prophetx.py:_write_heartbeat()` — Existing Redis heartbeat pattern (worker:heartbeat:{name}, TTL = 3x poll interval)
- `backend/app/monitoring/mismatch_detector.py:compute_status_match()` — Status match computation used in WSREL-02 fix

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_write_heartbeat()` in both `ws_prophetx.py` and `poll_prophetx.py` — establishes the Redis key pattern for worker health
- `compute_status_match()` from `mismatch_detector.py` — already used in the update path; reuse for the create path (WSREL-02)
- `_sync_redis.from_url(settings.REDIS_URL)` — Redis connection pattern used throughout workers

### Established Patterns
- Worker heartbeat: `worker:heartbeat:{name}` key with TTL, written periodically
- SSE publish: `_publish_update()` pattern for pushing changes to dashboard
- Celery task registration: tasks in `backend/app/workers/` auto-discovered by celery_app

### Integration Points
- `ws_prophetx.py:_connect_and_run()` — reconnect logic lives here; reconciliation trigger goes at connection establishment
- `ws_prophetx.py:_handle_broadcast_event()` — sport_event handler; Redis key updates go here
- `poll_prophetx.py` task signature — needs to accept optional `trigger` kwarg for logging
- Redis keys namespace: `ws:*` prefix for all new diagnostic keys (distinct from `worker:heartbeat:*`)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches for Redis key design and gate observation.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 08-ws-diagnostics-and-instrumentation*
*Context gathered: 2026-03-31*
