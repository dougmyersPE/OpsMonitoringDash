# Pitfalls Research

**Domain:** Real-time API polling system with automated corrective actions and financial consequences (prediction market operations)
**Researched:** 2026-02-24 (v1.0) / 2026-03-01 (v1.1 update)
**Confidence:** HIGH for Celery/Redis/SSE patterns (well-established, stable ecosystems); MEDIUM for ProphetX-specific behavior (undocumented external API); HIGH for event-matching failure modes (sports data industry patterns); HIGH for RedBeat dynamic scheduling (source code confirmed); MEDIUM for API usage tracking via response headers (documented for Odds API, inferred for api-sports.io via rate-limit behavior docs)

---

## v1.1 Pitfalls — API Usage Monitoring + Dynamic Poll Frequency

These pitfalls are specific to the v1.1 milestone. v1.0 pitfalls follow below.

---

### v1.1 Pitfall A: RedBeat Static beat_schedule Overwrites Dynamic Interval Changes on Restart

**What goes wrong:**
The UI lets an operator change a worker's poll interval at runtime (e.g., slow down Odds API polling from 10 min to 60 min to conserve quota). The FastAPI endpoint calls `RedBeatSchedulerEntry.from_key()`, updates the interval, and saves it back to Redis. This works — until the Beat container restarts. On startup, RedBeat's `setup_schedule()` calls `update_from_dict()` for every entry in the static `beat_schedule` config. This method **overwrites the Redis entry with the interval from code**, discarding the operator's runtime change. The operator has no warning that their setting was lost.

**Why it happens:**
RedBeat preserves `last_run_at` on restart (to avoid re-running immediately) but overwrites the interval and schedule definition from the static configuration. This is confirmed behavior in `redbeat/schedulers.py`: `update_from_dict()` loads the static definition and saves it, overwriting what was in Redis. The natural assumption — "I saved it to Redis, Redis survives restarts, therefore my change survives restarts" — is wrong for entries that also exist in the static config.

**How to avoid:**
Two valid approaches:

1. **Pure Redis approach (recommended):** Remove poll-frequency entries from the static `beat_schedule` in `celery_app.py`. Bootstrap them into Redis once (on first startup, if the key does not exist) via a startup script that calls `RedBeatSchedulerEntry(...).save()`. After that, they live only in Redis and are never overwritten by static config. The Beat container must handle a missing key gracefully on first deploy.

2. **Database-backed approach:** Store the operator-set intervals in PostgreSQL (`system_config` table). Add a Beat startup hook that reads current intervals from the DB and writes them to Redis before RedBeat loads its schedule. The DB is the source of truth; Redis is always reconciled from DB on startup.

Do NOT attempt to modify poll intervals by patching the running Beat process's schedule dict in memory — it does not persist and is not accessible from the FastAPI process.

**Warning signs:**
- Operator changes poll interval via UI; confirms it worked; Beat restarts for any reason; interval silently reverts to code default
- `docker compose restart beat` after any deploy undoes all runtime interval changes
- Redis key `redbeat:poll-odds-api` shows the operator's custom interval; after restart it shows the `.env` default
- No log entry or SSE event when the interval is overwritten — silent regression

**Phase to address:** Phase 2 (Dynamic Frequency Controls) — the storage strategy must be decided before building the UI. Choosing the wrong approach means rewriting the UI and backend on discovery of the restart problem.

---

### v1.1 Pitfall B: API Call Counter Race Condition Under --concurrency=6

**What goes wrong:**
The system tracks per-worker API call counts in Redis to display in the "API Usage" tab. Each worker uses a pattern like:

```python
current = redis.get("api_calls:sports_api:today")
redis.set("api_calls:sports_api:today", int(current or 0) + N)
```

With `--concurrency=6`, up to 6 worker processes can run concurrently. If two workers execute this read-modify-write in the same millisecond window, one worker reads the stale value, increments it, and writes back — overwriting the other's increment. The counter undercounts, sometimes by a significant margin when multiple sports are fetched concurrently. The displayed "calls used today" is wrong. If the system makes quota-management decisions based on this counter (e.g., "slow down when > 80% used"), those decisions fire too late.

**Why it happens:**
`redis.get()` + `redis.set()` is not atomic. It's a read-modify-write across two separate Redis commands. Under concurrent workers this is a classic check-then-act race. Many developers know Redis has atomic operations but reach for `get`/`set` by habit since it mirrors familiar patterns.

**How to avoid:**
Use `redis.incr(key, amount)` or `redis.incrby(key, N)` for all counter increments. `INCRBY` is a single atomic Redis command — there is no window between read and write. Also use `redis.expire(key, seconds)` immediately after the first `INCRBY` of the day (or use `INCR` + `EXPIREAT` with next midnight in one pipeline) to auto-reset at day boundaries.

```python
# Correct atomic pattern
pipe = redis.pipeline()
pipe.incrby("api_calls:sports_api:today", calls_made)
pipe.expireat("api_calls:sports_api:today", next_midnight_unix)
pipe.execute()
```

Do not use `INCR` for tracking "calls remaining" — track "calls made" instead and derive remaining from the known limit. This avoids the initialization problem (what is the "starting" value for remaining?).

**Warning signs:**
- Counter values do not match the sum visible in worker logs (`sports_api_games_fetched` log entries)
- Counter resets unexpectedly between page loads (TTL set incorrectly)
- Displayed "calls today" is lower than what poll logs show was actually fetched
- API source reports quota exceeded but dashboard shows 60% remaining

**Phase to address:** Phase 1 (API Usage Tab Backend) — use `INCRBY` from the start. Do not build the UI against a racy counter and then fix it later; the fix requires no code changes in the UI but requires the backend to be built correctly.

