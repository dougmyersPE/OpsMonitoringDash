# Architecture Research

**Domain:** Real-time external API monitoring system with background workers and live dashboard
**Researched:** 2026-02-24
**Confidence:** HIGH (core patterns verified from PRD context + established Celery/FastAPI/Redis/SSE patterns)

---

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL DATA SOURCES                        │
│  ┌──────────────────────┐          ┌──────────────────────────────┐  │
│  │   SportsDataIO API   │          │       ProphetX API           │  │
│  │  (real-world status) │          │  (market status + liquidity) │  │
│  └──────────┬───────────┘          └──────────────┬───────────────┘  │
└─────────────┼────────────────────────────────────┼──────────────────┘
              │ poll every ~30s                     │ poll + write
              ▼                                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      BACKGROUND WORKER LAYER                         │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │  Celery Beat     │  │  Poll Workers    │  │  Action Workers  │   │
│  │  (scheduler)     │→ │  poll_sports     │  │  update_status   │   │
│  │  30s tick        │  │  poll_prophetx   │→ │  send_slack      │   │
│  └──────────────────┘  └────────┬─────────┘  └────────┬─────────┘   │
│                                 │ write state          │ write audit  │
└─────────────────────────────────┼──────────────────────┼─────────────┘
                                  │                      │
              ┌───────────────────▼──────────────────────▼───────────┐
              │                   DATA LAYER                          │
              │  ┌──────────────────────┐  ┌──────────────────────┐  │
              │  │  PostgreSQL          │  │  Redis               │  │
              │  │  (persistent store)  │  │  (cache + broker +   │  │
              │  │  events, markets,    │  │   pub/sub)           │  │
              │  │  audit_log, users,   │  │                      │  │
              │  │  config, notifs      │  │                      │  │
              │  └──────────────────────┘  └──────────┬───────────┘  │
              └──────────────────────────────────────┬─┘              │
                                                      │                │
┌─────────────────────────────────────────────────────▼───────────────┐
│                       API / DELIVERY LAYER                           │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  FastAPI Backend                                             │   │
│  │  - REST endpoints (events, markets, audit, notifications)    │   │
│  │  - JWT auth / RBAC enforcement                               │   │
│  │  - SSE /api/v1/stream (subscribes to Redis pub/sub)          │   │
│  │  - Reads from Redis cache for speed                          │   │
│  │  - Writes config changes / manual triggers to PostgreSQL     │   │
│  └──────────────────────────────┬───────────────────────────────┘   │
└─────────────────────────────────┼────────────────────────────────────┘
                                  │ SSE stream + REST
              ┌───────────────────▼────────────────────────────────┐
              │                FRONTEND LAYER                       │
              │  ┌──────────────────────────────────────────────┐  │
              │  │  React + TypeScript SPA                      │  │
              │  │  - EventSource() consumes /api/v1/stream     │  │
              │  │  - TanStack Query for REST data fetching     │  │
              │  │  - Events table (status mismatch highlight)  │  │
              │  │  - Markets table (liquidity threshold view)  │  │
              │  │  - Notification bell + center                │  │
              │  │  - Admin config panel                        │  │
              │  └──────────────────────────────────────────────┘  │
              └────────────────────────────────────────────────────┘

                        Reverse Proxy: Nginx (SSL termination, static serving)
                        Deployment: Docker Compose on VPS
