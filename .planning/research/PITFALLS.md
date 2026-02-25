# Pitfalls Research

**Domain:** Real-time API polling system with automated corrective actions and financial consequences (prediction market operations)
**Researched:** 2026-02-24
**Confidence:** HIGH for Celery/Redis/SSE patterns (well-established, stable ecosystems); MEDIUM for ProphetX-specific behavior (undocumented external API); HIGH for event-matching failure modes (sports data industry patterns)

---

## Critical Pitfalls

### Pitfall 1: Duplicate Automated Actions (The Double-Fire Problem)

**What goes wrong:**
Two polling cycles overlap, or two Celery workers both detect the same status mismatch at the same time, and both enqueue a `update_event_status` task. Both tasks execute — ProphetX receives two identical PATCH requests in quick succession. At best, the second call is a no-op. At worst, it causes a race condition in ProphetX's own state machine (e.g., trying to transition an event that is already "live" to "live" again errors out) and triggers a false "Action Failed" alert to Slack.

**Why it happens:**
Celery Beat by default does not guarantee at-most-once task delivery. If a worker is slow, the scheduler will re-enqueue the task. If you run multiple workers (for redundancy), both workers can pick up and detect the same mismatch in the same polling window. Most developers write the detection logic ("if ProphetX status != real-world status, enqueue update") without a distributed lock around it.

**How to avoid:**
Use Redis-backed distributed locks (via `redis-py` with `SET NX EX` or `celery-redbeat`) for every action task. The lock key should encode the action intent: `lock:update_event:{prophetx_event_id}:to:{target_status}`. If the lock exists, skip enqueuing. Set lock TTL to at least 2× the max expected task execution time (e.g., 60 seconds for a task that should complete in 5). Additionally, write an "in-flight" status to the database/Redis before calling ProphetX, and check that status at the start of any action task before proceeding.

```python
# Pattern: lock before enqueue
lock_key = f"lock:status_update:{prophetx_event_id}"
acquired = redis_client.set(lock_key, "1", nx=True, ex=60)
if acquired:
    update_event_status.delay(prophetx_event_id, target_status)
# If not acquired, another worker is handling it — skip
```

**Warning signs:**
- Audit log shows the same event being updated twice within seconds
- Slack receives duplicate "updated to Live" messages for the same event
- ProphetX API returns 409 Conflict or equivalent errors on status updates
- Celery task count exceeds expected polling rate in monitoring

**Phase to address:** Phase 2 (Monitoring Engine) — must be built into the action-enqueuing logic from day one. Not a retrofit.

---

### Pitfall 2: Fuzzy Event Matching False Positives (Wrong Game Gets Updated)

**What goes wrong:**
The event matching layer incorrectly links a ProphetX event to the wrong SportsDataIO game. The system confidently detects a "mismatch" and auto-updates ProphetX — but it updated the wrong event. For example: two NBA games on the same night involving the same team (regular season game + an incorrectly scheduled preseason entry), or two games between the same teams in a playoff series on consecutive days. The matching by `sport + team names + scheduled_start_time` has a narrow collision window but real collisions exist.

**Why it happens:**
Developers trust the match result without a confidence score. The matching logic typically works for 95% of cases, so it's validated in testing and shipped. The 5% edge cases include: team name variations ("LA Lakers" vs "Los Angeles Lakers" vs "Lakers"), timezone bugs in scheduled_start comparisons, double-headers in MLB, playoff rematches, rescheduled games that retain the old start time in one system but get updated in another. A match that is "close enough" gets used.

**How to avoid:**
Never take automated action on a low-confidence match. Require all three of these to agree before auto-acting: (1) sport match exact, (2) both team names fuzzy-match above 0.85 similarity using `rapidfuzz`, (3) scheduled start within ±15 minutes. If any criterion falls below threshold, flag as "unmatched" and require manual review — do not auto-update. Log the confidence score for every match. Add a fourth tie-breaker: league (NFL vs. NCAAF both have "football" — league is essential). Store the match in the database with a `match_confidence` field. Dashboard should show "LOW CONFIDENCE MATCH" warning on any event where the matching score was below 0.90.