---

### v1.1 Pitfall C: Response Headers Are the Only Reliable Usage Source — But They Are Not Always Saved

**What goes wrong:**
The Odds API returns `x-requests-remaining` and `x-requests-used` response headers on every call. The system relies on these for the "API Usage" tab. The poll worker (`poll_odds_api.py`) calls the API, gets games, and discards the response headers — only the JSON body is used. The FastAPI endpoint for the usage tab then has no data to display except the locally-incremented Redis counter, which may drift from the actual provider count (e.g., if the worker crashes mid-call, if the API counts differently than expected, or if calls are made outside this system).

The api-sports.io API returns `x-ratelimit-requests-remaining` and `x-ratelimit-requests-limit` headers on every response. Same problem: the current `SportsApiClient.get_games()` calls `resp.raise_for_status()` and returns `data` but never touches the headers.

**Why it happens:**
When first writing an HTTP client, developers extract the JSON body they need and move on. Response headers are an afterthought. The usage tab is a later feature — by the time it's built, the client code is already written and the headers are already being discarded.

**How to avoid:**
Modify the client classes to capture and return usage headers alongside game data. The pattern is:

```python
# In SportsApiClient.get_games()
resp = await client.get(config["endpoint"], params=params)
resp.raise_for_status()
# Capture headers before extracting body
remaining = resp.headers.get("x-ratelimit-requests-remaining")
limit = resp.headers.get("x-ratelimit-requests-limit")
if remaining is not None:
    redis.set("api_usage:sports_api:remaining", remaining, ex=3600)
    redis.set("api_usage:sports_api:limit", limit or "unknown", ex=86400)
data = resp.json()
```

For the Odds API:
- `x-requests-remaining` = credits remaining until monthly quota resets
- `x-requests-used` = credits used since last monthly reset
- `x-requests-last` = cost of the last call (varies by endpoint)

For api-sports.io:
- `x-ratelimit-requests-remaining` = daily requests remaining
- `x-ratelimit-requests-limit` = daily limit per subscription tier

Note: SportsDataIO (SDIO) uses an Azure API Management gateway. It does not appear to expose usage headers; call counting must be done locally via Redis `INCRBY` or by monitoring the SDIO account dashboard. MEDIUM confidence on this — verify by inspecting actual response headers from the SDIO API on first call.

**Warning signs:**
- "API Usage" tab shows Redis-counted calls but no "provider-confirmed remaining" value
- Odds API quota runs out unexpectedly despite dashboard showing usage headroom
- `x-requests-remaining: 0` appears in logs but the dashboard does not reflect it

**Phase to address:** Phase 1 (API Usage Tab Backend) — modify client classes to capture headers before building the frontend. The UI can only display what the backend captures.

---

### v1.1 Pitfall D: Sports API Wrong-Game Match Produces Inprogress Status for Not-Started Events

**What goes wrong:**
The current Sports API matching in `poll_sports_api.py` uses a ±1 day index window to absorb UTC/timezone offsets. A game on Feb 28 at 11pm ET appears as Mar 1 in UTC. This is correct. However, the same two NBA teams can play on Feb 28 AND Mar 1 (consecutive-day series). The Feb 28 game finishes; its status is `FT` (final). The Mar 1 game has not started; ProphetX shows it as `not_started`. The fuzzy matcher scores both games highly for the Mar 1 ProphetX event (same teams, same sport, similar name). The Feb 28 game may score slightly higher because the game_date used for indexing is Mar 1 UTC (after midnight), creating a date-proximity tie. Result: the finished Feb 28 game's `FT` status (or `Q1`/`Q2` if it was being tracked mid-game) gets applied to the Mar 1 ProphetX event, triggering a false mismatch alert.

This is the root cause of the existing "Sports API returns Q1 for games ProphetX shows as not_started" known issue.

**Why it happens:**
The 12-hour guard (`hours_apart > 12 → skip`) compares the game date to a noon-UTC proxy timestamp rather than the game's actual start time. When the Sports API does not return a precise start time for the game (only a date), the proxy is noon UTC. A game actually starting at 7pm ET (midnight UTC) on Feb 28 has `game_date = Mar 1` (UTC), and the noon proxy for Mar 1 is 12:00 UTC. The ProphetX event on Mar 1 starting at 7pm ET is scheduled for midnight UTC Mar 2 — so `hours_apart` between noon Mar 1 and midnight Mar 2 = 12 hours exactly. The guard is `> 12`, not `>= 12`. This is a boundary condition bug.

**How to avoid:**
Three reinforcing fixes:

1. **Use actual start time from Sports API when available.** The api-sports.io response includes a `date` field with a full ISO datetime (e.g., `2026-03-01T23:00:00+00:00`). Use this, not a date-only proxy. The guard then compares real start times to real start times.

2. **Tighten the hours-apart threshold.** Change `> 12` to `> 6` or `> 8`. A legitimate UTC timezone offset is at most 5 hours for US time zones. If the two start times differ by more than 6 hours, they are different games.

3. **Prefer same-date matches over cross-date matches.** When scoring candidates, give a penalty (not just no bonus) to matches that cross a calendar day boundary. A same-date match scoring 0.85 should beat a cross-date match scoring 0.90.

**Warning signs:**
- Dashboard shows `status_match = False` for events that ProphetX shows as `not_started` but Sports API shows as `Q1` or `FT`
- The mismatch clears itself within 30 minutes (after the next poll cycle, the actual game has started and the status legitimately became live)
- Two different ProphetX events have the same Sports API game matched to them (the finished game matched both yesterday's and today's event)
- Log entry `sports_api_event_matched` shows `game_date: 2026-03-01` but `scheduled_start: 2026-03-02T...`

