# Pitfalls Research

**Domain:** Adding an external RabbitMQ consumer (OpticOdds tennis) to an existing Celery/Redis/PostgreSQL system (ProphetX Market Monitor v1.3)
**Researched:** 2026-04-01
**Confidence:** HIGH for pika connection management (official docs + pika GitHub issues); HIGH for codebase-specific integration points (direct inspection of ws_prophetx.py, celery_app.py, mismatch_detector.py); MEDIUM for OpticOdds-specific queue lifecycle (limited public docs; REST queue API not fully documented publicly); HIGH for Docker/VPS resource concerns (confirmed from CloudAMQP + community reports at this scale)

---

## Critical Pitfalls

### Pitfall 1: pika BlockingConnection Heartbeat Starvation — Connection Silently Dropped

**What goes wrong:**
`pika.BlockingConnection` runs its I/O loop on a single thread. If the `on_message_callback` does any meaningful work — a database write, a Redis publish, a REST call — the I/O loop is blocked for the duration. RabbitMQ sends periodic heartbeat frames (default: every 60 seconds) expecting a response. If the message handler takes long enough that the I/O loop cannot service the heartbeat in time, the broker closes the connection with "missed heartbeat" — silently, from the consumer's perspective.

For this project, each OpticOdds message triggers a `_upsert_event()` DB write (SQLAlchemy synchronous session) plus a Redis publish. Under normal conditions this is <50ms. But under PostgreSQL lock contention (another Celery worker mid-transaction) or on a loaded single-VPS, wall-clock time can spike unpredictably and breach the heartbeat window.

**Why it happens:**
pika's `BlockingConnection` does not run the I/O pump in a separate thread. Any Python code in the callback directly competes for the same thread. The official pika docs state explicitly: "A common solution is to delegate processing of the incoming messages to another thread, while the connection adapter's thread continues to service its I/O loop's message pump." Most first implementations ignore this warning and write simple synchronous callbacks.

**How to avoid:**
Two approaches, in order of preference:

1. **Set a conservative heartbeat value** in `ConnectionParameters`. The default is negotiated with the broker (often 60s); setting `heartbeat=600` gives 600 seconds of tolerance. This is the correct approach for a low-volume consumer where message processing completes in well under 600s. For OpticOdds tennis result messages, 600s is appropriate — tennis matches update infrequently.

   ```python
   params = pika.ConnectionParameters(
       host="v3-rmq.opticodds.com",
       port=5672,
       virtual_host="api",
       credentials=pika.PlainCredentials(api_key, password),
       heartbeat=600,
       blocked_connection_timeout=300,
   )
   ```

2. **Delegate heavy processing to a thread pool** if message handling becomes heavier (e.g., multiple DB operations per message). The callback enqueues work; a separate thread drains it.

Do not set `heartbeat=0` to disable heartbeats. This prevents the broker from detecting a dead TCP connection — the opposite problem.

**Warning signs:**
- `pika.exceptions.AMQPHeartbeatTimeout` or `ConnectionResetError` in consumer logs
- Consumer reconnects trigger every ~60 seconds like clockwork (exactly the heartbeat interval)
- RabbitMQ broker logs show "missed heartbeat from client" on the OpticOdds side (if OpticOdds exposes broker logs — unlikely; look for connection drops)

**Phase to address:** Phase 1 (RabbitMQ consumer foundation) — `ConnectionParameters` must include explicit `heartbeat` and `blocked_connection_timeout` from the first implementation. Retrofitting these after a heartbeat drop has been diagnosed costs a production incident.

---

### Pitfall 2: Reconnect Storm — No Backoff on Connection Failure Loop

**What goes wrong:**
When the consumer reconnects after a failure, naive implementations re-enter the `start_consuming()` call immediately in a tight loop. If the external broker is temporarily unreachable (OpticOdds v3-rmq.opticodds.com planned maintenance, VPS network blip, DNS failure), the consumer will attempt reconnection thousands of times per minute. This:

