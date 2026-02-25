# Phase 1: Foundation - Research

**Researched:** 2026-02-25
**Domain:** Python/FastAPI project skeleton, PostgreSQL + Alembic async migrations, Redis with memory limits, JWT auth with RBAC, Celery/RedBeat scaffold, ProphetX and SportsDataIO API clients
**Confidence:** HIGH (core patterns verified via official docs and current web sources; two library-level corrections to prior STACK.md research identified and documented)

---

## Summary

Phase 1 builds the structural foundation that every subsequent phase depends on. The goal is a `docker compose up` system where authenticated users can reach a live FastAPI backend backed by PostgreSQL and Redis, external API clients authenticate and log raw responses, and Celery Beat fires a 30-second heartbeat via RedBeat. No monitoring logic is implemented yet — only the skeleton that enables it.

The stack is well-established: FastAPI + SQLAlchemy 2 async + asyncpg + Alembic for the web and DB layer; Celery 5 + celery-redbeat + redis-py 5 for the worker layer; PyJWT + pwdlib for auth (important: prior research recommended deprecated libraries — see corrections below). The main architectural insight for Phase 1 is that **Celery workers must use a sync SQLAlchemy engine**, not the async one used by FastAPI, because Celery does not natively support asyncio. The two engines share the same PostgreSQL database but use different connection patterns.

Two library-level corrections to the existing STACK.md apply to Phase 1: `python-jose` is effectively abandoned (last release 2021, security issues) — FastAPI's own docs now recommend `PyJWT`; and `passlib` does not work on Python 3.13+ — `pwdlib` (supports Argon2 and bcrypt, Python 3.10–3.14) is the modern replacement. Use these corrected libraries from day one; retrofitting auth hashing is painful.

**Primary recommendation:** Build the Docker Compose skeleton first, verify all services start healthy, then layer in migrations → auth → API clients → Celery in that order. Do not write comparison logic; do not design the monitoring schema in detail — Phase 1 only needs the users/config tables. Log every raw ProphetX and SportsDataIO API response verbatim so Phase 2 can build against confirmed enum values.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CORE-01 | System polls ProphetX events and markets every ~30 seconds via Celery Beat workers | RedBeat scheduler config + Celery Beat separate container pattern; stub tasks that only log — no actual polling logic needed in Phase 1 |
| CORE-02 | System polls real-world game statuses from SportsDataIO every ~30 seconds | SportsDataIO API client setup + same 30s Beat schedule; stub task logs that it fired; raw response logging confirms actual endpoint structure |
| AUTH-01 | User logs in with email/password and receives a JWT; session persists across browser refresh | PyJWT + pwdlib (bcrypt) + FastAPI OAuth2PasswordBearer; `users` table in Alembic migration; seed admin user in migration or startup script |
| AUTH-02 | Three roles enforced server-side: Admin, Operator, Read-Only | Role enum in User model; `require_role` FastAPI dependency; server-side check on every protected endpoint — not client-side gating |
| AUTH-03 | Admin can configure system settings via UI (polling interval, Slack URL, global threshold, etc.) | `system_config` table with key/value rows; Admin-only PATCH endpoint; no UI in Phase 1 — just the table + REST endpoint for validation |
</phase_requirements>

---

## Standard Stack

