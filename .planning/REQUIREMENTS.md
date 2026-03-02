# Requirements: ProphetX Market Monitor

**Defined:** 2026-02-24
**Core Value:** Operators always know the true health of their ProphetX platform — stale event statuses and low-liquidity markets are caught and resolved before they impact bettors.

## v1.0 Requirements (Complete)

### Core Engine

- [x] **CORE-01**: System polls ProphetX events and markets every ~30 seconds via Celery Beat workers
- [x] **CORE-02**: System polls real-world game statuses from SportsDataIO every ~30 seconds
- [x] **CORE-03**: Event ID matching layer links ProphetX events to SportsDataIO games by sport + teams + scheduled start time, with confidence scoring (≥0.90 required to trigger auto-actions; below threshold flagged for manual review)

### Status Sync

- [x] **SYNC-01**: System auto-updates ProphetX event status Upcoming→Live→Ended when real-world game state changes (only when match confidence ≥0.90 and distributed lock acquired)
- [x] **SYNC-02**: System detects postponed/cancelled events and flags them with alert + dashboard indicator; manual operator resolution required
- [x] **SYNC-03**: Operator can manually trigger status sync for any event via the dashboard

### Liquidity

- [x] **LIQ-01**: Admin can configure per-market liquidity thresholds with a global default fallback
- [x] **LIQ-02**: System detects when market liquidity falls below configured threshold and alerts (no auto top-up in v1)

### Dashboard

- [x] **DASH-01**: Real-time dashboard shows all ProphetX events with current ProphetX status vs. real-world status; mismatches highlighted visually
- [x] **DASH-02**: Real-time dashboard shows all markets with current liquidity vs. configured threshold; below-threshold markets highlighted
- [x] **DASH-03**: Dashboard updates via Server-Sent Events (SSE) within 30 seconds of any status or liquidity change
- [x] **DASH-04**: Dashboard shows system health indicator: polling workers active/stopped, last-checked timestamps per event

### Alerting

- [x] **ALERT-01**: System sends Slack webhook alerts for: status mismatch detected, auto-update success, auto-update failure, low liquidity breach, cancelled/postponed event detected, ProphetX API retries exhausted
- [x] **ALERT-02**: Alert deduplication — maximum 1 alert per event per condition type per 5 minutes (Redis TTL key pattern)
- [x] **ALERT-03**: Alert-only mode — when enabled via admin config, system detects mismatches and alerts but takes no automated write actions to ProphetX API

### Notifications

- [x] **NOTIF-01**: In-app notification center (bell icon + sliding panel) shows all system events with read/unread state; clicking a notification navigates to the relevant event or market

### Auth & Access

- [x] **AUTH-01**: User logs in with email and password via JWT authentication; session persists across browser refresh
- [x] **AUTH-02**: Three roles enforced server-side: Admin (full access including config), Operator (dashboard read + manual sync actions), Read-Only (dashboard view only)
- [x] **AUTH-03**: Admin can configure system settings via UI: polling interval, Slack webhook URL, global liquidity threshold, per-market liquidity thresholds, alert-only mode toggle

### Audit

- [x] **AUDIT-01**: All automated and manual actions are logged append-only: timestamp, actor (user or system), affected event/market, action type, before state, after state — no deletions permitted
- [x] **AUDIT-02**: Operator can view the full audit log in the dashboard with basic pagination

## v1.1 Requirements

Requirements for milestone v1.1 (Stabilization + API Usage). Each maps to roadmap phases.

### Stabilization

- [ ] **STAB-01**: Sports API false-positive alerts are eliminated by using actual game start times instead of noon-UTC proxy and tightening the time-distance guard
- [ ] **STAB-02**: Worker health endpoint (`/api/v1/health/workers`) returns correct worker status instead of 404
- [ ] **STAB-03**: Event matching confidence threshold is validated against real ProphetX + source data and tuned if needed

### API Usage Tracking

- [ ] **USAGE-01**: Operator can see total API calls made per worker per day on the API Usage tab
- [ ] **USAGE-02**: Operator can see provider-reported quota (used/remaining/limit) for Odds API and Sports API on the API Usage tab
- [ ] **USAGE-03**: Operator can see a 7-day call volume history chart per worker on the API Usage tab
- [ ] **USAGE-04**: Operator can see projected monthly call volume at current polling rate on the API Usage tab

### Poll Frequency Controls

