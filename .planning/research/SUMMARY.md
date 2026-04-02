# Project Research Summary

**Project:** ProphetX Market Monitor — v1.3 OpticOdds Tennis Integration
**Domain:** Real-time operations monitoring — external RabbitMQ consumer integration
**Researched:** 2026-04-01
**Confidence:** MEDIUM-HIGH (stack HIGH; architecture HIGH; features MEDIUM on OpticOdds endpoint schema; pitfalls HIGH)

## Executive Summary

v1.3 adds OpticOdds as a fifth real-time data source for tennis match status monitoring. Unlike the four existing poll-based workers (SDIO, ESPN, Odds API, OddsBlaze), OpticOdds delivers status updates via AMQP push over a managed RabbitMQ broker (`v3-rmq.opticodds.com`). The integration requires a persistent consumer process — not a Celery task — modeled directly after the existing `ws-consumer` Docker service that handles ProphetX WebSocket events. The net scope is narrow: one new Python package (`pika`), one new Docker service, one new worker file, one DB migration, and minor additive changes to `mismatch_detector.py`, `health.py`, and the frontend health badge.

The recommended approach is to pattern-match everything against the existing `ws_prophetx.py` / `ws-consumer` precedent. The architecture, reconnect strategy, heartbeat pattern, Redis health keys, and Docker service definition are all already proven in this codebase. The only genuinely novel work is the OpticOdds queue lifecycle (a `POST /fixtures/results/queue/start` REST call to obtain a dynamic queue name before connecting), the `pika` AMQP connection parameters for the OpticOdds broker, and a tennis status normalization mapping.

The primary risks are all implementation-level, not architectural: pika heartbeat starvation from a blocking callback, reconnect storms without exponential backoff, and silent queue mis-configuration where the consumer connects but receives nothing because the queue start REST call was not made. All three risks are well-understood and have definitive prevention strategies documented in PITFALLS.md. The status mapping risk (tennis-specific states like `walkover`, `retired`, `suspended`) is also clearly scoped. None of these risks require exploratory research during planning — the prevention patterns are known.

---

## Key Findings

### Recommended Stack

The existing stack is unchanged. v1.3 adds exactly one new Python package. `pika` (`>=1.3.2,<2.0`) is the AMQP 0-9-1 client for the OpticOdds broker — it is the library used in OpticOdds developer examples and is the standard choice for a dedicated-thread blocking consumer. `httpx` (already installed at `>=0.27`) handles the REST queue lifecycle calls synchronously inside the consumer process. No new HTTP client, no async AMQP wrapper, no local RabbitMQ broker is needed.

**New dependency:**
- `pika>=1.3.2,<2.0`: AMQP consumer — only library documented by OpticOdds; pure-Python, no native deps; supports `BlockingConnection` for the dedicated-thread pattern this project already uses

**Key connection parameters (confirmed from pika docs + OpticOdds docs):**
- `host=v3-rmq.opticodds.com`, `port=5672`, `virtual_host="api"`
- `heartbeat=600` (or 30 as per ARCHITECTURE.md — see Gap 1 below), `blocked_connection_timeout=300`
- Credentials: `OPTICODDS_RMQ_USERNAME` (= API key) and `OPTICODDS_RMQ_PASSWORD` (from sales)

**What NOT to add:** `aio-pika`, local RabbitMQ, `kombu` for this consumer, Celery task wrapping `start_consuming()`, or `requests` as a second HTTP client.

See: `.planning/research/STACK.md`

---

### Expected Features

The integration is additive. Every feature follows an existing codebase pattern with a well-defined analogue.

**Must have (table stakes) — all P1:**
- `opticodds_status` nullable `VARCHAR(50)` column on `events` table (Alembic migration 010) — unblocks all downstream work
- `_OPTICODDS_CANONICAL` status map + `compute_status_match()` updated with OpticOdds source tuple — enables mismatch detection
- `consume_opticodds.py` worker: queue start on startup, `pika.BlockingConnection`, fuzzy event matching, status write, SSE publish, heartbeat
- `opticodds-consumer` Docker service (standalone, `restart: unless-stopped`, 128m memory limit)
- `worker:heartbeat:rmq_opticodds` Redis key written on every message
- `/health/workers` endpoint updated + `SystemHealth.tsx` dashboard badge
- REST API queue lifecycle endpoints: `POST /api/v1/opticodds/queue/start`, `POST /api/v1/opticodds/queue/stop`, `GET /api/v1/opticodds/queue/status`

**Should have (operational polish) — P2, add after P1 is stable:**
- `opticodds_status` column visible in `EventsTable.tsx` (add after real data is confirmed flowing)
- `rmq:connection_state` + `rmq:connection_state_since` Redis keys for health badge tooltip
- Queue overflow protection: detect channel deletion error, auto-reinitialize queue, reconnect with new queue name
- Tennis flag-only handling for `cancelled`/`suspended` (set `is_flagged = True` without auto-advancing ProphetX status)