**Phase to address:** Phase 1 (False-Positive Fixes) — this is the first item to address in v1.1. All three fixes should land together; fixing only the threshold without using actual start times leaves the boundary condition exposed.

---

### v1.1 Pitfall E: SDIO NFL/NCAAB/NCAAF 404s Are Path Issues, Not Subscription Issues

**What goes wrong:**
`SportsDataIOClient.get_games_by_date_raw()` for NFL returns a 404 and logs `sportsdataio_no_games` — the same log message used when no games are scheduled. The operator sees the log and assumes there are no NFL games today, or that the off-season filter is working correctly. In fact, the 404 is caused by a wrong URL path segment: NFL uses `/nfl/` but SDIO's actual path is `/nfl/scores/json/...` with a different API prefix or version than NBA.

Wait — the existing `SPORT_PATH_MAP` already maps `ncaab → cbb` and `ncaaf → cfb`. The `nfl` path is passed through as-is (`nfl`). But SDIO's NFL API lives at `/nfl/` under v3, which is the same as NBA. The URL built is `/nfl/scores/json/GamesByDate/2026-03-01` which should be valid.

The actual issue documented in the milestone context is that NFL/NCAAB/NCAAF return 404s. The 404 suppression in `get_games_by_date_raw()` silently swallows the error and returns `[]`, making it indistinguishable from "no games today." A true 404 (wrong path) and a legitimate 404 (no games scheduled) produce identical logs.

**Why it happens:**
The 404 fallback was written to handle off-season dates (SDIO returns 404 when no games are scheduled, not an empty array). This is correct behavior for off-season. However, it also silences configuration errors. When the URL path is wrong or the subscription does not cover a sport, the 404 is swallowed with a `DEBUG` log — not a `WARNING` or `ERROR` — so it goes unnoticed.

**How to avoid:**
Add a one-time subscription probe on startup (the existing `probe_subscription_coverage()` method in `SportsDataIOClient` is already written for this). Run it on first deploy and log a `WARNING` for every sport returning non-200. This distinguishes "not subscribed" (403) from "no games today" (404) from "correct 404 for off-season" (also 404 but expected only on gameless dates).

For ongoing operation, track the ratio of 404 responses per sport over a rolling window. If NFL returns 404 on 10 consecutive polling days during the regular season, that is suspicious and should generate an alert.

Additionally: verify the actual SDIO URL paths for NFL, NCAAB, NCAAF against the live API before assuming the path is correct. The `SPORT_PATH_MAP` currently only remaps `ncaab → cbb` and `ncaaf → cfb`. If NFL uses a different path, add it to `SPORT_PATH_MAP`. Test this with a direct `curl` against the SDIO API before writing code.

**Warning signs:**
- `sportsdataio_no_games` log entries for NFL on a game day
- Dashboard shows no SDIO data for NFL events but ESPN and Sports API show live data
- `sport_counts` in `sdio_games_fetched` log shows `nfl: 0` during NFL season
- EventMatcher match rates drop to 0% for NFL events despite games being live

**Phase to address:** Phase 1 (False-Positive Fixes + SDIO Endpoint Fix) — run `probe_subscription_coverage()` before writing any polling logic fix. Confirm which URLs actually work before modifying code.

---

### v1.1 Pitfall F: Worker Health Endpoint Returns 404 Due to Router Registration Gap

**What goes wrong:**
The existing `/api/v1/health/workers` endpoint already exists in `health.py` and the router is registered in `main.py`. The known issue is that it returns 404. This typically means either: (a) the route path is wrong and the endpoint exists at a different URL than expected, (b) the router is not included in the FastAPI app (check `main.py`), or (c) the frontend is calling a different URL than the backend serves.

Looking at `main.py`: `app.include_router(health.router, prefix="/api/v1")`. The health router defines `@router.get("/health/workers")`. Combined prefix: `/api/v1/health/workers`. This should work.

The most likely cause of the 404: Nginx is configured to route requests to the backend, but the specific path `/api/v1/health/workers` is not proxied correctly, OR the frontend is calling `/api/v1/workers/health` (path segment reversed).

**Why it happens:**
FastAPI route registration bugs are usually discovered at startup (the framework logs all registered routes). The 404 in production for a route that exists in code almost always means the URL the client is calling does not match the URL the server has registered — off-by-one in prefix stacking, path segments reversed, or Nginx config stripping a path prefix.

**How to avoid:**
Before spending time debugging the FastAPI code, run `curl -v http://localhost:8000/api/v1/health/workers` from inside the backend container. If it returns 200, the bug is in the frontend URL or Nginx config. If it returns 404, check the registered routes at startup (`docker compose logs backend | grep "GET /api"` — FastAPI logs all routes on startup with `--log-level debug`).

Also verify: the workers health check uses `redis.mget()` to check heartbeat keys. If the Redis client connection is failing (not the route itself), FastAPI may return a 500, not a 404. Distinguish these cases before debugging.

**Warning signs:**
- `curl /api/v1/health` returns 200 but `curl /api/v1/health/workers` returns 404
- Frontend console shows `GET /api/v1/health/workers 404` (check exact URL in browser DevTools)
- Backend startup logs do not list `/api/v1/health/workers` in the route table

**Phase to address:** Phase 1 (Bug Fixes) — diagnose with curl before writing code.

---

### v1.1 Pitfall G: Displaying "API Usage" From Multiple Sources Requires a Consistent Data Contract

