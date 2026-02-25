# Feature Research

**Domain:** Internal operations monitoring dashboard — prediction market / sports event lifecycle management
**Researched:** 2026-02-24
**Confidence:** HIGH (domain is well-understood; PRD is detailed; patterns from NOC/SOC dashboards, trading ops tools, and real-time monitoring systems are established)

---

## Feature Landscape

### Table Stakes (Users Expect These)

These are non-negotiable. Missing any of these means the system fails its stated purpose as an operations tool.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Real-time event status table | Core purpose — operators must see all ProphetX events and their current ProphetX vs. real-world status at a glance | MEDIUM | SSE stream from Redis pub/sub; dual-status columns with mismatch indicator |
| Real-time market liquidity table | Core purpose — operators must see all markets with current liquidity vs. configured threshold | MEDIUM | Same SSE stream; highlight below-threshold markets |
| Automated status sync (Upcoming → Live → Ended) | The system's primary value — removing manual status correction | HIGH | Requires event ID matching layer; Celery worker; ProphetX write API |
| Postponed/cancelled event flagging | Without this, bettors remain in open positions on dead events — high operational risk | MEDIUM | Read-only detection in v1; alert + dashboard highlight; optional auto-cancel if ProphetX API supports it |
| Status mismatch highlighting | Operators must be able to spot problems instantly without reading every row | LOW | CSS color coding: amber = mismatch detected, red = action failed, blue = resolving |
| Slack webhook alerting | Team must know about issues even when not watching the dashboard | LOW | Slack Block Kit messages; one webhook URL in config |
| In-app notification center | Audit trail of what the system has done; read/unread state | MEDIUM | Bell icon + panel; notifications link to relevant event/market |
| Configurable liquidity thresholds | Each market has different liquidity needs; global default plus per-market override | LOW | Admin-only; stored in SystemConfig and Market tables |
| Audit log (append-only) | Compliance, debugging, accountability — any operator tool that takes automated actions must log them | MEDIUM | PostgreSQL append-only table; no DELETE; before/after state in JSON |
| JWT authentication | Multi-user tool requires authentication; no shared passwords | LOW | Standard FastAPI/JWT pattern; email + password |
| Role-based access control (Admin, Operator, Read-Only) | Multiple team members with different permission levels | MEDIUM | Three roles; server-side enforcement; affects all write endpoints |
| Manual status sync trigger | Operators need an override for cases where automation fails or is uncertain | LOW | POST /events/{id}/sync-status; Operator + Admin only |
| "Last checked" timestamps | Operators must know data freshness — stale data without a timestamp is worse than no data | LOW | Display last_prophetx_poll and last_real_world_poll per row |
| System health indicator | If polling workers are down, operators must know immediately | MEDIUM | Worker heartbeat; banner/badge showing "Polling active" vs. "Polling stopped" |
| Auto-retry with exponential backoff | ProphetX API failures must not silently drop actions; team must be alerted after retries exhausted | MEDIUM | Celery retry with 1s/2s/4s backoff; after 3 failures send critical alert |
| Poll cycle configuration | Operators need to tune polling frequency without code changes | LOW | polling_interval_seconds in SystemConfig; Admin-only |

### Differentiators (Competitive/Operational Advantage)

