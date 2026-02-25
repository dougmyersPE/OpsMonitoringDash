# Stack Research

**Domain:** Real-time operations monitoring dashboard — Python/FastAPI backend, Celery/Redis workers, PostgreSQL, React/TypeScript frontend
**Researched:** 2026-02-24
**Confidence:** MEDIUM (web search unavailable; based on training data through August 2025 + official ecosystem knowledge; flag versions for pin-time verification)

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12 | Runtime | 3.12 is the production-stable release as of late 2024; 3.13 released but ecosystem compatibility still maturing. 3.11+ required for `tomllib`, improved error messages, and performance gains (~25% faster than 3.10). |
| FastAPI | 0.115.x | REST API + SSE backend | Async-native, Pydantic v2 integrated, automatic OpenAPI docs, first-class SSE support via `StreamingResponse`. The de facto Python API framework for async workloads. |
| Pydantic | 2.x | Data validation and serialization | FastAPI 0.100+ requires Pydantic v2. v2 is Rust-core, 5-50x faster than v1 validation. All models use `model_validator`, `field_validator` patterns. |
| Uvicorn | 0.30.x | ASGI server | Standard production ASGI server for FastAPI. Use with `--workers` flag behind Gunicorn in production, or directly in Docker with process-level restart. |
| Celery | 5.4.x | Background task queue and periodic polling | Industry standard for Python periodic tasks. Celery Beat handles the 30-second polling schedule. Supports retry with exponential backoff natively. v5+ requires Python 3.8+ and has proper async support. |
| Redis | 7.x | Celery broker + result backend + SSE pub/sub cache | Single service handles three roles: Celery message broker, task result storage, and fast pub/sub channel for SSE push. Redis 7 adds key expiry notifications and improved performance. |
| PostgreSQL | 16.x | Primary relational database | Audit log, events, markets, users, config, notifications. JSONB columns for `before_state`/`after_state` in audit log. pg16 improves parallel query performance and logical replication. |
| SQLAlchemy | 2.x | ORM + async DB access | SQLAlchemy 2.0 is a major API rewrite — use `async_sessionmaker`, `select()` syntax (not legacy `Query`). Async engine with `asyncpg` driver is required for non-blocking DB access in FastAPI routes. |
| Alembic | 1.13.x | Database migrations | Standard SQLAlchemy migration tool. Works with async engines when using `run_sync` in migration env. All schema changes go through Alembic — never manual DDL in production. |
| asyncpg | 0.29.x | Async PostgreSQL driver | Required for SQLAlchemy async engine. Pure-async, fastest Python PostgreSQL driver. Do NOT use `psycopg2` with async SQLAlchemy — it blocks the event loop. |
| React | 18.x | Frontend UI framework | React 18 brings concurrent rendering, `useTransition`, `Suspense` for async states — all relevant for a real-time dashboard. Stable, mature ecosystem. React 19 released late 2024 but wait for TanStack Query and shadcn to fully support it. |
| TypeScript | 5.x | Frontend type safety | Required for maintainability. v5 adds `const` type parameters and improved inference. Use strict mode. |
| Vite | 5.x | Frontend build tool | Replaces Create React App (deprecated). Extremely fast HMR, native ESM. Standard choice for React apps in 2025. |
| TanStack Query | 5.x | Server state management + data fetching | Replaces manual `useEffect` + `fetch` patterns. Handles caching, background refetching, stale-while-revalidate. v5 (`@tanstack/react-query`) dropped `useQuery` legacy API in favor of object config. Essential for the dashboard's REST data layer. |
| Tailwind CSS | 3.x | Utility-first CSS | Industry standard for rapid dashboard UI development. v3 is stable with JIT compiler. Avoid v4 (alpha/early beta as of 2025) — ecosystem tooling not ready. |
| shadcn/ui | latest | Component library | NOT an npm package — it's a copy-into-project component system built on Radix UI + Tailwind. Gives Tables, Dialogs, Badges, Notification patterns, and more with zero runtime overhead. Perfect for this dashboard. |