### Core — Phase 1 Scope

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12 | Runtime | 3.12 is production-stable; 3.13 is available but ecosystem compatibility (especially Celery 5.4.x) still maturing as of early 2026 — stay on 3.12 |
| FastAPI | 0.115.x | REST API framework | Async-native, Pydantic v2 integrated, `OAuth2PasswordBearer` built-in — the de facto Python API framework |
| Pydantic v2 | 2.x | Data validation | FastAPI 0.100+ requires Pydantic v2; Rust core, 5–50x faster than v1 |
| pydantic-settings | 2.x | Env var config | `BaseSettings` reads `.env` into typed config; replaces python-dotenv for FastAPI projects |
| Uvicorn | 0.30.x | ASGI server | Standard production ASGI for FastAPI; `--workers` flag behind Gunicorn for multi-process; single process in Docker is fine for Phase 1 |
| SQLAlchemy | 2.x | ORM — async for FastAPI, sync for Celery | Two engine patterns in same project: `create_async_engine` for FastAPI routes; `create_engine` (sync) for Celery tasks |
| asyncpg | 0.29.x | Async PostgreSQL driver | Required for SQLAlchemy async engine (`postgresql+asyncpg://`); pure-async, fastest Python pg driver |
| psycopg2-binary | 2.9.x | Sync PostgreSQL driver | Required for SQLAlchemy sync engine in Celery workers (`postgresql+psycopg2://`); psycopg2-binary for Docker simplicity |
| Alembic | 1.13.x | Database migrations | Standard SQLAlchemy migration tool; init with `-t async` flag for async env.py; `alembic upgrade head` on container startup |
| Redis | 7.x | Broker + cache + pub/sub | All three roles: Celery broker (db=0), Celery results (db=1), app cache/pub/sub (db=2) |
| redis-py | 5.x | Python Redis client | Async (`redis.asyncio`) for FastAPI; sync for Celery; v5 merged aioredis into the main package |
| Celery | 5.4.x | Task queue + periodic scheduler | Industry standard for Python background tasks; 5.4.x required for Python 3.12 support (5.3 has known issues) |
| celery-redbeat | 2.x | Redis-backed Beat scheduler | Stores schedule state in Redis — survives container restarts without losing schedule; prevents duplicate tasks on Beat restart (locked decision from STATE.md) |
| httpx | 0.27.x | Async HTTP client | Async API calls to ProphetX and SportsDataIO; used in clients/ layer; FastAPI TestClient is built on httpx |
| tenacity | 8.x | Retry with exponential backoff | `@retry(wait=wait_exponential(min=1, max=4), stop=stop_after_attempt(3))` for ProphetX client; works with both sync and async |
| **PyJWT** | **2.x** | **JWT creation and verification** | **Replaces python-jose — python-jose has not been updated since 2021 and has security vulnerabilities; FastAPI docs now officially recommend PyJWT** |
| **pwdlib** | **0.2.x+** | **Password hashing** | **Replaces passlib — passlib is unmaintained and breaks on Python 3.13+; pwdlib supports Argon2 and bcrypt, Python 3.10–3.14** |
| structlog | 24.x | Structured JSON logging | JSON logs from FastAPI and Celery; essential for log aggregation; consistent format with timestamps and worker metadata |
| uv | latest | Python dependency management | Replaces pip/poetry; extremely fast resolver; `uv sync --frozen` in Docker; `pyproject.toml` as source of truth |

### Supporting — Phase 1

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Ruff | latest | Python linting + formatting | Replaces Black + isort + flake8; configure in pyproject.toml; run in pre-commit hook |
| pytest | 8.x | Test framework | Phase 1 sets up pytest.ini and conftest.py even if tests are minimal — prevents drift |
| pytest-asyncio | 0.23.x | Async test support | `asyncio_mode = "auto"` in pytest config; required for testing async FastAPI routes |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyJWT | python-jose | python-jose is abandoned; do not use |
| pwdlib | argon2-cffi directly | argon2-cffi alone doesn't handle bcrypt; pwdlib wraps both cleanly |
| celery-redbeat | Default file-based scheduler | Default scheduler loses state on container restart, causes duplicate tasks — use RedBeat from day one per STATE.md decision |
| asyncpg (FastAPI) + psycopg2 (Celery) | psycopg3 for both | psycopg3 supports true async and is actively maintained; viable alternative but adds complexity of one driver for two engine types; defer for now |
| uv | Poetry | Poetry is significantly slower; 2025 consensus has moved to uv |

**Installation:**
```bash
# Backend (using uv)
uv init prophet-monitor-backend
uv add fastapi[standard] uvicorn[standard]
uv add sqlalchemy[asyncio] asyncpg psycopg2-binary alembic
uv add celery[redis] celery-redbeat redis
uv add httpx tenacity pydantic-settings structlog
uv add PyJWT pwdlib[bcrypt]
uv add --dev pytest pytest-asyncio ruff mypy

# OR in pyproject.toml [project].dependencies block, then:
uv sync
```

---

## Architecture Patterns

### Recommended Project Structure