**What goes wrong:**
The API Usage tab displays data from three different sources in one UI: (1) provider-reported remaining calls from response headers, (2) locally-counted calls from Redis `INCRBY`, and (3) configured limits from `settings.py`. Each source has different refresh rates, different reset periods, and different reliability. The UI is built to show all three together without clearly distinguishing which is which. An operator sees "Sports API: 47 calls today / 100 limit" and assumes this is accurate, but the "100 limit" came from a hardcoded constant in settings, the "47 calls" is a Redis counter that undercounts due to the race condition in Pitfall B, and the provider-reported remaining (88) was last updated 30 minutes ago. All three numbers disagree silently.

**Why it happens:**
The UI is built quickly to "show something useful." Each field is wired to whichever data source was easiest to access at the time. The inconsistency is invisible until an operator asks why "47 calls today" plus "88 remaining" doesn't add up to the "100 limit."

**How to avoid:**
Define the data contract before building the UI. For each API source, decide exactly one authoritative number for each field:

| Source | Calls Used | Calls Remaining | Limit | Reset Period |
|--------|-----------|-----------------|-------|--------------|
| Odds API | `x-requests-used` header | `x-requests-remaining` header | From header or plan | Monthly (1st of month) |
| api-sports.io | Local Redis `INCRBY` | `x-ratelimit-requests-remaining` header | `x-ratelimit-requests-limit` header | Daily (rolling 24h) |
| SDIO | Local Redis `INCRBY` | N/A (no header) | Configured in settings | Per subscription |

Each field in the UI must have a tooltip or label indicating its source and last-updated timestamp. If a source is unavailable (header not captured, Redis key expired), show "—" not "0."

**Warning signs:**
- "Calls used" + "Calls remaining" does not equal "Limit"
- Numbers update at different rates, causing visible inconsistency
- Operator asks support why the numbers don't add up

**Phase to address:** Phase 1 (API Usage Tab Backend) — define the schema before building the frontend. A JSON schema for the `/api/v1/api-usage` endpoint with explicit field semantics prevents the inconsistency from being built in.

---

## v1.0 Pitfalls (Original)

The following pitfalls were documented during v1.0 research (2026-02-24). They remain relevant for v1.1 work.

---

### Pitfall 1: Duplicate Automated Actions (The Double-Fire Problem)

**What goes wrong:**
Two polling cycles overlap, or two Celery workers both detect the same status mismatch at the same time, and both enqueue a `update_event_status` task. Both tasks execute — ProphetX receives two identical PATCH requests in quick succession. At best, the second call is a no-op. At worst, it causes a race condition in ProphetX's own state machine (e.g., trying to transition an event that is already "live" to "live" again errors out) and triggers a false "Action Failed" alert to Slack.

**Why it happens:**
Celery Beat by default does not guarantee at-most-once task delivery. If a worker is slow, the scheduler will re-enqueue the task. If you run multiple workers (for redundancy), both workers can pick up and detect the same mismatch in the same polling window. Most developers write the detection logic ("if ProphetX status != real-world status, enqueue update") without a distributed lock around it.

**How to avoid:**
Use Redis-backed distributed locks (via `redis-py` with `SET NX EX` or `celery-redbeat`) for every action task. The lock key should encode the action intent: `lock:update_event:{prophetx_event_id}:to:{target_status}`. If the lock exists, skip enqueuing. Set lock TTL to at least 2× the max expected task execution time (e.g., 60 seconds for a task that should complete in 5). Additionally, write an "in-flight" status to the database/Redis before calling ProphetX, and check that status at the start of any action task before proceeding.

```python
# Pattern: lock before enqueue
lock_key = f"lock:status_update:{prophetx_event_id}"
acquired = redis_client.set(lock_key, "1", nx=True, ex=60)
if acquired:
    update_event_status.delay(prophetx_event_id, target_status)
# If not acquired, another worker is handling it — skip
```

**Warning signs:**
- Audit log shows the same event being updated twice within seconds
- Slack receives duplicate "updated to Live" messages for the same event
- ProphetX API returns 409 Conflict or equivalent errors on status updates
- Celery task count exceeds expected polling rate in monitoring

**Phase to address:** Phase 2 (Monitoring Engine) — must be built into the action-enqueuing logic from day one. Not a retrofit.

---

### Pitfall 2: Fuzzy Event Matching False Positives (Wrong Game Gets Updated)

**What goes wrong:**
The event matching layer incorrectly links a ProphetX event to the wrong SportsDataIO game. The system confidently detects a "mismatch" and auto-updates ProphetX — but it updated the wrong event. For example: two NBA games on the same night involving the same team (regular season game + an incorrectly scheduled preseason entry), or two games between the same teams in a playoff series on consecutive days. The matching by `sport + team names + scheduled_start_time` has a narrow collision window but real collisions exist.

**Why it happens:**
Developers trust the match result without a confidence score. The matching logic typically works for 95% of cases, so it's validated in testing and shipped. The 5% edge cases include: team name variations ("LA Lakers" vs "Los Angeles Lakers" vs "Lakers"), timezone bugs in scheduled_start comparisons, double-headers in MLB, playoff rematches, rescheduled games that retain the old start time in one system but get updated in another. A match that is "close enough" gets used.

**How to avoid:**
Never take automated action on a low-confidence match. Require all three of these to agree before auto-acting: (1) sport match exact, (2) both team names fuzzy-match above 0.85 similarity using `rapidfuzz`, (3) scheduled start within ±15 minutes. If any criterion falls below threshold, flag as "unmatched" and require manual review — do not auto-update. Log the confidence score for every match. Add a fourth tie-breaker: league (NFL vs. NCAAF both have "football" — league is essential). Store the match in the database with a `match_confidence` field. Dashboard should show "LOW CONFIDENCE MATCH" warning on any event where the matching score was below 0.90.

