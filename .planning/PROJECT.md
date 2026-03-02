# ProphetX Market Monitor

## What This Is

An internal operations tool for a ProphetX prediction market operator. It continuously monitors sports event statuses on ProphetX against real-world game states (via SportsDataIO), automatically syncs them when mismatches are detected, monitors market liquidity levels against configurable thresholds, and surfaces all issues to the team via a real-time dashboard, Slack alerts, and an in-app notification center.

## Core Value

Operators always know the true health of their ProphetX platform — stale event statuses and low-liquidity markets are caught and resolved before they impact bettors.

## Current Milestone: v1.1 Stabilization + API Usage

**Goal:** Fix false-positive alerts and data source gaps from v1.0, add API usage monitoring with per-worker poll frequency controls.

**Target features:**
- Fix false-positive alerts (Sports API wrong-game matching)
- Fix SDIO NFL/NCAAB/NCAAF endpoint 404s
- Fix worker health endpoint 404
- Validate event matching confidence threshold against real data
- API usage tab: pull usage/limits from SDIO, Odds API, Sports API endpoints
- API usage tab: track total call volume across all workers
- API usage tab: per-worker poll frequency controls (adjustable from UI)

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

### Active

(Defined in REQUIREMENTS.md for v1.1)

### Out of Scope

- Automated liquidity top-up — deferred until ProphetX API liquidity mechanics confirmed
- Market creation or odds-making — not an operator tool for that
- Email/SMS alerting — Slack + in-app covers v1 needs
- Mobile native app — web dashboard sufficient
- Historical analytics beyond audit log — future phase

## Context

- Platform: ProphetX prediction market (sports betting markets)
- ProphetX REST API + WebSocket consumer live at `https://api-ss-sandbox.betprophet.co/partner`
- ProphetX status enum values confirmed: `ended`, `live`, `not_started`
- SportsDataIO is the existing sports data subscription (main key + soccer key)
- Sports focus: NFL, NBA, MLB, NHL, NCAAB, NCAAF, Soccer
- Supplementary sources: The Odds API, ESPN unofficial API, Sports API
- Deployed on Hetzner CX23 (Tailscale access at http://100.111.249.12)
- GitHub: https://github.com/dougmyersPE/OpsMonitoringDash (private)
- Team of multiple people with Admin, Operator, Read-Only roles
- Event ID matching layer uses sport + team names + scheduled start time with confidence scoring

## Constraints

- **Tech Stack**: Python/FastAPI backend, React/TypeScript frontend, PostgreSQL + Redis — chosen for async polling capability, sports data ecosystem, real-time dashboard support
- **Latency**: Dashboard and status correction must reflect changes within 30 seconds
- **Reliability**: Polling workers must auto-restart; ProphetX API failures retry with exponential backoff (3 attempts); system stays up even if SportsDataIO is temporarily unavailable
- **Security**: API keys stored as environment variables; JWT auth; HTTPS only; audit log append-only
- **Deployment**: Docker Compose on VPS; infrastructure cost target ~$15–30/month

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python + FastAPI backend | Best ecosystem for sports data integrations; async-native for concurrent polling | — Pending |
| Celery + Redis for background workers | Industry standard for periodic tasks; horizontally scalable | — Pending |
| SSE over WebSockets for dashboard | Simpler server-side implementation; unidirectional push sufficient | — Pending |
| Liquidity: alert-only in v1 | ProphetX API top-up mechanics unconfirmed; avoid financial risk | — Pending |
| Event matching layer required | ProphetX and SportsDataIO use different IDs; match by sport + teams + time | — Pending |

---
*Last updated: 2026-03-01 after v1.1 milestone start*