```
prophet-monitor/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── auth.py          # POST /auth/login, /auth/refresh
│   │   │   │   ├── config.py        # GET/PATCH /config (Admin only)
│   │   │   │   └── health.py        # GET /health (no auth)
│   │   │   └── deps.py              # get_current_user, require_role
│   │   ├── workers/
│   │   │   ├── celery_app.py        # Celery app factory + Beat schedule
│   │   │   ├── poll_prophetx.py     # Stub task: log "poll_prophetx fired"
│   │   │   └── poll_sports_data.py  # Stub task: log "poll_sports_data fired"
│   │   ├── clients/
│   │   │   ├── base.py              # Base async httpx client with retry
│   │   │   ├── prophetx.py          # ProphetX REST client
│   │   │   └── sportsdataio.py      # SportsDataIO client
│   │   ├── models/
│   │   │   ├── user.py              # User model (id, email, password_hash, role)
│   │   │   └── config.py            # SystemConfig model (key, value)
│   │   ├── schemas/
│   │   │   ├── auth.py              # LoginRequest, TokenResponse
│   │   │   └── config.py            # ConfigItem schema
│   │   ├── db/
│   │   │   ├── session.py           # Async engine + session factory (FastAPI)
│   │   │   ├── sync_session.py      # Sync engine + session factory (Celery)
│   │   │   └── redis.py             # Redis connection pools (async + sync)
│   │   ├── core/
│   │   │   ├── config.py            # Settings (pydantic-settings BaseSettings)
│   │   │   ├── security.py          # JWT encode/decode (PyJWT), password hash (pwdlib)
│   │   │   └── constants.py         # Role enum, status placeholders
│   │   └── main.py                  # FastAPI app factory + lifespan
│   ├── alembic/
│   │   ├── versions/
│   │   │   └── 001_initial_schema.py   # users + system_config tables
│   │   └── env.py                   # Async env.py (alembic init -t async)
│   ├── tests/
│   │   ├── conftest.py              # Shared fixtures (async session, test client)
│   │   └── test_health.py           # Smoke test: GET /health returns 200
│   ├── Dockerfile
│   └── pyproject.toml
├── docker-compose.yml
├── docker-compose.dev.yml
├── nginx/
│   └── nginx.conf
└── .env.example
```

### Pattern 1: Two SQLAlchemy Engines in One Project

**What:** FastAPI uses an async engine (`create_async_engine` + asyncpg driver) because async routes require non-blocking DB operations. Celery workers use a sync engine (`create_engine` + psycopg2 driver) because Celery does not natively support asyncio — running `asyncio.run()` inside a Celery task creates a new event loop per task invocation, which is incompatible with connection pooling and causes subtle session lifecycle bugs.

**When to use:** Always — this is a foundational architectural constraint, not a choice.

**Example:**
```python
# db/session.py — FastAPI async engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from typing import AsyncGenerator

async_engine = create_async_engine(
    settings.ASYNC_DATABASE_URL,  # postgresql+asyncpg://...
    echo=False,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

# db/sync_session.py — Celery sync engine
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

sync_engine = create_engine(
    settings.SYNC_DATABASE_URL,  # postgresql+psycopg2://...
    pool_pre_ping=True,
    pool_size=5,
)
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)

def get_sync_session() -> Generator[Session, None, None]:
    with SyncSessionLocal() as session:
        yield session
```

### Pattern 2: PyJWT + pwdlib for Auth (Corrected from STACK.md)

**What:** PyJWT encodes/decodes JWT tokens; pwdlib handles password hashing with bcrypt or Argon2. Both are actively maintained and Python 3.12/3.13 compatible.

**Example:**
```python
# core/security.py
import jwt
from datetime import datetime, timedelta, timezone
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

pwd_hasher = PasswordHash([BcryptHasher()])

def hash_password(plain: str) -> str:
    return pwd_hasher.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_hasher.verify(plain, hashed)

def create_access_token(user_id: str, role: str, expires_minutes: int = 60) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

def decode_access_token(token: str) -> dict:
    # Raises jwt.ExpiredSignatureError, jwt.InvalidTokenError on failure
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
```

### Pattern 3: RBAC FastAPI Dependency

**What:** A `require_role` factory creates per-endpoint dependencies that enforce role server-side. Never trust client-side role checks.

**Example:**
```python
# api/deps.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.core.security import decode_access_token
from app.models.user import RoleEnum

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return payload

def require_role(*roles: RoleEnum):
    async def _checker(user: dict = Depends(get_current_user)):
        if user.get("role") not in [r.value for r in roles]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user
    return _checker

# Usage in routes:
@router.patch("/config", dependencies=[Depends(require_role(RoleEnum.admin))])
async def update_config(...): ...
```

### Pattern 4: Celery + RedBeat Configuration