- [ ] **FREQ-01**: Admin can adjust poll frequency per worker from the API Usage tab with changes taking effect within seconds
- [ ] **FREQ-02**: Server enforces minimum poll interval per worker to prevent API abuse (HTTP 422 on violation)
- [ ] **FREQ-03**: Poll interval settings persist across Beat restarts (DB-backed, not overwritten by static config)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Operational Polish

- **OPER-01**: Manual event mapping correction UI — admin can confirm, reject, or manually override automatic event ID matches
- **OPER-02**: Audit log search and filter — filter by date range, actor, action type, event
- **OPER-03**: Notification acknowledgement — operator can mark notifications as "seen and handled"
- **OPER-04**: ProphetX API circuit breaker — auto-pause API calls after repeated failures, alert when circuit opens

### Data Sources

- **DATA-01**: Supplementary real-world data source (The Odds API or ESPN) as fallback when SportsDataIO lacks coverage for a specific event
- **DATA-02**: Slack digest mode — group multiple alerts within a 60-second window into a single message (e.g., during NFL Sunday bulk Live transitions)

### Alerting Enhancements

- **ALERT-V2-01**: Operator receives Slack alert when API quota usage exceeds configurable threshold
- **ALERT-V2-02**: Operator can see per-sport call breakdown for Sports API (basketball, hockey, baseball, football)

### Data Source Coverage

- **DATA-V2-01**: SDIO NFL/NCAAF endpoints are fixed when those seasons resume and events are active
- **DATA-V2-02**: Per-worker pause toggle from the UI (set interval to very long = effectively paused)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Automated liquidity top-up | ProphetX API liquidity mechanics unconfirmed; financial risk if logic has bugs |
| Email / SMS alerting | Slack + in-app covers team needs; additional channels add integration complexity |
| Mobile native app | Web dashboard is sufficient for ops tool |
| Market creation / odds management | Out of scope for this tool; ProphetX manages natively |
| Automated quota throttling | Risk of oscillation; operators should make the call |
| Real-time calls/second display | Always 0.0–0.1 at this scale; operationally meaningless |
| Full API call log (every request in DB) | ~1.3M rows/month, no actionable use case beyond Redis counters |
| SDIO quota tracking | SDIO plans are "unlimited calls"; no quota endpoint or headers documented |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

### v1.0

| Requirement | Phase | Status |
|-------------|-------|--------|
| CORE-01 | Phase 1 | Complete |
| CORE-02 | Phase 1 | Complete |
| AUTH-01 | Phase 1 | Complete |
| AUTH-02 | Phase 1 | Complete |
| AUTH-03 | Phase 1 | Complete |
| CORE-03 | Phase 2 | Complete |
| SYNC-01 | Phase 2 | Complete |
| SYNC-02 | Phase 2 | Complete |
| SYNC-03 | Phase 2 | Complete |
| LIQ-01 | Phase 2 | Complete |
| LIQ-02 | Phase 2 | Complete |
| AUDIT-01 | Phase 2 | Complete |
| AUDIT-02 | Phase 2 | Complete |
| DASH-01 | Phase 3 | Complete |
| DASH-02 | Phase 3 | Complete |
| DASH-03 | Phase 3 | Complete |
| DASH-04 | Phase 3 | Complete |
| ALERT-01 | Phase 3 | Complete |
| ALERT-02 | Phase 3 | Complete |
| ALERT-03 | Phase 3 | Complete |
| NOTIF-01 | Phase 3 | Complete |

### v1.1

| Requirement | Phase | Status |
|-------------|-------|--------|
| STAB-01 | Phase 4 | Pending |
| STAB-02 | Phase 4 | Pending |
| STAB-03 | Phase 4 | Pending |
| USAGE-01 | Phase 4 | Pending |
| FREQ-02 | Phase 5 | Pending |
| FREQ-03 | Phase 5 | Pending |
| USAGE-02 | Phase 6 | Pending |
| USAGE-03 | Phase 6 | Pending |
| USAGE-04 | Phase 6 | Pending |
| FREQ-01 | Phase 6 | Pending |

**Coverage:**
- v1.0 requirements: 21 total — 21 complete ✓
- v1.1 requirements: 10 total — 10 mapped ✓
- Unmapped: 0 ✓

---
*Requirements defined: 2026-02-24*
*Last updated: 2026-03-01 after v1.1 roadmap created (phases 4-6)*
