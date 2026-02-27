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
    """Returns live/dead status for each poll worker based on Redis heartbeat keys."""
    redis = await get_redis_client()
    keys = [
        "worker:heartbeat:poll_prophetx",
        "worker:heartbeat:poll_sports_data",
        "worker:heartbeat:poll_odds_api",
        "worker:heartbeat:poll_sports_api",
        "worker:heartbeat:poll_espn",
    ]
    results = await redis.mget(*keys)
    return {
        "poll_prophetx":    results[0] is not None,
        "poll_sports_data": results[1] is not None,
        "poll_odds_api":    results[2] is not None,
        "poll_sports_api":  results[3] is not None,
        "poll_espn":        results[4] is not None,
    }