**Defer (v1.4+):**
- OpticOdds coverage for non-tennis sports (validate tennis end-to-end first)
- Live tennis score display (sets/games) — not an operational need for status monitoring

**Do not build:**
- Polling fallback for OpticOdds HTTP `/fixtures/results` — 4 other poll sources already cover tennis as fallback
- ProphetX write triggered by OpticOdds data alone — must be multi-source consensus per existing model
- Per-message audit log entries — only log status changes (before/after value), not every message

See: `.planning/research/FEATURES.md`

---

### Architecture Approach

v1.3 is an additive integration onto the stable v1.2 architecture (8 Docker services, `events` table with 5 source status columns). The ninth Docker service (`opticodds-consumer`) runs `app/workers/consume_opticodds.py` as a standalone blocking process — not a Celery task — using the exact same lifecycle pattern as `ws-consumer`. The consumer performs: queue start REST call on startup → `pika.BlockingConnection` to `v3-rmq.opticodds.com` → `channel.start_consuming()` blocking loop → fuzzy-match incoming `fixture-results` messages to `events` rows → write `opticodds_status` → recompute `status_match` → publish SSE → write Redis health keys. On SIGTERM, it calls the queue stop REST endpoint. On AMQP failure, it reconnects with exponential backoff (5s initial, 60s cap) without re-calling queue start (the queue name is cached in Redis).

**New components:**
1. `opticodds-consumer` Docker service — ninth service, mirrors `ws-consumer` exactly
2. `app/workers/consume_opticodds.py` — blocking AMQP consumer with queue lifecycle management
3. `app/clients/opticodds_api.py` — thin REST client wrapping `start_queue()`, `stop_queue()`, `queue_status()`
4. Alembic migration 010 — adds `opticodds_status VARCHAR(50) NULLABLE` to `events`
5. `_OPTICODDS_CANONICAL` dict in `mismatch_detector.py` + `compute_status_match()` extended with 6th optional param

**Modified components (minor additive changes only):**
- `app/core/config.py` — 3 new env vars (`OPTICODDS_API_KEY`, `OPTICODDS_RMQ_USERNAME`, `OPTICODDS_RMQ_PASSWORD`)
- `app/api/v1/health.py` — add `opticodds_consumer` key to `/health/workers` MGET
- `app/models/event.py` — add `opticodds_status` mapped column
- `app/monitoring/mismatch_detector.py` — new canonical map + updated function signatures (backward compatible)

**Unchanged:** All existing workers (`ws_prophetx.py`, all poll workers, `update_event_status.py`, `send_alerts.py`), Celery beat schedule, SSE stream, non-dashboard React pages.

See: `.planning/research/ARCHITECTURE.md`

---

### Critical Pitfalls

1. **Heartbeat starvation from blocking callback** — Set `heartbeat=600` (or conservatively `heartbeat=30`) in `ConnectionParameters` from day one. Never let the callback exceed the heartbeat interval. For tennis message rates at this scale, no thread delegation is needed. Fix: explicit `heartbeat` and `blocked_connection_timeout=300` in `pika.ConnectionParameters` before first deployment.

2. **Reconnect storm — no backoff** — Naive retry loops attempt reconnection thousands of times per minute on broker outage, exhausting FDs and spiking CPU. Fix: exponential backoff with jitter, starting at 5s, capping at 60s — mirror the existing `ws_prophetx.py` pattern exactly.

3. **Consumer connected but queue never started** — `pika.BlockingConnection` connects successfully; `start_consuming()` blocks; no messages ever arrive; no error is raised. The queue must be provisioned by calling `POST /fixtures/results/queue/start` before connecting. Fix: build queue start into the consumer startup sequence (not a manual step); abort with fatal log if the call fails; cache the queue name in Redis.

4. **Incomplete tennis status mapping** — `walkover`, `retired`, `suspended`, `interrupted`, `delayed` require explicit handling. Wrong mappings cause false-positive mismatches or matches that never terminate in the dashboard. Fix: define a complete mapping dict with no default fallthrough; log `WARNING` for any unknown status string.

5. **Consumer inside a Celery worker process** — `pika.BlockingConnection.start_consuming()` blocks indefinitely; Celery's `worker_max_memory_per_child=400000` will recycle the process; `prefork` model breaks pika connections at fork boundaries. Fix: standalone Docker service only — the `ws-consumer` precedent is already established.

See: `.planning/research/PITFALLS.md`

---

## Implications for Roadmap

The dependency chain is clear: the DB migration unblocks everything; the consumer core is the primary deliverable; health visibility and dashboard column are polish. Two phases are sufficient.

### Phase 1: Consumer Foundation

