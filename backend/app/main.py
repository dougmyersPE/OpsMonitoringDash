from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.api.v1 import auth, audit, config, events, health, markets, notifications, probe, stream, usage
from app.db.redis import close_redis_pool, get_redis_client

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", message="Starting Prophet Monitor API")
    # Initialize Redis connection pool on startup
    await get_redis_client()
    yield
    # Clean up Redis connection pool on shutdown
    await close_redis_pool()
    log.info("shutdown", message="Prophet Monitor API shut down")


app = FastAPI(
    title="Prophet Monitor API",
    description="API Monitoring for ProphetX platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(config.router, prefix="/api/v1")
app.include_router(probe.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(markets.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(stream.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(usage.router, prefix="/api/v1")
