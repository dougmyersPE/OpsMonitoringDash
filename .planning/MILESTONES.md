# Milestones: ProphetX Market Monitor

## v1.4 Source Toggle Completeness (Shipped: 2026-04-08)

**Phases completed:** 8 phases, 14 plans, 26 tasks

**Key accomplishments:**

- Test hanging issue (Task 2):
- Pure is_ws_authoritative() helper, Event model columns (status_source + ws_delivered_at), Alembic migration 008, and WS_AUTHORITY_WINDOW_SECONDS=600 config setting with 5 TDD unit tests
- Authority wiring into all three workers: ws_prophetx sets status_source='ws'+ws_delivered_at on 3 code paths; poll_prophetx checks is_ws_authoritative() with metadata-unconditional split; update_event_status sets status_source='manual'; 17 integration tests covering all behaviors
- ProphetX WebSocket connection health surfaced on operator dashboard via extended /health/workers endpoint and WS badge with Pusher state tooltip
- Sports API (api-sports.io) fully excised from backend: client/worker deleted, DB column dropped via migration 009, mismatch detector reduced to 4-source signatures, all callers updated across 10 files
- Sports API fully excised from frontend and planning docs: EventsTable column removed, SystemHealth badge removed, all API Usage page references eliminated, SportsApiQuotaCard deleted, ROADMAP/REQUIREMENTS/architecture updated to reflect removal
- pika AMQP dependency, four OpticOdds Settings fields, and opticodds_status VARCHAR(50) column (migration 010) laying the schema foundation for the OpticOdds AMQP consumer
- One-liner:
- opticodds-consumer Docker Compose service plus opticodds_consumer key in /health/workers endpoint following the ws_prophetx shape (connected/state/since), backed by Redis opticodds:connection_state keys
- OpticOdds extended as 6th mismatch detection source with _OPTICODDS_CANONICAL mapping and all 13 call sites updated
- OpticOdds consumer now fuzzy-matches tennis messages to ProphetX events and writes opticodds_status with verbatim special status handling and Slack alerting
- OpticOdds consumer health badge and per-event status column added to operator dashboard, exposing Phase 12-13 data in the UI
- ProphetX WS toggle guard added to ws_prophetx._upsert_event, poll_prophetx authority bypass wired for D-03, and usage API extended to return all 6 source toggle states
- SOURCE_DISPLAY extended with OddsBlaze, OpticOdds, ProphetX WS — all 6 data sources now visible and toggleable in the API Usage page Data Sources section

---

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