**Rationale:** All table-stakes features have hard dependencies on the `opticodds_status` DB column and the consumer process itself. The DB migration is the unblocking first step; the consumer is the primary deliverable. All critical pitfalls (heartbeat, backoff, queue lifecycle, status mapping, architecture isolation) must be addressed here — they are not retrofittable without a production incident.

**Delivers:**
- DB migration 010 (`opticodds_status` column)
- `_OPTICODDS_CANONICAL` status map + `compute_status_match()` / `compute_is_critical()` updated
- `app/clients/opticodds_api.py` (REST queue lifecycle client)
- `app/workers/consume_opticodds.py` (full AMQP consumer: queue start/stop, reconnect with backoff, fuzzy match, status write, SSE publish, heartbeat)
- `opticodds-consumer` Docker service in `docker-compose.yml`
- `/health/workers` endpoint updated + `SystemHealth.tsx` badge
- REST API queue lifecycle endpoints (`/api/v1/opticodds/queue/[start|stop|status]`)
- `.env` additions for 3 OpticOdds credential vars

**Features addressed:** All P1 table-stakes features from FEATURES.md

**Pitfalls to prevent (non-negotiable, must be in the implementation):**
- `heartbeat` + `blocked_connection_timeout` in `ConnectionParameters`
- Exponential backoff with jitter in reconnect loop
- Queue start REST call integrated into consumer startup (not manual)
- Complete tennis status map covering `walkover`, `retired`, `suspended`, `interrupted`, `cancelled`, `delayed`, `abandoned`, `postponed`
- Standalone Docker service (not Celery task)

**Research flag:** MEDIUM — OpticOdds REST endpoint exact request/response schema must be verified against live credentials before implementation. The endpoint path pattern (`/v3/copilot/results/queue/start` vs `/fixtures/results/queue/start`) has a minor discrepancy between FEATURES.md and STACK.md (see Gap 3 below). Confirm with OpticOdds docs or sales contact before coding the client.

---

### Phase 2: Operational Polish

**Rationale:** These features add resilience and operator visibility on top of a proven consumer. Adding the dashboard column before data is confirmed flowing creates confusion. Queue overflow handling requires the consumer to be stable first.

**Delivers:**
- `opticodds_status` column in `EventsTable.tsx` (add after P1 data confirmed in DB)
- `rmq:connection_state` + `rmq:connection_state_since` Redis keys + health badge tooltip
- Queue overflow detection and auto-reinitialize (channel deletion error → re-call `/queue/start` → reconnect)
- Tennis flag-only handling for `cancelled`/`suspended` (set `is_flagged = True`)

**Features addressed:** All P2 differentiator features from FEATURES.md

**Pitfall to prevent:**
- Queue overflow: 10K unread messages causes broker to delete the queue; consumer must detect AMQP channel closure with deletion error code and call `/queue/start` again to get a new queue name.

**Research flag:** LOW — all patterns are established in codebase. Queue overflow detection requires knowing the specific AMQP error code/reason string OpticOdds broker sends on queue deletion. This can be determined empirically during implementation (log the full exception on any `ChannelClosedByBroker`) rather than requiring upfront research.

---

### Phase Ordering Rationale

- The DB migration must be first because `opticodds_status` is a prerequisite for the consumer to write data, `compute_status_match()` to be updated, and the frontend column to be added.
- Consumer core and health monitoring are co-deployed in Phase 1 because a consumer with no health visibility is not production-ready — operators cannot detect if it silently stopped receiving.
- Dashboard column is deliberately deferred to Phase 2 to avoid showing an empty column to operators before data is confirmed flowing. This follows the explicit dependency note in FEATURES.md.
- Queue overflow handling belongs in Phase 2 because it requires the consumer to be stable under normal conditions first; rushing it into Phase 1 adds complexity to the most critical delivery.

### Research Flags

Needs verification before Phase 1 implementation:
- **Phase 1:** OpticOdds REST endpoint paths — minor discrepancy between research files; verify exact path format (`/v3/copilot/results/queue/start` vs `/fixtures/results/queue/start`) against live credentials or OpticOdds support before coding `opticodds_api.py`.
- **Phase 1:** `auto_ack` decision — STACK.md and PITFALLS.md recommend `auto_ack=False` with manual ack for reliability; ARCHITECTURE.md uses `auto_ack=True` citing the `ws_prophetx.py` pattern and acceptable-loss rationale. Recommendation: use `auto_ack=False` per PITFALLS.md — the overhead is minimal and the resilience benefit is real for a low-volume consumer.
- **Phase 1:** Heartbeat value — STACK.md recommends `heartbeat=600`; ARCHITECTURE.md uses `heartbeat=30`. Recommendation: use `heartbeat=30` for faster dead-connection detection; message processing time for tennis updates at this scale is well under 30 seconds.