```python
# Matching criteria with gating
def match_event(prophetx_event, sportsdata_games):
    candidates = []
    for game in sportsdata_games:
        sport_match = prophetx_event.sport == game.sport  # exact
        team_score = max(
            fuzz.ratio(prophetx_event.home_team, game.home_team),
            fuzz.ratio(prophetx_event.away_team, game.away_team),
        )
        time_delta = abs((prophetx_event.scheduled_start - game.start_time).total_seconds())
        if sport_match and team_score >= 85 and time_delta <= 900:
            candidates.append((team_score * (1 - time_delta/3600), game))
    if not candidates:
        return None, 0.0
    best_score, best_game = max(candidates)
    if best_score < 0.90:
        return best_game, best_score  # Flag for review, do not auto-act
    return best_game, best_score
```

**Warning signs:**
- The audit log shows an event updated that the operator doesn't remember being scheduled
- A ProphetX event gets marked "Live" but operators know the game hasn't started yet
- Two different ProphetX events both match to the same SportsDataIO game ID
- Match confidence scores cluster near the threshold (many 0.85–0.90 scores = fragile matching)

**Phase to address:** Phase 2 (Monitoring Engine) — the matching layer is the most critical piece of Phase 2. Budget extra time. Build the manual override UI in Phase 4 so operators can correct bad matches.

---

### Pitfall 3: Alert Storms Causing Operator Blindness

**What goes wrong:**
Every 30-second polling cycle re-detects the same unresolved mismatch (e.g., ProphetX is still showing "upcoming" because the API update failed, or is slow). Each cycle fires a new Slack message and creates a new in-app notification. After 10 minutes, the Slack channel has 20 identical alerts for the same event. Operators start ignoring Slack. The next genuinely new critical alert is missed because it's buried in the noise.

**Why it happens:**
Developers implement alert-on-detect without alert-on-new-state. The detection logic correctly runs every cycle, but the alerting logic doesn't track whether an alert for that specific condition has already been sent. It's an easy miss because in testing, each test scenario runs once — the repeat-cycle behavior only manifests in production.

**How to avoid:**
Store alert state in Redis with a TTL. Key: `alert_sent:{event_id}:{condition_type}`. When an alert is sent, write this key with TTL = alert suppression window (e.g., 5 minutes for warnings, 15 minutes for critical). Before sending an alert, check if the key exists. Only send if the key is absent. Also implement a "still unresolved" digest: after the suppression window expires, if the condition is still present, re-alert but with "STILL UNRESOLVED (10 min)" context rather than treating it as a fresh alert. Separately, the PRD already calls for "max 1 alert per event per minute" — this pitfall reinforces that requirement and adds the Redis-TTL pattern for implementation.

**Warning signs:**
- Slack channel is scrolling with repeated messages about the same event
- Operators say they "don't trust" the Slack channel
- In-app notification count grows by 2+ per minute for the same event
- `notifications` table grows by hundreds of rows for a single unresolved issue

**Phase to address:** Phase 4 (Alerting) — implement alert deduplication from day one in alerting phase. Do not defer to Phase 5 ("polish") — this is a correctness requirement, not polish.

---

### Pitfall 4: SSE Connection Drops Break Dashboard Without Visible Indication

**What goes wrong:**
The browser's SSE connection to `/api/v1/stream` silently drops (network hiccup, server restart, Nginx timeout, 30-minute load balancer idle timeout). The React dashboard continues displaying data, but it's now frozen — the last state it received. Operators make decisions based on 45-minute-old data and don't know the dashboard is stale. The browser's EventSource API does auto-reconnect, but (a) there may be a delay during which the page shows no warning, and (b) on reconnect, the server starts streaming new events but the client has missed all events that occurred during the disconnect.

