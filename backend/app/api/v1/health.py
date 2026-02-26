from fastapi import APIRouter
from sqlalchemy import text

from app.db.redis import get_redis_client
from app.db.session import async_engine

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint — pings PostgreSQL and Redis to confirm connectivity."""
    # Verify PostgreSQL
    async with async_engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

    # Verify Redis
    redis = await get_redis_client()
    await redis.ping()

    return {"status": "ok", "postgres": "connected", "redis": "connected"}


@router.get("/health/workers")
async def worker_health():
    """Returns live/dead status for each poll worker based on Redis heartbeat keys.

    Workers write 'worker:heartbeat:{name}' with 90s TTL on each successful run.
    Key absence means worker has not run in the last 90 seconds (dead or stopped).
    """
    redis = await get_redis_client()
    px_alive = await redis.exists("worker:heartbeat:poll_prophetx") == 1
    sdio_alive = await redis.exists("worker:heartbeat:poll_sports_data") == 1
    return {
        "poll_prophetx": px_alive,
        "poll_sports_data": sdio_alive,
    }
