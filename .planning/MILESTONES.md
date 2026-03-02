# Milestones: ProphetX Market Monitor

## Completed

### v1.0 — Core Monitoring Platform
**Completed:** 2026-02-26
**Deployed:** 2026-03-01 (Hetzner CX23, Tailscale access)
**Phases:** 1-3

**What shipped:**
- Docker Compose infrastructure (PostgreSQL, Redis/RedBeat, Nginx)
- JWT auth with 3-role RBAC (Admin, Operator, Read-Only)
- Event ID matching layer (sport + teams + start time, confidence scoring)
- 5 poll workers: ProphetX WS, SportsDataIO, ESPN, Sports API, Odds API
- Mismatch detection and automated status sync
- Append-only audit log
- Real-time SSE dashboard with mismatch/liquidity highlighting
- Slack alerting with 5-minute deduplication
- Alert-only mode (no ProphetX writes without explicit enable)
- In-app notification center with read/unread state

**Carried concerns → v1.1:**
- False-positive alerts (Sports API matching wrong games)
- SDIO NFL/NCAAB/NCAAF endpoints return 404
- Worker health endpoint returns 404
- Event matching confidence threshold needs real-data validation

---
*Last updated: 2026-03-01*