**Why it happens:**
SSE is deceptively simple. Sending events is easy. The missed-events-on-reconnect problem is invisible in development (the dev server restarts quickly and few events happen). The Nginx `proxy_read_timeout` (default 60 seconds) silently kills SSE connections sitting idle. The browser EventSource reconnects but the server has no "last event ID" support to replay missed events.

**How to avoid:**
(1) Send a heartbeat SSE comment (`: heartbeat\n\n`) every 15 seconds from the server — this keeps the Nginx connection alive and makes drops detectable. (2) Implement `id:` fields on every SSE event with an incrementing sequence number or timestamp. (3) On reconnect, have the client send `Last-Event-ID` header and have the server replay events from Redis (store last N events in a Redis list with TTL). (4) Show a visible "Connection lost — reconnecting..." banner in the dashboard when EventSource enters the `CONNECTING` state. This is critical: operators must know when their view is stale. (5) Configure Nginx: `proxy_read_timeout 3600s;` and `proxy_buffering off;` for the SSE endpoint.

```nginx
# Nginx config for SSE endpoint
location /api/v1/stream {
    proxy_pass http://backend;
    proxy_buffering off;
    proxy_read_timeout 3600s;
    proxy_set_header Connection '';
    proxy_http_version 1.1;
    chunked_transfer_encoding on;
}
```

**Warning signs:**
- Dashboard data stops updating but no error is visible
- Browser DevTools Network tab shows SSE connection as "Pending" then "Failed" then "Pending" cycling
- Redis pub/sub is publishing events (verifiable via `redis-cli monitor`) but dashboard doesn't update
- Users report dashboard "freezing" after being open for 30–60 minutes

**Phase to address:** Phase 3 (Dashboard) — implement heartbeats, SSE event IDs, and the stale-connection banner from day one. Add Nginx config in Phase 5 (Deploy). The missed-events replay can be Phase 5 if Phase 3 implements the ID tracking scaffolding.

---

### Pitfall 5: Automated Actions on Financially Consequential State Without Idempotency

**What goes wrong:**
The `update_event_status` Celery task calls ProphetX API to set an event to "ended." The API call succeeds, but the network response times out before Celery gets the 200 OK. Celery marks the task as failed and retries. The retry calls ProphetX again — now the event is "ended" again (no-op if ProphetX is idempotent, disaster if it triggers settlement logic twice). Or worse: the task updates the database before calling ProphetX, then ProphetX fails — now the database says the event is "ended" but ProphetX still says "live." The system believes the action is complete and stops trying.

**Why it happens:**
Developers write: "call external API → if success, write to DB → done." The happy path works perfectly. Partial failures (API success but response lost, or DB write fails after API call) create inconsistent state that's hard to detect. In a financial system, "the books say settled but the platform is still accepting bets" is a serious problem.

**How to avoid:**
(1) Write action intent to the database BEFORE calling the external API (event status = "update_pending"). (2) Call the ProphetX API. (3) On success, update status to the new value. (4) On failure, mark as "update_failed" and trigger the human-intervention alert. This way, if the task is retried, it can check the current DB state and verify ProphetX's actual current state before deciding to retry. (5) Make all retry logic read the current ProphetX state first — if ProphetX already shows the desired status, the task was already successful and can be marked complete without calling again. This is the "verify before retry" pattern.

```python
# Idempotent update pattern
async def update_event_status(prophetx_event_id: str, target_status: str):
    # 1. Check current ProphetX state first (don't assume it needs updating)
    current = await prophetx_client.get_event(prophetx_event_id)
    if current.status == target_status:
        # Already done — mark success and exit
        await audit_log.write(action="status_update", result="already_complete")
        return

    # 2. Write intent to DB
    await db.update_event(prophetx_event_id, status="update_pending")

    # 3. Call API
    try:
        await prophetx_client.update_status(prophetx_event_id, target_status)
        await db.update_event(prophetx_event_id, status=target_status)
        await audit_log.write(action="status_update", result="success")
    except Exception as e:
        await db.update_event(prophetx_event_id, status="update_failed")
        await audit_log.write(action="status_update", result="failure", error=str(e))
        raise  # Let Celery retry logic handle it
```