These features separate a great ops tool from a basic one. Not required for launch, but provide meaningful value.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Event ID matching layer with manual override | ProphetX and SportsDataIO use different IDs — a robust fuzzy-matching layer (sport + teams + start time) that can be manually corrected removes the biggest integration risk | HIGH | The hardest part of the whole system; fuzzy string matching + time window; admin UI to confirm/reject matches; stored as mapping table |
| Alert deduplication / rate limiting | Without this, a single stuck event generates a Slack alert every 30 seconds — alert fatigue causes operators to ignore alerts | MEDIUM | Per-event, per-issue cooldown (e.g., 1 alert/event/minute); digest mode for bulk changes during busy sports windows |
| "Action Failed" state with manual resolution CTA | When automation fails, the UI should not just show an error — it should tell the operator exactly what to do next | LOW | "Action Failed" badge + "Retry" or "Open ProphetX" button; links to relevant audit log entries |
| Supplementary data source fallback | SportsDataIO has coverage gaps; pluggable source architecture means those gaps don't silently produce "Unknown" statuses forever | HIGH | Abstract data source interface; The Odds API or ESPN API as secondary; per-source confidence scoring |
| "Alert-only mode" (dry run) | Running in monitor-only mode for 48 hours before enabling auto-updates builds trust in the matching and detection logic | LOW | Single config flag: auto_updates_enabled in SystemConfig; when false, system detects and alerts but takes no write actions |
| Slack digest for bulk status changes | During game starts on a Sunday (NFL), 10+ events go Live simultaneously — individual alerts cause notification spam | MEDIUM | Group alerts within a 60-second window into a single Slack message: "7 events updated to Live" |
| Audit log search and filter UI | The raw audit log becomes useful only when operators can query it — date range, actor, event, action type | MEDIUM | Frontend filter panel + paginated table; relies on indexed audit_log table |
| Notification acknowledgement | Operators should be able to mark issues as "seen and handled" to reduce noise in the notification center | LOW | is_acknowledged field on Notification; acknowledged_by, acknowledged_at |
| Manual event mapping correction UI | When the automatic event ID matching is wrong, admins need a way to fix it without a database query | HIGH | Admin-only view of pending/confirmed event mappings; confirm, reject, or manually map |
| Worker health dashboard panel | Shows Celery worker status, last task run times, and task queue depths — critical for diagnosing polling failures | MEDIUM | Flower (Celery monitoring) embedded or FastAPI endpoint querying Celery inspect; read-only panel |
| ProphetX API circuit breaker | If ProphetX returns repeated errors, stop hammering their API and wait — prevents ban/rate-limit escalation | MEDIUM | Circuit breaker pattern in ProphetX client; open/half-open/closed states; alert when circuit opens |

### Anti-Features (Things to Explicitly NOT Build in v1)

