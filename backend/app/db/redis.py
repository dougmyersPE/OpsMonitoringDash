import redis.asyncio as aioredis
import redis as sync_redis

from app.core.config import settings

# Async Redis pool for FastAPI
_async_redis_pool: aioredis.Redis | None = None


async def get_redis_client() -> aioredis.Redis:
    global _async_redis_pool
    if _async_redis_pool is None:
        _async_redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
    return _async_redis_pool


async def close_redis_pool() -> None:
    global _async_redis_pool
    if _async_redis_pool is not None:
        await _async_redis_pool.aclose()
        _async_redis_pool = None


# Sync Redis client for Celery tasks
def get_sync_redis() -> sync_redis.Redis:
    return sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