**Warning signs:**
- Audit log shows same event with both "success" and "failure" entries within seconds
- Redis and PostgreSQL show different statuses for the same event
- ProphetX shows an event as "ended" but the system dashboard still shows it as "live"
- Duplicate Slack alerts for the same action ("Updated to Live" followed by "Failed to update to Live")

**Phase to address:** Phase 2 (Monitoring Engine) — the idempotent task pattern must be the default from the start. This cannot be retrofitted without rewriting all action tasks.

---

### Pitfall 6: Celery Beat Clock Drift Causing Missed Polling Cycles

**What goes wrong:**
Celery Beat is the scheduler. There is only one Beat process per deployment (by design — running multiple Beat processes causes duplicate task scheduling). When the Beat process restarts (container redeploy, VPS maintenance, OOM kill), it can lose track of when tasks last ran. Depending on configuration, it may either skip cycles that should have run during downtime, or immediately fire all overdue tasks simultaneously when it comes back up — creating a thundering herd against the ProphetX API.

**Why it happens:**
The default Celery Beat scheduler persists state in a local file (`celerybeat-schedule`). In Docker, this file lives inside the container and is lost on container restart unless mounted as a volume. Without persistent state, Beat starts fresh every restart and may re-run all tasks at once.

**How to avoid:**
Use `celery-redbeat` (a Redis-backed Beat scheduler) instead of the default file-based scheduler. RedBeat stores schedule state in Redis, survives container restarts without data loss, and handles the "catch up or skip" logic correctly. Configure it to skip overdue tasks on startup (not catch up) to avoid API thundering herd. Mount nothing — Redis is already in the stack.

```python
# settings.py
CELERY_BEAT_SCHEDULER = 'redbeat.RedBeatScheduler'
CELERY_REDBEAT_REDIS_URL = REDIS_URL
CELERY_REDBEAT_LOCK_TIMEOUT = 60  # Beat leadership lock TTL
```

**Warning signs:**
- After any container restart, audit log shows a burst of polling activity all at the same timestamp
- ProphetX API rate limit errors immediately after deployment
- `celerybeat-schedule` file is missing after container restart
- Polling gaps in the audit log (no entries for 2–5 minutes during a restart window)

**Phase to address:** Phase 1 (Foundation) — configure RedBeat during initial Celery setup. Do not use the default scheduler even for development.

---

### Pitfall 7: Redis Memory Exhaustion Killing the Entire System

**What goes wrong:**
Redis is used for three things: Celery task broker, application cache, and SSE pub/sub. On a ~$15/month VPS with 1–2GB RAM, Redis shares memory with PostgreSQL and the application processes. If Redis runs without a `maxmemory` policy, it grows unbounded. Celery task results are stored in Redis by default and never expire. After weeks of operation, Redis consumes all available memory. When Redis OOMs, it either starts evicting Celery task data (causing task tracking failures) or the VPS OOM killer terminates Redis entirely — taking down the Celery broker and all background workers simultaneously.

**Why it happens:**
Celery's default `result_backend` stores task results in Redis with no TTL. In development this is invisible because there are few tasks. In production with 30-second polling cycles (2 per minute × 2 tasks = 4 task results/minute × 1440 minutes/day = ~5,760 task results/day), Redis grows steadily. Developers don't think about Redis memory until it's full.