```

### Component Responsibilities

| Component | Responsibility | Communicates With |
|-----------|----------------|-------------------|
| Celery Beat | Schedules recurring poll tasks on 30s interval | Celery workers (via Redis task queue) |
| Poll Workers (Celery) | Fetch external API data, detect mismatches, enqueue action tasks | ProphetX API, SportsDataIO, Redis cache, PostgreSQL, Celery action queue |
| Action Workers (Celery) | Execute ProphetX status updates, send Slack alerts | ProphetX API, Slack Webhook, PostgreSQL (audit), Redis pub/sub |
| Event Matching Layer | Map ProphetX event IDs to SportsDataIO game IDs | PostgreSQL (event mapping table), used by Poll Workers |
| FastAPI Backend | Serve REST API, authenticate users, expose SSE stream | PostgreSQL (reads/writes), Redis (pub/sub subscribe, cache reads) |
| Redis | Task broker, state cache, pub/sub message bus | Celery Beat, Poll Workers, Action Workers, FastAPI |
| PostgreSQL | Durable storage for all entities and audit log | Poll Workers, Action Workers, FastAPI |
| React Dashboard | Real-time operations UI | FastAPI REST endpoints, FastAPI SSE stream |
| Nginx | Reverse proxy, SSL termination, static file serving | React SPA (static), FastAPI (proxy) |

---

## Recommended Project Structure

```
prophet-monitor/
├── backend/
│   ├── app/
│   │   ├── api/                     # FastAPI route handlers
│   │   │   ├── v1/
│   │   │   │   ├── events.py        # GET /events, POST /events/{id}/sync-status
│   │   │   │   ├── markets.py       # GET /markets, PATCH /markets/{id}/config
│   │   │   │   ├── audit.py         # GET /audit-log
│   │   │   │   ├── notifications.py # GET /notifications
│   │   │   │   ├── stream.py        # GET /stream (SSE endpoint)
│   │   │   │   ├── auth.py          # POST /auth/login, /auth/refresh
│   │   │   │   └── config.py        # GET/PATCH /config
│   │   │   └── deps.py              # Shared dependencies (auth, DB session)
│   │   ├── workers/                 # Celery tasks
│   │   │   ├── celery_app.py        # Celery app + Beat schedule config
│   │   │   ├── poll_prophetx.py     # Task: poll ProphetX events + markets
│   │   │   ├── poll_sports_data.py  # Task: poll SportsDataIO + supplementary
│   │   │   ├── update_status.py     # Task: call ProphetX to update event status
│   │   │   └── send_alerts.py       # Task: send Slack + create notification
│   │   ├── services/                # Business logic (no framework coupling)
│   │   │   ├── mismatch_detector.py # Compare ProphetX status vs real-world
│   │   │   ├── liquidity_monitor.py # Evaluate liquidity vs thresholds
│   │   │   ├── event_matcher.py     # ID matching layer: ProphetX ↔ SportsDataIO
│   │   │   ├── audit_writer.py      # Append-only audit log writes
│   │   │   └── notification_svc.py  # Create/deliver notifications
│   │   ├── clients/                 # External API clients (isolated wrappers)
│   │   │   ├── prophetx.py          # ProphetX REST client (auth + retry)
│   │   │   ├── sportsdataio.py      # SportsDataIO client (per-sport adapters)
│   │   │   ├── slack.py             # Slack webhook client
│   │   │   └── base.py              # Base client with retry/backoff logic
│   │   ├── models/                  # SQLAlchemy ORM models
│   │   │   ├── event.py
│   │   │   ├── market.py
│   │   │   ├── audit_log.py
│   │   │   ├── user.py
│   │   │   ├── notification.py
│   │   │   └── config.py
│   │   ├── schemas/                 # Pydantic request/response schemas
│   │   │   ├── event.py
│   │   │   ├── market.py
│   │   │   └── ...
│   │   ├── db/
│   │   │   ├── session.py           # SQLAlchemy session factory
│   │   │   └── redis.py             # Redis connection + pub/sub helpers
│   │   ├── core/
│   │   │   ├── config.py            # Settings (env vars via pydantic-settings)
│   │   │   ├── security.py          # JWT creation/verification, bcrypt
│   │   │   └── constants.py         # Status enums, event types
│   │   └── main.py                  # FastAPI app factory + startup events
│   ├── alembic/                     # Database migrations
│   │   ├── versions/
│   │   └── env.py
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── conftest.py
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── EventsTable.tsx      # Status mismatch view
│   │   │   ├── MarketsTable.tsx     # Liquidity monitoring view
│   │   │   ├── NotificationBell.tsx # Unread count + dropdown
│   │   │   ├── NotificationCenter.tsx
│   │   │   └── AdminConfig.tsx      # Threshold + system settings
│   │   ├── hooks/
│   │   │   ├── useSSE.ts            # EventSource connection + reconnect
│   │   │   ├── useEvents.ts         # TanStack Query for events list
│   │   │   └── useMarkets.ts
│   │   ├── lib/
│   │   │   ├── api.ts               # Axios/fetch client + auth interceptors
│   │   │   └── queryClient.ts       # TanStack Query client config
│   │   ├── store/
│   │   │   └── notificationsStore.ts # Zustand or React context for unread count
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx        # Main ops view
│   │   │   ├── AuditLog.tsx
│   │   │   └── Login.tsx
│   │   ├── types/                   # TypeScript interfaces matching backend schemas
│   │   └── App.tsx
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml               # All services: backend, frontend, postgres, redis, celery, nginx
├── docker-compose.dev.yml           # Dev overrides (hot reload, no SSL)
├── nginx/
│   ├── nginx.conf
│   └── ssl/                         # Certbot-managed certs
└── .env.example                     # All required env vars documented
```

### Structure Rationale

- **`workers/` separate from `api/`:** Celery workers and FastAPI routes share models and services but are separate entry points. Keeps polling logic out of request-response handlers.
- **`clients/` layer:** All external API calls go through isolated client classes. If ProphetX changes their API, only `prophetx.py` changes. Retry/backoff logic lives in `base.py`, inherited by all clients.
- **`services/` layer:** Business logic (mismatch detection, liquidity comparison, event matching) is framework-agnostic. Can be called by both Celery workers and FastAPI endpoints (for manual sync triggers) without duplication.
- **`models/` vs `schemas/`:** SQLAlchemy ORM models define database shape. Pydantic schemas define API request/response shape. Kept separate to avoid coupling persistence to serialization.

---

## Architectural Patterns

### Pattern 1: Celery Beat + Worker Separation

**What:** Celery Beat is a separate process that acts only as a scheduler — it does not execute tasks itself. It reads the beat schedule and publishes task messages to the Redis broker queue on the configured interval. Celery workers are separate processes that consume from that queue and execute tasks.

**When to use:** Any periodic background work that must survive crashes and be independently scalable.

**Trade-offs:** Adds operational complexity (must run beat + at least one worker process) but gains: independent restarts, horizontal scaling (add workers), task retry queues, and complete isolation from the web server.

**How it fits this system:**
```
Celery Beat (1 process, scheduler only)
    → publishes "poll_prophetx" every 30s to Redis queue
    → publishes "poll_sports_data" every 30s to Redis queue