---

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-jose | 3.3.x | JWT creation and verification | For issuing and validating JWT tokens in FastAPI auth middleware. Use `python-jose[cryptography]` for RS256/HS256 support. |
| passlib | 1.7.x | Password hashing | bcrypt hashing for user passwords. Use `passlib[bcrypt]`. Always hash with work factor 12+. |
| httpx | 0.27.x | Async HTTP client | Replaces `requests` for async API calls to ProphetX and SportsDataIO. FastAPI's `TestClient` is built on httpx. Supports retries via `httpx-retries` or custom transport. |
| tenacity | 8.x | Retry logic with backoff | Declarative retry decorator for ProphetX API calls. `@retry(wait=wait_exponential(min=1, max=4), stop=stop_after_attempt(3))`. Far cleaner than hand-rolling backoff loops. |
| redis-py | 5.x | Python Redis client | Async-compatible (`redis.asyncio`). Used for SSE pub/sub in FastAPI and for cache reads/writes from workers. v5 consolidates `aioredis` into the main package. |
| celery-redbeat | 2.x | Redis-backed Celery Beat scheduler | Replaces the default file-based Celery Beat scheduler with Redis storage. Required when running multiple Beat instances or Docker containers — prevents duplicate task scheduling. |
| pydantic-settings | 2.x | Environment variable config | Reads `.env` files and environment variables into typed Pydantic settings models. Replaces `python-dotenv` for FastAPI apps. Use `BaseSettings` subclass for all config. |
| structlog | 24.x | Structured JSON logging | JSON logs from both FastAPI and Celery workers. Essential for log aggregation in production. Provides consistent log format with timestamps, request IDs, and worker metadata. |
| sentry-sdk | 2.x | Error tracking and alerting | Free tier captures unhandled exceptions from FastAPI and Celery. Integrate with `sentry_sdk.init()` in both app and worker entrypoints. |
| pytest | 8.x | Testing framework | Standard Python test runner. |
| pytest-asyncio | 0.23.x | Async test support | Required for testing async FastAPI routes and SQLAlchemy sessions. Set `asyncio_mode = "auto"` in pytest config. |
| pytest-mock | 3.x | Mocking in tests | For mocking ProphetX/SportsDataIO HTTP calls and Celery tasks in unit tests. |
| factory-boy | 3.x | Test data factories | For generating realistic test fixtures for Events, Markets, Users. Reduces test setup boilerplate. |
| React Router | 6.x | Client-side routing | For `/dashboard`, `/audit-log`, `/settings`, `/admin` routes. v6 uses `createBrowserRouter` API. |
| date-fns | 3.x | Date formatting | Lightweight, tree-shakable date utilities. Use for "Last updated 30s ago" counters. Do NOT use moment.js (deprecated). |
| zod | 3.x | Frontend schema validation | Validates API responses and form inputs. Pair with `react-hook-form` for admin config forms. |
| react-hook-form | 7.x | Form state management | For threshold config forms, user management forms. Integrates with zod via `@hookform/resolvers`. |

---

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| Docker + Docker Compose | Container orchestration for all services | Use Compose v2 syntax (`docker compose`, not `docker-compose`). Separate `docker-compose.yml` for dev vs `docker-compose.prod.yml` for production overrides. |
| uv | Python dependency management | Replaces pip/poetry/pyenv. Extremely fast resolver and installer. Use `uv sync` instead of `pip install -r requirements.txt`. Write `pyproject.toml` as source of truth. |
| Ruff | Python linting + formatting | Replaces Black + isort + flake8 with a single tool. 100x faster. Configure in `pyproject.toml`. |
| mypy | Python type checking | Run in CI. Catches type errors before runtime. Configure `strict = true` for new projects. |
| ESLint | TypeScript/React linting | Use `@typescript-eslint/eslint-plugin`. Extend with `plugin:react-hooks/recommended` to catch stale closure bugs in SSE hooks. |
| Nginx | Reverse proxy + SSL termination | Serves the React build at `/`, proxies `/api/` to FastAPI, proxies `/stream` (SSE) with buffering disabled. Critical SSE config: `proxy_buffering off; proxy_cache off; X-Accel-Buffering: no`. |
| Certbot | SSL certificate management | Let's Encrypt automation for Nginx. Free. Run as a Docker sidecar with auto-renewal cron. |
| pgAdmin / TablePlus | Database inspection | For development debugging of PostgreSQL. Not in production Docker Compose. |
| Flower | Celery task monitoring | Web UI for inspecting Celery task queues, results, and worker status. Run as optional Docker service. |

