# Feature Research

**Domain:** Internal operations monitoring dashboard — prediction market / sports event lifecycle management
**Researched:** 2026-03-01 (v1.1 update; original v1 research 2026-02-24)
**Confidence:** HIGH (v1 domain is built; v1.1 features grounded in actual code + confirmed API provider capabilities)

---

## v1.1 Feature Scope: API Usage Monitoring + Stabilization

This section covers the new features for the v1.1 milestone. The v1 feature landscape is preserved below for reference.

---

### Table Stakes for v1.1 (Users Expect These)

These are required for the API Usage tab to be genuinely useful. Without them, the tab delivers incomplete information that operators cannot act on.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Per-provider quota display (used / limit / remaining) | Operators configuring poll intervals need to know current standing against monthly limits before adjusting — a "remaining calls" number is the minimum viable signal | MEDIUM | Odds API: read `x-requests-remaining` + `x-requests-used` headers on every poll response. Sports API (api-sports.io): read `x-ratelimit-requests-remaining` + `x-ratelimit-requests-limit` headers. SDIO: no documented quota — display "unlimited" per official docs. ESPN: no documented quota — display "N/A" |
| Internal call counter per worker | Odds API and Sports API headers only reflect the provider's counter — they don't tell you which worker made which calls. An internal Redis `INCR` counter per worker per day gives attribution and lets you see who's consuming quota fastest | LOW | Redis key pattern: `api_calls:{worker}:{YYYY-MM-DD}`. Increment on each outbound call inside the client. Reset naturally when date rolls over (key TTL = 48h). No DB schema change needed |
| Total monthly call volume across all workers | Operators need one number: "how many calls have we made this month across all sources?" to assess whether usage is on track | LOW | Aggregate Redis daily counters into a rolling monthly total. Computed at read time — no separate counter needed |
| Per-worker poll frequency control (UI) | The single biggest lever for controlling API costs. Currently requires `.env` edit + container rebuild — operators cannot adjust without engineering involvement | HIGH | Requires: (1) DB-backed schedule table (sqlalchemy-celery-beat or equivalent), (2) API endpoint to read/write intervals, (3) UI controls in the API Usage tab, (4) Beat scheduler restart or dynamic interval update. This is the most complex feature in v1.1 |
| Projected monthly call volume at current rate | If you're 10 days in and have used 40% of quota, you'll exceed limits. Operators need a projection, not just current consumption | LOW | `(calls_this_month / days_elapsed) * days_in_month`. Computed in the API layer — no storage needed |

### Differentiators (Operational Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Quota alert threshold (configurable % warning) | "Alert me when Odds API is at 80% of monthly quota" prevents surprise quota exhaustion mid-month | LOW | Store `api_usage_alert_threshold` in SystemConfig (default 80%). Check on each provider poll response. Fire Slack alert via existing deduplication system |
| Per-worker pause toggle | When approaching quota limits, operators want to pause the highest-consumption workers without stopping everything | MEDIUM | Celery Beat dynamic schedule: set interval to 0 or use a `worker_enabled` flag checked at task start. Simpler than full interval control — just a boolean |
| Provider status badge (last poll success/fail) | Was the last Odds API call successful? Did it return quota headers? A green/red indicator next to each provider's quota tells operators whether the displayed numbers are current | LOW | Already tracked in worker heartbeat keys (`worker:heartbeat:{name}`). Extend heartbeat payload to include last HTTP status code |
| Call cost breakdown by sport key | For Odds API: each sport key is 1 credit. With 5 sport keys at 10-min intervals, knowing which sport keys consume the most helps operators decide which to disable off-season | MEDIUM | Extend Redis counter to include sport key dimension: `api_calls:odds_api:{sport_key}:{YYYY-MM-DD}`. Requires updating the Odds API client to pass sport key to counter |