Celery Worker Pool A (poll_queue)
    → consumes poll_prophetx task
    → consumes poll_sports_data task
    → on mismatch: publishes "update_event_status" to action_queue
    → on threshold breach: publishes "send_slack_alert" to action_queue

Celery Worker Pool B (action_queue)
    → consumes update_event_status task (calls ProphetX API)
    → consumes send_slack_alert task (calls Slack webhook)
    → on ProphetX API failure: retries with exponential backoff (3x)
    → after 3 failures: publishes "send_slack_alert" with CRITICAL severity
```

**Key configuration:**
```python
# celery_app.py
from celery import Celery
from celery.schedules import crontab
from kombu import Queue

app = Celery("prophet_monitor", broker="redis://redis:6379/0", backend="redis://redis:6379/1")

app.conf.task_queues = (
    Queue("poll_queue"),
    Queue("action_queue"),
)

app.conf.beat_schedule = {
    "poll-prophetx": {
        "task": "workers.poll_prophetx.run",
        "schedule": 30.0,  # seconds
        "options": {"queue": "poll_queue"},
    },
    "poll-sports-data": {
        "task": "workers.poll_sports_data.run",
        "schedule": 30.0,
        "options": {"queue": "poll_queue"},
    },
}

# Retry config for action tasks
app.conf.task_acks_late = True  # Only ack after successful execution
app.conf.task_reject_on_worker_lost = True  # Re-queue if worker dies
```

### Pattern 2: Redis as Three-Role Middleware

**What:** Redis serves three distinct roles in this system: (1) Celery task broker — the message queue between Beat and workers; (2) application state cache — current event/market state for fast dashboard reads; (3) pub/sub message bus — workers publish events, FastAPI SSE endpoint subscribes and pushes to browsers.

**When to use:** When you need low-latency reads for a dashboard that is updated by background processes, not user requests.

**Trade-offs:** Single Redis instance is a shared dependency for three concerns. Use separate Redis databases (db=0 broker, db=1 results, db=2 app cache/pubsub) to isolate concerns. For this scale (< 500 events), one instance is fine.

**How it fits:**
```
db=0 : Celery broker (task queues)
db=1 : Celery result backend (task status)
db=2 : App cache (current events/markets state as JSON)
       + pub/sub channels (event_updates, market_updates, notifications)