**What:** RedBeat stores Beat schedule state in Redis. Configuration uses lowercase keys in Celery 5 (uppercase is Celery 3 compatibility mode). Stub tasks log only — no actual API calls in Phase 1.

**Example:**
```python
# workers/celery_app.py
from celery import Celery

celery_app = Celery(
    "prophet_monitor",
    broker=settings.CELERY_BROKER_URL,     # redis://redis:6379/0
    backend=settings.CELERY_RESULT_BACKEND, # redis://redis:6379/1
    include=["app.workers.poll_prophetx", "app.workers.poll_sports_data"],
)

celery_app.conf.update(
    # RedBeat scheduler (replaces file-based scheduler)
    beat_scheduler="redbeat.RedBeatScheduler",
    redbeat_redis_url=settings.REDBEAT_REDIS_URL,  # redis://redis:6379/0
    redbeat_lock_timeout=300,  # 5 minutes; prevents duplicate Beat instances

    # Task settings
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,            # Only ack after successful execution
    task_reject_on_worker_lost=True, # Re-queue if worker dies mid-task

    # Memory management
    result_expires=3600,             # 1-hour TTL on task results in Redis
    task_ignore_result=True,         # Polling tasks don't need result storage

    # Beat schedule — 30-second stub tasks
    beat_schedule={
        "poll-prophetx": {
            "task": "app.workers.poll_prophetx.run",
            "schedule": 30.0,
        },
        "poll-sports-data": {
            "task": "app.workers.poll_sports_data.run",
            "schedule": 30.0,
        },
    },
)

# workers/poll_prophetx.py — Phase 1 stub
from app.workers.celery_app import celery_app
import structlog

log = structlog.get_logger()

@celery_app.task(name="app.workers.poll_prophetx.run")
def run():
    log.info("poll_prophetx fired")
    # Phase 2 will add actual ProphetX API calls here
```

### Pattern 5: Docker Compose with Health Checks

**What:** Use `condition: service_healthy` on postgres and redis so the backend and workers wait for actual service readiness, not just container start. Run `alembic upgrade head` as a startup command in the backend container (not a separate migration container in Phase 1).

**Example:**
```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-d", "${POSTGRES_DB}", "-U", "${POSTGRES_USER}"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 10s

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  backend:
    build: ./backend
    command: bash -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  worker:
    build: ./backend
    command: celery -A app.workers.celery_app worker --loglevel=info -Q default
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  beat:
    build: ./backend
    command: celery -A app.workers.celery_app beat --scheduler redbeat.RedBeatScheduler --loglevel=info
    env_file: .env
    depends_on:
      redis:
        condition: service_healthy

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - backend

volumes:
  postgres_data:
```

### Pattern 6: Alembic Async env.py

**What:** Initialize with `alembic init -t async alembic`. The async template uses `async_engine_from_config` and `connection.run_sync` — Alembic does not support native async, so migrations execute synchronously inside an async context.

**Example:**
```python
# alembic/env.py (key additions beyond the generated template)
import asyncio
from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool
from app.core.config import settings
from app.models import Base  # Import all models so metadata is populated

config = context.config
config.set_main_option("sqlalchemy.url", settings.ASYNC_DATABASE_URL)
target_metadata = Base.metadata

async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # NullPool required for migration-time async engine
    )
    async with connectable.connect() as connection:
        await connection.run_sync(
            lambda conn: context.configure(conn, target_metadata=target_metadata)
        )
        await connection.run_sync(lambda conn: context.run_migrations())
    await connectable.dispose()

def run_migrations_online():
    asyncio.run(run_async_migrations())
```

### Pattern 7: ProphetX and SportsDataIO API Client Structure

**What:** Both clients are isolated in `clients/` behind a base class with retry logic. Phase 1 verifies authentication and logs raw responses — no parsing of status enums yet (those values are unconfirmed per STATE.md).