### Anti-Features (Do Not Build)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Dynamic interval updates without container restart | Operators want "set it and live" frequency control | RedBeat stores schedule state in Redis and reads it at Beat startup. Changing intervals in DB while Beat is running requires either Beat restart or a custom scheduler loop. Django-celery-beat solves this but requires significant scheduler replacement — not appropriate for a one-container Beat setup | Require a Beat restart after interval change (one `docker compose restart beat` command); document this clearly in the UI tooltip. Acceptable operational cost vs. scheduler complexity |
| Real-time call-per-second rate display | Monitoring dashboards show "requests per second" | This system has at most 6 concurrent workers and ~30s poll intervals — never more than ~1 req/sec average. Rate display adds complexity for a metric that will always show "0.0" or "0.1" | Show calls per cycle and calls per day instead — operationally meaningful for this system |
| Full API call log (every request) | "Show me every API call made" | PostgreSQL table growing at 30 rows/minute = 1.3M rows/month. Requires log rotation, indexes, and a query interface. No actionable use case beyond what Redis counters already provide | Keep Redis counters (daily granularity). Add structured log lines already emitted by workers. Archive logs via Docker log rotation |
| Automated quota throttling (auto-reduce interval when near limit) | Sounds smart — system adjusts itself | Requires feedback loop logic that could interact badly with Beat's scheduling state. Risk: system oscillates intervals every poll cycle as quota approaches threshold | Alert at 80% threshold; let operators make the interval adjustment manually |

---

## Feature Dependencies for v1.1

```
[Redis API Call Counters]
    └──required by──> [Per-Worker Internal Call Display]
    └──required by──> [Total Monthly Volume]
    └──required by──> [Projected Monthly Volume]
    └──required by──> [Call Cost by Sport Key]

[Provider Response Header Capture]
    └──required by──> [Per-Provider Quota Display (used/limit/remaining)]
    └──required by──> [Quota Alert at Threshold]
    (requires BaseAPIClient to capture and store headers from Odds API + Sports API responses)

[Per-Provider Quota Display] ──enhances──> [Projected Monthly Volume]
    (provider quota remaining = ground truth; internal counter = attribution)

[DB-Backed Schedule Table]
    └──required by──> [Per-Worker Poll Frequency Control (UI)]
    └──required by──> [Per-Worker Pause Toggle]
    (replaces hardcoded beat_schedule in celery_app.py)

[Per-Worker Poll Frequency Control]
    └──requires──> [Beat Restart on Interval Change]
    (RedBeat re-reads schedule from Redis on startup; interval changes take effect after restart)

[Existing Worker Heartbeat Keys]
    └──enhances──> [Provider Status Badge]
    (extend heartbeat to include last_http_status)

[Existing Slack Alerting + Deduplication]
    └──required by──> [Quota Alert Threshold]
    (reuses existing send_alerts.py + Redis TTL dedup pattern)
```

### Dependency Notes

- **Redis counters before any display feature**: All call-count display features depend on the counters being incremented correctly in the client layer. The counter increment must be in `BaseAPIClient._get()` or in each specific client's methods — not in the workers — so all clients benefit automatically.
- **Provider headers require BaseAPIClient refactor**: Currently `BaseAPIClient._get()` discards the `Response` object and returns only `response.json()`. To capture `x-requests-remaining` headers, `_get()` must return the raw `Response` or a tuple `(data, headers)`. This is a breaking change to every client. Plan the refactor carefully.
- **Beat schedule DB migration is a prerequisite for interval controls**: Until the beat schedule is stored in a table rather than hardcoded in `celery_app.py`, no UI can change intervals at runtime.

---

## MVP Definition for v1.1

### Launch With (v1.1)