These seem useful but create disproportionate problems or complexity for v1.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Automated liquidity top-up | Operators want hands-free liquidity management | ProphetX API liquidity add mechanics are unconfirmed; financial risk if logic has bugs; could drain capital on misconfigured thresholds | Alert-only in v1; add top-up only after API mechanics are confirmed and system has been running stably for 2+ weeks |
| Email/SMS alerting | Some team members prefer email; SMS feels urgent for critical alerts | Adds SendGrid/Twilio integration complexity for marginal v1 gain; Slack already covers the team | Slack + in-app covers v1; add email digest in v2 |
| Historical analytics charts | "It would be great to see liquidity trends over time" | Requires time-series data aggregation, chart library, new data model — significant scope | Audit log provides full history for debugging; add trend charts in v2 |
| Market creation / odds management | Full-featured ops console feels incomplete without it | Out of scope for this tool; ProphetX manages this natively; overlap would create confusion | Use ProphetX's own admin UI for market creation |
| Mobile native app | "Operators need to check status on the phone" | Native app doubles development effort; web dashboard on mobile browser is sufficient for an ops tool | Responsive web dashboard (tablet-primary); defer native to v2+ |
| Real-time price/odds feed | Operators like seeing market prices alongside liquidity | Odds data adds a third polling source; dashboard complexity increases significantly; not needed for status/liquidity ops | Show liquidity only; operators use ProphetX UI for odds |
| Auto-escalation chains (PagerDuty-style) | "What if no one sees the Slack alert for 10 minutes?" | Requires user on-call schedules, escalation logic, and phone integration — significant ops infrastructure | Configurable Slack channel per severity in v2 (e.g., #ops-critical vs. #ops-info); not v1 |
| Per-user notification preferences | "I only want alerts for NFL events" | Notification routing adds significant data model complexity; premature for a small team tool | Global notification settings in SystemConfig; per-user preferences in v2 |
| Public API for external consumers | "We could expose this data to other systems" | External API requires versioning, rate limiting, API key management, and stability guarantees | Internal-only REST API is sufficient; external exposure is a future architectural decision |

---

## Feature Dependencies

```
[JWT Authentication]
    └──required by──> [RBAC Enforcement]
                          └──required by──> [Admin Config Panel]
                          └──required by──> [Manual Status Sync]
                          └──required by──> [User Management]

[ProphetX API Client]
    └──required by──> [Event Status Polling Worker]
    └──required by──> [Automated Status Sync Actions]
    └──required by──> [Manual Status Sync Trigger]

[SportsDataIO API Client]
    └──required by──> [Event Status Polling Worker]

[Event Status Polling Worker]
    └──required by──> [Status Mismatch Detection]
                          └──required by──> [Automated Status Sync Actions]
                          └──required by──> [Status Mismatch Highlighting]
                          └──required by──> [Slack Alerting]
                          └──required by──> [In-App Notifications]

[Event ID Matching Layer]
    └──required by──> [Event Status Polling Worker]
    (blocking: without this, SportsDataIO data cannot be correlated to ProphetX events)

[Liquidity Polling Worker]
    └──required by──> [Low Liquidity Detection]
                          └──required by──> [Liquidity Threshold Highlighting]
                          └──required by──> [Slack Alerting (liquidity)]
                          └──required by──> [In-App Notifications (liquidity)]

[Configurable Liquidity Thresholds]
    └──required by──> [Low Liquidity Detection]

[Audit Log Writes]
    └──required by──> [Audit Log Viewer UI]
    └──required by──> [Append-Only Compliance]

[Redis Pub/Sub]
    └──required by──> [SSE Stream Endpoint]
                          └──required by──> [Real-Time Dashboard Updates]

[Alert Deduplication]
    └──enhances──> [Slack Alerting]
    └──enhances──> [In-App Notifications]

[Slack Alerting] ──independent of──> [In-App Notification Center]
(both notify but are separate channels; either can fail without breaking the other)

[Alert-Only Mode flag] ──gates──> [Automated Status Sync Actions]
(when false, detection still runs but write actions are suppressed)
```

### Dependency Notes

- **Event ID Matching Layer is the critical path blocker:** Without a working match between ProphetX event IDs and SportsDataIO game IDs, the entire monitoring engine produces no useful output. This must be solved before any status comparison logic can be validated.
- **Auth before anything write-capable:** JWT + RBAC must be in place before the admin config panel, manual sync triggers, or user management are exposed — even in development.
- **Alert deduplication must precede Slack go-live in production:** Without rate limiting, a single persistently mismatched event will flood the Slack channel every 30 seconds. Implement before enabling Slack in production.
- **Alert-only mode should be first production state:** Build the flag from the start so the rollout plan (48 hours monitor-only) is a config toggle, not a code change.
- **Redis pub/sub is the SSE backbone:** The real-time dashboard depends on polling workers publishing to Redis channels and the SSE endpoint streaming those events to browsers. Redis must be running before SSE is testable end-to-end.

---

## MVP Definition

### Launch With (v1)

- [x] Event ID matching layer (sport + teams + scheduled start time fuzzy match) — system is non-functional without this
- [x] ProphetX API client (authenticated, with exponential backoff retry) — foundation for all read/write operations
- [x] SportsDataIO API client (poll all scheduled/in-progress games by date) — foundation for real-world status
- [x] Celery polling workers: poll_sports_data + poll_prophetx on 30-second schedule — the monitoring engine
- [x] Status mismatch detection and auto-update (Upcoming→Live, Live→Ended) — primary value delivery
- [x] Postponed/cancelled event detection with alert + dashboard flag — high operational risk if missing
- [x] Liquidity polling worker with configurable thresholds — second primary value delivery
- [x] Real-time dashboard: Events Table + Markets Table with mismatch/liquidity highlighting via SSE — operator visibility
- [x] Slack webhook alerts for: mismatch detected, auto-update success/fail, low liquidity, cancellation detected — team awareness when not watching dashboard
- [x] In-app notification center (bell + panel, read/unread, click-to-navigate) — asynchronous alert review
- [x] Audit log (append-only, all auto and manual actions) — accountability and debugging
- [x] JWT authentication — required before any production use
- [x] RBAC: Admin / Operator / Read-Only with server-side enforcement — multi-user team use
- [x] Admin config panel: liquidity thresholds, polling interval, Slack webhook URL — operators must configure without code changes
- [x] Alert-only mode flag — enables safe production rollout without auto-write risk
- [x] Worker health indicator — operators must know if polling has stopped
- [x] Alert deduplication / per-event rate limiting — required before Slack goes live in production

### Add After Validation (v1.x)

- [ ] Manual event mapping correction UI — add when mismatched mappings are observed in production (trigger: first mapping error reported by operators)
- [ ] Audit log search/filter UI — add when log volume makes the raw list unwieldy (trigger: >500 audit entries)
- [ ] Supplementary data source (The Odds API or ESPN) — add when SportsDataIO coverage gaps affect specific monitored events (trigger: first "Unknown" status that blocks auto-sync)
- [ ] Slack digest for bulk changes — add when NFL/NBA Sunday volume causes alert fatigue (trigger: operators complain about Slack spam)
- [ ] Notification acknowledgement (acknowledged_by/at) — add when operators request it to manage notification center noise
- [ ] ProphetX API circuit breaker — add if ProphetX API instability becomes recurring issue (trigger: >3 circuit events in a week)

### Future Consideration (v2+)

- [ ] Automated liquidity top-up — defer until ProphetX API top-up mechanics are confirmed and system has 2+ weeks stable operational history
- [ ] Historical analytics / trend charts — build after operators request insight into patterns (why defer: significant scope, low urgency for v1 ops)
- [ ] Email digest / daily summary — add when team requests asynchronous summary (why defer: Slack covers real-time; digest is a reporting feature)
- [ ] Predictive liquidity management — requires ML model trained on historical data; no training data until system has been running
- [ ] Alert escalation chains (PagerDuty-style) — add if SLA requirements demand it (why defer: small team, Slack is sufficient)
- [ ] Per-user notification preferences — add when team grows beyond 5 operators (why defer: premature optimization)
- [ ] Multi-platform monitoring (other prediction market platforms) — add if business expands to other platforms

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Event ID matching layer | HIGH | HIGH | P1 — v1 blocker |
| ProphetX + SportsDataIO API clients | HIGH | MEDIUM | P1 — v1 blocker |
| Celery polling workers | HIGH | MEDIUM | P1 — v1 blocker |
| Auto status sync (Upcoming→Live→Ended) | HIGH | MEDIUM | P1 |
| Postponed/cancelled event flagging | HIGH | LOW | P1 |
| Liquidity threshold monitoring + alerting | HIGH | MEDIUM | P1 |
| Real-time dashboard (SSE) | HIGH | MEDIUM | P1 |
| Slack alerting | HIGH | LOW | P1 |
| JWT auth + RBAC | HIGH | MEDIUM | P1 |
| Audit log (append-only) | HIGH | LOW | P1 |
| In-app notification center | MEDIUM | MEDIUM | P1 |
| Alert deduplication | HIGH | LOW | P1 — required before production Slack |
| Alert-only mode flag | HIGH | LOW | P1 — required for rollout plan |
| Admin config panel | MEDIUM | LOW | P1 |
| Worker health indicator | MEDIUM | LOW | P1 |
| "Action Failed" state with retry CTA | MEDIUM | LOW | P1 |
| Audit log search/filter UI | MEDIUM | MEDIUM | P2 |
| Supplementary data sources | MEDIUM | HIGH | P2 |
| Slack digest for bulk changes | MEDIUM | MEDIUM | P2 |
| Notification acknowledgement | LOW | LOW | P2 |
| Manual event mapping correction UI | MEDIUM | HIGH | P2 |
| ProphetX API circuit breaker | MEDIUM | MEDIUM | P2 |
| Historical analytics charts | LOW | HIGH | P3 |
| Email/SMS alerting | LOW | MEDIUM | P3 |
| Automated liquidity top-up | HIGH | HIGH | P3 — blocked on API confirmation |
| Predictive liquidity management | MEDIUM | HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

---

## Competitor Feature Analysis

This is an internal operations tool with no direct commercial competitors. The closest analogues are:

| Feature | NOC/SOC Dashboards (e.g., Grafana, PagerDuty) | Trading Operations Tools (e.g., exchange ops consoles) | Our Approach |
|---------|----------------------------------------------|-------------------------------------------------------|--------------|
| Real-time status view | Always present; core feature | Always present; critical path | Real-time via SSE; dual-status columns (ProphetX vs. real-world) |
| Alerting | Multi-channel (email, Slack, PagerDuty, SMS) | Multi-channel; escalation chains | Slack + in-app for v1; covers the immediate team need |
| Audit log | Standard in all ops tools; immutable in financial contexts | Mandatory; regulatory requirement in trading | Append-only PostgreSQL; no delete; before/after state |
| RBAC | Standard; typically 3-5 roles | Always present; strict separation of read vs. write | Three roles (Admin, Operator, Read-Only); server-side enforcement |
| Alert deduplication | Critical; all mature alerting tools do this | Critical; alert fatigue is a known ops problem | Per-event rate limiting + optional digest mode |
| Automated remediation | Present in mature NOC tools (runbooks) | Present in automated trading risk systems | Auto status sync is the core automation; more remediation in v2 |
| Event ID correlation | Not typically a problem in homogeneous systems | Cross-system ID mapping is a known hard problem | Custom matching layer: sport + teams + start time + fuzzy string |
| Manual override | Always present as safety valve | Always present; critical for human-in-the-loop | Manual sync trigger; alert-only mode as global override |

---

## Key Design Decisions Implied by Feature Analysis

1. **Event ID matching is the riskiest feature and must be built first.** Everything else depends on it. Budget for it being harder than expected — fuzzy team name matching across different data sources is non-trivial (e.g., "LA Lakers" vs. "Los Angeles Lakers" vs. "Lakers").

2. **Alert-only mode is not optional for rollout.** The rollout plan calls for 48 hours of monitor-only operation. This must be a day-one config flag, not something added later.

3. **Deduplication before production Slack.** Without a 1-alert-per-event-per-minute cooldown, a single stuck event generates 120 Slack alerts/hour. This is a v1 blocker for production use, even though it reads like a v2 nice-to-have.

4. **Audit log must be append-only by design, not convention.** Use PostgreSQL row-level security or application-level enforcement to prevent deletions. This is a compliance feature, not just logging.

5. **SSE over WebSockets is correct for this use case.** The dashboard only needs server-to-client push. WebSockets add bidirectional complexity that is not needed. SSE reconnects automatically and is simpler to implement and debug.

6. **RBAC must be server-side enforced.** Frontend role checks are for UX only. Every write endpoint must verify role server-side. This is especially critical for audit log integrity and threshold configuration.

---

## Sources

- Project context: `/Users/doug/Prophet API Monitoring/.planning/PROJECT.md`
- Full PRD: `/Users/doug/Prophet API Monitoring/docs/PRD.md`
- Domain knowledge: NOC/SOC dashboard patterns, trading operations tooling, prediction market operator workflows (HIGH confidence — established, well-documented domain)
- Alert deduplication pattern: industry-standard practice in all production monitoring systems (e.g., PagerDuty, OpsGenie, Grafana Alerting all implement de-duplication as a core feature)
- Event ID matching complexity: known hard problem in sports data integration; documented in SportsDataIO and similar provider documentation patterns
- Circuit breaker pattern: Martin Fowler's circuit breaker pattern; Celery retry/chord patterns

*Note: WebSearch and Brave Search unavailable during this research session. All findings based on PRD analysis and domain knowledge. Confidence is HIGH for this domain — internal ops monitoring dashboard patterns are well-established and the PRD is detailed enough to drive complete feature categorization without external sources.*

---
*Feature research for: ProphetX Market Monitor — internal operations monitoring dashboard*
*Researched: 2026-02-24*
