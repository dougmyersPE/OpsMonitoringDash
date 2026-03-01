# Architecture: ProphetX Market Monitor

## System Overview

ProphetX Market Monitor is an internal operations tool for a ProphetX prediction market operator. It continuously polls five external sports data sources, fuzzy-matches those games to ProphetX events, and detects when a game's real-world status (live, ended, postponed) disagrees with what ProphetX shows. When a mismatch is found, the system automatically writes a status correction to ProphetX, sends a Slack alert, and surfaces the issue in a real-time dashboard — all within roughly 30 seconds of the real-world change.

The system is used exclusively by the internal ops team (admin, operator, read-only roles). It is not user-facing. The primary value is preventing bettors from placing wagers on events with stale statuses — a live game showing as "not started" in ProphetX is the worst-case scenario.

The entire stack runs on a single Hetzner CX23 VPS inside Docker Compose. Team access is via Tailscale; no public domain or SSL is required.

---

## Tech Stack

**Backend: FastAPI + Celery**
FastAPI was chosen for its async-native request handling, which is critical when 5 poll workers each need their own database connections without thread contention. Celery handles periodic task scheduling with RedBeat as the Beat scheduler — RedBeat is Redis-backed, which prevents the common problem of duplicate tasks firing when the Beat container restarts.

**Database: PostgreSQL 16 + SQLAlchemy (asyncpg)**
Standard choice for relational data with audit-log requirements. asyncpg gives native async support without thread pool overhead. Alembic handles migrations and runs automatically at container startup (`alembic upgrade head` before uvicorn).

**Cache & Broker: Redis**
Used for three distinct purposes: Celery task broker/result backend, SSE pub/sub channel (`prophet:updates`), and short-lived application cache (team name lookups, soccer competition lists, alert deduplication TTLs, worker heartbeats). Configured with `maxmemory 256mb` + `allkeys-lru` to avoid OOM-killing the Celery broker under memory pressure.

**Frontend: React 19 + TypeScript + Vite**
Tailwind v4 (via `@tailwindcss/vite` plugin, no config file) and shadcn/ui v3 for components. TanStack React Query for cache management; Zustand for auth state (persisted to localStorage or sessionStorage depending on "remember me"). Real-time updates via SSE — simpler than WebSockets for a unidirectional push use case.

**Infrastructure: Docker Compose + Nginx**
8 services, single-host deployment. Nginx sits in front as a reverse proxy with special SSE handling (`proxy_buffering off`, `chunked_transfer_encoding off`). Code is baked into images at build time — no bind mounts — so a code change requires `docker compose build <svc> && docker compose up -d <svc>`.

---

## Directory Structure

```
.
├── backend/
│   ├── app/
│   │   ├── api/v1/         # FastAPI route handlers (9 modules)
│   │   ├── clients/        # External API clients (ProphetX, SDIO, Odds API, Sports API, ESPN)
│   │   ├── core/           # Config (Pydantic Settings), security (JWT/bcrypt), constants
│   │   ├── db/             # SQLAlchemy async engine, sync engine (for Celery), Redis pool
│   │   ├── models/         # ORM models (Event, Market, User, AuditLog, Notification, etc.)
│   │   ├── monitoring/     # EventMatcher, MismatchDetector, LiquidityMonitor (pure functions)
│   │   ├── schemas/        # Pydantic request/response shapes
│   │   ├── workers/        # Celery app config + all task modules + WS consumer
│   │   ├── main.py         # FastAPI app setup, router registration, lifespan
│   │   └── seed.py         # One-time admin user creation on startup
│   ├── alembic/versions/   # 5 schema migrations (001–005)
│   └── tests/
├── frontend/
│   └── src/
│       ├── api/            # axios query functions (events, markets, notifications)
│       ├── components/     # UI components (EventsTable, SseProvider, NotificationCenter, etc.)
│       ├── hooks/          # useSse hook
│       ├── pages/          # LoginPage, DashboardPage, MarketsPage
│       ├── stores/         # Zustand auth store
│       └── lib/            # statusDisplay utilities, Tailwind merge helper
├── nginx/nginx.conf        # Reverse proxy — routes /api/, /api/v1/stream (SSE), / (SPA)
└── docker-compose.yml      # 8-service orchestration with memory limits
```

The `backend/app/monitoring/` directory is the intellectual core of the system — those pure functions do all the status comparison logic and should be treated carefully. The `workers/` directory contains the tasks that call those functions on schedule.

---

## Data Flow

### Primary: Real-World Status Update

```
Celery Beat (RedBeat)
    └─► poll_sports_data task (every 30s)
            ├── Fetch games: yesterday/today/tomorrow from SDIO
            ├── Load all ProphetX events from DB
            ├── EventMatcher: fuzzy-match each event to a SDIO game
            │       confidence = 0.35×home + 0.35×away + 0.30×start_time_proximity
            ├── confidence ≥ 0.90 → update sdio_status on Event row
            ├── compute_status_match() → recompute status_match
            ├── mismatch detected → enqueue send_alerts + update_event_status tasks
            └── Redis PUBLISH prophet:updates → SSE subscribers → frontend cache invalidation
```

