# Project Research Summary

**Project:** ProphetX Market Monitor — v1.1 (API Usage Monitoring + Poll Frequency Controls)
**Domain:** Real-time operational monitoring dashboard for prediction market / sports event lifecycle management
**Researched:** 2026-03-01
**Confidence:** HIGH (v1.0 codebase directly inspected; all new patterns verified against official documentation and live code)

## Executive Summary

ProphetX Market Monitor v1.1 is a well-scoped incremental milestone on top of an already-deployed v1.0 system. The core v1.0 stack — FastAPI, Celery/RedBeat, Redis, PostgreSQL, React 19, TanStack Query 5, Tailwind 4, shadcn/ui 3 — is validated and unchanged. The v1.1 work adds three orthogonal concerns: (1) capturing and displaying API call volume and provider quota data, (2) giving operators UI controls to adjust per-worker poll frequencies without engineering involvement, and (3) stabilizing known false-positive mismatch bugs and broken SDIO endpoints. The only new library is `recharts@^3.7.0` for the 7-day call-volume bar chart.

The recommended approach for the two highest-complexity features is deliberately conservative. For quota display: capture provider response headers (`x-requests-remaining` from Odds API, `x-ratelimit-requests-remaining` from api-sports.io) inside the client layer, store to Redis with a 25-hour TTL, and serve via a new `/api/v1/usage` endpoint. For poll frequency control: extend the existing `system_config` table pattern with `poll_interval_*` keys, write to both PostgreSQL (durability across restarts) and RedBeat Redis (live effect within 5 seconds), and remove poll-interval entries from the static `beat_schedule` to prevent restart overwrite. SDIO and ESPN have no documented quota mechanisms; their usage monitoring is call-count-only via Redis `INCRBY`.

The single greatest implementation risk is the RedBeat restart overwrite pitfall: if `poll_interval_*` entries remain in the static `beat_schedule` dict in `celery_app.py`, every Beat container restart silently reverts operator-configured intervals to the code defaults. This must be addressed at the architecture level before any UI is built — the correct fix is to remove these entries from the static config and bootstrap them from the database at startup. Secondary risks include the api-sports.io quota-per-sport-family nuance (each sport is a separate API base URL with a separate daily quota), the need for atomic `INCRBY` counters (not `GET`/`SET`) to avoid race conditions under 6-worker concurrency, and the SDIO 404-suppression behavior that silently hides path and subscription errors. All three risks have clear, implementable mitigations documented in PITFALLS.md.

## Key Findings

### Recommended Stack

The v1.0 stack requires no changes for v1.1. `celery-redbeat 2.3.3` is already installed and supports runtime schedule mutation via `RedBeatSchedulerEntry.from_key().save()` — this is the mechanism for live poll-interval updates without Beat restart. The existing `system_config` table and `/api/v1/config` PATCH endpoint already handle the persistence pattern; v1.1 extends it with `poll_interval_*` keys. The new `/api/v1/usage` endpoint is a read-light endpoint combining Redis MGET (live today counts + quota keys) and a single PostgreSQL SELECT (7-day snapshot history). All HTTP client work uses `httpx`, already present.

**Core technologies (all existing — no changes):**
- FastAPI 0.115.x — API server; extend `/api/v1/config` and add `/api/v1/usage` router
- celery-redbeat 2.3.3 — runtime schedule mutation via `RedBeatSchedulerEntry`; already installed and in production
- Redis 7.x — `INCRBY` call counters (atomic, O(1)); quota key storage with 25h TTL; no new Redis infrastructure
- PostgreSQL 16.x — new `api_usage_snapshots` table for 7-day history; `system_config` extension for interval persistence
- React 19 / TanStack Query 5 — new `ApiUsagePage` with 60-second `refetchInterval`; no additional complexity

**New library (frontend only):**
- recharts 3.7.x — 7-day call-volume bar chart; React 19 peer dependency issue resolved in 3.x; ~180KB, SVG-based, composable; no peer override needed in most cases

See `.planning/research/STACK.md` for full library rationale, alternatives considered, and version compatibility notes.

### Expected Features

The v1.1 feature set is grounded in actual codebase inspection and confirmed API provider capabilities. All P1 features are required for the API Usage tab to deliver genuinely useful operator information.