---

## Installation

```bash
# Python backend (using uv)
uv init prophex-monitor
cd prophex-monitor
uv add fastapi uvicorn[standard] celery[redis] redis sqlalchemy[asyncio] asyncpg alembic
uv add pydantic-settings python-jose[cryptography] passlib[bcrypt] httpx tenacity
uv add celery-redbeat structlog sentry-sdk pydantic
uv add --dev pytest pytest-asyncio pytest-mock factory-boy ruff mypy

# Frontend (using Vite)
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install @tanstack/react-query react-router-dom
npm install tailwindcss @tailwindcss/forms postcss autoprefixer
npm install date-fns zod react-hook-form @hookform/resolvers
npm install -D typescript @typescript-eslint/eslint-plugin eslint

# shadcn/ui (copy-into-project — run after Tailwind is configured)
npx shadcn@latest init
npx shadcn@latest add table badge button dialog sheet card skeleton
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Celery + Redis | APScheduler (in-process) | Only if you have a single worker process with no horizontal scaling needs. APScheduler is simpler but loses distributed scheduling, retry queues, and worker monitoring. For this project's reliability requirements, Celery wins. |
| Celery + Redis | ARQ (async task queue) | ARQ is a pure-async alternative to Celery built on asyncio. Simpler, less overhead, but smaller ecosystem and no Celery Beat equivalent. Use if you want to go fully async without Celery's hybrid model. Viable alternative if Celery complexity feels heavy. |
| SQLAlchemy 2 async | Tortoise ORM | Tortoise is async-first and simpler. But SQLAlchemy 2 is the standard for complex schemas with audit logs, and Alembic integration is more mature. |
| asyncpg (via SQLAlchemy) | psycopg3 | psycopg3 supports true async and is more actively maintained as of 2025. Works with SQLAlchemy 2. Viable alternative, especially for more direct SQL control. |
| TanStack Query v5 | SWR (Vercel) | SWR is simpler and lighter. Use SWR for small apps with basic fetch-and-display needs. TanStack Query v5 wins for this dashboard due to its mutation support, optimistic updates, and background refetch behavior needed for real-time operational data. |
| Vite | Next.js | Next.js adds SSR/SSG complexity that this internal tool does not need. It also complicates SSE streaming in client components. Vite SPA is the right tool here. |
| shadcn/ui | Chakra UI / MUI | shadcn/ui has zero runtime overhead and full styling control. Chakra and MUI add bundle weight and opinionated theming that fights with Tailwind. For a dashboard built from scratch on Tailwind, shadcn/ui is strictly better. |
| python-jose | PyJWT | Both work. python-jose supports JWK sets and more algorithms. PyJWT is more minimal. Either is fine; python-jose used here for flexibility. |
| tenacity | httpx-retries | httpx-retries is transport-level and works well for HTTP retries. tenacity is more general and can also retry ProphetX SDK calls or DB writes. Tenacity chosen for consistency across all retry scenarios. |
| uv | Poetry | Poetry is well-established but significantly slower. uv is a drop-in replacement with far superior performance and lockfile support. 2025 consensus is moving to uv. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| WebSockets (for dashboard) | Bidirectional protocol adds server state management complexity — you need to track connections, handle reconnects, and fan out messages. SSE is unidirectional (server → browser) which is all the dashboard needs. SSE reconnects automatically with `EventSource`. | Server-Sent Events (SSE) via FastAPI `StreamingResponse` + Redis pub/sub |
| Django / Django REST Framework | DRF is synchronous at its core (async support is bolted-on). Celery workers would be fine, but FastAPI's native async performance and Pydantic v2 integration is superior for a polling-heavy, real-time API. | FastAPI |
| Flask / Flask-RESTful | No native async support. Would require `asgiref` wrappers or `Quart` to handle concurrent polling. | FastAPI |
| SQLite | Not suitable for concurrent writes from multiple Celery workers. Write contention will cause errors under load. | PostgreSQL |
| psycopg2 | Synchronous PostgreSQL driver. Using it with SQLAlchemy async engine blocks the event loop and defeats the purpose of async FastAPI. | asyncpg (via SQLAlchemy `create_async_engine`) |
| Celery + RabbitMQ | RabbitMQ adds operational complexity (separate service, separate monitoring) when Redis already handles the broker role. For this scale (< 500 events, ~30s polling), Redis as broker is entirely sufficient. | Redis as Celery broker |
| moment.js | Deprecated, massive bundle size (67KB). | date-fns (tree-shakable, ~13KB for commonly used functions) |
| axios | Heavier than `fetch` for modern browsers; TanStack Query v5 works best with native `fetch`. Axios still fine but adds an extra dependency. | Native `fetch` or `ky` if a wrapper is desired |
| Create React App | Deprecated by the React team in 2023. No longer maintained. | Vite |
| Redux / Redux Toolkit | Overkill for this dashboard. Server state (API data) belongs in TanStack Query; UI state (notification panel open/closed) belongs in `useState`. RTK adds bundle weight and cognitive overhead without benefit. | TanStack Query (server state) + React `useState`/`useContext` (UI state) |
| Pydantic v1 | FastAPI 0.100+ migrated to Pydantic v2. Mixing v1 models causes deprecation warnings and eventual breakage. All models must use v2 syntax. | Pydantic v2 |

---

## Stack Patterns by Variant

**For SSE streaming in FastAPI:**
- Use `StreamingResponse` with `media_type="text/event-stream"`
- Subscribe to a Redis pub/sub channel per user or per room
- Set response headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`
- FastAPI route must be `async def` with `yield`-based generator
- Client uses native `EventSource` API (no library needed)

