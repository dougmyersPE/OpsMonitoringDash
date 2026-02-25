# Requirements: ProphetX Market Monitor

**Defined:** 2026-02-24
**Core Value:** Operators always know the true health of their ProphetX platform — stale event statuses and low-liquidity markets are caught and resolved before they impact bettors.

## v1 Requirements

### Core Engine

- [x] **CORE-01**: System polls ProphetX events and markets every ~30 seconds via Celery Beat workers
- [x] **CORE-02**: System polls real-world game statuses from SportsDataIO every ~30 seconds
- [ ] **CORE-03**: Event ID matching layer links ProphetX events to SportsDataIO games by sport + teams + scheduled start time, with confidence scoring (≥0.90 required to trigger auto-actions; below threshold flagged for manual review)

### Status Sync

- [ ] **SYNC-01**: System auto-updates ProphetX event status Upcoming→Live→Ended when real-world game state changes (only when match confidence ≥0.90 and distributed lock acquired)
- [ ] **SYNC-02**: System detects postponed/cancelled events and flags them with alert + dashboard indicator; manual operator resolution required
- [ ] **SYNC-03**: Operator can manually trigger status sync for any event via the dashboard

### Liquidity

- [ ] **LIQ-01**: Admin can configure per-market liquidity thresholds with a global default fallback
- [ ] **LIQ-02**: System detects when market liquidity falls below configured threshold and alerts (no auto top-up in v1)

### Dashboard

- [ ] **DASH-01**: Real-time dashboard shows all ProphetX events with current ProphetX status vs. real-world status; mismatches highlighted visually
- [ ] **DASH-02**: Real-time dashboard shows all markets with current liquidity vs. configured threshold; below-threshold markets highlighted
- [ ] **DASH-03**: Dashboard updates via Server-Sent Events (SSE) within 30 seconds of any status or liquidity change
- [ ] **DASH-04**: Dashboard shows system health indicator: polling workers active/stopped, last-checked timestamps per event

### Alerting

- [ ] **ALERT-01**: System sends Slack webhook alerts for: status mismatch detected, auto-update success, auto-update failure, low liquidity breach, cancelled/postponed event detected, ProphetX API retries exhausted
- [ ] **ALERT-02**: Alert deduplication — maximum 1 alert per event per condition type per 5 minutes (Redis TTL key pattern)
- [ ] **ALERT-03**: Alert-only mode — when enabled via admin config, system detects mismatches and alerts but takes no automated write actions to ProphetX API

### Notifications

- [ ] **NOTIF-01**: In-app notification center (bell icon + sliding panel) shows all system events with read/unread state; clicking a notification navigates to the relevant event or market

### Auth & Access

- [x] **AUTH-01**: User logs in with email and password via JWT authentication; session persists across browser refresh
- [x] **AUTH-02**: Three roles enforced server-side: Admin (full access including config), Operator (dashboard read + manual sync actions), Read-Only (dashboard view only)
- [x] **AUTH-03**: Admin can configure system settings via UI: polling interval, Slack webhook URL, global liquidity threshold, per-market liquidity thresholds, alert-only mode toggle

### Audit

- [ ] **AUDIT-01**: All automated and manual actions are logged append-only: timestamp, actor (user or system), affected event/market, action type, before state, after state — no deletions permitted
- [ ] **AUDIT-02**: Operator can view the full audit log in the dashboard with basic pagination

## v2 Requirements

### Operational Polish

- **OPER-01**: Manual event mapping correction UI — admin can confirm, reject, or manually override automatic event ID matches
- **OPER-02**: Audit log search and filter — filter by date range, actor, action type, event
- **OPER-03**: Notification acknowledgement — operator can mark notifications as "seen and handled"
- **OPER-04**: ProphetX API circuit breaker — auto-pause API calls after repeated failures, alert when circuit opens

### Data Sources

- **DATA-01**: Supplementary real-world data source (The Odds API or ESPN) as fallback when SportsDataIO lacks coverage for a specific event
- **DATA-02**: Slack digest mode — group multiple alerts within a 60-second window into a single message (e.g., during NFL Sunday bulk Live transitions)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Automated liquidity top-up | ProphetX API liquidity mechanics unconfirmed; financial risk if logic has bugs — defer until API mechanics confirmed and system has 2+ stable weeks |
| Email / SMS alerting | Slack + in-app covers v1 team needs; additional channels add integration complexity for marginal gain |
| Historical analytics / trend charts | Requires time-series aggregation and charting infrastructure; audit log covers debugging needs in v1 |
| Mobile native app | Web dashboard is sufficient for ops tool; native doubles development effort |
| Market creation / odds management | Out of scope for this tool; ProphetX manages natively |
| Real-time price / odds feed | Third polling source adds complexity; not needed for status/liquidity ops |
| Per-user notification preferences | Premature for a small team tool; global settings sufficient in v1 |
| Public API for external consumers | Internal-only tool; external API requires versioning and stability guarantees |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CORE-01 | Phase 1 | Complete |
| CORE-02 | Phase 1 | Complete |
| AUTH-01 | Phase 1 | Complete |
| AUTH-02 | Phase 1 | Complete |
| AUTH-03 | Phase 1 | Complete |
| CORE-03 | Phase 2 | Pending |
| SYNC-01 | Phase 2 | Pending |
| SYNC-02 | Phase 2 | Pending |
| SYNC-03 | Phase 2 | Pending |
| LIQ-01 | Phase 2 | Pending |
| LIQ-02 | Phase 2 | Pending |
| AUDIT-01 | Phase 2 | Pending |
| AUDIT-02 | Phase 2 | Pending |
| DASH-01 | Phase 3 | Pending |
| DASH-02 | Phase 3 | Pending |
| DASH-03 | Phase 3 | Pending |
| DASH-04 | Phase 3 | Pending |
| ALERT-01 | Phase 3 | Pending |
| ALERT-02 | Phase 3 | Pending |
| ALERT-03 | Phase 3 | Pending |
| NOTIF-01 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 21 total
- Mapped to phases: 21
- Unmapped: 0

---
*Requirements defined: 2026-02-24*
*Last updated: 2026-02-25 — AUTH-01, AUTH-02, AUTH-03 marked complete (Plan 01-02)*