**Must have for v1.1 launch (P1):**
- Redis `INCRBY` call counter per worker per day — foundation for all display; must be built first; atomic under 6-worker concurrency
- Response header capture in `BaseAPIClient` — `_capture_quota_headers()` hook (no-op default); overridden in Odds API and Sports API clients
- Per-provider quota display (used / remaining / limit) — Odds API and api-sports.io only; SDIO shows call-count only; ESPN shows N/A
- Projected monthly call volume at current rate — computed at read time in API layer, no storage needed
- DB-backed poll intervals (`system_config` table, `poll_interval_*` keys) — prerequisite for all UI controls
- UI poll interval controls (`WorkerFrequencyPanel`) — Admin-only; live update via RedBeat + DB persistence across restarts
- `api_usage_snapshots` table (new Alembic migration) + nightly rollup worker — durable 7-day history for chart
- `ApiUsagePage` frontend — `UsageSummaryCards`, `WorkerFrequencyPanel`, `CallVolumeChart`

**Should have (defer to v1.2):**
- Quota alert Slack notification at configurable threshold — reuses existing alerting; deferred because quota display itself prevents surprise exhaustion
- Per-sport-key call breakdown (Odds API) — adds counter dimension complexity; defer until operators request sport-level attribution
- Per-worker pause toggle — interval control covers the use case (set to very long interval = effectively paused)

**Anti-features (do not build):**
- Automated quota throttling (auto-reduce interval near limit) — risk of oscillation; operators make the call
- Real-time calls/second display — always 0.0–0.1 at this scale; operationally meaningless
- Full API call log (every request in DB) — 1.3M rows/month, no actionable use case beyond what Redis counters provide

**Critical finding on quota burn rates:** At current intervals, the system burns ~21,600 Odds API calls/month (43x the 500-call free tier) and ~720 Sports API calls/day (7x the 100-call free tier). The API Usage tab will make this visible immediately; operators need interval controls to manage it. This is not a bug — it is a consequence of polling intervals set for data freshness without visibility into cost.

See `.planning/research/FEATURES.md` for full prioritization matrix, dependency graph, and dynamic interval control option analysis.

### Architecture Approach

v1.1 follows three existing architectural patterns from v1.0 without introducing new patterns. Pattern 1: Redis for hot data (call counters, quota snapshots, heartbeats), PostgreSQL for durable data (daily snapshots, system config, events). Pattern 2: `system_config` table as runtime override for env-var defaults — v1.1 adds `poll_interval_*` keys to this existing mechanism. Pattern 3: client-layer concerns stay in the client layer — quota header capture belongs in `clients/`, not in `workers/`, so future clients automatically get it.

**Major components:**
1. **Redis call counters** — `INCRBY api_calls:{worker}:{YYYY-MM-DD}` per poll cycle; 8-day TTL; atomic under 6-worker concurrency; incremented in each `poll_*.py` after the external fetch
2. **Quota header capture hook** — `BaseAPIClient._capture_quota_headers()` (no-op default); overridden by `OddsAPIClient` and `SportsApiClient`; writes `api_quota:{provider}:*` keys to Redis with 25h TTL
3. **`api_usage_snapshots` table** — `worker_name + snapshot_date + call_count` (UNIQUE constraint); written by nightly rollup task (02:00 UTC); read by `/api/v1/usage` endpoint
4. **`/api/v1/usage` endpoint** — parallel Redis MGET (today counts + quota keys) + PostgreSQL SELECT (7-day history); expected < 50ms; `require_role(read_only)`
5. **Interval control path** — PATCH `/api/v1/config/poll_interval_{worker}` writes to DB (persistence) + `RedBeatSchedulerEntry.from_key().save()` (live update); `celery_app.py` reads DB on startup with env-var fallback
6. **`ApiUsagePage`** — `UsageSummaryCards` + `WorkerFrequencyPanel` (Admin-only) + `CallVolumeChart` (recharts); `refetchInterval: 60_000`

**Build order (dependencies determine sequence):**
Step 1 — Call counter infra (no dependencies) → Step 2 — Quota header capture → Step 3 — DB schema migration → Step 4 — Nightly rollup worker → Step 5 — `/api/v1/usage` endpoint → Step 6 — Interval control backend → Step 7 — Frontend `ApiUsagePage`

See `.planning/research/ARCHITECTURE.md` for full data flow diagrams, component boundary rules, code patterns, and anti-patterns to avoid.

### Critical Pitfalls

1. **RedBeat restart overwrite (CRITICAL)** — Static `beat_schedule` in `celery_app.py` overwrites Redis entries on every Beat restart via `update_from_dict()`. Operator-configured intervals are silently lost. Prevention: remove poll-interval entries from static `beat_schedule`; bootstrap into Redis from DB at startup. This must be addressed before building any UI — choosing the wrong storage strategy requires rewriting both backend and frontend on discovery.