**How to avoid:**
(1) Set `CELERY_RESULT_EXPIRES = 3600` (1 hour TTL on task results). (2) Configure Redis `maxmemory` and `maxmemory-policy allkeys-lru` in `redis.conf`. For a 1GB VPS, set `maxmemory 256mb` for Redis. (3) If task results are not needed after completion (they aren't needed for fire-and-forget polling tasks), set `CELERY_TASK_IGNORE_RESULT = True` for polling tasks. (4) Monitor Redis memory via `INFO memory` in periodic health checks. Alert if used memory exceeds 80% of maxmemory.

```python
# Celery config
CELERY_TASK_IGNORE_RESULT = True  # For polling tasks
CELERY_RESULT_EXPIRES = 3600      # For tasks where results matter
```

```yaml
# docker-compose.yml Redis service
redis:
  image: redis:7-alpine
  command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
```

**Warning signs:**
- `redis-cli info memory` shows `used_memory` growing over days/weeks
- Celery workers report "BrokerConnectionError" or "ConnectionError" intermittently
- Background polling tasks stop running without any error (Redis OOM killed the broker)
- VPS memory usage climbing steadily over weeks

**Phase to address:** Phase 1 (Foundation) — set Redis memory limits in docker-compose.yml during initial infrastructure setup.

---

### Pitfall 8: ProphetX API Status Enum Assumptions Causing Silent Failures

**What goes wrong:**
The comparison logic is built against assumed ProphetX status values (e.g., `"upcoming"`, `"live"`, `"ended"`). The actual ProphetX API uses different values (e.g., `"SCHEDULED"`, `"IN_PROGRESS"`, `"CLOSED"`, or numeric codes). The status comparison `prophetx_status == "upcoming"` never matches, so mismatches are never detected. No errors are thrown — the system runs, polls successfully, logs clean — but never detects anything. This could go unnoticed for days until an operator manually checks.

**Why it happens:**
The PRD itself notes "verify exact values from ProphetX API docs" — this is a known unknown. Developers prototype the comparison logic with guessed values, then forget to update after reading the actual API docs. Or the API uses different values in sandbox vs. production.

**How to avoid:**
(1) Log every raw status value received from ProphetX to the database on the very first poll — before writing any comparison logic. Review those raw values and build the enum from actual data, not documentation. (2) Define a ProphetX status enum in Python with a fallback: if a status value is received that is not in the enum, log a `WARNING: unknown_prophetx_status` alert and notify the operator. This catches API changes post-launch too. (3) Add an integration test that calls the real ProphetX API (or a recorded response), asserts that the status values received are in the known set, and fails loudly if unknown values appear.

**Warning signs:**
- No mismatches ever detected despite events being live in the real world
- `status_match` field is always `True` in the database (suspicious if events are actively running)
- ProphetX polling shows 0 "mismatch detected" log entries across a full day
- Dashboard shows all events as "matched" during a live game day

**Phase to address:** Phase 1 (Foundation) — the ProphetX API client should log raw responses. Phase 2 (Monitoring Engine) — build the comparison layer only after validating real enum values against actual API responses.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Polling tasks check Redis only (skip DB read) | Faster polling cycles | Redis and DB diverge; DB becomes unreliable source of truth | Never — always write canonical state to DB, use Redis as cache only |
| Skip match confidence scoring; match on team name only | Simpler matching code | False positive matches; wrong events get auto-updated | Never for auto-actions; acceptable for display-only confidence hints |
| Use Celery default file-based scheduler (not RedBeat) | No extra dependency | Duplicate tasks and schedule drift on container restart | Acceptable only for local development |
| Ignore result for all Celery tasks | Simpler code, less Redis memory | No way to track action task outcomes; audit log must be explicit | Acceptable for polling tasks; never for action tasks where outcome matters |
| No SSE heartbeat | Simpler server code | Silent stale dashboard; operators can't trust data | Never in production |
| Alert on every detection (no deduplication) | Easier alert code | Alert storm → operator blindness → missed real alerts | Acceptable only during initial 48-hour shadow mode testing |
| No distributed lock on action enqueueing | Simpler polling code | Duplicate automated actions | Never in production |
| Manual event ID mapping in a config file | Fast to get started | Doesn't scale; breaks when new events are added | Acceptable for early testing of the comparison logic; must be replaced by automated matching before launch |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| ProphetX API | Assume rate limit is generous; don't track request rate | Count requests per minute in polling logic; use a Redis counter; back off proactively before hitting the limit |
| ProphetX API | Treat all 4xx errors as permanent failures | 429 (rate limited) needs backoff + retry; 404 may mean event was deleted and should be removed from monitoring; 422 may indicate invalid status transition — each code needs distinct handling |
| SportsDataIO | Call sport-specific endpoints without confirming subscription coverage | Check subscription tier before building polling for each sport; log which sports are actually covered vs. returning 403; don't assume NBA access implies NCAAB access |
| SportsDataIO | Poll `GamesByDate` for all sports every 30 seconds | Not all sports have active games every day; build a "is there anything scheduled today?" check to skip unnecessary calls; respect SportsDataIO's daily request limits |
| SportsDataIO | Assume `Final` is the only terminal state | `F/OT`, `F/SO` (shootout), `Postponed`, `Canceled`, `Suspended` are all terminal or need distinct handling; map all of them before building comparison logic |
| Slack webhook | Post one message per detected issue per cycle | Rate limit Slack at 1 req/sec; burst posting will trigger 429 from Slack; use a message queue with delay for bulk alert scenarios |
| Redis pub/sub | Subscribe to all channels in the SSE endpoint handler | Channel-per-event-type is cleaner (e.g., `events:updated`, `markets:updated`, `notifications`); avoid wildcard subscriptions that send all Redis messages to every SSE client |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Querying full events list from PostgreSQL on every polling cycle to check for mismatches | Polling worker takes 2+ seconds per cycle; query load spikes every 30 seconds | Cache current event/market state in Redis; polling worker updates Redis, comparison logic reads Redis | At ~200+ events; immediate on a slow VPS |
| N+1 query: fetching each market's liquidity individually after fetching the events list | Hundreds of DB queries per polling cycle; polling cycle creeps from 1s to 10s+ | Batch fetch all markets in one query; use `WHERE event_id IN (...)` | At ~50 markets |
| SSE: sending full event object on every change (large payload) | SSE messages are large; browser is receiving and parsing 10KB+ JSON every 30 seconds for minor changes | Send delta events (only changed fields); use a `type: event_updated` event with minimal payload; client fetches full details on demand | With 100+ concurrent SSE clients |
| Celery result storage in Redis without TTL | Redis memory grows unbounded over weeks | `CELERY_RESULT_EXPIRES = 3600` and `CELERY_TASK_IGNORE_RESULT = True` for fire-and-forget tasks | After ~2 weeks of production with 30s polling cycles |
| No database indexes on `prophetx_event_id` and `status_match` columns | Slow dashboard queries as event/market count grows | Add indexes on: `events.prophetx_event_id`, `events.status_match`, `events.prophetx_status`, `audit_log.timestamp`, `audit_log.entity_id` | At ~1,000 audit log entries; visible at ~10,000 |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Passing JWT in SSE query parameter (`?token=...`) without additional protection | Token is logged in Nginx access logs; visible in browser history | Use a short-lived SSE token endpoint: exchange JWT for a 60-second SSE token; or use cookie-based auth for SSE and set `SameSite=Strict` |
| Exposing ProphetX API key in client-side JavaScript or browser-visible API responses | Attacker can make ProphetX API calls as the operator — create/cancel markets, update statuses | ProphetX API key lives only in backend environment; never included in any response to the browser |
| No rate limiting on the `/api/v1/events/{id}/sync-status` manual trigger endpoint | An operator (or compromised session) can spam ProphetX API with update requests | Rate limit manual trigger to 1 request per event per 30 seconds; enforce at the FastAPI middleware level |
| Audit log that can be modified (e.g., using `UPDATE` in repair scripts) | Compliance risk; removes ability to detect unauthorized automated actions | PostgreSQL `GRANT` permissions: application DB user has `INSERT` only on `audit_log` table, never `UPDATE` or `DELETE`; enforce at DB level, not just application level |
| Slack webhook URL stored in plaintext in source code or committed to git | Anyone with repo access can post to the operations Slack channel | Store in environment variable only; validate that Slack webhook URL is not in git history before first commit |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Dashboard shows last-updated timestamp per-table but not per-row | Operator can't tell if a specific row's data is 5 seconds old or 5 minutes old (SSE dropped) | Show `last_prophetx_poll` and `last_real_world_poll` per row; highlight rows where the poll timestamp is > 90 seconds old (stale data warning) |
| Auto-resolution shows no in-progress state — status jumps from "mismatch" to "resolved" | Operator thinks nothing is happening; may manually intervene while auto-fix is in progress, creating conflicts | Show explicit "Resolving..." badge during the window between enqueue and completion; prevent manual trigger for events in "Resolving" state |
| Notifications accumulate without dismissal; no bulk actions | After 48 hours of operation, notification panel has 200+ entries; operators stop looking at it | Implement "mark all as read" and auto-archive notifications older than 24 hours (keep in DB, just hide from panel) |
| Config changes (liquidity thresholds) take effect silently | Admin changes a threshold; nothing visible confirms the change is active | Show confirmation toast + immediately refresh the market row to show new threshold; log config change in audit log and surface it in notification center |
| Manual sync button shows no feedback while the async task is running | Operator clicks "Sync" twice because nothing seemed to happen | Disable the button and show spinner from click until the Celery task completes and SSE pushes the result back; use task ID polling if needed |

---

## "Looks Done But Isn't" Checklist

- [ ] **Event matching layer:** Looks done after matching 10 test games — verify it handles: same two teams playing twice in one week (playoff series), doubleheaders (MLB), timezone edge cases around midnight, postponed games that get rescheduled but retain old start time in one system
- [ ] **Duplicate action prevention:** Looks done after adding the lock — verify the lock TTL is long enough to cover worst-case API retry duration (3 retries × 4 seconds backoff = ~12 seconds minimum; use 60 seconds)
- [ ] **SSE stale connection:** Looks done after implementing heartbeat — verify behavior when Nginx `proxy_read_timeout` is hit; test with `proxy_read_timeout 30s` locally and confirm the reconnect banner appears
- [ ] **Alert deduplication:** Looks done after adding Redis TTL key — verify the "still unresolved" re-alert fires correctly after the suppression window; verify alerts are NOT suppressed across different conditions on the same event (low liquidity alert should still fire even if a status mismatch alert is suppressed for that event)
- [ ] **Celery worker restart:** Looks done with `restart: unless-stopped` in docker-compose — verify: (a) tasks in flight when a worker dies are re-queued (requires `acks_late=True`), (b) Beat restarts don't duplicate tasks (requires RedBeat), (c) the audit log shows the task as failed (not silently lost)
- [ ] **ProphetX API status enums:** Looks done after reading API docs — verify by logging raw responses from the actual live/staging API and asserting all observed values are in the Python enum
- [ ] **Audit log append-only:** Looks done after writing INSERT-only application code — verify by attempting an UPDATE on `audit_log` with the application DB user and confirming it is rejected by PostgreSQL permissions
- [ ] **RBAC enforcement:** Looks done after adding role check in endpoint handlers — verify that Read-Only users cannot reach Operator endpoints even with a valid JWT and role manually modified in the request (server-side role check, not client-side gating only)

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Duplicate actions already fired | LOW if ProphetX is idempotent; HIGH if it triggered settlement twice | Check ProphetX API for current event state; compare to audit log; if duplicate settlement occurred, requires manual ProphetX support intervention |
| Wrong event matched and auto-updated | MEDIUM | Audit log shows the incorrect update; manually revert via ProphetX API; add the event pair to a "manual match override" table to prevent recurrence |
| Alert storm already flooded Slack | LOW | Delete duplicate messages via Slack API; deploy fix with deduplication; add Redis alert-state keys for all currently-open conditions |
| Redis memory exhausted, broker down | HIGH (all polling stopped) | `redis-cli FLUSHDB` (clears broker queue — loses in-flight tasks); restart Celery workers; set maxmemory immediately; polling resumes from next cycle |
| SSE connection silently stale (operators using old data) | MEDIUM | Hard page refresh restores SSE; add the stale-connection banner to prevent recurrence; no data loss since SSE is display-only (DB is source of truth) |
| Celery Beat scheduled duplicate tasks on restart | LOW-MEDIUM | Purge Celery queue (`celery -A app purge`); switch to RedBeat immediately |
| ProphetX status enums wrong — no mismatches ever detected | HIGH (all auto-updates missed since launch) | Emergency: add logging to raw poll response, identify actual enum values, deploy fix; retroactively review audit log for missed events; manually correct any stale events on ProphetX |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Duplicate automated actions (double-fire) | Phase 2 (Monitoring Engine) | Integration test: trigger two concurrent mismatch detections for same event; verify only one ProphetX API call is made |
| Fuzzy event matching false positives | Phase 2 (Monitoring Engine) | Test suite with known ambiguous cases: same teams, same sport, different days; verify confidence scores and gating logic |
| Alert storms / operator blindness | Phase 4 (Alerting) | Test: simulate same mismatch persisting across 5 polling cycles; verify only 1 Slack message sent in the suppression window |
| SSE silent stale connection | Phase 3 (Dashboard) + Phase 5 (Deploy/Nginx) | Test: kill SSE connection from server side; verify "connection lost" banner appears in browser within 20 seconds |
| Automated actions without idempotency | Phase 2 (Monitoring Engine) | Test: simulate API success with response timeout; verify retry does not double-apply the action |
| Celery Beat clock drift / duplicate tasks | Phase 1 (Foundation) | Restart Beat container; verify no burst of duplicate tasks in Celery logs |
| Redis memory exhaustion | Phase 1 (Foundation) | Set maxmemory in docker-compose.yml; verify with `redis-cli info memory` after 48 hours of polling |
| ProphetX status enum assumptions | Phase 1 (Foundation) + Phase 2 | Log raw ProphetX API responses in first integration test; assert against actual observed values |
| Timezone bugs in scheduled_start comparison | Phase 2 (Monitoring Engine) | Test with games scheduled near midnight UTC; verify matching uses UTC-normalized timestamps throughout |
| Slack rate limiting under alert bursts | Phase 4 (Alerting) | Load test: simulate 50 simultaneous alerts; verify no 429 errors from Slack |
| JWT token visible in Nginx logs (SSE endpoint) | Phase 3 (Dashboard) | Check Nginx access logs after first SSE connection; verify token is not logged |
| No database indexes on hot query paths | Phase 1 (Foundation) | Add `EXPLAIN ANALYZE` to polling queries in initial migration review |

---

## Sources

- Celery documentation on task deduplication and distributed locks: https://docs.celeryq.dev/en/stable/userguide/tasks.html#avoiding-launching-the-same-task
- celery-redbeat documentation (Redis-backed Beat scheduler): https://github.com/sibson/redbeat
- FastAPI SSE patterns and EventSource reconnection: MDN Web Docs — Server-sent events; FastAPI docs on StreamingResponse
- Redis maxmemory configuration: https://redis.io/docs/manual/eviction/
- rapidfuzz library for fuzzy string matching: https://github.com/maxbachmann/RapidFuzz
- Nginx proxy_read_timeout for long-lived connections: https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_read_timeout
- General knowledge: Celery production best practices (acks_late, result expiry, RedBeat); SSE production patterns; financial operations tooling (idempotency, audit logs)
- Confidence: HIGH for all patterns above — these are well-documented, stable behaviors of these technologies

*Note: WebSearch and Brave Search were unavailable during this research session. All findings are based on training knowledge through August 2025. ProphetX-specific behavior (rate limits, status enums, API stability) is MEDIUM confidence — must be verified against actual ProphetX API documentation and live testing.*

---
*Pitfalls research for: ProphetX Market Monitor — real-time API polling system with automated corrective actions*
*Researched: 2026-02-24*
