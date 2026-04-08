# ProphetX Market Monitor

## What This Is

An internal operations tool for a ProphetX prediction market operator. It continuously monitors sports event statuses on ProphetX against real-world game states (via SportsDataIO, ESPN, Odds API, and OpticOdds), automatically syncs them when mismatches are detected, monitors market liquidity levels against configurable thresholds, tracks API usage with quota monitoring and per-worker frequency controls, and surfaces all issues to the team via a real-time dashboard, Slack alerts, and an in-app notification center.

## Core Value

Operators always know the true health of their ProphetX platform — stale event statuses and low-liquidity markets are caught and resolved before they impact bettors.

## Requirements

### Validated

- ✓ Real-time polling of ProphetX events and markets — v1.0
- ✓ Real-world game status data from SportsDataIO with supplementary sources — v1.0
- ✓ Automated event status sync: Upcoming → Live → Ended — v1.0
- ✓ Alert and flag events when real-world game is postponed or cancelled — v1.0
- ✓ Configurable per-market liquidity thresholds with global defaults — v1.0
- ✓ Liquidity monitoring: alert when market falls below threshold — v1.0
- ✓ Real-time dashboard showing all events/markets with mismatch and low-liquidity highlighting — v1.0
- ✓ Slack alerting (webhook) with deduplication — v1.0
- ✓ In-app notification center with read/unread state — v1.0
- ✓ Audit log of all automated and manual actions (append-only) — v1.0
- ✓ Role-based access control: Admin, Operator, Read-Only — v1.0
- ✓ False-positive mismatch alerts eliminated (actual game datetimes + 6h threshold) — v1.1
- ✓ Worker health endpoint returns correct status — v1.1
- ✓ Confidence threshold validated against real data — v1.1
- ✓ Daily API call counts per worker visible on API Usage tab — v1.1
- ✓ Provider quota display (Odds API + Sports API per sport) — v1.1
- ✓ 7-day call volume history chart — v1.1
- ✓ Projected monthly call volume — v1.1
- ✓ Admin poll frequency controls with <5s effect — v1.1
- ✓ Server-enforced minimum poll intervals (HTTP 422) — v1.1
- ✓ DB-backed intervals surviving Beat restarts — v1.1

- ✓ WS consumer computes status_match on event creation (WSREL-02 bug fix) — v1.2 Phase 8
- ✓ WS reconnect triggers immediate poll_prophetx reconciliation (WSREL-01) — v1.2 Phase 8
- ✓ Redis WS diagnostic keys for connection health observability — v1.2 Phase 8
- ✓ status_source tracking (ws/poll/manual) on every prophetx_status write (AUTH-01) — v1.2 Phase 9
- ✓ WS authority window: poll cannot overwrite WS-delivered status within 10 minutes (AUTH-02) — v1.2 Phase 9
- ✓ Metadata-only updates when WS is authoritative (AUTH-03) — v1.2 Phase 9
- ✓ WS health badge on dashboard alongside poll worker badges (WSHLT-01, WSHLT-02) — v1.2 Phase 10
- ✓ Pusher connection state detail with transition timestamp in badge tooltip (WSHLT-03) — v1.2 Phase 10
- ✓ Sports API integration fully removed — client, worker, DB column, config, frontend references (DEBT-01) — v1.2 Phase 11
- ✓ OpticOdds AMQP consumer with pika connection, queue lifecycle, reconnection backoff (AMQP-01) — v1.3 Phase 12
- ✓ OpticOdds consumer health monitoring via Redis keys and /health/workers endpoint (AMQP-02) — v1.3 Phase 12
- ✓ OpticOdds status column in events table via migration 010 (TNNS-01 schema) — v1.3 Phase 12

- ✓ OpticOdds health badge on dashboard with connection state tooltip (DASH-01) — v1.3 Phase 14
- ✓ OpticOdds status column in events table UI with sortable header (DASH-02) — v1.3 Phase 14

- ✓ OddsBlaze toggle in Data Sources section with enable/disable control (TOGL-01) — v1.4 Phase 15
- ✓ OpticOdds toggle in Data Sources section with enable/disable control (TOGL-02) — v1.4 Phase 15
- ✓ ProphetX WS toggle in Data Sources section with enable/disable control (TOGL-03) — v1.4 Phase 15
- ✓ ProphetX WS disabled skips DB writes, connection stays alive for health monitoring (TOGL-04) — v1.4 Phase 15
- ✓ OddsBlaze toggle verified end-to-end: poll skip + clear + frontend display (TOGL-05) — v1.4 Phase 15
- ✓ OpticOdds toggle verified end-to-end: poll skip + clear + frontend display (TOGL-06) — v1.4 Phase 15