2. **API call counter race condition** — `GET`/`SET` counter pattern is non-atomic; under `--concurrency=6` multiple workers overwrite each other's increments and the counter undercounts. Prevention: always use `INCRBY` (single atomic Redis command). Same effort as `GET`/`SET` — no excuse to use the racy pattern.

3. **Response headers discarded by clients** — Current `BaseAPIClient._get()` extracts JSON and discards the `Response` object; Odds API and Sports API quota data is lost on every call. Prevention: add header capture hook to `_get()` before building any quota display. Note: `SportsApiClient` does not extend `BaseAPIClient` and needs a direct addition to `get_games()`.

4. **Inconsistent data contract on API Usage tab** — Provider headers, local counters, and configured limits have different refresh rates and reset periods. Displaying them side-by-side without clear source labels misleads operators (e.g., "47 calls today" + "88 remaining" does not equal "100 limit" when sources differ). Prevention: define the JSON schema for `/api/v1/usage` with explicit field semantics before building the frontend; label each field with its source and last-updated timestamp; show "—" not "0" when data is unavailable.

5. **api-sports.io quota is per-sport-family, not global** — Each sport on api-sports.io is a separate API base URL with a separate daily quota. "Basketball remaining: 88" does not imply "Hockey remaining: 88." Quota capture must key by sport family, not just by provider name.

6. **SDIO 404 suppression hides real errors** — The 404 fallback in `get_games_by_date_raw()` silently returns `[]` for both "no games today" (correct) and "wrong URL / not subscribed" (error). Prevention: run `probe_subscription_coverage()` on startup to distinguish 403 (not subscribed) from 404 (no games today) from 200 (working).

See `.planning/research/PITFALLS.md` for full v1.1 and v1.0 pitfall details, warning signs, recovery strategies, technical debt table, and integration gotchas per provider.

## Implications for Roadmap

The build order for v1.1 is dictated primarily by data dependencies: counters must emit before displays can be built; schema must exist before rollup workers can write; backend must return real data before frontend is built. The interval control and usage display concerns are independent of each other after the shared counter foundation is in place and can be developed in parallel.

### Phase 1: Stabilization + Counter Foundation

**Rationale:** Fix the active false-positive mismatch bugs and SDIO 404 issues before adding new features — these undermine operator trust in the existing system and are blocking v1.0 correctness. Simultaneously, lay the Redis counter infrastructure that all v1.1 display features depend on. Counters can begin accumulating real data immediately, providing a week of history by the time the UI is built.

**Delivers:** False-positive mismatch fixes (Sports API start-time matching, cross-day guard tightened from `>12h` to `>6h`), SDIO NFL/NCAAB/NCAAF endpoint path verification and fix, `probe_subscription_coverage()` startup run, `/api/v1/health/workers` 404 diagnosis and fix, Redis `INCRBY` call counters in all 5 workers

**Addresses features:** Known bugs from project context; Redis counter foundation for all usage display features

**Avoids pitfalls:** SDIO 404 suppression (run startup probe; distinguish subscription errors from gameless-date 404s), race condition (use `INCRBY` from day one), Sports API wrong-game match (use actual ISO start time from api-sports.io; tighten hours-apart threshold)

**Research flag:** No additional research needed — bugs are diagnosed, patterns are established

### Phase 2: Quota Capture + Usage API Backend

**Rationale:** Build the backend data pipeline before the frontend. Quota header capture in clients is a targeted change to `BaseAPIClient._get()` — it needs coordination because all existing clients are affected (no-op default means no regression, but the `SportsApiClient` exception requires separate handling). The `/api/v1/usage` endpoint can serve live data (Redis) immediately; historical data (PostgreSQL snapshots) accumulates over the following days.

**Delivers:** `BaseAPIClient._capture_quota_headers()` hook, Odds API quota capture (`x-requests-remaining`, `x-requests-used`), Sports API quota capture per sport family (`x-ratelimit-requests-remaining`, `x-ratelimit-requests-limit`), `api_usage_snapshots` DB table + Alembic migration, nightly rollup worker (02:00 UTC), `/api/v1/usage` endpoint with explicit JSON schema

**Uses:** Redis MGET, PostgreSQL `api_usage_snapshots`, existing `system_config` pattern, existing `/api/v1/health` pattern for role gating

**Avoids pitfalls:** Data contract inconsistency (define JSON schema before frontend build; each field includes source and last-updated), per-sport quota nuance (key quota capture by sport family for api-sports.io), header discard (add hook before building any display), stale quota display (25h TTL — shows "—" not stale value if key expires)