**For Celery Beat periodic polling:**
- Use `celery-redbeat` instead of file-based scheduler (prevents duplicate tasks across restarts)
- Define tasks with `@app.task(bind=True, max_retries=3, default_retry_delay=60)`
- Use `countdown` and `exponential_backoff` on `self.retry()` for ProphetX API failures
- Separate task queues: `polling` (high priority, time-sensitive) and `actions` (ProphetX writes)

**For async SQLAlchemy with FastAPI:**
- Use `AsyncSession` with dependency injection via `Depends(get_async_session)`
- Always use `async with session.begin()` context manager for transaction boundaries
- Run Alembic migrations synchronously using `run_sync` in `env.py` — Alembic doesn't support async natively
- Use `selectinload` / `joinedload` for eager loading relationships — do NOT use lazy loading in async context (will raise `MissingGreenlet` error)

**For JWT auth in FastAPI:**
- Issue JWT with `exp` (expiration), `sub` (user_id), `role` claim
- Use `OAuth2PasswordBearer` scheme for Swagger UI integration
- Create a `get_current_user` dependency that decodes JWT and loads user from DB
- For the SSE endpoint, pass JWT as a query parameter (`?token=...`) because `EventSource` cannot set custom headers

**For Docker Compose production layout:**
- Services: `postgres`, `redis`, `backend` (FastAPI+Uvicorn), `worker` (Celery worker), `beat` (Celery Beat with redbeat), `frontend` (Nginx serving React build)
- Backend and worker share the same Docker image — different `command` entrypoints
- Use `depends_on` with `condition: service_healthy` for postgres and redis health checks
- Use named volumes for PostgreSQL data persistence
- Never commit `.env` — use `.env.example` as template

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| FastAPI 0.115.x | Pydantic 2.x | FastAPI 0.100+ dropped Pydantic v1 support. Do not mix. |
| SQLAlchemy 2.x | asyncpg 0.29.x | Requires `create_async_engine("postgresql+asyncpg://...")` URL scheme. |
| SQLAlchemy 2.x | Alembic 1.13.x | Alembic 1.8+ added async migration support via `run_sync`. Use `asyncio` run mode in `env.py`. |
| Celery 5.4.x | Redis 7.x (via redis-py 5.x) | redis-py 5.x merged `aioredis` — use `redis.asyncio` for async access. Celery 5 requires `redis-py >= 4.0`. |
| celery-redbeat 2.x | Celery 5.x | celery-redbeat 2.x is Celery 5 compatible. v1.x is Celery 4 only. |
| React 18.x | TanStack Query 5.x | TanStack Query v5 dropped React 16/17 support. React 18 required. |
| TanStack Query 5.x | React Router 6.x | No conflicts. Both are independent. |
| shadcn/ui (latest) | Tailwind CSS 3.x | shadcn/ui components are Tailwind 3 classes. Tailwind 4 alpha uses different syntax — avoid until shadcn updates. |
| Python 3.12 | Celery 5.4.x | Celery 5.4+ added Python 3.12 support. Celery 5.3 has known issues on 3.12. Pin to 5.4.x minimum. |