The other 4 workers (Odds API, Sports API, ESPN, poll_prophetx) follow the same pattern but run less frequently and update different `*_status` columns on the Event row.

### ProphetX Real-Time: WebSocket Consumer

```
ws_prophetx (standalone service, not Celery)
    └── Persistent Pusher connection to ProphetX
            ├── sport_event message → upsert Event row
            │       └── update last_prophetx_poll (only WS writes this field)
            └── Redis PUBLISH prophet:updates → SSE → frontend
```

The WebSocket consumer updates ProphetX status in real time; `poll_prophetx` runs every 5 minutes as reconciliation fallback if the WS connection drops.

### SSE: Dashboard Real-Time Updates

```
Worker publishes → Redis prophet:updates channel
                        └── GET /api/v1/stream (SSE endpoint, authenticated via ?token=)
                                └── frontend SseProvider receives event
                                        └── queryClient.invalidateQueries() → refetch affected data
```

No data is sent in the SSE payload beyond `{type, entity_id}`. The frontend always fetches fresh data from the REST API after invalidation. This keeps the SSE logic simple and avoids stale cache issues.

---

## Key Abstractions

**Event** — The central entity. An `events` row represents a single ProphetX sport event and stores status columns from every data source (`prophetx_status`, `sdio_status`, `odds_api_status`, `sports_api_status`, `espn_status`). `status_match` (all sources agree) and `is_flagged` (any source reports postponed/cancelled) are recomputed each poll cycle, not stored as sticky state.

**EventMatcher** (`monitoring/event_matcher.py`) — Fuzzy-matches a ProphetX event to a real-world game using team name similarity (rapidfuzz `token_sort_ratio`) and start time proximity. Weights: 35% home team, 35% away team, 30% start time. Threshold of 0.90 triggers auto-action; below that the match is flagged for manual review. The mapping is cached in `EventIDMapping` rows.

**MismatchDetector** (`monitoring/mismatch_detector.py`) — Pure functions that convert each source's status strings to a canonical three-value form (`scheduled / inprogress / final`) and compare them. `compute_is_critical()` identifies the most severe case: real-world game is live but ProphetX shows `not_started`. These functions are called in every poll worker after updating the status column.

**send_alerts task** (`workers/send_alerts.py`) — Redis SETNX deduplication (`alert_dedup:{type}:{entity_id}`, 300s TTL) ensures at most one alert per event per condition per 5-minute window. Always writes an in-app Notification row regardless of Slack configuration; Slack is best-effort.

**update_event_status task** (`workers/update_event_status.py`) — Currently stubbed (logs but does not write). Intended to call `PATCH /mm/update_sport_event_status` on ProphetX. Uses a distributed lock to prevent two workers from correcting the same event simultaneously.

**SystemConfig** — Key/value table in the DB. `alert_only_mode` is the most important key: when `"true"`, the system detects mismatches and alerts but skips the ProphetX write. Read fresh from DB at task start (not cached) so an admin toggle takes effect within one poll cycle without a restart.

---

## API / Interface Boundaries

All endpoints are under `/api/v1/`. Authentication is JWT (HS256) via `Authorization: Bearer <token>` header. The SSE endpoint (`/api/v1/stream`) uses `?token=<jwt>` in the query string because the EventSource API cannot set headers.

Login is `POST /api/v1/auth/login` with `application/x-www-form-urlencoded` body (not JSON) — this is the OAuth2PasswordRequestForm pattern, which enables the Swagger UI Authorize button.

| Method | Path | Role | Purpose |
|--------|------|------|---------|
| POST | `/auth/login` | public | Get JWT |
| GET | `/health` | public | Postgres + Redis liveness |
| GET | `/health/workers` | any | Worker heartbeat status |
| GET | `/events` | any | All events with status columns |
| POST | `/events/refresh-all` | operator+ | Immediately enqueue all poll workers |
| POST | `/events/{id}/sync-status` | operator+ | Manually trigger status correction |
| GET | `/markets` | any | All markets with liquidity |
| GET | `/audit` | any | Paginated audit log (read-only) |
| GET | `/notifications` | any | In-app notifications |
| PATCH | `/notifications/mark-all-read` | any | Mark all notifications read |
| PATCH | `/notifications/{id}/read` | any | Mark one notification read |
| GET | `/stream` | any | SSE stream (auth via ?token=) |
| GET | `/config/system` | admin | Read system config |
| PATCH | `/config/system/{key}` | admin | Update config (e.g., alert_only_mode) |

No API versioning beyond the `/v1/` prefix. No rate limiting implemented.

---

## Configuration & Environment

All configuration flows through `app/core/config.py` (Pydantic Settings, reads `.env`). The `.env.example` at repo root documents every variable.