1. Floods OpticOdds connection logs and may trigger their rate limiting or IP ban
2. Exhausts local file descriptors (each failed TCP attempt opens and closes an FD)
3. Saturates Redis with error-path logging if the consumer also writes health keys in the retry loop
4. Shows up as CPU spike on the already-constrained CX23 VPS

**Why it happens:**
The `pika.exceptions.AMQPConnectionError` is raised and caught by the retry loop, which immediately tries again. No sleep, no cap on retries, no jitter. This is the default pattern in most code examples that don't explicitly handle reconnect backoff.

**How to avoid:**
Implement explicit exponential backoff with jitter and a maximum cap:

```python
import random
import time

MAX_BACKOFF = 60  # seconds
backoff = 1

while True:
    try:
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)
        backoff = 1  # reset on successful connect
        channel.start_consuming()
    except (pika.exceptions.AMQPConnectionError, pika.exceptions.AMQPChannelError) as exc:
        log.error("opticodds_rmq_connection_failed", error=str(exc), retry_in=backoff)
        time.sleep(backoff + random.uniform(0, 1))
        backoff = min(backoff * 2, MAX_BACKOFF)
    except Exception as exc:
        log.exception("opticodds_rmq_unexpected_error", error=str(exc))
        time.sleep(backoff)
        backoff = min(backoff * 2, MAX_BACKOFF)
```

Mirror the existing `ws_prophetx.py` exponential backoff pattern: that service already caps at 60s. Apply the same discipline here.

**Warning signs:**
- Consumer Docker container shows near-100% CPU during a known broker outage
- Logs show hundreds of `pika.exceptions.AMQPConnectionError` per minute
- `docker stats` shows memory growing during reconnect phase (FD leak per failed TCP open)

**Phase to address:** Phase 1 (RabbitMQ consumer foundation) — the reconnect loop must include backoff before the first deployment. Non-negotiable.

---

### Pitfall 3: Forgetting to Call the Queue Start REST API — Consumer Connects But Receives Nothing

**What goes wrong:**
OpticOdds manages queue provisioning through a REST API. You must call their `/start` (or equivalent) endpoint to activate message delivery to your queue before connecting. If the queue is not started:

- `pika.BlockingConnection` may connect successfully (TCP handshake with the broker works)
- `channel.basic_consume()` may succeed (queue may exist but be empty)
- The consumer enters `start_consuming()` and waits indefinitely
- No messages ever arrive, no error is raised
- Health diagnostics will show "consumer running" but tennis events never update

This is the most common "why isn't it working" failure mode when integrating with provisioned external queues.

**Why it happens:**
RabbitMQ itself is unaware of whether OpticOdds is feeding the queue. From pika's perspective, a queue that exists but has no producer is normal operation. The connection and consume calls succeed. The silence from the queue is indistinguishable from "no tennis matches are happening right now."

**How to avoid:**
1. **Call the queue start REST API at consumer startup**, not as a manual pre-flight step. Build this into the consumer's startup sequence: `_start_opticodds_queue()` → `_connect_and_consume()`. If the start API call fails, abort with a fatal log and let the Docker container restart.

2. **Track `queue_started_at` in Redis** so that health diagnostics can distinguish "consumer running, queue active" from "consumer running, queue never started."

3. **Queue the stop REST API call on graceful shutdown** (SIGTERM handler) to release the queue on OpticOdds's side when the consumer exits cleanly.

4. **Handle stale queue from a previous run**: If the container was killed without calling stop, the queue may already be active from the last session. The start API may return an error or a new queue name. Design the startup to handle "already started" gracefully — re-use the existing queue name or call stop first then start.

**Warning signs:**
- Consumer logs show successful connection and `basic_consume` call but no subsequent `opticodds_message_received` entries for an hour or more during a period when tennis matches were scheduled
- Health endpoint shows consumer "running" but `last_message_at` is NULL or very stale
- OpticOdds dashboard (if available) shows queue is not active

**Phase to address:** Phase 1 (RabbitMQ consumer foundation) — the queue start/stop lifecycle must be built into the consumer startup sequence from day one.

---