### Active

See REQUIREMENTS.md for v1.4 scoped requirements.

## Current State

Shipped v1.4 Source Toggle Completeness (2026-04-08). All 6 data sources (Odds API, SportsDataIO, ESPN, OddsBlaze, OpticOdds, ProphetX WS) are now visible and toggleable on the API Usage page. Operators can enable/disable any source; disabled sources skip polling and are excluded from mismatch detection. ProphetX WS toggle uniquely preserves the connection for health monitoring while suppressing DB writes.

No active milestone — ready for `/gsd:new-milestone`.

### Out of Scope

- Automated liquidity top-up — ProphetX API liquidity mechanics unconfirmed; financial risk
- Market creation or odds-making — not an operator tool
- Email/SMS alerting — Slack + in-app covers team needs
- Mobile native app — web dashboard sufficient
- Automated quota throttling — risk of oscillation; operators should decide
- Real-time calls/second display — always 0.0-0.1 at this scale; meaningless
- Full API call log (every request in DB) — ~1.3M rows/month, no actionable use case
- SDIO quota tracking — SDIO plans are "unlimited calls"; no quota endpoint

## Context

Shipped v1.1 with ~9,869 LOC (7,192 Python + 2,677 TypeScript).
Tech stack: FastAPI + Celery/Redis/RedBeat + PostgreSQL, React/TypeScript + Tailwind v4 + shadcn/ui v3.
Deployed on Hetzner CX23 (Tailscale access at http://100.111.249.12).
GitHub: https://github.com/dougmyersPE/OpsMonitoringDash (private).

ProphetX REST API + WebSocket consumer live at `https://api-ss-sandbox.betprophet.co/partner`.
4 poll workers: ProphetX WS, SportsDataIO, ESPN, Odds API. (Sports API removed in Phase 11.)
OpticOdds poll worker for tennis fixture status added in Phase 12-13 (converted from AMQP to REST poll).
Sports focus: NFL, NBA, MLB, NHL, NCAAB, NCAAF, Soccer.

Known tech debt:
- SDIO NFL/NCAAB/NCAAF endpoints 404 (off-season; deferred until seasons resume)
- ProphetX write endpoint still stubbed (log-only until PATCH path confirmed)

## Constraints

- **Tech Stack**: Python/FastAPI backend, React/TypeScript frontend, PostgreSQL + Redis — chosen for async polling capability, sports data ecosystem, real-time dashboard support
- **Latency**: Dashboard and status correction must reflect changes within 30 seconds
- **Reliability**: Polling workers must auto-restart; ProphetX API failures retry with exponential backoff (3 attempts); system stays up even if a data source is temporarily unavailable
- **Security**: API keys stored as environment variables; JWT auth; HTTPS only; audit log append-only
- **Deployment**: Docker Compose on VPS; infrastructure cost target ~$15-30/month

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python + FastAPI backend | Best ecosystem for sports data integrations; async-native for concurrent polling | ✓ Good — handles 5 concurrent workers well |
| Celery + Redis for background workers | Industry standard for periodic tasks; horizontally scalable | ✓ Good — RedBeat solved restart issues |
| SSE over WebSockets for dashboard | Simpler server-side implementation; unidirectional push sufficient | ✓ Good — reconnect banner handles drops |
| Liquidity: alert-only in v1 | ProphetX API top-up mechanics unconfirmed; avoid financial risk | ✓ Good — still appropriate |
| Event matching layer required | ProphetX and SportsDataIO use different IDs; match by sport + teams + time | ✓ Good — 0.90 threshold validated |
| RedBeat for Celery Beat scheduler | Prevents duplicate tasks on restart; Redis-backed | ✓ Good — DB bootstrap added in v1.1 |
| DB-backed poll intervals (v1.1) | Operator changes must survive Beat restarts; static config was fragile | ✓ Good — bootstrap reads DB on start |
| Deferred import for celery_app in API | Avoids loading Celery machinery in API process; only runs on admin PATCH | ✓ Good — clean separation |
| Recharts for data visualization | Compatible with React 19; simpler API than D3 | ✓ Good — stacked bar chart works well |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-08 — v1.4 milestone shipped*