- [ ] Redis `INCR` counter per worker per day in `BaseAPIClient` — every outbound call counted. Foundation for everything else.
- [ ] Response header capture in Odds API client — capture and store `x-requests-remaining`, `x-requests-used`, `x-requests-last` from every Odds API response into Redis key `api_quota:odds_api`.
- [ ] Response header capture in Sports API client — capture and store `x-ratelimit-requests-remaining`, `x-ratelimit-requests-limit` from every Sports API response into Redis key `api_quota:sports_api`.
- [ ] API Usage tab in frontend — shows per-provider quota (used/remaining/limit), internal call counts by worker, projected monthly total.
- [ ] DB-backed poll intervals — migrate `beat_schedule` intervals from hardcoded `celery_app.py` to a `worker_schedule` table in PostgreSQL. Read at Beat startup. Admin can update via API.
- [ ] UI controls for poll intervals — slider or number input per worker in the API Usage tab. Admin-only. Displays "requires Beat restart to take effect" warning.

### Defer (v1.2+)

- [ ] Per-sport-key call breakdown — useful but adds counter dimension complexity. Defer until operators request sport-level attribution.
- [ ] Quota alert Slack notification — useful but not blocking. The quota display itself prevents surprise exhaustion for operators watching the dashboard.
- [ ] Per-worker pause toggle — interval control covers the use case (set to very long interval = effectively paused).

---

## Feature Prioritization Matrix (v1.1)

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Redis call counters (internal) | HIGH | LOW | P1 — foundation for all display |
| Odds API quota header capture | HIGH | MEDIUM | P1 — requires BaseAPIClient refactor |
| Sports API quota header capture | HIGH | MEDIUM | P1 — same refactor |
| API Usage tab UI (read-only) | HIGH | MEDIUM | P1 — the visible deliverable |
| DB-backed poll intervals | HIGH | HIGH | P1 — enables operator control |
| UI poll interval controls | HIGH | MEDIUM | P1 — depends on DB-backed intervals |
| Projected monthly volume display | MEDIUM | LOW | P1 — computed at read time, cheap |
| Quota alert Slack notification | MEDIUM | LOW | P2 — reuses existing alerting |
| Per-sport-key call breakdown | LOW | MEDIUM | P2 |
| Per-worker pause toggle | MEDIUM | MEDIUM | P2 |

**Priority key:**
- P1: Must have for v1.1 launch
- P2: Add after core usage tab is working

---

## Call Volume Reference (As-Built)

Actual call volume based on production code and current intervals:

| Worker | Interval | Calls/Cycle | Calls/Hour | Calls/Day | Calls/Month | Quota |
|--------|----------|-------------|------------|-----------|-------------|-------|
| poll_sports_data | 30s | 18+ (6 sports × 3 dates, non-soccer) | 2,160 | 51,840 | ~1.6M | SDIO: unlimited |
| poll_odds_api | 600s | ~5 (active sport keys) | 30 | 720 | ~21,600 | 500/month (free tier) |
| poll_sports_api | 1800s | ~15 (5 sports × 3 dates) | 30 | 720 | ~21,600 | 100/day (free tier) |
| poll_espn | 600s | ~5 (sports × date) | 30 | 720 | ~21,600 | No published limit |
| poll_prophetx | 300s | ~1-5 (pagination) | 12-60 | 288-1,440 | ~9K-43K | ProphetX: unconfirmed |

**Critical finding**: Odds API free tier is 500 calls/month. At current 600s interval with ~5 sport keys, the system burns ~21,600 calls/month — 43x the free tier. The existing 600s interval was set to conserve usage but is not conservative enough for the free tier. The API Usage tab will make this visible; operators need interval controls to manage it.

**Sports API (api-sports.io)**: Free tier is 100 calls/day. Current 1800s interval generates ~720 calls/day — 7x the free tier. Same issue as Odds API.