**Warning signs:**
- The audit log shows an event updated that the operator doesn't remember being scheduled
- A ProphetX event gets marked "Live" but operators know the game hasn't started yet
- Two different ProphetX events both match to the same SportsDataIO game ID
- Match confidence scores cluster near the threshold (many 0.85–0.90 scores = fragile matching)

**Phase to address:** Phase 2 (Monitoring Engine) — the matching layer is the most critical piece of Phase 2. Budget extra time. Build the manual override UI in Phase 4 so operators can correct bad matches.

---

### Pitfall 3: Alert Storms Causing Operator Blindness

**What goes wrong:**
Every 30-second polling cycle re-detects the same unresolved mismatch (e.g., ProphetX is still showing "upcoming" because the API update failed, or is slow). Each cycle fires a new Slack message and creates a new in-app notification. After 10 minutes, the Slack channel has 20 identical alerts for the same event. Operators start ignoring Slack. The next genuinely new critical alert is missed because it's buried in the noise.

**Why it happens:**
Developers implement alert-on-detect without alert-on-new-state. The detection logic correctly runs every cycle, but the alerting logic doesn't track whether an alert for that specific condition has already been sent. It's an easy miss because in testing, each test scenario runs once — the repeat-cycle behavior only manifests in production.

**How to avoid:**
Store alert state in Redis with a TTL. Key: `alert_sent:{event_id}:{condition_type}`. When an alert is sent, write this key with TTL = alert suppression window (e.g., 5 minutes for warnings, 15 minutes for critical). Before sending an alert, check if the key exists. Only send if the key is absent. Also implement a "still unresolved" digest: after the suppression window expires, if the condition is still present, re-alert but with "STILL UNRESOLVED (10 min)" context rather than treating it as a fresh alert.

**Warning signs:**
- Slack channel is scrolling with repeated messages about the same event
- Operators say they "don't trust" the Slack channel
- In-app notification count grows by 2+ per minute for the same event
- `notifications` table grows by hundreds of rows for a single unresolved issue

**Phase to address:** Phase 4 (Alerting) — implement alert deduplication from day one in alerting phase.

---

### Pitfall 4: SSE Connection Drops Break Dashboard Without Visible Indication

**What goes wrong:**
The browser's SSE connection to `/api/v1/stream` silently drops (network hiccup, server restart, Nginx timeout, 30-minute load balancer idle timeout). The React dashboard continues displaying data, but it's now frozen — the last state it received. Operators make decisions based on 45-minute-old data and don't know the dashboard is stale.

**Why it happens:**
SSE is deceptively simple. Sending events is easy. The missed-events-on-reconnect problem is invisible in development. The Nginx `proxy_read_timeout` (default 60 seconds) silently kills SSE connections sitting idle.

**How to avoid:**
(1) Send a heartbeat SSE comment (`: heartbeat\n\n`) every 15 seconds from the server. (2) Implement `id:` fields on every SSE event. (3) On reconnect, replay events from Redis. (4) Show a visible "Connection lost — reconnecting..." banner. (5) Configure Nginx: `proxy_read_timeout 3600s;` and `proxy_buffering off;`.

**Warning signs:**
- Dashboard data stops updating but no error is visible
- Browser DevTools Network tab shows SSE connection cycling Pending→Failed→Pending
- Redis pub/sub is publishing events but dashboard doesn't update
- Users report dashboard "freezing" after being open for 30–60 minutes

**Phase to address:** Phase 3 (Dashboard) + Phase 5 (Deploy/Nginx).

---

### Pitfall 5: Automated Actions on Financially Consequential State Without Idempotency

**What goes wrong:**
The `update_event_status` Celery task calls ProphetX API to set an event to "ended." The API call succeeds, but the network response times out before Celery gets the 200 OK. Celery marks the task as failed and retries. The retry calls ProphetX again — now the event is "ended" again (no-op if ProphetX is idempotent, disaster if it triggers settlement logic twice).

**Why it happens:**
Developers write: "call external API → if success, write to DB → done." Partial failures (API success but response lost) create inconsistent state. In a financial system, "the books say settled but the platform is still accepting bets" is a serious problem.

**How to avoid:**
(1) Write action intent to the database BEFORE calling the external API. (2) Call the ProphetX API. (3) On success, update status. (4) On failure, mark as "update_failed" and trigger human-intervention alert. (5) Make all retry logic read current ProphetX state first — if already at desired status, mark complete without calling again.

**Warning signs:**
- Audit log shows same event with both "success" and "failure" entries within seconds
- Redis and PostgreSQL show different statuses for the same event
- Duplicate Slack alerts for the same action

**Phase to address:** Phase 2 (Monitoring Engine) — the idempotent task pattern must be the default from the start.

---

### Pitfall 6: Celery Beat Clock Drift Causing Missed Polling Cycles

**What goes wrong:**
When the Beat process restarts (container redeploy, VPS maintenance, OOM kill), it can lose track of when tasks last ran — either skipping cycles or firing all overdue tasks simultaneously when it comes back up.

**Why it happens:**
The default Celery Beat scheduler persists state in a local file (`celerybeat-schedule`). In Docker, this file lives inside the container and is lost on container restart unless mounted as a volume.

**How to avoid:**
Use `celery-redbeat` (already in use in this codebase). Configure it to skip overdue tasks on startup rather than catch up.

**Warning signs:**
- After any container restart, audit log shows a burst of polling activity all at the same timestamp
- ProphetX API rate limit errors immediately after deployment