```

**Pub/sub flow:**
```python
# In action worker (after ProphetX update succeeds):
redis_client.publish("event_updates", json.dumps({
    "event_id": str(event.id),
    "prophetx_status": "live",
    "status_match": True,
    "last_prophetx_poll": datetime.utcnow().isoformat(),
}))

# In FastAPI SSE endpoint:
async def event_stream(request: Request):
    pubsub = redis_client.pubsub()
    pubsub.subscribe("event_updates", "market_updates", "notifications")
    async for message in pubsub.listen():
        if message["type"] == "message":
            yield f"event: event_updated\ndata: {message['data']}\n\n"
        if await request.is_disconnected():
            break
```

### Pattern 3: Event ID Matching Layer

**What:** A dedicated matching service that maintains a mapping table between ProphetX event IDs and SportsDataIO game IDs. The match is established using a fuzzy combination of: sport type, normalized team names, and scheduled start time (within a tolerance window).

**When to use:** Required whenever two external systems refer to the same real-world entity with different identifiers and no shared key exists.

**Trade-offs:** Matching is probabilistic — team name normalization and time-window matching can produce false positives or missed matches. Requires an admin UI for reviewing and correcting matches.

**Design:**

```
Database table: event_id_mappings
┌─────────────────────────────────────────────────────────────────┐
│  id              UUID PK                                         │
│  prophetx_id     string UNIQUE NOT NULL                          │
│  sportsdataio_id string NULLABLE (null = not yet matched)        │
│  sport           string (NFL, NBA, MLB, NHL...)                  │
│  match_confidence enum [HIGH, MEDIUM, LOW, MANUAL]               │
│  match_method    string (auto_time_team / manual_admin)          │
│  verified_by     UUID FK → User (null = auto-matched)            │
│  created_at      timestamp                                       │
│  updated_at      timestamp                                       │
└─────────────────────────────────────────────────────────────────┘

Matching algorithm (event_matcher.py):
1. For each unmatched ProphetX event:
   a. Filter SportsDataIO games by sport
   b. Normalize team names (lowercase, strip punctuation, city aliases)
   c. Find SportsDataIO games with scheduled_start within ±2 hours
   d. Score candidates: team name similarity (fuzzy match) + time proximity
   e. If score > HIGH_CONFIDENCE_THRESHOLD: auto-match (match_confidence=HIGH)
   f. If score > MEDIUM_THRESHOLD: flag for admin review (match_confidence=MEDIUM)
   g. Otherwise: mark as UNMATCHED, alert admin

2. Admin can manually confirm or override any mapping from dashboard
3. Once matched, mapping is cached in Redis (key: prophetx_id) for O(1) lookup
   by poll workers
```

**Implementation approach:**
```python
# services/event_matcher.py
from rapidfuzz import fuzz  # HIGH confidence: fuzz.ratio > 85

TEAM_NAME_ALIASES = {
    "chiefs": ["kansas city chiefs", "kc chiefs"],
    "eagles": ["philadelphia eagles", "philly eagles"],
    # ... expand as needed
}

def normalize_team_name(name: str) -> str:
    name = name.lower().strip()
    # Remove city prefix variations, punctuation
    # Check alias table
    return normalized

def compute_match_score(prophetx_event, sportsdataio_game) -> float:
    home_score = fuzz.ratio(
        normalize_team_name(prophetx_event.home_team),
        normalize_team_name(sportsdataio_game.home_team)
    )
    away_score = fuzz.ratio(
        normalize_team_name(prophetx_event.away_team),
        normalize_team_name(sportsdataio_game.away_team)
    )
    time_delta_minutes = abs(
        (prophetx_event.scheduled_start - sportsdataio_game.date_time).total_seconds() / 60
    )
    time_score = max(0, 100 - time_delta_minutes)  # penalize time difference
    return (home_score + away_score + time_score) / 3