### Pitfall 4: Tennis Status Values Do Not Map 1:1 to the Existing Event Status Model

**What goes wrong:**
The existing system uses a three-value `prophetx_status` model: `not_started`, `live`, `ended`. OpticOdds tennis result data uses its own vocabulary. Tennis matches have richer lifecycle states that do not map cleanly into this model:

| OpticOdds/tennis status | Correct mapping | Risk |
|-------------------------|-----------------|------|
| `not_started` / `scheduled` | `not_started` | Straightforward |
| `in_progress` / `live` | `live` | Straightforward |
| `finished` / `complete` | `ended` | Straightforward |
| `retired` | `ended` (match completed, winner exists) | **Easy to miss** — might be mapped to `live` if checked naively |
| `walkover` | `ended` (one player withdrew pre-match) | **Easy to miss** — never started but has a result |
| `suspended` | `live` (match paused mid-play, will resume) | **Wrong if mapped to ended** — match is not over |
| `interrupted` | `live` (brief stoppage, expect resume) | Transient — do not treat as ended |
| `cancelled` | custom / `ended` with flag | Irreversible non-completion |
| `delayed` | `not_started` (pre-match start delay) | Fine, but must not be treated as `live` |
| `start_delayed` | `not_started` | Same as delayed |
| `abandoned` | `ended` (no result possible) | Different from `cancelled` on some APIs |

The three most dangerous wrong mappings:
- Mapping `walkover` as `live` (match never started)
- Mapping `suspended`/`interrupted` as `ended` (match will resume)
- Mapping `retired` as `not_started` (match did complete with a result)

**Why it happens:**
Tennis has genuinely complex match lifecycle semantics. A developer unfamiliar with tennis often writes a simple `if status == "finished": return "ended"` and misses the tail cases. `walkover` and `retired` are common in professional tennis (WTA/ATP injury-related retirements happen in roughly 3-5% of matches).

**How to avoid:**
Define a complete, explicit mapping function with no fallthrough default:

```python
_OPTICODDS_TENNIS_STATUS_MAP = {
    "not_started": "not_started",
    "scheduled":   "not_started",
    "delayed":     "not_started",
    "start_delayed": "not_started",
    "in_progress": "live",
    "live":        "live",
    "suspended":   "live",        # match paused, will resume
    "interrupted": "live",        # brief stoppage
    "finished":    "ended",
    "complete":    "ended",
    "retired":     "ended",       # player retired mid-match — match has a winner
    "walkover":    "ended",       # opponent withdrew pre-match — result is final
    "cancelled":   "ended",       # irreversible non-completion
    "abandoned":   "ended",       # no result, match will not resume
    "postponed":   "not_started", # rescheduled; no result yet
}

def map_opticodds_tennis_status(raw_status: str | None) -> str | None:
    if raw_status is None:
        return None
    mapped = _OPTICODDS_TENNIS_STATUS_MAP.get(raw_status.lower())
    if mapped is None:
        log.warning("opticodds_unknown_tennis_status", raw_status=raw_status)
        return None  # Do not write unknown statuses to DB
    return mapped
```

Log every unknown status at WARNING so that new OpticOdds status values surface quickly.

**Warning signs:**
- Tennis events showing `live` after match has been finished (walkover/retired mapped wrong)
- Mismatch alerts for tennis events that are actually correctly ended
- `opticodds_unknown_tennis_status` log entries appearing (new status values from OpticOdds)

**Phase to address:** Phase 1 (RabbitMQ consumer foundation, status mapping module) — the mapping must be complete before any status is written to the DB.

---

### Pitfall 5: `auto_ack=True` Causes Silent Message Loss on Consumer Crash

**What goes wrong:**
The OpticOdds Getting Started example uses `channel.basic_consume(..., auto_ack=True)`. With `auto_ack=True`, RabbitMQ marks messages as acknowledged the moment they are delivered to the consumer — before the callback processes them. If the consumer crashes (OOM kill, unhandled exception, SIGKILL) between receiving and processing a message, that message is permanently lost. There is no redelivery.

