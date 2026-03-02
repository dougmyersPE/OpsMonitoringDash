"""API Usage endpoint — returns today's API call counts per worker.

Counts come from Redis INCRBY counters incremented each successful poll cycle.
Key format: api_calls:{worker_name}:{YYYY-MM-DD}
Returns 0 (not null) for workers that have not run today.
"""

from datetime import date

from fastapi import APIRouter, Depends

from app.api.deps import require_role
from app.core.constants import RoleEnum
from app.db.redis import get_redis_client

router = APIRouter()

WORKER_NAMES = [
    "poll_prophetx",
    "poll_sports_data",
    "poll_odds_api",
    "poll_sports_api",
    "poll_espn",
]


@router.get("/usage")
async def get_usage(
    _=Depends(require_role(RoleEnum.readonly, RoleEnum.operator, RoleEnum.admin)),
):
    """Return today's API call counts per worker.

    Accessible to all authenticated users (readonly, operator, admin) per
    USAGE-01: 'Operator can see total API calls made per worker per day.'
    """
    today = date.today().isoformat()
    redis = await get_redis_client()
    keys = [f"api_calls:{name}:{today}" for name in WORKER_NAMES]
    values = await redis.mget(*keys)
    return {
        "date": today,
        "calls_today": {
            name: int(val or 0)
            for name, val in zip(WORKER_NAMES, values)
        },
    }