```

### Pattern 4: SSE over WebSockets for Unidirectional Push

**What:** Server-Sent Events (SSE) is a simpler alternative to WebSockets for the specific use case of server-to-client push. The browser opens a long-lived HTTP GET connection; the server pushes text/event-stream formatted messages.

**When to use:** When the dashboard only needs to receive updates from the server (not send data back in real-time). Manual triggers (sync now, acknowledge alert) go through regular REST POST calls — not the SSE connection.

**Trade-offs:** SSE has a browser limit of 6 concurrent connections per domain. Not an issue for an internal ops tool where < 10 users are expected. SSE auto-reconnects natively in browsers. Much simpler to implement and debug than WebSockets.

**FastAPI SSE implementation pattern:**
```python
# api/v1/stream.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse  # sse-starlette package

router = APIRouter()

@router.get("/stream")
async def dashboard_stream(current_user: User = Depends(get_current_user)):
    async def event_generator():
        async with redis_client.pubsub() as pubsub:
            await pubsub.subscribe("event_updates", "market_updates", "notifications")
            async for message in pubsub.listen():
                if message["type"] == "message":
                    channel = message["channel"].decode()
                    data = message["data"].decode()
                    yield {"event": channel, "data": data}

    return EventSourceResponse(event_generator())
```

**React client:**
```typescript
// hooks/useSSE.ts
export function useSSE(url: string) {
  const queryClient = useQueryClient()

  useEffect(() => {
    const es = new EventSource(url, { withCredentials: true })

    es.addEventListener("event_updates", (e) => {
      const updated = JSON.parse(e.data)
      queryClient.setQueryData(["events"], (old) =>
        old?.map(ev => ev.id === updated.event_id ? { ...ev, ...updated } : ev)
      )
    })

    es.addEventListener("market_updates", (e) => { /* similar */ })
    es.addEventListener("notifications", (e) => { /* increment unread count */ })

    es.onerror = () => { /* SSE auto-reconnects, just log */ }
    return () => es.close()
  }, [url])
}
```

---

## Data Flow

### Flow 1: Status Mismatch Detection and Auto-Correction

```
[Celery Beat - 30s tick]
    │
    ├──→ enqueue poll_sports_data to poll_queue
    └──→ enqueue poll_prophetx to poll_queue
                    │
    ┌───────────────▼──────────────────────────────┐
    │  Poll Worker: poll_sports_data               │
    │  1. GET SportsDataIO /GamesByDate/{today}    │
    │  2. For each game: update real_world_status  │
    │     in PostgreSQL + Redis cache (db=2)       │
    └───────────────────────────────────────────────┘
                    │
    ┌───────────────▼──────────────────────────────┐
    │  Poll Worker: poll_prophetx                  │
    │  1. GET ProphetX /events                     │
    │  2. For each event:                          │
    │     a. Update prophetx_status in PostgreSQL  │
    │        + Redis cache                         │
    │     b. Look up SportsDataIO ID from          │
    │        event_id_mappings (Redis O(1) lookup) │
    │     c. Compare prophetx_status vs            │
    │        real_world_status (mismatch_detector) │
    │     d. If MISMATCH → enqueue                 │
    │        update_event_status to action_queue   │
    │     e. Check market liquidity vs thresholds  │
    │     f. If BELOW THRESHOLD → enqueue          │
    │        send_slack_alert to action_queue      │
    └───────────────────────────────────────────────┘
                    │
    ┌───────────────▼──────────────────────────────┐
    │  Action Worker: update_event_status          │
    │  1. PATCH ProphetX /events/{id}              │
    │     with new status                          │
    │  2. On success:                              │
    │     a. Write AuditLog to PostgreSQL          │
    │     b. Publish "event_updates" to Redis ch.  │
    │     c. Enqueue send_slack_alert (success msg)│
    │  3. On failure (retry up to 3x with backoff) │
    │     a. After 3 failures: write AuditLog      │
    │        (result=failure)                      │
    │     b. Enqueue send_slack_alert (CRITICAL)   │
    │     c. Publish "event_updates" with          │
    │        action_failed=true to Redis channel   │
    └───────────────────────────────────────────────┘
                    │
    ┌───────────────▼──────────────────────────────┐
    │  FastAPI SSE Endpoint                        │
    │  - Subscribed to Redis pub/sub channels      │
    │  - Forwards "event_updates" message to all   │
    │    connected browser clients                 │
    └───────────────────────────────────────────────┘
                    │
    ┌───────────────▼──────────────────────────────┐
    │  React Dashboard (browser)                   │
    │  - EventSource receives event_updated event  │
    │  - TanStack Query cache updated in-place     │
    │  - Events table row re-renders:              │
    │    "Resolving..." → green (success)          │
    │    or red "Action Failed" (failure)          │
    └───────────────────────────────────────────────┘