For a real-time tennis status consumer, this means a match status transition message (e.g., `in_progress` → `finished`) can vanish without being written to the DB. The mismatch detector will then flag the event indefinitely until a manual correction or the next corroborating poll-source update.

**Why it happens:**
`auto_ack=True` is shown in most introductory RabbitMQ examples because it simplifies the code. OpticOdds explicitly uses it in their Getting Started guide. For high-volume consumers where redelivery of duplicate messages causes problems, auto-ack makes sense. For a low-volume, stateful consumer like this one, it is a reliability liability.

**How to avoid:**
Use manual acknowledgment (`auto_ack=False`) with explicit `ch.basic_ack(delivery_tag=method.delivery_tag)` after successful DB write. The callback should only ack after all side effects (DB write, Redis publish) have completed without exception. On exception, use `basic_nack` with `requeue=True` to return the message to the queue for retry.

```python
def callback(ch, method, properties, body):
    try:
        data = json.loads(body)
        _process_tennis_event(data)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        log.exception("opticodds_message_processing_failed")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
```

Exception: if OpticOdds sends high-frequency heartbeat/ping messages that need no processing, auto-ack for those specific message types is acceptable.

**Warning signs:**
- Tennis event statuses do not update after a known match result, with no error log — the message was delivered but processing failed silently
- Consumer crashes correlate with missing status transitions visible in the DB
- `basic_nack` with `requeue=True` causing infinite redelivery loop (also a bug, but detectable)

**Phase to address:** Phase 1 (RabbitMQ consumer foundation) — manual ack must be the default from the first implementation.

---

### Pitfall 6: Running the pika Consumer in a Celery Worker Process

**What goes wrong:**
A natural temptation is to run the OpticOdds pika consumer inside a Celery task — perhaps a long-running task that calls `channel.start_consuming()` inside a worker process. This creates multiple serious problems:

1. **Celery worker memory limit kills the consumer**: `worker_max_memory_per_child=400000` (400MB) is set in `celery_app.py`. When the worker process exceeds this limit, Celery recycles it — which drops the RabbitMQ connection mid-consume without calling the queue stop API.

2. **Celery beat restarts kill the consumer**: Any Celery worker restart (deploy, OOM recycle, watchdog) terminates the pika connection. There is no Celery mechanism for "restart this task on worker death that also re-connects cleanly."

3. **Celery task queuing semantics are wrong**: Celery tasks are designed to be short-lived (seconds to minutes). A task that blocks forever in `start_consuming()` holds a Celery worker slot indefinitely, starving other tasks.

4. **`pika.BlockingConnection` I/O loop conflicts with Celery's `prefork` model**: Celery workers fork child processes. pika connections must not be shared across fork boundaries — a connection opened before a fork will be broken in the child.

**Why it happens:**
The existing `ws_prophetx.py` consumer runs as a separate Docker service (`ws-consumer`), not as a Celery task. Developers sometimes think "it's another long-running consumer, let's add it to the existing Celery worker" — but the existing WS consumer is already correctly isolated as its own service.

**How to avoid:**
Run the OpticOdds consumer as a separate Docker service (`opticodds-consumer`), exactly as `ws-consumer` runs alongside the Celery worker. The pattern is already established in this codebase. Add a new service to `docker-compose.yml`:

```yaml
opticodds-consumer:
  build: ./backend
  command: python -m app.workers.opticodds_consumer
  env_file: .env
  restart: unless-stopped
  depends_on:
    - db
    - redis
```

The consumer is a standalone Python process. It uses the same `SyncSessionLocal` and Redis client patterns as `ws_prophetx.py`. No Celery involvement.

**Warning signs:**
- Consumer task disappears from Celery worker after the `worker_max_memory_per_child` limit is hit
- Other Celery tasks queue up waiting for a slot (one slot always occupied by the consuming task)
- Consumer loses RabbitMQ connection every time any Celery worker restarts