**Research flag:** Inspect actual SDIO response headers from a live worker call before finalizing SDIO quota handling — research is LOW confidence that SDIO exposes no quota headers (absence of evidence only; must verify from live response)

### Phase 3: Interval Control Backend

**Rationale:** The RedBeat restart overwrite pitfall must be resolved before any UI for interval control is built. This is purely a backend concern. The critical change is removing poll-interval entries from the static `beat_schedule` and bootstrapping them from the DB at startup. Test the Beat startup path with a disconnected database to confirm graceful fallback to env-var defaults.

**Delivers:** `celery_app.py` modified to read intervals from DB at startup with env-var fallback (3-second timeout, fail-safe), poll-interval entries removed from static `beat_schedule`, config PATCH endpoint extended to write to RedBeat live schedule when key matches `poll_interval_*`, per-worker minimum interval enforcement server-side (HTTP 422 on violation)

**Uses:** `RedBeatSchedulerEntry.from_key().save()` (already confirmed in research), existing `system_config` PATCH endpoint pattern

**Avoids pitfalls:** RedBeat restart overwrite (intervals removed from static config; DB is the source of truth bootstrapped into Redis at startup), minimum interval bypass (server-side validation only — not client-side)

**Research flag:** Verify RedBeat key prefix and task name format against live `redis-cli KEYS "redbeat:*"` before writing `Entry.from_key()` — confirmed `redbeat:{task_name}` pattern in research but must match actual production Beat keys. Also confirm that importing `celery_app` in the FastAPI process does not trigger worker registration side effects.

### Phase 4: Frontend ApiUsagePage

**Rationale:** Build after both the usage API backend (Phase 2) and interval control backend (Phase 3) return real data. The frontend is purely a consumer. Building it against mocked data delays discovery of API shape mismatches. Admin-only interval controls must be gated by the existing role check (`require_role(RoleEnum.admin)`).

**Delivers:** `ApiUsagePage` with `UsageSummaryCards` (calls today + remaining quota per provider with source labels), `WorkerFrequencyPanel` (current interval + number input + save; Admin-only), `CallVolumeChart` (recharts 7-day bar chart per worker); new `/usage` route in `App.tsx`; nav entry in `Layout.tsx`

**Uses:** recharts 3.7.x (only new npm dependency), TanStack Query `useQuery` (refetchInterval: 60s) + `useMutation` (optimistic UI on interval save), shadcn/ui Tabs + Card + Slider + Button

**Avoids pitfalls:** Data contract inconsistency (label each field with source + last-updated in UI; show "—" when source is unavailable), api-sports.io per-sport quota (display per-sport or clearly labeled, never aggregated as a single "Sports API" number without explanation)

**Research flag:** After `npm install recharts@^3.7.0`, verify React 19 compatibility with `npm ls react-is` — if a conflict appears, add `"react-is": "^19.0.0"` to `package.json` overrides

### Phase Ordering Rationale

- Phase 1 (Stabilization) comes first because false positives undermine operator trust, and starting counters early gives the chart meaningful data by the time the frontend is built
- Phase 2 (Backend data pipeline) before Phase 4 (Frontend) is non-negotiable — the display has nothing to show without the backend
- Phase 3 (Interval control backend) before Phase 4 (Frontend) prevents the RedBeat restart pitfall from being built into a UI that operators start using before the bug is discovered
- Phases 2 and 3 can run in parallel if development bandwidth allows — they share no code dependencies (different files, different concerns)
- All backend phases (1–3) can be deployed and validated via `curl` before any frontend work begins

### Research Flags

Phases requiring deeper research or validation during planning:

- **Phase 3 (Interval control):** Verify RedBeat Redis key prefix and task name format against live `redis-cli KEYS "redbeat:*"` before writing `Entry.from_key()` — confirmed `redbeat:{task_name}` pattern in research but must match production Beat
- **Phase 2 (Quota capture — SDIO):** Inspect actual SDIO response headers from a live worker call before hardcoding "no quota headers" — research is LOW confidence on this specific point (absence of evidence only)
- **Phase 2 (Sports API quota):** Confirm whether the api-sports.io `/status` endpoint counts against daily quota — if it does not, it can supplement header-based tracking

Phases with standard, well-established patterns (skip additional research):

