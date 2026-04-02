# Phase 12: Consumer Foundation - Context

**Gathered:** 2026-04-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Standalone OpticOdds AMQP consumer service that connects to the OpticOdds RabbitMQ broker (`v3-rmq.opticodds.com`), manages queue lifecycle automatically on startup/shutdown, writes tennis match status data to the `opticodds_status` DB column, and reconnects reliably with exponential backoff. The consumer runs as a dedicated Docker service (not a Celery task), following the `ws-consumer` precedent exactly.

Requirements: AMQP-01, AMQP-02, TNNS-01

</domain>

<decisions>
## Implementation Decisions

### Queue Lifecycle Management
- **D-01:** Consumer is fully self-managing — starts queue on boot via OpticOdds REST call, stops queue on SIGTERM. No operator-facing REST endpoints (`/api/v1/opticodds/queue/start|stop|status`). Operators use `docker compose restart opticodds-consumer` if manual intervention is needed. Matches the `ws-consumer` pattern exactly.
- **D-02:** Queue name cached in Redis after startup REST call. Consumer aborts with fatal log if queue start call fails.

### OpticOdds Endpoint Path
- **D-03:** `OPTICODDS_BASE_URL` configurable env var with default pointing to `/v3/copilot/results/queue/start` path (per Oct 2025 changelog, most likely correct). Easy to override without code change if the path turns out to be `/fixtures/results/queue/start` instead.

### Unknown Status Handling
- **D-04:** When an unmapped tennis status string arrives: (1) write the raw value verbatim to `opticodds_status` column, (2) log at WARNING level, (3) fire a Slack alert so operators investigate. No data loss, no silent failures.
- **D-05:** Known statuses use the `_OPTICODDS_CANONICAL` mapping dict. No default fallthrough — every status is either explicitly mapped or handled via D-04.

### Carried Forward (locked in research/prior phases)
- **D-06:** Standalone Docker service (`opticodds-consumer`), `restart: unless-stopped` — pika `BlockingConnection` blocks indefinitely; Celery incompatible (research pitfall #5)
- **D-07:** `heartbeat=30`, `blocked_connection_timeout=300` in pika `ConnectionParameters` — faster dead-connection detection; tennis message processing well under 30s (research decision)
- **D-08:** `auto_ack=False` with manual ack — negligible overhead, real resilience benefit for low-volume consumer (research decision)
- **D-09:** Exponential backoff with jitter on reconnect: 5s initial, 60s cap — mirrors `ws_prophetx.py` pattern (research decision)
- **D-10:** Log full raw message body at DEBUG level on first few messages to verify AMQP message schema empirically (research flag — MEDIUM confidence on exact JSON field names)

### Claude's Discretion
- Redis health key design for the consumer (key names, TTLs, update frequency) — follow `ws_prophetx.py` patterns with `ws:*` → `rmq:*` prefix adaptation
- DB migration 010 specifics (column type, index decisions)
- Consumer logging verbosity beyond the explicit decisions above
- `opticodds_status` model column mapping details

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Consumer Pattern (primary analogue)
- `backend/app/workers/ws_prophetx.py` — Standalone consumer pattern: reconnect logic, Redis health keys, SIGTERM handler, heartbeat. The OpticOdds consumer mirrors this architecture.
- `backend/docker-compose.yml` — `ws-consumer` service definition; `opticodds-consumer` follows identical structure

### Fuzzy Matching & Status Processing
- `backend/app/workers/poll_oddsblaze.py` — Fuzzy-match pattern, source column write, SSE publish, `compute_status_match()` call pattern
- `backend/app/monitoring/mismatch_detector.py` — `compute_status_match()` signature, `_ODDSBLAZE_CANONICAL` dict pattern for status mapping

### Health & Infrastructure
- `backend/app/api/v1/health.py` — `/health/workers` endpoint; add `opticodds_consumer` key to Redis MGET
- `backend/app/core/config.py` — Settings pattern for new env vars (`OPTICODDS_API_KEY`, `OPTICODDS_RMQ_USERNAME`, `OPTICODDS_RMQ_PASSWORD`, `OPTICODDS_BASE_URL`)
- `backend/app/models/event.py` — Event model; add `opticodds_status` mapped column

### Research (verified architecture)
- `.planning/research/SUMMARY.md` — Full research summary with confidence assessment and gaps
- `.planning/research/ARCHITECTURE.md` — Detailed architecture approach for the consumer
- `.planning/research/PITFALLS.md` — Critical pitfalls with prevention strategies (heartbeat starvation, reconnect storms, silent queue misconfiguration)
- `.planning/research/STACK.md` — pika connection parameters, dependency details
- `.planning/research/FEATURES.md` — P1/P2 feature breakdown with phase mapping

### Requirements
- `.planning/REQUIREMENTS.md` §AMQP Consumer Infrastructure — AMQP-01 (consumer service), AMQP-02 (queue start + Redis cache)
- `.planning/REQUIREMENTS.md` §Tennis Status Integration — TNNS-01 (opticodds_status column)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ws_prophetx.py` — Full standalone consumer pattern: `_connect_and_run()`, `_handle_broadcast_event()`, `_write_heartbeat()`, SIGTERM handler, Redis health keys. Direct template for the OpticOdds consumer.
- `poll_oddsblaze.py` — Fuzzy matching logic, `compute_status_match()` integration, SSE publish pattern
- `mismatch_detector.py` — `_ODDSBLAZE_CANONICAL` dict pattern for status normalization; `compute_status_match()` function signature
- `httpx` (already installed `>=0.27`) — REST client for queue lifecycle calls; no new HTTP dependency needed

### Established Patterns
- Worker heartbeat: `worker:heartbeat:{name}` key with TTL, written periodically
- Redis health keys: `ws:connection_state`, `ws:last_message_at` pattern (Phase 8)
- Docker service: `ws-consumer` in `docker-compose.yml` with `restart: unless-stopped`
- Config: `Settings` class in `config.py` with env var bindings
- Alembic migrations: sequential numbering (last was 009 for Phase 11)

### Integration Points
- `docker-compose.yml` — Add `opticodds-consumer` service definition
- `backend/pyproject.toml` — Add `pika>=1.3.2,<2.0` dependency
- `backend/app/core/config.py` — Add 4 new env vars
- `backend/app/models/event.py` — Add `opticodds_status` column
- `backend/app/api/v1/health.py` — Add consumer health key to MGET
- `.env` / `.env.example` — Add OpticOdds credential placeholders

</code_context>

<specifics>
## Specific Ideas

- Consumer should mirror `ws-consumer` Docker service definition as closely as possible — same restart policy, similar memory limits, same network
- The `OPTICODDS_BASE_URL` env var approach means the endpoint path discrepancy (Gap 3 from research) is handled without blocking implementation
- Unknown statuses stored raw + alerted ensures no tennis status vocabulary surprises are missed during initial rollout

</specifics>

<deferred>
## Deferred Ideas

- **REST API queue endpoints** — Operator-facing `/api/v1/opticodds/queue/start|stop|status` endpoints were discussed but deferred. Self-managing consumer is sufficient for now. Could add in a future phase if operators need finer control.
- **Health badge** — DASH-01 mapped to Phase 14. Basic health key infrastructure ships in Phase 12 (Redis keys), but the dashboard badge UI ships in Phase 14.

None — discussion stayed within phase scope

</deferred>

---

*Phase: 12-consumer-foundation*
*Context gathered: 2026-04-02*