**Phase to address:** Phase 1 (RabbitMQ consumer foundation) — architecture decision made at service creation. Retrofitting from Celery task to standalone service is a significant refactor.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| `auto_ack=True` copied from OpticOdds example | Less callback boilerplate | Silent message loss on consumer crash; missed tennis result transitions | Never in production; use manual ack |
| Running pika consumer as a Celery task | Simpler deployment (one fewer Docker service) | Consumer killed by Celery memory limits; starves task workers; fork-safety violations | Never — must be a standalone service |
| Hard-coding queue name (not calling start API) | Avoids REST API integration work | Consumer silently receives nothing if queue is not active; breaks after every restart without queue start | Never |
| Single-status fallthrough default in tennis status map (`else: return "live"`) | Fewer code lines | Unknown statuses silently treated as live; walkover matches never end | Never |
| No `blocked_connection_timeout` in `ConnectionParameters` | Slightly simpler config | Consumer hangs indefinitely if broker stops reading (resource pressure) without being detected | Never |
| Calling queue stop API only on SIGTERM, not in finally block | Simpler signal handling | Container kill (SIGKILL) or crash leaves queue active on OpticOdds side until their TTL; next startup may get stale messages | Acceptable MVP: SIGTERM is standard Docker stop signal |

---

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| OpticOdds RabbitMQ | Connecting to broker before calling queue start REST API | Call `/start` endpoint → get queue name → connect to broker using that queue name |
| OpticOdds RabbitMQ | Using a static queue name in code | Queue names are assigned by the `/start` response; store and use the returned name |
| OpticOdds RabbitMQ | Forgetting to call queue stop on shutdown | Register SIGTERM handler that calls the stop REST API before the process exits |
| pika + external host | Not setting `virtual_host="api"` in `ConnectionParameters` | Default virtual host is `/`; OpticOdds uses `api` — connection will fail or connect to the wrong VHost |
| pika `PlainCredentials` | Using ProphetX API key format (UUID) as username without testing | OpticOdds credentials are per-API-key; the username IS the API key string; verify exact format with OpticOdds docs/sales contact |
| pika blocking consumer | Using `channel.basic_get()` poll loop instead of `channel.start_consuming()` | `basic_get` is polling (pull), `start_consuming` is push. Use push; polling wastes connections and adds latency |
| tennis status mapping | Treating `suspended`/`interrupted` as terminal states | These are transient pauses (rain delay, darkness, medical timeout) — the match will resume; map to `live` |
| `compute_status_match()` | Passing OpticOdds raw status strings directly | The function expects the internal model values (`not_started`/`live`/`ended`); always map first, then pass to `compute_status_match()` |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Creating a new Redis connection per message (`_sync_redis.from_url()`) | Acceptable at low volume; same pattern as `ws_prophetx.py` | Mirror existing pattern; do not call `from_url()` per-callback if message rate spikes | >10 messages/second sustained; not a concern for tennis |
| Opening a new pika connection per message | Massive overhead (7+ TCP round trips per AMQP handshake) | Never do this; one persistent connection + one channel for the consumer | Would break immediately at any non-trivial volume |
| No `basic_qos(prefetch_count=...)` set | Broker pushes all queued messages to consumer buffer at once | Set `channel.basic_qos(prefetch_count=10)` — limits unacked messages in-flight | If the queue accumulates thousands of messages during downtime and the consumer reconnects; 4GB VPS can be overwhelmed |
| No max-length on the OpticOdds queue | During extended consumer downtime, messages accumulate on OpticOdds broker | This is managed by OpticOdds's infrastructure, not ours; however, on reconnect the consumer must process a large backlog without blocking | Not our concern if OpticOdds TTLs the queue; confirm with OpticOdds |

---

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Logging full RabbitMQ message body at INFO level | OpticOdds tennis data (match IDs, scores, player names) in Docker logs; leaks data if logs are forwarded | Log at DEBUG; at INFO log only shape (keys, sport, event_id, status) |
| Storing OpticOdds RabbitMQ credentials in `docker-compose.yml` | Credentials committed to Git history | Store in `.env` as `OPTICODDS_RMQ_USERNAME` and `OPTICODDS_RMQ_PASSWORD`; follow the existing pattern for all other API keys |
| Trusting any queue name received from network without validation | Malformed queue name causes unexpected broker behavior | Validate queue name format from start API response before passing to `basic_consume` |
| Not validating incoming message JSON schema | Unexpected OpticOdds message format causes unhandled exception and message nack storm | Wrap `json.loads` in try/except; validate required fields exist before processing |