```

### Flow 2: Dashboard Initial Load and Ongoing State

```
[Browser opens Dashboard]
    │
    ├──→ REST GET /api/v1/events         (FastAPI reads from PostgreSQL)
    ├──→ REST GET /api/v1/markets        (FastAPI reads from PostgreSQL)
    ├──→ REST GET /api/v1/notifications  (FastAPI reads from PostgreSQL)
    └──→ GET /api/v1/stream              (opens SSE connection)
              │
              └──→ FastAPI subscribes to Redis pub/sub
                   → forwards all future updates to this browser client

[Subsequent real-time updates arrive via SSE — no polling from browser]
```

### Flow 3: Manual Status Sync (Operator-Triggered)

```
[Operator clicks "Sync Now" in dashboard]
    │
    ├──→ REST POST /api/v1/events/{id}/sync-status
              │
              ├──→ FastAPI validates JWT + Operator role
              ├──→ Calls mismatch_detector service directly
              ├──→ Enqueues update_event_status to action_queue
              └──→ Returns 202 Accepted
                        │
                   [Action Worker runs same flow as auto-correction]
                   → Publishes to Redis pub/sub
                   → Dashboard updates via SSE
```

### Flow 4: Slack Alert Delivery

```
[Any action worker detects alertable condition]
    │
    └──→ Enqueue send_slack_alert task (action_queue)
              │
              ├──→ Rate limit check: has alert been sent for this
              │    entity_id + alert_type in last 60 seconds?
              │    (checked against Redis key with 60s TTL)
              │    YES → skip (dedup prevention)
              │    NO  → proceed
              │
              ├──→ POST Slack webhook URL (from SystemConfig in Redis)
              │    with Block Kit formatted message
              │
              └──→ INSERT Notification record in PostgreSQL
                   └──→ Publish "notifications" to Redis pub/sub
                         → SSE pushes to dashboard
                         → notification bell increments
```

---

## Build Order (Phase Dependencies)

The build order follows strict dependency chains. Each layer must exist before the next can be built.

```
Phase 1: Foundation (must be first — everything depends on this)
├── Docker Compose skeleton (postgres, redis, backend, frontend, celery, nginx)
├── Database schema + Alembic migrations
├── SQLAlchemy models (Event, Market, AuditLog, User, Notification, Config)
├── Pydantic settings (core/config.py — env vars pattern set here)
├── Redis connection helpers (db separation, pub/sub helpers)
├── JWT auth system (FastAPI deps.py)
├── ProphetX API client (clients/prophetx.py — needed by Phase 2 workers)
└── SportsDataIO API client (clients/sportsdataio.py — needed by Phase 2 workers)

Phase 2: Worker Engine (depends on Phase 1 clients + DB)
├── Celery app + Beat schedule (celery_app.py)
├── Event matching layer (event_matcher.py + event_id_mappings table)
│   NOTE: Build this before poll workers — workers need it to match IDs
├── Mismatch detector service (mismatch_detector.py)
├── Liquidity monitor service (liquidity_monitor.py)
├── Poll workers: poll_prophetx + poll_sports_data
├── Action worker: update_event_status (with retry logic)
├── Audit writer service (audit_writer.py)
└── Slack client + send_alerts worker

Phase 3: FastAPI API Layer (depends on Phase 1 DB + Phase 2 for SSE pub/sub)
├── REST endpoints: /events, /markets, /audit-log, /notifications, /config
│   NOTE: These can be built in Phase 1 for auth testing, but full data
│         requires Phase 2 workers to have populated the database
├── SSE /stream endpoint (depends on Redis pub/sub from Phase 2)
└── Manual sync endpoint (POST /events/{id}/sync-status)

Phase 4: React Dashboard (depends on Phase 3 API + Phase 2 SSE stream)
├── Authentication + routing
├── EventsTable component (reads from /events REST + SSE updates)
├── MarketsTable component
├── useSSE hook (depends on /stream endpoint existing)
├── Notification bell + center
└── Admin config panel