---

## SSE Implementation Pattern

This is the most technically nuanced part of the stack. Full pattern:

**Backend (FastAPI):**
```python
# Redis pub/sub channel per dashboard "room" (or global for this tool)
async def event_stream(token: str, redis: Redis):
    pubsub = redis.pubsub()
    await pubsub.subscribe("dashboard:updates")
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                yield f"data: {message['data']}\n\n"
    finally:
        await pubsub.unsubscribe("dashboard:updates")

@router.get("/api/v1/stream")
async def stream_endpoint(token: str = Query(...)):
    user = verify_jwt_token(token)  # JWT via query param
    return StreamingResponse(
        event_stream(token, redis_client),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )
```

**Celery Worker (publishes events):**
```python
# After updating an event status
await redis_client.publish("dashboard:updates", json.dumps({
    "type": "event_updated",
    "event_id": str(event.id),
    "prophetx_status": event.prophetx_status,
    "real_world_status": event.real_world_status,
}))
```

**Frontend (React):**
```typescript
// Use native EventSource — no library needed
// TanStack Query handles REST data; SSE provides invalidation triggers

useEffect(() => {
    const token = getAuthToken();
    const source = new EventSource(`/api/v1/stream?token=${token}`);

    source.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "event_updated") {
            queryClient.invalidateQueries({ queryKey: ["events"] });
        }
    };

    source.onerror = () => source.close(); // auto-reconnects
    return () => source.close();
}, []);
```

The pattern: SSE triggers TanStack Query cache invalidation, which causes a re-fetch from the REST endpoint. This avoids the complexity of patching local state from SSE payloads while still providing near-real-time updates.

---

## Sources

- Training data through August 2025 — FastAPI, Celery, SQLAlchemy, React ecosystem (HIGH confidence for established patterns; MEDIUM for specific version numbers)
- FastAPI official docs architecture patterns — HIGH confidence
- SQLAlchemy 2.0 async documentation patterns — HIGH confidence
- Celery 5 documentation patterns — HIGH confidence
- celery-redbeat GitHub — MEDIUM confidence (version compatibility with Celery 5.4)
- shadcn/ui documentation — HIGH confidence for Tailwind 3 compatibility
- TanStack Query v5 migration guide — HIGH confidence (React 18 requirement)
- NOTE: Version numbers could not be live-verified (web fetch unavailable). Recommend running `pip index versions fastapi celery sqlalchemy` and checking npm to confirm pinned versions before creating lockfiles.

---

*Stack research for: ProphetX Market Monitor — real-time operations dashboard*
*Researched: 2026-02-24*
