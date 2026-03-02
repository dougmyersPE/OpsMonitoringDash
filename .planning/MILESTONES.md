# Milestones: ProphetX Market Monitor

## v1.1 Stabilization + API Usage (Shipped: 2026-03-02)

**Phases:** 4-7 (4 phases, 7 plans, ~15 tasks)
**Files modified:** 61 (+7,279 / -102 lines)
**Timeline:** 6 days (2026-02-24 → 2026-03-02)
**Git range:** `8357b1f..2ca87ad`

**Key accomplishments:**
- Eliminated false-positive mismatch alerts by using actual game datetimes with tightened 6h threshold (STAB-01)
- Added Redis INCRBY call counters to all 5 poll workers with /api/v1/usage endpoint (USAGE-01)
- Replaced static Beat schedule with DB-backed intervals surviving Beat restarts (FREQ-03)
- Added server-side minimum interval enforcement with HTTP 422 validation and live RedBeat propagation (FREQ-02)
- Built complete API Usage page: provider quota cards, 7-day stacked bar chart, monthly projections, admin interval controls (USAGE-02, USAGE-03, USAGE-04, FREQ-01)
- Fixed /health/workers endpoint 404 (STAB-02), validated confidence threshold against real data (STAB-03)

**Carried concerns → v2:**
- SportsApiClient bypasses BaseAPIClient (architecturally inconsistent but functional)
- Sports API quota reads not batched (15 sequential Redis reads vs MGET)
- quota_limit_odds_api not auto-seeded (manual PATCH required)
- SDIO NFL/NCAAB/NCAAF endpoints still 404 (off-season, deferred until seasons resume)

---

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