**Phase to address:** Phase 1 (Foundation) — configure RedBeat during initial Celery setup.

---

### Pitfall 7: Redis Memory Exhaustion Killing the Entire System

**What goes wrong:**
Redis is used for three things: Celery task broker, application cache, and SSE pub/sub. On a ~$15/month VPS with 1–2GB RAM, if Redis runs without a `maxmemory` policy, it grows unbounded. When Redis OOMs, the VPS OOM killer terminates Redis — taking down the Celery broker and all background workers simultaneously.

**Why it happens:**
Celery's default `result_backend` stores task results in Redis with no TTL. With 30-second polling cycles, Redis grows by ~5,760 task results/day.

**How to avoid:**
(1) Set `result_expires=3600`. (2) Configure `maxmemory 256mb` and `maxmemory-policy allkeys-lru`. (3) Set `task_ignore_result=True` for polling tasks (already done in this codebase).

**Warning signs:**
- `redis-cli info memory` shows `used_memory` growing over days/weeks
- Celery workers report "BrokerConnectionError" intermittently

**Phase to address:** Phase 1 (Foundation).

---

### Pitfall 8: ProphetX API Status Enum Assumptions Causing Silent Failures

**What goes wrong:**
The comparison logic is built against assumed ProphetX status values. The actual ProphetX API uses different values. The status comparison never matches, so mismatches are never detected. No errors are thrown — the system runs, polls successfully, logs clean — but never detects anything. This could go unnoticed for days.

**Why it happens:**
Developers prototype the comparison logic with guessed values, then forget to update after reading the actual API docs. Or the API uses different values in sandbox vs. production.

**How to avoid:**
Log every raw status value received from ProphetX on the very first poll. Build the enum from actual observed data, not documentation.

**Warning signs:**
- No mismatches ever detected despite events being live in the real world
- `status_match` field is always `True` in the database

**Phase to address:** Phase 1 (Foundation) + Phase 2 (Monitoring Engine).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Poll intervals in static `beat_schedule` only (no DB backup) | Simple setup | Runtime changes are lost on Beat container restart | Acceptable for v1.0 where intervals never change; unacceptable once v1.1 UI controls are added |
| Counting API calls with `get`/`set` instead of `INCRBY` | Familiar pattern | Race condition undercounts under `--concurrency=6` | Never — `INCRBY` is the same effort |
| Discarding HTTP response headers in API clients | Simpler client code | Can't show provider-reported quota data in UI | Acceptable before API usage tab is built; must be fixed when usage tab is added |
| Suppressing all 404s from SDIO as "no games" | Handles off-season dates cleanly | Silences path/subscription errors; NFL/NCAAB/NCAAF 404s go undetected | Acceptable if a startup probe distinguishes subscription errors from gameless-date 404s |
| Hardcoding API limits in `settings.py` | Fast to implement | Limits drift from what provider actually enforces | Acceptable as fallback when headers are unavailable; must be labeled as "configured" not "confirmed" in UI |
| Polling tasks check Redis only (skip DB read) | Faster polling cycles | Redis and DB diverge; DB becomes unreliable source of truth | Never — always write canonical state to DB, use Redis as cache only |
| Skip match confidence scoring; match on team name only | Simpler matching code | False positive matches; wrong events get auto-updated | Never for auto-actions; acceptable for display-only confidence hints |
| No SSE heartbeat | Simpler server code | Silent stale dashboard; operators can't trust data | Never in production |
| Alert on every detection (no deduplication) | Easier alert code | Alert storm → operator blindness → missed real alerts | Acceptable only during initial 48-hour shadow mode testing |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| The Odds API | Count calls via local Redis counter only | Capture `x-requests-remaining` and `x-requests-used` response headers; show provider-reported value in UI, use local counter as fallback when headers are absent |
| The Odds API | Assume monthly quota resets on the 1st | Quota resets on the 1st of each month; build reset-day detection into the UI so "X calls used this month" resets visually at the right time |
| api-sports.io | Assume one quota counter for all sports | Each sport is a separate API base URL; daily quota is per API endpoint family, not global. Basketball, Hockey, Baseball, American Football all have separate quotas |
| api-sports.io | Miss the `/status` endpoint | The api-sports.io `/status` endpoint returns account information; the `x-ratelimit-requests-remaining` header on every response is more reliable for real-time tracking |
| SDIO | Call sport-specific endpoints without confirming subscription coverage | Check subscription tier before building polling for each sport; log which sports return 200 vs. 403 vs. 404; don't assume NBA access implies NFL/NCAAB access |
| SDIO | Treat all 404 responses identically | A 404 on a gameless date is correct; a 404 on a game day is a path or subscription error; distinguish via startup probe |
| ProphetX API | Assume rate limit is generous; don't track request rate | Count requests per minute in polling logic; use a Redis counter; back off proactively before hitting the limit |
| RedBeat | Modify schedule in Redis via API endpoint, assuming it persists through restarts | Static `beat_schedule` in code overwrites Redis entries on restart; use DB-backed intervals or remove entries from static config entirely |
| Slack webhook | Post one message per detected issue per cycle | Rate limit Slack at 1 req/sec; burst posting will trigger 429 from Slack |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Querying full events list from PostgreSQL on every polling cycle | Polling worker takes 2+ seconds per cycle; query load spikes every 30 seconds | Cache current event/market state in Redis; polling worker updates Redis | At ~200+ events; immediate on a slow VPS |
| N+1 query: fetching each market's liquidity individually | Hundreds of DB queries per polling cycle | Batch fetch all markets in one query | At ~50 markets |
| SSE: sending full event object on every change | Large SSE messages; browser parsing 10KB+ JSON every 30 seconds | Send delta events; client fetches full details on demand | With 100+ concurrent SSE clients |
| Celery result storage in Redis without TTL | Redis memory grows unbounded over weeks | `result_expires=3600` and `task_ignore_result=True` for fire-and-forget tasks | After ~2 weeks of production |
| API usage counters reset on Redis restart | Usage tab shows 0 after Redis restart despite many calls made | Set counter TTL to end-of-day only; restore from provider headers on first successful call after restart | Any Redis restart |
| No database indexes on `prophetx_event_id` and `status_match` columns | Slow dashboard queries as event/market count grows | Add indexes on hot query columns during initial migration | At ~1,000 audit log entries |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Passing JWT in SSE query parameter (`?token=...`) | Token is logged in Nginx access logs | Use a short-lived SSE token endpoint; or cookie-based auth |
| Exposing ProphetX API key in browser-visible responses | Attacker can make ProphetX API calls as the operator | ProphetX API key lives only in backend environment |
| No rate limiting on the manual sync trigger endpoint | Operator can spam ProphetX API with update requests | Rate limit manual trigger to 1 request per event per 30 seconds |
| Audit log that can be modified | Compliance risk; removes ability to detect unauthorized automated actions | PostgreSQL `GRANT` permissions: application DB user has `INSERT` only on `audit_log` |
| API usage endpoint accessible to Read-Only users without filtering | Exposes internal rate limit state | Gate the API usage tab behind Operator or Admin role; Read-Only users should not see quota details |
| Poll frequency control endpoint accessible to Operator role | An Operator could set intervals to 1 second, exhausting API quotas | Restrict dynamic frequency controls to Admin role only |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| API usage tab shows three numbers that don't add up (provider remaining + local counter + configured limit from different reset periods) | Operator confusion; distrust of the feature | Show exactly one authoritative value per field with source label and last-updated time; never display inconsistent values side by side without explaining why they differ |
| Poll frequency controls take effect but the next run is still the old interval away | Operator changes 60-min interval to 5-min; waits 60 minutes wondering why nothing changed | After saving a new interval, show "Next run: in X minutes" based on the new schedule; optionally offer "Run now" button |
| API quota bar reaches 100% with no warning | Operator has no chance to act before quota is exhausted | Alert at 80% and 95%; show days remaining in billing period; suggest which worker to slow down |
| Dashboard shows last-updated timestamp per-table but not per-row | Operator can't tell if a specific row's data is 5 seconds old or 5 minutes old (SSE dropped) | Show `last_real_world_poll` per row; highlight rows where the poll timestamp is > 90 seconds old |
| Manual sync button shows no feedback while the async task is running | Operator clicks "Sync" twice because nothing seemed to happen | Disable button and show spinner from click until Celery task completes |

