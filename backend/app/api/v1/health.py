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