**Example:**
```python
# clients/base.py
import httpx
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
import structlog

log = structlog.get_logger()

class BaseAPIClient:
    def __init__(self, base_url: str, timeout: float = 10.0):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=4),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def _get(self, path: str, **kwargs) -> dict:
        response = await self._client.get(path, **kwargs)
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self._client.aclose()

# clients/prophetx.py
class ProphetXClient(BaseAPIClient):
    def __init__(self, api_key: str):
        super().__init__(base_url="https://api.prophetx.co")  # confirm base URL
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def get_events_raw(self) -> dict:
        """Returns raw API response — Phase 1 logs this verbatim to confirm enum values."""
        raw = await self._get("/events", headers=self._headers)
        log.info("prophetx_events_raw", response_keys=list(raw.keys()))
        return raw

# clients/sportsdataio.py
class SportsDataIOClient(BaseAPIClient):
    def __init__(self, api_key: str):
        super().__init__(base_url="https://api.sportsdata.io/v3")
        self._api_key = api_key

    async def get_games_by_date_raw(self, sport: str, date: str) -> list:
        """SportsDataIO uses Ocp-Apim-Subscription-Key header for auth."""
        raw = await self._get(
            f"/{sport}/scores/json/GamesByDate/{date}",
            headers={"Ocp-Apim-Subscription-Key": self._api_key},
        )
        log.info("sportsdataio_games_raw", sport=sport, date=date, count=len(raw))
        return raw
```

### Anti-Patterns to Avoid

- **Using asyncio.run() in Celery tasks:** Creates a new event loop per task invocation; incompatible with connection pooling; breaks session lifecycle. Use a sync SQLAlchemy engine in Celery workers instead.
- **Using python-jose:** Abandoned, last release 2021, known CVEs. Use PyJWT.
- **Using passlib on Python 3.12 with plans to upgrade to 3.13:** Passlib breaks on 3.13. Use pwdlib from day one.
- **Running Celery Beat inside the FastAPI process:** Causes double-scheduling when multiple API replicas run; Beat and FastAPI have different resource profiles. Run Beat as its own container.
- **Using default file-based Celery Beat scheduler:** State is lost on container restart; causes duplicate tasks. Use RedBeat from day one (locked decision in STATE.md).
- **Setting Redis maxmemory without a policy:** Redis grows unbounded, OOM kills the broker. Always set `--maxmemory 256mb --maxmemory-policy allkeys-lru` in the redis command (locked decision in STATE.md).
- **Writing comparison logic before confirming ProphetX enum values:** STATE.md explicitly notes ProphetX status enum values are unconfirmed. Phase 1 must log raw responses; Phase 2 builds comparison logic.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JWT signing/verification | Custom HMAC logic | PyJWT | Algorithm selection, expiry handling, signature verification have subtle edge cases |
| Password hashing | Custom bcrypt wrapper | pwdlib | Salt generation, work factor, timing-safe comparison are easy to get wrong |
| HTTP retry with backoff | Custom retry loop | tenacity | Handles jitter, exceptions, max attempts, async/sync transparently |
| Celery task scheduling with Redis state | Custom Redis locking for Beat | celery-redbeat | RedBeat handles distributed lock for single Beat instance, state persistence, and overdue task skipping |
| Docker container readiness | Shell sleep loops | Docker `healthcheck` + `depends_on: condition: service_healthy` | Proper readiness signaling without arbitrary sleep waits |
| Environment variable parsing | Manual os.environ.get | pydantic-settings BaseSettings | Type coercion, validation, .env loading, missing-var errors in one place |

**Key insight:** Every item in this table has caused production incidents when hand-rolled. The listed libraries have been battle-tested for exactly these problems.

---

## Common Pitfalls

### Pitfall 1: Mixing Async and Sync SQLAlchemy Engines

**What goes wrong:** Developer creates one `create_async_engine` engine and tries to use it in both FastAPI routes (via `await session.execute(...)`) and Celery tasks (via `asyncio.run(session.execute(...))`). The Celery task runs, but connection pool state becomes corrupt after a few cycles because each `asyncio.run()` creates a new event loop and the pool was created in a different loop.

**Why it happens:** The docs show async SQLAlchemy as the "modern" approach, so developers default to async everywhere — not realizing Celery is a sync runtime.

**How to avoid:** Maintain two engine instances and two session factories from day one. `db/session.py` for FastAPI (async). `db/sync_session.py` for Celery (sync). Both point to the same PostgreSQL database with the same credentials, just different drivers (`asyncpg` vs `psycopg2`).

**Warning signs:** Celery tasks throw `MissingGreenlet` errors; connection pool exhaustion after worker restarts; tasks that pass in development fail intermittently in production with concurrent workers.

### Pitfall 2: Alembic Import Order Causing Missing Tables

**What goes wrong:** `alembic revision --autogenerate` generates an empty migration (no tables detected) even though SQLAlchemy models are defined.

