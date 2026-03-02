# Stack Research

**Domain:** Real-time operations monitoring dashboard — v1.1 additions only (API usage monitoring, poll frequency controls, SDIO endpoint fixes)
**Researched:** 2026-03-01
**Confidence:** HIGH for backend patterns; MEDIUM for Recharts React 19 compatibility (requires install verification)

---

## Context: What This Covers

This is a **subsequent milestone** research document. The v1.0 stack (FastAPI, Celery/Redis, PostgreSQL, React 19, TanStack Query 5, Tailwind 4, shadcn/ui 3) is already deployed and validated. This document covers only what is **new or changed** for v1.1 features:

1. **API usage tab** — pull usage/limits from provider response headers + a dedicated Sports API `/status` endpoint
2. **Call volume tracking** — count outbound API calls per worker across all polling cycles
3. **Poll frequency controls** — UI-driven adjustment of per-worker Celery Beat intervals at runtime
4. **SDIO NFL/NCAAB/NCAAF endpoint 404s** — data/config fix, no new libraries

Nothing in the v1.0 stack needs to be replaced or upgraded for these features.

---

## Recommended Stack

### Core Technologies (existing — no changes)

The full v1.0 stack continues unchanged:

| Technology | Version | Status |
|------------|---------|--------|
| FastAPI | 0.115.x | No change |
| Celery | 5.4.x | No change |
| celery-redbeat | 2.3.3 | **Already installed; critical for poll frequency controls** |
| PostgreSQL | 16.x | No change — new table added for usage tracking |
| Redis | 7.x | No change — INCR counters added |
| React 19 | 19.2.x | No change |
| TanStack Query | 5.x | No change |

### New Supporting Libraries

| Library | Version | Purpose | Rationale |
|---------|---------|---------|-----------|
| recharts | ^3.7.0 | Bar/line charts for API usage history in the UI | Already the ecosystem standard for React admin dashboards. v3.7.0 (Jan 2025) is the latest stable. Works with React 19 — the react-is mismatch issue from 2.x is resolved in 3.x. No peer dependency overrides needed. Lightweight (~180KB), composable, SVG-based. Sufficient for the simple time-series call-count charts this feature needs. |

That is the **only new npm dependency**. No new Python packages are required.

---

## How Each Feature Maps to the Stack

### Feature 1: API Usage Tab — Provider Usage/Limits

**How provider quotas are exposed:**

| Provider | Mechanism | Header/Endpoint | What's Available |
|----------|-----------|-----------------|-----------------|
| The Odds API | Response headers | `x-requests-remaining`, `x-requests-used`, `x-requests-last` | Credits remaining until monthly reset, credits used, cost of last call |
| Sports API (api-sports.io) | Response headers | `x-ratelimit-requests-limit`, `x-ratelimit-requests-remaining` | Daily request limit and remaining per subscription; also per-minute: `X-RateLimit-Limit`, `X-RateLimit-Remaining` |
| Sports API (api-sports.io) | Dedicated endpoint | `GET /status` (per-sport base URL) | Account subscription info — confirms remaining daily requests at any time without consuming quota |
| SportsDataIO | None confirmed | No response headers or quota endpoint found in official docs | SDIO advertises "unlimited API calls" on paid plans; no quota tracking mechanism exposed. Track call volume internally only. |
| ESPN | Unofficial API | No rate limit headers or quota endpoint | Unofficial API; track call volume internally only. |

**Implementation:** Capture headers inside `BaseAPIClient._get()` after each response. Store latest values in Redis with per-provider keys (e.g., `api_usage:odds_api:remaining`). FastAPI endpoint reads Redis and returns combined payload to the UI. No new Python library needed — `httpx` already used, and headers are on the `response` object.

**Confidence:** HIGH for Odds API (official docs verified). HIGH for Sports API (API-Football docs confirmed header names). LOW for SDIO (no quota tracking mechanism found — confirmed "unlimited" but no header evidence).

### Feature 2: Call Volume Tracking

**Mechanism: Redis INCR counters**

Redis `INCR` is the correct tool. It is:
- Atomic — safe for concurrent writes from 6 Celery worker processes
- O(1) — no performance cost at this scale
- Already present (Redis is in the stack)
- No new library needed