Standard patterns (skip research-phase):
- **Phase 2:** Dashboard column, Redis connection state keys, health badge tooltip — all follow fully established codebase patterns with direct analogues already deployed.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | `pika` version, connection parameters, and threading model verified against official pika docs and existing codebase. Single-line `pyproject.toml` change. |
| Features | MEDIUM-HIGH | P1 features are grounded in direct codebase inspection and OpticOdds developer docs. OpticOdds message schema (exact JSON field names, tennis period structure) is MEDIUM — inferred from generic API reference, not a live message sample. |
| Architecture | HIGH | All integration points verified by direct inspection of `ws_prophetx.py`, `poll_oddsblaze.py`, `mismatch_detector.py`, `health.py`, `docker-compose.yml`, and `celery_app.py`. No guesswork in component boundaries. |
| Pitfalls | HIGH | pika heartbeat, reconnect, and thread-safety pitfalls sourced from official pika docs and confirmed GitHub issues. Celery incompatibility confirmed from `celery_app.py` direct inspection. OpticOdds queue lifecycle pitfall sourced from official docs. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

1. **Heartbeat value discrepancy:** STACK.md recommends `heartbeat=600`; ARCHITECTURE.md specifies `heartbeat=30`. Recommendation: use `heartbeat=30` — faster dead-connection detection, and tennis message processing is fast enough that 30s is never a risk.

2. **`auto_ack` decision:** PITFALLS.md makes a clear case for `auto_ack=False`; ARCHITECTURE.md uses `auto_ack=True` with an explicit acceptable-loss rationale. This is a product decision, not a technical ambiguity. Recommendation: use `auto_ack=False` — the overhead is negligible and the resilience benefit is real for a persistent monitoring consumer.

3. **OpticOdds REST endpoint path format:** STACK.md documents `/fixtures/results/queue/start`; FEATURES.md documents `/v3/copilot/results/queue/start`. The OpticOdds changelog (Oct 2025) confirmed copilot-specific results queue endpoints, making the `/v3/copilot/` prefix likely correct. Verify against live credentials before writing `opticodds_api.py` — wrong path means the consumer never starts.

4. **`fixture-results` message JSON schema:** The exact field names in the AMQP message body are MEDIUM confidence — inferred from the REST `/fixtures/results` endpoint shape, not confirmed from a live message sample. The consumer should log the full raw message body at DEBUG level on the first few messages received so the schema can be verified empirically before relying on parsed fields.

---

## Sources

### Primary (HIGH confidence)
- `backend/app/workers/ws_prophetx.py` — standalone consumer pattern, backoff, Redis health keys, SIGTERM handler
- `backend/app/workers/poll_oddsblaze.py` — fuzzy-match, source column write, SSE publish, `compute_status_match()` call pattern
- `backend/app/monitoring/mismatch_detector.py` — `compute_status_match()` signature, `_ODDSBLAZE_CANONICAL` pattern
- `backend/app/api/v1/health.py` — worker health endpoint structure
- `backend/docker-compose.yml` — service definitions, `ws-consumer` precedent
- `backend/pyproject.toml` — confirmed `pika` absent, `httpx>=0.27` present
- pika PyPI (`https://pypi.org/project/pika/`) — version 1.3.2, May 2023, Python >=3.7
- pika heartbeat docs (`https://pika.readthedocs.io/en/stable/examples/heartbeat_and_blocked_timeouts.html`) — `heartbeat=600`, `blocked_connection_timeout=300`
- pika `BlockingConnection` docs — single-thread constraint, `add_callback_threadsafe()`, thread delegation pattern
- pika multi-host recovery example — exception-loop reconnection pattern

### Secondary (MEDIUM confidence)
- OpticOdds Developer Docs — Getting Started with RabbitMQ (`https://developer.opticodds.com/docs/getting-started`) — host, port, vhost, pika usage, queue name from `/start` response
- OpticOdds API Reference (`https://developer.opticodds.com/reference/getting-started`) — REST endpoint paths, `X-Api-Key` auth header
- OpticOdds Fixtures Lifecycle (`https://developer.opticodds.com/reference/fixtures-lifecycle`) — status values: `unplayed`, `live`, `half`, `completed`, `cancelled`, `suspended`, `delayed`
- OpticOdds Fixtures API Reference — score structure with periods model
- OpticOdds changelog Oct 2025 — copilot-specific results queue endpoints confirmed (`https://developer.opticodds.com/changelog?page=2`)

### Tertiary (supporting context)
- CloudAMQP: 13 Common RabbitMQ Mistakes — prefetch limits, connection reuse
- Sportradar Tennis API: Match Status Workflow — tennis status vocabulary canonical semantics
- pika GitHub issues #1104, #1333 — heartbeat and thread-safety confirmed bugs

---
*Research completed: 2026-04-01*
*Ready for roadmap: yes*
