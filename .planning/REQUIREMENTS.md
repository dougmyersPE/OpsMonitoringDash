# Requirements: ProphetX Market Monitor

**Defined:** 2026-04-02
**Core Value:** Operators always know the true health of their ProphetX platform — stale event statuses and low-liquidity markets are caught and resolved before they impact bettors.

## v1.3 Requirements

Requirements for OpticOdds Tennis Integration milestone. Each maps to roadmap phases.

### AMQP Consumer Infrastructure

- [ ] **AMQP-01**: OpticOdds RabbitMQ consumer runs as standalone Docker service with pika, auto-reconnect on failure, and heartbeat management
- [ ] **AMQP-02**: Consumer starts OpticOdds results queue via REST API on startup and caches queue name in Redis
- [ ] **AMQP-03**: Redis keys track OpticOdds connection state (connected/reconnecting/disconnected) and last message timestamp

### Tennis Status Integration

- [ ] **TNNS-01**: Events table has `opticodds_status` column (nullable) populated by the consumer for tennis matches
- [ ] **TNNS-02**: Consumer matches OpticOdds tennis fixtures to ProphetX events by competitor names + date window (fuzzy match)
- [ ] **TNNS-03**: Walkover, retired, and suspended statuses display their actual value in the OpticOdds column and trigger Slack alerts

### Health & Dashboard

- [ ] **DASH-01**: Health endpoint includes OpticOdds consumer connection state; SystemHealth shows OpticOdds badge with connection state tooltip
- [ ] **DASH-02**: Events table shows OpticOdds status column alongside existing source columns

### Mismatch Detection

- [ ] **MISM-01**: OpticOdds status included in `compute_status_match` for tennis events; NULL safely skipped for non-tennis events

## v1.2 Requirements (Complete)

### WS Diagnostics & Reliability

- [x] **WSREL-01**: System detects WS disconnection gaps and triggers immediate poll_prophetx reconciliation run on reconnect
- [x] **WSREL-02**: WS consumer computes status_match when creating new events (fix NULL bug)

### Status Authority

- [x] **AUTH-01**: Events table tracks status_source (ws/poll/manual) for each prophetx_status write
- [x] **AUTH-02**: poll_prophetx skips prophetx_status overwrite when WS delivered the status recently (within configurable threshold)
- [x] **AUTH-03**: poll_prophetx updates only metadata (teams, scheduled_start, league) when WS is authoritative for an event

### WS Health Dashboard

- [x] **WSHLT-01**: /health/workers endpoint includes ws_prophetx connection status
- [x] **WSHLT-02**: SystemHealth.tsx displays WS health badge alongside existing worker badges
- [x] **WSHLT-03**: Dashboard shows Pusher connection state detail (connected/connecting/reconnecting/unavailable) with last transition time

### Tech Debt

- [x] **DEBT-01**: Sports API integration fully removed (client, worker, DB column, config, frontend references)

## Future Requirements

Deferred to future milestone. Tracked but not in current roadmap.

### WS Operational Metrics

- **WSOPS-01**: Reconciliation run counter displayed on dashboard or API Usage tab
- **WSOPS-02**: WS vs poll update breakdown chart showing source attribution over time
- **WSOPS-03**: Disconnect duration history and uptime percentage metrics

### Tech Debt

- **DEBT-02**: Sports API quota reads batched via Redis MGET (15 sequential reads → 1 call)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| WS message replay / event sourcing buffer | Pusher has no server-side message replay; poll reconciliation covers gaps |
| Remove polling workers | WS is single-point-of-failure; polling at 5-min intervals is insurance |
| Automated WS failover to polling-only mode | Feedback loop complexity; risk of oscillation if WS flaps |
| Client-side (browser) WebSocket health monitoring | WS consumer is server-side Python (pysher), not browser WebSocket |
| Automated liquidity top-up | ProphetX API liquidity mechanics unconfirmed; financial risk |
| Market creation or odds-making | Not an operator tool |
| OpticOdds for non-tennis sports | Tennis-only scope for v1.3; expand later if data quality is validated |
| OpticOdds odds/pricing data | Only consuming results/scores stream, not odds stream |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| WSREL-01 | Phase 8 | Complete |
| WSREL-02 | Phase 8 | Complete |
| AUTH-01 | Phase 9 | Complete |
| AUTH-02 | Phase 9 | Complete |
| AUTH-03 | Phase 9 | Complete |
| WSHLT-01 | Phase 10 | Complete |
| WSHLT-02 | Phase 10 | Complete |
| WSHLT-03 | Phase 10 | Complete |
| DEBT-01 | Phase 11 | Complete |
| AMQP-01 | — | Pending |
| AMQP-02 | — | Pending |
| AMQP-03 | — | Pending |
| TNNS-01 | — | Pending |
| TNNS-02 | — | Pending |
| TNNS-03 | — | Pending |
| DASH-01 | — | Pending |
| DASH-02 | — | Pending |
| MISM-01 | — | Pending |

**Coverage:**
- v1.3 requirements: 9 total
- Mapped to phases: 0 (pending roadmap)
- Unmapped: 9

---
*Requirements defined: 2026-04-02*
*Last updated: 2026-04-02 — v1.3 requirements defined*
