# Requirements: ProphetX Market Monitor

**Defined:** 2026-03-31
**Core Value:** Operators always know the true health of their ProphetX platform — stale event statuses and low-liquidity markets are caught and resolved before they impact bettors.

## v1.2 Requirements

Requirements for WebSocket-Primary Status Authority milestone. Each maps to roadmap phases.

### WS Diagnostics & Reliability

- [ ] **WSREL-01**: System detects WS disconnection gaps and triggers immediate poll_prophetx reconciliation run on reconnect
- [ ] **WSREL-02**: WS consumer computes status_match when creating new events (fix NULL bug)

### Status Authority

- [ ] **AUTH-01**: Events table tracks status_source (ws/poll/manual) for each prophetx_status write
- [ ] **AUTH-02**: poll_prophetx skips prophetx_status overwrite when WS delivered the status recently (within configurable threshold)
- [ ] **AUTH-03**: poll_prophetx updates only metadata (teams, scheduled_start, league) when WS is authoritative for an event

### WS Health Dashboard

- [ ] **WSHLT-01**: /health/workers endpoint includes ws_prophetx connection status
- [ ] **WSHLT-02**: SystemHealth.tsx displays WS health badge alongside existing worker badges
- [ ] **WSHLT-03**: Dashboard shows Pusher connection state detail (connected/connecting/reconnecting/unavailable) with last transition time

### Tech Debt

- [ ] **DEBT-01**: SportsApiClient refactored to use BaseAPIClient pattern consistently

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

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| WSREL-01 | Phase 8 | Pending |
| WSREL-02 | Phase 8 | Pending |
| AUTH-01 | Phase 9 | Pending |
| AUTH-02 | Phase 9 | Pending |
| AUTH-03 | Phase 9 | Pending |
| WSHLT-01 | Phase 10 | Pending |
| WSHLT-02 | Phase 10 | Pending |
| WSHLT-03 | Phase 10 | Pending |
| DEBT-01 | Phase 11 | Pending |

**Coverage:**
- v1.2 requirements: 9 total
- Mapped to phases: 9
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-31*
*Last updated: 2026-03-31 — traceability filled during v1.2 roadmap creation*