**Why it happens:** `target_metadata` in `alembic/env.py` is set but the model files have not been imported at that point. Python's lazy import means the ORM models are never registered against the `Base.metadata` object.

**How to avoid:** In `alembic/env.py`, explicitly import all model modules after setting `target_metadata`:
```python
from app.models import Base
from app.models.user import User      # noqa: F401 — triggers model registration
from app.models.config import SystemConfig  # noqa: F401
target_metadata = Base.metadata
```
Alternatively, use a central `app/models/__init__.py` that imports all models, and import that in env.py.

**Warning signs:** `alembic revision --autogenerate` generates a migration with empty `upgrade()` and `downgrade()` functions.

### Pitfall 3: Celery Beat Missing REDBEAT_REDIS_URL Causes Silent Fallback

**What goes wrong:** Beat container starts without `redbeat_redis_url` configured. Celery silently falls back to the default file-based scheduler. No error is thrown. The file-based scheduler writes `celerybeat-schedule` to the container filesystem, which is lost on restart — causing duplicate tasks and the exact problem RedBeat was meant to prevent.

**Why it happens:** `redbeat_redis_url` defaults to `broker_url` only if that key is in the Celery config; if it's missing, fallback behavior is silent.

**How to avoid:** Explicitly set `redbeat_redis_url` in the Celery config. Add a startup assertion in `celery_app.py`:
```python
assert celery_app.conf.beat_scheduler == "redbeat.RedBeatScheduler", \
    "Beat scheduler must be RedBeat — check REDBEAT_REDIS_URL config"
```

**Warning signs:** After Beat container restart, audit log shows a burst of poll task executions all at the same timestamp; Beat logs show "celerybeat-schedule" file instead of Redis references.

### Pitfall 4: ProphetX API Base URL and Auth Header Unknown

**What goes wrong:** Phase 1 builds the ProphetX client with assumed base URL and auth header format (e.g., `Bearer {api_key}`). The actual ProphetX Service API may use a different auth scheme (token + secret, or a separate login endpoint to exchange for a session token, or a WebSocket-based API rather than REST).

**Why it happens:** ProphetX documentation is partially published on Medium and Swagger but not widely indexed. The research found evidence of both a REST-style API and a WebSocket-based parlay API.

**How to avoid:** Retrieve ProphetX API documentation from Doug before implementing the client. The client stub in Phase 1 must be tested against the real API to confirm: (1) base URL, (2) auth mechanism, (3) which endpoints exist for event + market reads, (4) raw response structure. Log the full response body verbatim on first successful call.

**Warning signs:** HTTP 401/403 errors from ProphetX client immediately on first test; 404 on all endpoints suggesting wrong base URL; unexpected WebSocket protocol requirement.

### Pitfall 5: SportsDataIO Header vs. Query Param Authentication Ambiguity

**What goes wrong:** SportsDataIO accepts the API key as either the `Ocp-Apim-Subscription-Key` header or as a `key=` query parameter. The query param approach logs the API key in Nginx access logs and web server logs — a security risk.

**How to avoid:** Always use the header `Ocp-Apim-Subscription-Key` for authentication. Never pass API key as a query parameter. This is confirmed from SportsDataIO developer documentation.

**Warning signs:** API key appearing in application logs or Nginx access logs.

### Pitfall 6: Redis Memory Limits Not Applied Correctly

**What goes wrong:** The `--maxmemory` flag is set in the Docker Compose command but the Redis server ignores it because the flag syntax is wrong, or the redis image version overrides it.

**How to avoid:** After `docker compose up`, verify with:
```bash
docker compose exec redis redis-cli CONFIG GET maxmemory
docker compose exec redis redis-cli CONFIG GET maxmemory-policy
```
Expected: `256mb` (or 268435456 bytes) and `allkeys-lru`. If not, the compose config is not being applied correctly.

**Warning signs:** `redis-cli INFO memory` shows no `maxmemory` limit set; Redis memory grows unbounded in long-running development sessions.

---

## Code Examples

### Database Schema — Phase 1 Tables Only

```python
# models/user.py
import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from sqlalchemy import String, Boolean, DateTime, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base

class RoleEnum(str, PyEnum):
    admin = "admin"
    operator = "operator"
    readonly = "readonly"

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum), nullable=False, default=RoleEnum.readonly)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

# models/config.py
class SystemConfig(Base):
    __tablename__ = "system_config"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc))
```