**Data sources for quota info:**
- Odds API: Response headers `x-requests-remaining`, `x-requests-used` (confirmed — HIGH confidence from official docs)
- Sports API (api-sports.io): Response headers `x-ratelimit-requests-remaining`, `x-ratelimit-requests-limit` (confirmed — HIGH confidence from api-football.com rate limit documentation)
- SDIO: No documented quota API; advertises "unlimited API calls" (HIGH confidence)
- ESPN: No documented quota API; unofficial API with no published limits (MEDIUM confidence — rate limiting exists but thresholds unpublished)

---

## Dynamic Interval Control: Technical Options

The "per-worker poll frequency control" feature has three implementation paths. Listed in order of implementation effort:

### Option A: Restart-Required DB Intervals (RECOMMENDED)
Store intervals in a `worker_schedule` PostgreSQL table. `celery_app.py` reads from DB on startup instead of hardcoded dict. Admin changes interval via UI → DB update → operator runs `docker compose restart beat` → new interval takes effect.

**Effort:** Medium — DB migration + API endpoint + UI + Beat startup change
**Complexity:** Low — no scheduler replacement, no Redis state management
**Beat restart:** Required after every change (acceptable — documented in UI tooltip)
**Confidence:** HIGH — established pattern; FastAPI + SQLAlchemy already in place

### Option B: sqlalchemy-celery-beat Library
Replace RedBeat with `sqlalchemy-celery-beat`. Stores schedule in PostgreSQL. Beat polls the DB for schedule changes at configurable intervals. No restart required for interval changes.

**Effort:** High — replaces the Beat scheduler (RedBeat → sqlalchemy-celery-beat); risks disrupting existing RedBeat lock behavior
**Complexity:** High — `redbeat_lock_timeout=900` behavior must be replicated; `LockNotOwnedError` risk from PITFALLS.md returns
**Beat restart:** Not required
**Confidence:** MEDIUM — library exists and works but scheduler replacement in production carries risk

### Option C: Redis-Backed Dynamic Schedule (Custom)
Keep RedBeat. Add a Redis key `worker:interval:{name}` that workers check at task start. If interval has changed since last run, tasks self-reschedule via `apply_async(countdown=new_interval)`.

**Effort:** High — requires each worker to implement self-scheduling logic; bypasses Beat entirely
**Complexity:** High — Beat and worker self-scheduling can drift; hard to debug
**Confidence:** LOW — non-standard pattern; high risk of scheduling inconsistencies

**Recommendation: Option A.** Restart-required interval control is entirely adequate for an internal ops tool where interval changes happen once every few weeks. The added complexity of Option B or C is not justified by the use case.

---

## v1 Feature Landscape (Reference — Already Built)

### Table Stakes (Completed in v1)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Real-time event status table | Core purpose — operators must see all ProphetX events and their current ProphetX vs. real-world status at a glance | MEDIUM | SSE stream from Redis pub/sub; dual-status columns with mismatch indicator |
| Real-time market liquidity table | Core purpose — operators must see all markets with current liquidity vs. configured threshold | MEDIUM | Same SSE stream; highlight below-threshold markets |
| Automated status sync (Upcoming → Live → Ended) | The system's primary value — removing manual status correction | HIGH | Requires event ID matching layer; Celery worker; ProphetX write API |
| Postponed/cancelled event flagging | Without this, bettors remain in open positions on dead events — high operational risk | MEDIUM | Detection only in v1; alert + dashboard highlight |
| Status mismatch highlighting | Operators must be able to spot problems instantly without reading every row | LOW | CSS color coding: amber = mismatch detected, red = action failed |
| Slack webhook alerting | Team must know about issues even when not watching the dashboard | LOW | Slack Block Kit messages; one webhook URL in config |
| In-app notification center | Audit trail of what the system has done; read/unread state | MEDIUM | Bell icon + panel; notifications link to relevant event/market |
| Configurable liquidity thresholds | Each market has different liquidity needs; global default plus per-market override | LOW | Admin-only; stored in SystemConfig and Market tables |
| Audit log (append-only) | Compliance, debugging, accountability | MEDIUM | PostgreSQL append-only table; no DELETE; before/after state in JSON |
| JWT authentication | Multi-user tool requires authentication | LOW | Standard FastAPI/JWT pattern; email + password |
| Role-based access control (Admin, Operator, Read-Only) | Multiple team members with different permission levels | MEDIUM | Three roles; server-side enforcement |
| Manual status sync trigger | Operators need an override for cases where automation fails | LOW | POST /events/{id}/sync-status; Operator + Admin only |
| "Last checked" timestamps | Operators must know data freshness | LOW | Display last_prophetx_poll and last_real_world_poll per row |
| System health indicator | If polling workers are down, operators must know immediately | MEDIUM | Worker heartbeat via Redis keys; banner/badge |
| Auto-retry with exponential backoff | ProphetX API failures must not silently drop actions | MEDIUM | Celery retry with 1s/2s/4s backoff |
| Alert deduplication | Without this, one stuck event generates 120 Slack alerts/hour | MEDIUM | Redis TTL key per event + condition type |
| Alert-only mode flag | Required for safe production rollout | LOW | Single config flag: auto_updates_enabled |