Phase 5: Polish + Production (depends on all above)
├── Supplementary data sources (pluggable into poll_sports_data)
├── Alert deduplication / rate limiting
├── Error + empty + loading states in UI
├── Nginx + SSL configuration
└── Production Docker Compose hardening
```

**Critical path:** The event ID matching layer is the highest-risk dependency. It must be built and validated before poll workers produce meaningful comparisons. Plan a verification step after Phase 2 with real ProphetX and SportsDataIO data to confirm the matching algorithm works before building the dashboard on top of it.

---

## Component Boundary Rules

These boundaries prevent architectural decay over time:

| Rule | Rationale |
|------|-----------|
| Workers never import from `api/` | API layer is request-scoped; workers are async background processes. Mixing them causes session and context leaks. |
| API routes never directly call external APIs | All external calls go through `clients/`. API routes call `services/` which call `clients/`. This keeps routes thin and testable. |
| Services have no Celery or FastAPI imports | `services/` is plain Python business logic. This makes it unit-testable without mocking the full framework. |
| Redis pub/sub is the only channel between workers and API | Workers do not call FastAPI endpoints. The API does not import from workers. Communication is exclusively via Redis pub/sub messages. |
| Audit log is append-only | `audit_writer.py` has no UPDATE or DELETE methods. Enforced at the service layer, not just DB constraints. |
| Event matching layer is the single source of truth for ID cross-referencing | No poll worker or service performs its own ad-hoc matching. All lookups go through `event_matcher.py` / the mapping cache. |

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Current target (< 500 events, ~10 users) | Single Docker Compose on one VPS. One Celery Beat process, one poll worker process, one action worker process. Redis and PostgreSQL on same host. |
| 500-2000 events | Separate poll and action workers onto distinct Celery queues (already designed for this). May need to increase polling concurrency (`-c` flag on Celery worker). Add Redis connection pooling. PostgreSQL query optimization (index on scheduled_start, prophetx_status). |
| 2000+ events | Promote Redis and PostgreSQL to managed services (Redis Cloud, RDS). Scale workers horizontally (multiple containers). Celery Beat remains single instance. Consider partitioning poll_prophetx by sport/league. |

### Scaling Priorities

1. **First bottleneck:** Polling throughput. If 30 seconds is not enough to poll 1000+ events within a single task, partition by sport or paginate ProphetX API responses across multiple workers. Detection: poll task duration approaching 30s.
2. **Second bottleneck:** PostgreSQL write contention from concurrent poll workers. Mitigation: batch-write state updates (one INSERT/UPDATE per polling cycle, not per event). Detection: DB write latency increasing.
3. **Third bottleneck:** SSE connection overhead at > 50 concurrent dashboard users. Mitigation: implement a fan-out layer or use Redis Streams instead of pub/sub. Detection: SSE connection drop rate increasing.

---

## Anti-Patterns

### Anti-Pattern 1: Polling from the Browser

**What people do:** Have the React dashboard poll REST endpoints every 5-10 seconds with setInterval or TanStack Query refetchInterval.

**Why it's wrong:** Creates N×polling_interval×concurrent_users requests per minute against the FastAPI server. Masks state changes that happen between polls. Defeats the purpose of SSE. At 10 users polling every 5 seconds = 120 requests/minute of unnecessary load.

**Do this instead:** Use SSE for real-time state push. TanStack Query's `staleTime` should be set high (e.g., 60 seconds) so it only re-fetches on mount or manual invalidation — not on a timer. SSE updates query cache directly via `queryClient.setQueryData`.

### Anti-Pattern 2: Running Celery Beat Inside the FastAPI Process

**What people do:** Start Celery Beat programmatically inside the FastAPI `startup` event handler or as a background thread.

**Why it's wrong:** If the FastAPI container restarts, Beat restarts and loses its schedule state. Beat and FastAPI have different resource profiles and should scale independently. This pattern causes double-scheduling if multiple API replicas are run.

**Do this instead:** Run Celery Beat as its own Docker container with its own restart policy. It is a separate process, separate container, separate concern.

### Anti-Pattern 3: Performing Event Matching On-The-Fly in Every Poll Cycle

**What people do:** For every ProphetX event in every polling cycle, run the fuzzy matching algorithm against the full SportsDataIO game list to find the corresponding game.

**Why it's wrong:** Fuzzy string matching is O(n×m) per cycle. At 500 events × 1000 games × every 30 seconds = significant CPU waste. If matching logic has a bug, it silently mismatches events on every cycle.

**Do this instead:** Run the matching algorithm once when a new event is discovered. Store the result in the `event_id_mappings` table and cache in Redis. Subsequent poll cycles do O(1) Redis key lookup. Re-run matching only when a mapping is marked as UNMATCHED or manually invalidated.

### Anti-Pattern 4: Sending Slack Alerts Synchronously in Poll Workers

**What people do:** Call the Slack webhook directly inside the poll worker task, blocking until the HTTP request completes.

**Why it's wrong:** Slack API latency (or downtime) delays the poll worker, potentially causing it to miss its 30-second cycle. A Slack outage cascades into a polling failure.

**Do this instead:** Poll workers only enqueue a `send_slack_alert` Celery task to the action_queue. The action worker handles the actual HTTP call, with its own retry logic, completely decoupled from the polling cycle.

### Anti-Pattern 5: Storing API Keys in Code or Docker Images

**What people do:** Hard-code ProphetX API keys in `config.py` or bake them into the Docker image via ARG/ENV at build time.

**Why it's wrong:** Keys end up in git history and Docker layer cache. Rotating keys requires rebuilding images.

**Do this instead:** Use a `.env` file (gitignored) passed via `docker compose --env-file`. All secrets accessed via `pydantic-settings` `BaseSettings` from environment variables. Never in source code.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| ProphetX API | REST client class (`clients/prophetx.py`) with Bearer token auth, exponential backoff retry (3x), circuit breaker on sustained failures | Status enum values must be confirmed from ProphetX docs — use string constants, not hard-coded literals |
| SportsDataIO | REST client class per sport (`clients/sportsdataio.py`), API key as query param, pluggable adapter pattern so new sports use same interface | Each sport has a different endpoint path; abstract via `get_games_by_date(sport, date)` interface |
| Slack Webhook | Simple HTTP POST to webhook URL stored in SystemConfig (not env var — configurable at runtime by Admin) | Rate limit to 1 alert per entity per 60 seconds; implement at `send_alerts.py` level using Redis TTL keys |
| Supplementary APIs (The Odds API, ESPN) | Same pluggable adapter interface as SportsDataIO; registered as fallback providers in sport coverage map | Treat as optional; if all supplementary sources fail, mark real_world_status as "unknown", alert team |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Celery Beat → Poll Workers | Redis task queue (db=0) | Beat publishes task messages; workers consume. No direct call. |
| Poll Workers → Action Workers | Redis task queue (db=0) | Workers enqueue action tasks; never call action logic directly. Enables independent scaling. |
| Action Workers → FastAPI clients | Redis pub/sub (db=2) | Workers publish state change events; FastAPI SSE endpoint subscribes. No direct import between these modules. |
| FastAPI → PostgreSQL | SQLAlchemy async session (via `db/session.py`) | Session scoped per request via FastAPI dependency injection. Never share sessions across requests. |
| FastAPI → Redis | Async Redis client (`db/redis.py`) | Shared connection pool. SSE endpoint uses pub/sub subscription pattern (separate connection from cache reads). |
| Workers → PostgreSQL | SQLAlchemy sync session (Celery tasks are sync by default; async tasks require `celery[asyncio]`) | Workers use a separate session factory from the FastAPI app session factory. |

---

## Sources

- PRD.md (ProphetX Market Monitor, v1.0, 2026-02-24) — primary specification
- PROJECT.md (ProphetX Market Monitor project context) — constraints and key decisions
- Celery documentation: periodic tasks, task routing, retry policies (celeryq.dev — HIGH confidence, well-established patterns)
- FastAPI documentation: SSE via `sse-starlette`, dependency injection, async background tasks (fastapi.tiangolo.com — HIGH confidence)
- Redis pub/sub pattern for SSE fan-out: established industry pattern for real-time dashboards (MEDIUM confidence — training data, could not verify with live docs in this session)
- rapidfuzz library for fuzzy string matching: commonly used for entity resolution in Python data pipelines (MEDIUM confidence — training data)

---
*Architecture research for: ProphetX Market Monitor — real-time API monitoring system with background workers*
*Researched: 2026-02-24*
