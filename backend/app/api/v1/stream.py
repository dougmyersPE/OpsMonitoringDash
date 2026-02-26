"""
stream.py — Server-Sent Events endpoint for real-time dashboard updates.

Subscribes to Redis pub/sub channel 'prophet:updates'.
Celery workers publish to this channel after any state change.
Browser clients call queryClient.invalidateQueries() on each received event.

Auth: JWT passed as ?token= query param (native EventSource cannot send headers).
"""

import asyncio

import structlog
from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from app.api.deps import verify_token_from_query
from app.db.redis import get_redis_client

log = structlog.get_logger()

router = APIRouter(prefix="/stream", tags=["stream"])


@router.get("")
async def event_stream(
    request: Request,
    _user: dict = Depends(verify_token_from_query),
):
    """
    SSE endpoint: subscribes to Redis pub/sub, streams update events to browser.

    Browser connects with: EventSource('/api/v1/stream?token=<jwt>')
    On each 'update' event: queryClient.invalidateQueries(['events', 'markets', 'notifications'])
    """

    async def generator():
        redis = await get_redis_client()
        pubsub = redis.pubsub()
        await pubsub.subscribe("prophet:updates")
        log.info("sse_client_connected", user=_user.get("sub"))
        try:
            while True:
                if await request.is_disconnected():
                    log.info("sse_client_disconnected", user=_user.get("sub"))
                    break
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message and message.get("data"):
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    yield {"event": "update", "data": data}
                else:
                    await asyncio.sleep(0.1)
        finally:
            await pubsub.unsubscribe("prophet:updates")
            await pubsub.aclose()

    return EventSourceResponse(generator(), ping=20)
