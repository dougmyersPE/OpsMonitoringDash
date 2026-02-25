# ProphetX Market Monitor

## What This Is

An internal operations tool for a ProphetX prediction market operator. It continuously monitors sports event statuses on ProphetX against real-world game states (via SportsDataIO), automatically syncs them when mismatches are detected, monitors market liquidity levels against configurable thresholds, and surfaces all issues to the team via a real-time dashboard, Slack alerts, and an in-app notification center.

## Core Value

Operators always know the true health of their ProphetX platform — stale event statuses and low-liquidity markets are caught and resolved before they impact bettors.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Real-time polling of ProphetX events and markets every ~30 seconds
- [ ] Real-world game status data from SportsDataIO (primary) with supplementary sources as fallback
- [ ] Automated event status sync: Upcoming → Live → Ended when real-world state changes
- [ ] Alert and flag events when real-world game is postponed or cancelled (manual action required)
- [ ] Configurable per-market liquidity thresholds with global defaults
- [ ] Liquidity monitoring: alert when market falls below threshold (no auto-top-up in v1)
- [ ] Real-time dashboard showing all events/markets with mismatch and low-liquidity highlighting
- [ ] Slack alerting (webhook) for status mismatches, auto-updates, liquidity breaches, action failures
- [ ] In-app notification center with read/unread state
- [ ] Audit log of all automated and manual actions (append-only)
- [ ] Role-based access control: Admin, Operator, Read-Only

### Out of Scope

- Automated liquidity top-up — deferred until ProphetX API liquidity mechanics confirmed
- Market creation or odds-making — not an operator tool for that
- Email/SMS alerting — Slack + in-app covers v1 needs
- Mobile native app — web dashboard sufficient
- Historical analytics beyond audit log — future phase

## Context

- Platform: ProphetX prediction market (sports betting markets)
- ProphetX has a REST API with authentication; exact status enum values to be confirmed from API docs
- SportsDataIO is the existing sports data subscription (Doug's account)
- Sports focus: primarily NFL, NBA, MLB, NHL and other major leagues covered by SportsDataIO
- Supplementary sources (The Odds API, ESPN unofficial API, web scraping) fill gaps where SportsDataIO lacks coverage
- Greenfield project — no existing codebase
- Team of multiple people needs access (Admin, Operator, Read-Only roles)
- Deployment: VPS/cloud (Docker + Docker Compose, Nginx, SSL)
- Critical implementation risk: event ID mapping between ProphetX and SportsDataIO must be solved with a matching layer (sport type + team names + scheduled start time)

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
*Last updated: 2026-02-24 after initialization*