---

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No health badge for OpticOdds consumer on dashboard | Operators cannot tell if tennis data is flowing; only discover the outage when a tennis event status is wrong | Add `opticodds_consumer` to the `/health/workers` endpoint and display it alongside the existing worker health badges |
| Binary "consumer running: yes/no" health indicator for OpticOdds | Cannot distinguish "consumer connected, queue active" from "consumer running, queue not started" | Track `last_message_at` in Redis; show "connected / queue active / last message X minutes ago" |
| No `status_source` for OpticOdds | Operators see tennis events with statuses but cannot tell which source delivered them | Add `opticodds` as a value for the existing `status_source` column / field |
| Tennis events without player names on dashboard | Dashboard shows unnamed events for tennis (individual sport, not team sport) | Map `home_team`/`away_team` to `player_1`/`player_2` from OpticOdds; use tournament name as `league`; ensure the display gracefully handles no-team events |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Consumer is running:** Verify `opticodds_queue_started` log entry appears at startup — not just `opticodds_consumer_started`. The queue start REST API must have been called and returned a queue name.
- [ ] **Consumer is receiving messages:** Check Redis `opticodds:last_message_at` is not NULL after a period covering known scheduled tennis matches — a connected consumer receiving nothing could mean queue not started.
- [ ] **Tennis status mapping is complete:** Verify `_OPTICODDS_TENNIS_STATUS_MAP` covers `retired`, `walkover`, `suspended`, `interrupted`, `cancelled`, `postponed`, `abandoned` — not just `not_started`/`in_progress`/`finished`.
- [ ] **Manual ack is in use:** Grep the consumer for `auto_ack=True` — must not be present in the main consume call.
- [ ] **`compute_status_match()` receives mapped status (not raw):** Verify the consumer calls the mapping function before passing status to `compute_status_match()` — passing a raw `"in_progress"` to `compute_status_match()` will produce wrong results (it expects `"live"`).
- [ ] **Queue stop API called on shutdown:** Verify a SIGTERM handler exists that calls the stop REST endpoint before the process exits.
- [ ] **Health dashboard updated:** Verify the `/health/workers` endpoint response includes `opticodds_consumer` field — operator dashboard must show the new consumer's state.
- [ ] **Resource baseline measured:** Check `docker stats` before and after adding the opticodds-consumer service — the new persistent TCP connection + processing should add <50MB on this VPS; if higher, investigate.

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Consumer connected but queue not started | LOW | Call queue start REST API manually or restart consumer service (which calls start on startup); verify `last_message_at` updates |
| Heartbeat starvation causing repeated disconnects | LOW | Increase `heartbeat=` parameter in `ConnectionParameters`; redeploy consumer service |
| Reconnect storm during broker outage | LOW | Consumer will self-limit once backoff is implemented; if not implemented, restart container; add backoff immediately |
| Missed status transitions during consumer downtime | MEDIUM | Trigger manual reconciliation via existing `poll_prophetx` task; for tennis specifically, check OpticOdds REST API for current match states and update DB manually or via a one-shot reconciliation script |
| Wrong tennis status mapping (e.g., suspended treated as ended) | MEDIUM | Correct the mapping; run a DB update for affected events; the mismatch detector will surface events with wrong status |
| Consumer process uses too much VPS memory | MEDIUM | Profile with `docker stats`; if the pika connection itself is leaking (channel leak), add channel lifecycle logging; consider restarting consumer nightly via a scheduled `docker restart` |
| Queue stop API not called on crash — stale queue on next start | LOW | On startup, call stop before start; or call start and handle "queue already active" gracefully; OpticOdds likely has their own TTL on abandoned queues |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Heartbeat starvation from blocking callback | Phase 1: Consumer foundation | `ConnectionParameters` includes `heartbeat=600, blocked_connection_timeout=300`; no heartbeat timeout errors in logs over 24h |
| Reconnect storm — no backoff | Phase 1: Consumer foundation | Exponential backoff with jitter visible in logs during a simulated broker disconnect test |
| Queue not started — consumer receives nothing | Phase 1: Consumer foundation | Consumer startup calls start REST API; `opticodds_queue_started` log entry appears; `last_message_at` updates during tennis windows |
| Tennis status mapping gaps (walkover, suspended, etc.) | Phase 1: Consumer foundation, status mapping | `_OPTICODDS_TENNIS_STATUS_MAP` covers all known values; unit tests for each edge case; `opticodds_unknown_tennis_status` log never fires in testing |
| `auto_ack=True` — silent message loss | Phase 1: Consumer foundation | `auto_ack=False` confirmed in code review; manual ack pattern present |
| Consumer running in Celery worker | Phase 1: Architecture | `opticodds-consumer` defined as standalone Docker service in `docker-compose.yml`; not present in `celery_app.py` include list |
| Missing health badge on dashboard | Phase 2: Health monitoring integration | `/health/workers` endpoint response includes `opticodds_consumer`; dashboard shows badge |
| `compute_status_match()` receives raw status | Phase 1: Consumer foundation | Unit test: `map_opticodds_tennis_status("in_progress")` → `"live"` → passed to `compute_status_match("live", ...)` |