- **Phase 1 (Stabilization):** Bug fixes are diagnosed; patterns (INCRBY, Sports API matching) are confirmed from official docs and codebase inspection
- **Phase 4 (Frontend):** recharts + TanStack Query + shadcn/ui pattern is established and well-documented

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | v1.0 stack is in production; only new dep is recharts 3.7.x with documented React 19 compatibility. Verify post-install with `npm ls react-is`. |
| Features | HIGH | Feature scope grounded in actual codebase inspection + confirmed API provider docs. Quota burn rate analysis uses real worker config values. |
| Architecture | HIGH | Build order and component boundaries derived directly from live code inspection. All integration points (RedBeat, system_config, BaseAPIClient) verified against existing implementations. |
| Pitfalls | HIGH (infrastructure); MEDIUM (provider-specific) | RedBeat restart overwrite confirmed from `redbeat/schedulers.py` source inspection. Race condition confirmed from Redis docs. SDIO quota headers: LOW confidence (no evidence found either way — must inspect live response). api-sports.io per-sport quota nuance: MEDIUM (documented behavior, needs production confirmation). |

**Overall confidence:** HIGH

### Gaps to Address

- **SDIO quota headers:** Research found no documentation of SDIO quota response headers; paid plans are described as "unlimited." Before coding the SDIO quota capture (or deciding not to), inspect actual SDIO API response headers from a live worker call. Do not hardcode "unlimited" in the UI without checking subscription terms and inspecting actual response headers from a `docker compose logs worker` capture or temporary debug logging.

- **RedBeat key format in production:** Research confirms the `redbeat:{task_name}` key pattern with dashes (e.g., `redbeat:poll-sports-data`). Before writing the `Entry.from_key()` call, run `redis-cli KEYS "redbeat:*"` against the live Redis instance to confirm exact key names. A mismatch creates a new orphaned key rather than updating the existing Beat entry — no error is thrown, the change silently has no effect.

- **celery_app import in FastAPI process:** The interval control PATCH endpoint needs to import `celery_app` from `workers/celery_app.py`. The `include=[...]` in `celery_app.py` registers task modules — confirm this does not trigger worker startup side effects when imported in the API container. Validate by running the import in isolation before wiring into the config endpoint.

- **NCAAB/NCAAF SDIO endpoint paths:** The exact v3 URL paths for NFL, NCAAB (cbb), and NCAAF (cfb) endpoints must be confirmed against the SDIO API with a direct `curl` before modifying `sportsdataio.py`. The `SPORT_PATH_MAP` remapping is in place but the endpoint name variant may still be wrong for specific sports.

- **api-sports.io per-sport quota display:** Research recommends keying quota capture by sport family for api-sports.io (Basketball, Hockey, Baseball, American Football each have separate API base URLs and separate daily quotas). The frontend must display these separately or with clear sport-family labels — a single "Sports API: 47/100" number is misleading and possibly incorrect.

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: `workers/celery_app.py`, `workers/poll_*.py`, `clients/base.py`, `clients/odds_api.py`, `clients/sports_api.py`, `models/config.py`, `api/v1/config.py`, `api/v1/health.py`, `db/redis.py`, `docker-compose.yml`, `core/config.py`
- The Odds API v4 docs (https://the-odds-api.com/liveapi/guides/v4/) — `x-requests-remaining`, `x-requests-used`, `x-requests-last` headers confirmed
- api-football.com rate limit docs (https://www.api-football.com/news/post/how-ratelimit-works) — `x-ratelimit-requests-remaining`, `x-ratelimit-requests-limit` headers confirmed
- Redis INCR/INCRBY docs (https://redis.io/docs/latest/commands/incr/) — atomic counter pattern confirmed
- celery-redbeat PyPI + readthedocs — `RedBeatSchedulerEntry.save()` for runtime schedule mutation confirmed; v2.3.3 current
- SportsDataIO official site (https://sportsdata.io/apis) — "unlimited API calls" on paid plans confirmed

### Secondary (MEDIUM confidence)
- Recharts GitHub releases (https://github.com/recharts/recharts/releases/tag/v3.7.0) — v3.7.0 React 19 compatibility claimed; install verification required
- RedBeat source code (`redbeat/schedulers.py`) — `update_from_dict()` restart overwrite behavior confirmed via source inspection (confirmed pattern, not from docs)
- GitHub gist (nvpmai/bd475b5d562811dadc86381a49759040) — `Entry.from_key()` runtime update pattern confirmed working
- LogRocket best React chart libraries 2025 — Recharts recommended for admin dashboards

### Tertiary (LOW confidence — requires live validation)
- SDIO quota headers: no evidence found in public documentation — absence of evidence only; must verify from live response before committing to "no quota header" design

---
*Research completed: 2026-03-01*
*Ready for roadmap: yes*