### Differentiators (Completed in v1)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Event ID matching layer with confidence scoring | Bridges ProphetX and SportsDataIO ID spaces; gates auto-actions at ≥0.90 confidence | HIGH | fuzzy string matching + time window; stored as event_id_mappings table |
| Multi-source status confirmation | 4 real-world sources (SDIO, Odds API, Sports API, ESPN) reduce false positive risk | HIGH | Each worker updates its own source column; status_match is True only when ProphetX agrees with real-world consensus |
| 5 supplementary data source workers | SDIO + Odds API + Sports API + ESPN + ProphetX WS — redundancy across all major sports data providers | HIGH | Each source is a separate Celery worker with independent failure isolation |

### Anti-Features (Deferred from v1)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Automated liquidity top-up | Operators want hands-free liquidity management | ProphetX API liquidity mechanics unconfirmed; financial risk | Alert-only; add after API mechanics confirmed and 2+ stable weeks |
| Email/SMS alerting | Some team members prefer email | Adds integration complexity for marginal gain over Slack | Slack + in-app for v1 |
| Historical analytics charts | "It would be great to see trends" | Requires time-series aggregation + chart library — significant scope | Audit log covers v1 debugging needs |
| Automated quota throttling | System adjusts its own poll intervals near quota limit | Risk of oscillation; complex feedback loop | Alert at 80% threshold; manual adjustment |

---

## Sources

- `/Users/doug/Prophet API Monitoring/.planning/PROJECT.md` — v1.1 milestone target features
- `/Users/doug/Prophet API Monitoring/backend/app/workers/celery_app.py` — current beat_schedule and intervals
- `/Users/doug/Prophet API Monitoring/backend/app/clients/odds_api.py`, `sports_api.py`, `base.py` — current client implementation
- The Odds API v4 documentation (`https://the-odds-api.com/liveapi/guides/v4/`) — response headers `x-requests-remaining`, `x-requests-used`, `x-requests-last` confirmed (HIGH confidence)
- api-football.com rate limit documentation (`https://www.api-football.com/news/post/how-ratelimit-works`) — response headers `x-ratelimit-requests-remaining`, `x-ratelimit-requests-limit`, `x-ratelimit-remaining`, `x-ratelimit-limit` confirmed (HIGH confidence)
- SportsDataIO official site (`https://sportsdata.io/apis`) — "unlimited API calls" confirmed (HIGH confidence)
- sqlalchemy-celery-beat PyPI (`https://pypi.org/project/sqlalchemy-celery-beat/`) — Option B library (MEDIUM confidence)
- Redis distributed counter pattern — standard Redis INCR/EXPIRE pattern (HIGH confidence)

---
*Feature research for: ProphetX Market Monitor v1.1 — API usage monitoring + stabilization*
*Researched: 2026-03-01*