**Pattern:**
```
Key format: api_calls:{provider}:{YYYY-MM-DD}
TTL: 8 days (covers weekly trend display)
Increment: once per successful API call inside each client method
```

For historical trend display (last 7 days per provider), the FastAPI endpoint reads 7 keys per provider from Redis. No time-series DB or additional tooling needed at this scale.

**Why not PostgreSQL for call counts?** PostgreSQL write amplification from high-frequency INCR-equivalent updates (up to ~200 writes/day/provider) is unnecessary overhead when Redis already handles it. Persist to Postgres only if audit trail of historical usage beyond 8 days is required — defer to v1.2.

### Feature 3: Poll Frequency Controls

**Mechanism: RedBeat schedule mutation via Python API**

celery-redbeat (already installed, v2.3.3) supports runtime schedule updates without Beat restart. The mechanism:

```python
from redbeat import RedBeatSchedulerEntry
import celery.schedules

# Update an existing task's interval
entry = RedBeatSchedulerEntry(
    'poll-odds-api',
    'app.workers.poll_odds_api.run',
    celery.schedules.schedule(run_every=new_interval_seconds),
    app=celery_app
)
entry.save()  # writes to Redis; Beat picks up on next tick
```

Beat polls its Redis keys on each tick (default every second). The new interval takes effect within ~1-2 seconds of `entry.save()`.

**FastAPI endpoint:** `PATCH /api/v1/config/poll-intervals` — accepts `{worker: str, interval_seconds: int}`, validates bounds (min 30s, max 3600s), calls the RedBeat mutation, updates the `POLL_INTERVAL_*` value in the DB config table for persistence across restarts.

**Why not restart Beat?** Restarting Beat causes a ~5-10s gap in scheduling and loses the distributed lock. RedBeat's in-place mutation avoids this entirely.

**Persistence concern:** RedBeat stores intervals in Redis. If the Redis container restarts, Beat re-reads from `celery_app.conf.beat_schedule` (the hardcoded defaults). To survive Redis restarts, the admin-configured interval must also be written to the PostgreSQL `app_config` table and loaded on startup.

### Feature 4: SDIO NFL/NCAAB/NCAAF Endpoint 404s

No new stack additions. The fix is in `sportsdataio.py`:
- NFL uses `/nfl/scores/json/ScoresByDate/{date}` (not `GamesByDate`)
- NCAAB path: already mapped via `SPORT_PATH_MAP["ncaab"] = "cbb"` — investigate whether the endpoint variant is wrong
- NCAAF path: similarly mapped as `"cfb"` — verify endpoint name matches SDIO v3 docs

This is a data/routing fix, not a stack change.

---

## New Frontend Component: API Usage Tab

**No new major libraries beyond Recharts.** The existing stack handles everything:

| UI Element | Existing Tool |
|------------|---------------|
| Tab navigation | shadcn/ui Tabs component |
| Usage cards (remaining/used/limit) | shadcn/ui Card |
| 7-day call volume chart | recharts BarChart |
| Poll interval sliders | shadcn/ui Slider |
| Save interval button | shadcn/ui Button |
| API request | TanStack Query `useQuery` + `useMutation` |
| Optimistic UI on interval save | TanStack Query `onMutate` |

---

## New Backend: API Usage Endpoint

A single new FastAPI router at `/api/v1/usage`:

```
GET  /api/v1/usage          → provider quotas (from Redis) + 7-day call history
PATCH /api/v1/config/poll-intervals  → update worker schedule interval
```

Both are read/write-light endpoints; no new infrastructure needed.

---

## Installation

```bash
# Frontend — only new dependency
npm install recharts@^3.7.0

# Backend — no new dependencies
# All needed: httpx (header capture), redis-py (INCR), celery-redbeat (schedule mutation)
# are already in pyproject.toml
```

**Note on Recharts + React 19:** Recharts 3.x resolves the `react-is` peer dependency mismatch that affected 2.x. Install and verify with `npm ls react-is` — all instances should resolve to 19.x. If a conflict appears, add to `package.json` overrides: `"react-is": "^19.0.0"`.