### Health Check Endpoint

```python
# api/v1/health.py
from fastapi import APIRouter
from sqlalchemy import text
from app.db.session import async_engine
from app.db.redis import get_redis_client

router = APIRouter()

@router.get("/health")
async def health_check():
    """Success criteria #1: docker compose up passes basic health check."""
    # Verify PostgreSQL
    async with async_engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    # Verify Redis
    redis = await get_redis_client()
    await redis.ping()
    return {"status": "ok", "postgres": "connected", "redis": "connected"}
```

### Settings Pattern

```python
# core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def SYNC_DATABASE_URL(self) -> str:
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis
    REDIS_URL: str = "redis://redis:6379"
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"
    REDBEAT_REDIS_URL: str = "redis://redis:6379/0"

    # Auth
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # External APIs
    PROPHETX_API_KEY: str
    SPORTSDATAIO_API_KEY: str

settings = Settings()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact for Phase 1 |
|--------------|------------------|--------------|---------------------|
| python-jose for JWT | PyJWT | FastAPI docs updated 2024 | Use PyJWT from day one — do not follow old FastAPI JWT tutorials that use python-jose |
| passlib for password hashing | pwdlib | passlib unmaintained since 2020; breaks on Python 3.13 | Use pwdlib with BcryptHasher; migrating hashed passwords later requires rehashing at login time |
| Default Celery file scheduler | celery-redbeat | Well-established since 2016, critical for containers | Configure RedBeat from the very first docker-compose.yml — no technical debt to carry |
| docker-compose (v1 CLI) | docker compose (v2 plugin) | Docker Compose v2 became default ~2022 | Use `docker compose` not `docker-compose` in all commands and documentation |
| pip / poetry | uv | uv reached 1.0 in 2024 | `uv sync --frozen` in Docker; `uv add` locally; `pyproject.toml` as sole source of truth |
| Alembic sync env.py | Alembic async env.py (-t async) | Alembic 1.9+ | Use `alembic init -t async alembic` — generates the correct async template; do not manually patch a sync env.py |

**Deprecated / outdated:**
- `python-jose`: Last release 2021. Known CVEs. FastAPI removed from official docs. Do not use.
- `passlib`: Last meaningful release 2020. Raises deprecation warnings on Python 3.12. Breaks on 3.13. Do not use for new projects.
- `aioredis`: Merged into `redis-py` v4+. Use `redis.asyncio` from `redis` package. Do not install separately.
- `docker-compose` (hyphenated): Legacy v1 Python CLI. Use `docker compose` (Compose v2 plugin).
- `Create React App`: Deprecated by React team 2023. Use Vite (Phase 3 concern, noted for completeness).

---

## Open Questions

1. **ProphetX API authentication mechanism and base URL**
   - What we know: ProphetX has a Service API with Bearer token auth (from Medium articles); there is also a WebSocket-based Parlay API; OpticOdds aggregates ProphetX data suggesting a REST API exists
   - What's unclear: Exact base URL, whether auth is Bearer token, token+secret pair, or a login-then-session flow; whether the event status read endpoint is REST or WebSocket
   - Recommendation: Doug should provide ProphetX API credentials AND documentation before Phase 1 Plan 01-03 begins. Without confirmed base URL and auth header format, the client cannot be built and tested.

2. **ProphetX status enum values (confirmed unknown from STATE.md)**
   - What we know: STATE.md explicitly flags this as unconfirmed; PRD notes "verify exact values from ProphetX API docs"
   - What's unclear: Whether values are strings ("upcoming", "live", "ended") or something else ("SCHEDULED", "IN_PROGRESS", "CLOSED")
   - Recommendation: Phase 1 Plan 01-03 must call the actual ProphetX API, log raw responses verbatim, and document observed status values. Phase 2 comparison logic MUST NOT be written until this is confirmed.

3. **SportsDataIO subscription coverage**
   - What we know: Authentication uses `Ocp-Apim-Subscription-Key` header; endpoint pattern is `/v3/{sport}/scores/json/GamesByDate/{date}`; status values include Scheduled, InProgress, Final, F/OT, Postponed, Canceled, Suspended
   - What's unclear: Which sports are in Doug's current subscription tier (NFL, NBA, MLB, NHL, NCAAB, etc.); whether the account has access to real-time or only delayed data
   - Recommendation: On first authenticated API call in Phase 1, iterate over each expected sport and log the HTTP status code (200 = covered, 403 = not in subscription). Document coverage before Phase 2 builds polling workers.

4. **Seed data strategy for admin user**
   - What we know: Phase 1 requires a user to log in (AUTH-01); the `users` table will be created by Alembic
   - What's unclear: Whether to seed via Alembic `data_migrations`, a `seed.py` script run at container startup, or a `/api/v1/setup` endpoint (one-time admin creation)
   - Recommendation: Use a `seed.py` startup script that checks if an admin user exists and creates one from environment variables (`ADMIN_EMAIL`, `ADMIN_PASSWORD`). Avoids baking passwords into migration files. Run this script in the backend container startup command before Uvicorn.

---

## Sources

### Primary (HIGH confidence)

- [Alembic async env.py template](https://github.com/sqlalchemy/alembic/blob/main/alembic/templates/async/env.py) — Official template; confirmed `async_engine_from_config` + `connection.run_sync` pattern
- [Setup FastAPI with Async SQLAlchemy 2 + Alembic + PostgreSQL + Docker](https://berkkaraal.com/blog/2024/09/19/setup-fastapi-project-with-async-sqlalchemy-2-alembic-postgresql-and-docker/) — Complete reference implementation including Docker Compose, async session, and env.py; published September 2024
- [celery-redbeat Configuration docs](https://redbeat.readthedocs.io/en/latest/config.html) — Official RedBeat config reference; confirmed `redbeat_redis_url`, `redbeat_lock_timeout`, `redbeat_key_prefix` settings
- [FastAPI JWT documentation PR #11589](https://github.com/fastapi/fastapi/pull/11589) — Official FastAPI migration from python-jose to PyJWT; merged into main docs
- [pwdlib on PyPI](https://pypi.org/project/pwdlib/) — Modern passlib replacement; Python 3.10–3.14 support confirmed
- [SportsDataIO developer authentication](https://sportsdata.io/developers/apis) — Confirmed `Ocp-Apim-Subscription-Key` header authentication
- [Docker Compose health checks guide](https://last9.io/blog/docker-compose-health-checks/) — `condition: service_healthy` pattern confirmed; `start_period` for slow-starting services

### Secondary (MEDIUM confidence)

- [SQLAlchemy asyncio calls from Celery task gist](https://gist.github.com/devraj/6cf8467f0431caa2901330e06fb385de) — Confirms Celery does not natively support asyncio; sync engine recommended; WebSearch verified with multiple SQLAlchemy discussion threads
- [celery-redbeat PyPI page](https://pypi.org/project/celery-redbeat/) — Confirms latest release July 2, 2025; Python 3.8–3.12 support; Celery 5 compatible
- [FastAPI + uv integration guide](https://docs.astral.sh/uv/guides/integration/fastapi/) — Official uv docs for FastAPI; `uv sync --frozen --no-cache` in Docker confirmed
- [httpx async + tenacity pattern](https://medium.com/@benshearlaw/how-to-use-httpx-request-client-with-fastapi-16255a9984a4) — Confirms tenacity works with async httpx; `AsyncRetrying` for async contexts

### Tertiary (LOW confidence — flag for validation)

- ProphetX API base URL and authentication mechanism — Not publicly documented; must be confirmed from Doug's ProphetX credentials/docs before Plan 01-03
- ProphetX event status enum values — Explicitly unconfirmed per STATE.md; Medium article exists but returned 403 during fetch; must be confirmed from live API call

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — PyJWT, pwdlib, FastAPI, SQLAlchemy 2, Alembic async pattern all verified with official/recent sources; two corrections to prior STACK.md confirmed from FastAPI official discussions
- Architecture: HIGH — two-engine pattern (async FastAPI + sync Celery) is the established solution to Celery's lack of asyncio support; verified from multiple sources
- Pitfalls: HIGH for all infrastructure pitfalls (Celery/Redis/Alembic/Docker patterns are well-documented); MEDIUM for ProphetX-specific unknowns (API auth, enum values)
- External APIs: MEDIUM for SportsDataIO (auth method confirmed, coverage requires live validation); LOW for ProphetX (auth mechanism and enum values unconfirmed — must verify before Plan 01-03)

**Research date:** 2026-02-25
**Valid until:** 2026-04-25 (stable stack; 60-day validity; the two library corrections — PyJWT and pwdlib — are now stable recommendations)