**Required:**
- `POSTGRES_*` — connection credentials
- `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `REDBEAT_REDIS_URL`
- `JWT_SECRET` (min 32 chars), `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`
- `PROPHETX_BASE_URL`, `PROPHETX_ACCESS_KEY`, `PROPHETX_SECRET_KEY`
- `SPORTSDATAIO_API_KEY`
- `ADMIN_EMAIL`, `ADMIN_PASSWORD`

**Optional (degrades gracefully if missing):**
- `SPORTSDATAIO_SOCCER_API_KEY` — soccer polling disabled if absent
- `ODDS_API_KEY` — Odds API polling skipped
- `SPORTS_API_KEY` — Sports API polling skipped
- `SLACK_WEBHOOK_URL` — Slack alerts disabled; in-app notifications still work

**Poll intervals** (`POLL_INTERVAL_*`) have hardcoded defaults and are optional env vars.

Dev and prod use the same Docker Compose file; the only difference is the `.env` contents. There is no staging environment.

---

## Testing Strategy

Tests live in `backend/tests/` and use `pytest` + `pytest-asyncio`. The event loop scope is set to `session` (in `pyproject.toml`) because asyncpg connection pools are tied to the event loop — function-scoped loops break pool connections on the second test.

Test user creation uses `SyncSessionLocal` (not async) in fixtures to avoid async session scope conflicts with the test setup.

Coverage is not extensive. The monitoring pure functions (`mismatch_detector.py`, `event_matcher.py`) have unit tests. Poll workers do not have integration tests against live APIs; they're validated manually during deployment. This is a known gap — the fuzzy matching logic in particular would benefit from a fixture-based test suite against real API data samples.

To run tests: `docker compose exec backend pytest` or locally `uv run pytest` from `backend/`.

---

## Deployment & Infrastructure

**Production server:** Hetzner CX23 (2 vCPU, 4 GB RAM, ~$6/month). Code at `/root/prophet-monitor`. Team accesses via Tailscale at `http://100.111.249.12`. No SSL, no public domain — Tailscale handles network security.

**To deploy a code change:**
```bash
# From your local machine
rsync -av --exclude='.git' --exclude='.env' . root@46.225.233.32:/root/prophet-monitor/

# On the server
cd /root/prophet-monitor
docker compose build <svc>
docker compose up -d <svc>
```

**To deploy a migration only** (schema change, no code change):
```bash
# Restart backend — it runs `alembic upgrade head` on startup
docker compose up -d --force-recreate backend
```

**Celery Beat / Worker restarts** require both services restarted together to avoid the RedBeat lock timeout mismatch. `redbeat_lock_timeout=900` (must be ≥ 3× the longest poll interval; default 300s).

There is no CI/CD pipeline. All deployments are manual. Code is also mirrored to GitHub (`dougmyersPE/OpsMonitoringDash`, private), but the server deploys from rsync, not git pull.

---

## Known Tech Debt & Gotchas

**ProphetX write is stubbed.** `update_event_status` logs a "would update" message but never calls ProphetX. The endpoint path (`PATCH /mm/update_sport_event_status`) has not been confirmed. Until this is un-stubbed, the system is alert-and-detect only — it does not actually correct ProphetX statuses.

**`status_match` recomputation in poll_prophetx is global.** Every ProphetX reconciliation poll (every 5 min) recomputes `status_match` for all events, not just the ones it updated. This was an intentional fix for a stale-state bug but is O(n) against the event table. Fine at current scale; worth revisiting if event count grows to thousands.

**Confidence threshold (0.90) is unvalidated.** It was set based on one known example (`'LA Lakers' vs 'Los Angeles Lakers'` scores 0.857). Needs systematic validation against a real ProphetX event dump and real SDIO game data. Until validated, there may be silent false negatives (missed matches) or false positives (wrong matches above threshold).

**SDIO NFL/NCAAB/NCAAF returns 404.** These sports are in the worker code but fail silently — 404 is treated as "no games." The root cause (different URL format for those sports vs. NBA/MLB/NHL) hasn't been investigated. Fall-through to ESPN and Sports API covers the gap.

**Docker networking / Tailscale subnet conflict.** The Hetzner server has `172.17.0.0/16` advertised via Tailscale (company subnet). Docker's default bridge uses the same range. The fix is in `/etc/docker/daemon.json`: `default-address-pools` set to `192.168.0.0/16`. If Docker is reinstalled or reset, this config must be re-applied or the stack won't reach the internet.

**No bind mounts — always rebuild images.** Code changes require `docker compose build` to take effect. `docker compose up -d` without a build will run old code. This is intentional (prevents host/container venv conflicts from `.dockerignore` exclusion of `.venv`) but catches new contributors off guard.

**Celery worker OOM.** Worker memory limit is 700 MB with `worker_max_memory_per_child=400000` (400 MB). Without the per-child limit, a single runaway task can grow unbounded and trigger the kernel OOM killer, cascading to kill adjacent workers. The Beat scheduler is in a separate container for this reason.

**`last_prophetx_poll` vs `last_real_world_poll`** — these are easy to confuse. `last_prophetx_poll` is written only by the WebSocket consumer and represents the last time ProphetX sent an event update. `last_real_world_poll` is written by every real-world source worker and is what the "Last Checked" column in the dashboard shows. The 24-hour ended-event visibility filter uses `last_real_world_poll`.