---

## "Looks Done But Isn't" Checklist

- [ ] **Dynamic poll frequency:** Looks done after UI saves interval to Redis — verify that restarting the Beat container does not revert to the code-default interval; test by saving a custom interval, running `docker compose restart beat`, then checking the Redis key value
- [ ] **API usage counters:** Looks done after `INCRBY` is wired up — verify by running two workers concurrently against the same API for 1 minute; compare Redis counter to sum of log-reported call counts; they should match
- [ ] **Provider-reported quota headers:** Looks done after wiring headers in client — verify by inspecting the actual HTTP response with `httpx` logging; confirm headers are present and non-null on a real API call before building UI around them
- [ ] **SDIO endpoint paths:** Looks done after adding NFL to `SPORT_PATH_MAP` — verify with a real `curl` against `https://api.sportsdata.io/v3/nfl/scores/json/GamesByDate/2026-01-05` with the actual API key; confirm 200 not 404
- [ ] **Sports API false positive fix:** Looks done after tightening the hours-apart guard — verify by constructing a test case where the same two teams play on consecutive days; confirm only the correct game is matched to the ProphetX event
- [ ] **Worker health endpoint:** Looks done after confirming route exists in code — verify with `curl -v http://localhost:8000/api/v1/health/workers` from inside the backend container; if 200, test from outside via Nginx; if 404, check exact URL in browser DevTools
- [ ] **Event matching layer:** Looks done after matching 10 test games — verify it handles: same two teams playing twice in one week (playoff series), doubleheaders (MLB), timezone edge cases around midnight, postponed games that get rescheduled
- [ ] **Celery worker restart:** Looks done with `restart: unless-stopped` in docker-compose — verify: (a) tasks in flight when a worker dies are re-queued, (b) Beat restarts don't duplicate tasks, (c) audit log shows task as failed (not silently lost)

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Dynamic poll interval lost on Beat restart | LOW | Re-enter interval in UI; implement DB-backed persistence to prevent recurrence |
| API counter undercount discovered | LOW | Reset counter via Redis CLI; deploy `INCRBY` fix; accept that historical counts are inaccurate |
| Provider quota exhausted unexpectedly | MEDIUM | Stop the affected worker immediately (`docker compose stop poll_odds_api`); wait for quota reset; deploy interval slowdown; add 80% alert |
| SDIO NFL/NCAAB/NCAAF returning 404 in production | MEDIUM | Run `probe_subscription_coverage()` to distinguish path error from subscription error; test URL with curl; fix path in `SPORT_PATH_MAP` if wrong |
| Sports API false positive triggered a ProphetX status update | HIGH if action taken | Check audit log for the bad update; manually revert via ProphetX API; review matching logs for the affected event; tighten time guard |
| Duplicate actions already fired | LOW if ProphetX is idempotent; HIGH if settlement triggered twice | Check ProphetX API for current event state; compare to audit log; if duplicate settlement, requires manual ProphetX support intervention |
| Wrong event matched and auto-updated | MEDIUM | Audit log shows the incorrect update; manually revert via ProphetX API; add event pair to manual match override |
| Alert storm already flooded Slack | LOW | Delete duplicate messages via Slack API; deploy fix with deduplication |
| Redis memory exhausted, broker down | HIGH | `redis-cli FLUSHDB`; restart Celery workers; set maxmemory; polling resumes from next cycle |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| RedBeat static schedule overwrites dynamic intervals on restart (v1.1 A) | v1.1 Phase 2 (Dynamic Frequency Controls) | Restart Beat after saving custom interval; confirm Redis key retains operator value |
| API counter race condition under concurrency (v1.1 B) | v1.1 Phase 1 (API Usage Backend) | Run concurrent workers; compare Redis counter to log-reported totals |
| Response headers discarded in clients (v1.1 C) | v1.1 Phase 1 (API Usage Backend) | Inspect live API response headers; confirm values stored in Redis |
| Sports API wrong-game false positives (v1.1 D) | v1.1 Phase 1 (False-Positive Fixes) | Construct consecutive-day same-teams test; verify only correct game matches |
| SDIO 404s indistinguishable from off-season (v1.1 E) | v1.1 Phase 1 (SDIO Endpoint Fix) | Run probe on NFL during regular season; confirm 200 response |
| Worker health 404 (v1.1 F) | v1.1 Phase 1 (Bug Fixes) | Curl from inside container; confirm 200 |
| Inconsistent API usage data contract (v1.1 G) | v1.1 Phase 1 (API Usage Backend) | Review `/api/v1/api-usage` schema; confirm all fields have source labels and last-updated timestamps |
| Duplicate automated actions | Phase 2 (Monitoring Engine) | Integration test: two concurrent mismatch detections; verify one ProphetX API call only |
| Fuzzy event matching false positives | Phase 2 (Monitoring Engine) | Test suite with known ambiguous cases |
| Alert storms | Phase 4 (Alerting) | Simulate same mismatch across 5 cycles; verify 1 Slack message in suppression window |
| SSE silent stale connection | Phase 3 (Dashboard) + Phase 5 (Deploy) | Kill SSE connection from server; verify banner appears within 20 seconds |
| Automated actions without idempotency | Phase 2 (Monitoring Engine) | Simulate API success with response timeout; verify no double-apply on retry |
| Celery Beat clock drift | Phase 1 (Foundation) | Restart Beat container; verify no burst of duplicate tasks |
| Redis memory exhaustion | Phase 1 (Foundation) | Set maxmemory in docker-compose.yml; verify with `redis-cli info memory` after 48 hours |
| ProphetX status enum assumptions | Phase 1 (Foundation) + Phase 2 | Log raw ProphetX API responses; assert against actual observed values |