---

## Sources

- pika official documentation: [Ensuring well-behaved connection with heartbeat and blocked-connection timeouts](https://pika.readthedocs.io/en/stable/examples/heartbeat_and_blocked_timeouts.html) — heartbeat=600, blocked_connection_timeout=300 pattern; delegating work to threads
- pika official documentation: [Connection Parameters](https://pika.readthedocs.io/en/stable/modules/parameters.html) — all ConnectionParameters fields and defaults
- pika official documentation: [Blocking Connection with connection recovery](https://pika.readthedocs.io/en/stable/examples/blocking_consume_recover_multiple_hosts.html) — retry loop with exception-based reconnection
- pika GitHub issue #1104: [Connection gets closed due to missed heartbeats](https://github.com/pika/pika/issues/1104) — confirmed blocking callback causes missed heartbeats
- pika GitHub issue #1333: [Problem with using multithreading in pika](https://github.com/pika/pika/issues/1333) — one connection per thread constraint
- CloudAMQP: [13 Common RabbitMQ Mistakes and How to Avoid Them](https://www.cloudamqp.com/blog/part4-rabbitmq-13-common-errors.html) — prefetch limits, connection reuse, channel thread safety
- CloudAMQP: [RabbitMQ Best Practices](https://www.cloudamqp.com/blog/part1-rabbitmq-best-practice.html) — long-lived connections, push vs pull consumption
- OpticOdds developer documentation: [Getting Started with RabbitMQ](https://developer.opticodds.com/docs/getting-started) — host=v3-rmq.opticodds.com, port=5672, virtual_host=api, queue name from /start response, auto_ack=True example (note: not recommended for production reliability)
- Sportradar Tennis API: [Match Status Workflow](https://developer.sportradar.com/tennis/docs/ig-match-status-workflow) — tennis status vocabulary (not_started, live, ended, interrupted, suspended, cancelled, delayed, retired, walkover) with canonical semantics
- Direct codebase inspection: `backend/app/workers/ws_prophetx.py` — existing standalone service pattern, exponential backoff implementation, Redis health key design, `SyncSessionLocal` usage pattern
- Direct codebase inspection: `backend/app/workers/celery_app.py` — `worker_max_memory_per_child=400000`, `task_acks_late=True` confirming Celery is unsuitable as a host for a persistent consumer
- Direct codebase inspection: `backend/app/monitoring/mismatch_detector.py` — `compute_status_match()` signature expects internal status model values, not raw source strings

---
*Pitfalls research for: Adding OpticOdds RabbitMQ consumer for tennis match status to ProphetX Market Monitor v1.3*
*Researched: 2026-04-01*