---

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| Redis INCR for call counting | New PostgreSQL `api_call_log` table | Postgres write amplification for high-frequency counters is unnecessary overhead when Redis is already in the stack. Use Redis; persist to Postgres only if >8-day history is needed. |
| RedBeat runtime mutation | Restart Beat container on interval change | Restart causes scheduling gap and requires orchestration. RedBeat mutation is instantaneous and designed for this use case. |
| recharts | Nivo | Nivo is heavier (~400KB) and better suited for complex visualizations. Simple bar charts for call counts don't justify the bundle size. |
| recharts | react-chartjs-2 | Adds Chart.js as a dependency. Recharts is native React components with cleaner TypeScript types and better shadcn/ui theme integration. |
| Header capture in BaseAPIClient | Separate quota-polling task | Separate task wastes quota budget. Headers are free — they come with every existing poll call. |

---

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Time-series database (InfluxDB, TimescaleDB) | Massive infrastructure addition for what is 5 counters per provider per day. Redis INCR with 8-day TTL is sufficient. | Redis INCR keys |
| Prometheus + Grafana | Operational overhead far exceeds v1.1 value. The dashboard itself is the monitoring surface. | Redis counters + custom FastAPI endpoint |
| WebSockets for poll interval updates | SSE already handles real-time push. Poll interval changes are low-frequency config mutations, not a stream. | PATCH endpoint + TanStack Query mutation |
| New charting library (Victory, ECharts) | Victory adds complexity for minimal gain; ECharts is 1MB+. Recharts 3.x is the right weight for this use case. | recharts 3.7.x |
| SQLAlchemy-Celery-Beat | Alternative scheduler that stores Beat config in Postgres. Project is already on RedBeat and it works. Do not switch. | celery-redbeat (already installed) |

---

## Version Compatibility Notes

| Package | Notes |
|---------|-------|
| recharts 3.7.x + React 19 | Recharts 3.x resolves the react-is peer dependency issue from 2.x. Should install cleanly. Verify with `npm ls react-is` post-install. |
| celery-redbeat 2.3.3 + Celery 5.4.x | Confirmed compatible. v2.x is Celery 5 series. Already in production. |
| Redis INCR + redis-py 5.x | INCR is a core Redis command, available in all versions. redis-py 5.x supports it via both sync and async client. |
| RedBeat entries + Redis restart | RedBeat keys survive normal Redis operation but are lost on `redis-cli FLUSHALL` or container data wipe. Always write admin-configured intervals to Postgres as the durable source of truth; load on app startup into RedBeat. |

---

## Sources

- The Odds API v4 docs (https://the-odds-api.com/liveapi/guides/v4/) — response headers `x-requests-remaining`, `x-requests-used`, `x-requests-last` confirmed. HIGH confidence.
- API-Football rate limit docs (https://www.api-football.com/news/post/how-ratelimit-works) — headers `x-ratelimit-requests-limit`, `x-ratelimit-requests-remaining`, `X-RateLimit-Limit`, `X-RateLimit-Remaining` confirmed. HIGH confidence.
- SportsDataIO FAQ + developer docs — no quota tracking mechanism found. Consistent with "unlimited calls" positioning. LOW confidence that no tracking exists (absence of evidence only).
- celery-redbeat PyPI (https://pypi.org/project/celery-redbeat/) + readthedocs — v2.3.3 current, `RedBeatSchedulerEntry.save()` confirmed for runtime schedule mutation. HIGH confidence.
- Recharts GitHub releases (https://github.com/recharts/recharts/releases/tag/v3.7.0) — v3.7.0 released Jan 21 2025, React 19 peer dep issue resolved in 3.x branch. MEDIUM confidence on React 19 claim (no explicit peerDependencies list found; install verification required).
- Redis INCR docs (https://redis.io/docs/latest/commands/incr/) — atomic, O(1), standard counter pattern. HIGH confidence.
- LogRocket best React chart libraries 2025 — Recharts recommended for admin dashboards. MEDIUM confidence (editorial source).

---

*Stack research for: ProphetX Market Monitor v1.1 — API usage monitoring + poll frequency controls*
*Researched: 2026-03-01*