---

## Sources

- RedBeat schedulers.py source (setup_schedule, update_from_dict behavior on restart): https://github.com/sibson/redbeat/blob/main/redbeat/schedulers.py
- RedBeat documentation (task creation, modification, runtime behavior): https://redbeat.readthedocs.io/en/latest/tasks.html
- The Odds API documentation (x-requests-remaining, x-requests-used, x-requests-last headers): https://the-odds-api.com/liveapi/guides/v4/
- api-sports.io rate limit behavior (x-ratelimit-requests-limit, x-ratelimit-requests-remaining headers): https://www.api-football.com/news/post/how-ratelimit-works
- Redis INCR atomicity and counter patterns: https://redis.io/docs/latest/commands/incr/
- Redis distributed counter patterns (race conditions with GET/SET): https://dev.to/silentwatcher_95/fixing-race-conditions-in-redis-counters-why-lua-scripting-is-the-key-to-atomicity-and-reliability-38a4
- Celery documentation on task deduplication and distributed locks: https://docs.celeryq.dev/en/stable/userguide/tasks.html#avoiding-launching-the-same-task
- FastAPI SSE patterns and EventSource reconnection: MDN Web Docs — Server-sent events
- Redis maxmemory configuration: https://redis.io/docs/manual/eviction/
- rapidfuzz library: https://github.com/maxbachmann/RapidFuzz
- Nginx proxy_read_timeout: https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_read_timeout
- Codebase review: poll_sports_api.py (false positive root cause analysis), celery_app.py (static beat_schedule structure), sportsdataio.py (SPORT_PATH_MAP, 404 handling), mismatch_detector.py (compute_status_match, canonical mappings)

**Confidence notes:**
- v1.1 Pitfall A (RedBeat restart overwrite): HIGH — confirmed from schedulers.py source code
- v1.1 Pitfall B (Redis counter race): HIGH — standard Redis concurrency knowledge, confirmed by docs
- v1.1 Pitfall C (header capture): MEDIUM for api-sports.io headers (header names confirmed via api-football.com docs, which shares the same backend as api-sports.io); HIGH for Odds API headers (official docs)
- v1.1 Pitfall D (false positive root cause): HIGH — root cause traced directly in poll_sports_api.py source
- v1.1 Pitfall E (SDIO 404 indistinguishable): HIGH — confirmed in sportsdataio.py source; SDIO subscription coverage is MEDIUM (needs live verification)
- v1.1 Pitfall F (health endpoint 404): MEDIUM — route exists in code, actual 404 cause unknown without live debugging

---
*Pitfalls research for: ProphetX Market Monitor — real-time API polling system with automated corrective actions*
*v1.0 researched: 2026-02-24*
*v1.1 update: 2026-03-01*
