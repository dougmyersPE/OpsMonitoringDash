"""API Usage endpoint — serves call volume, quota, history, intervals, and projections.

Reads from:
- Redis: today's call counters (api_calls:{worker}:{today})
- Redis: provider quota keys (api_quota:{provider}:*)
- PostgreSQL: api_usage_snapshots (7-day history)
- PostgreSQL: system_config (poll intervals + minimums + quota limits)
"""
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.redis import get_redis_client
from app.db.session import get_async_session
from app.models.api_usage_snapshot import ApiUsageSnapshot
from app.models.config import SystemConfig

router = APIRouter()

WORKER_NAMES = [
    "poll_prophetx",
    "poll_sports_data",
    "poll_odds_api",
    "poll_sports_api",
    "poll_espn",
]

# Sports API sport families that have separate quotas
SPORTS_API_FAMILIES = ["basketball", "hockey", "baseball", "american-football", "soccer"]

# Seconds in a 30-day month (for projection calculation)
SECONDS_PER_MONTH = 30 * 24 * 3600

# Interval config key -> worker name mapping
INTERVAL_KEYS = {
    "poll_prophetx": ("poll_interval_prophetx", "poll_interval_prophetx_min"),
    "poll_sports_data": ("poll_interval_sports_data", "poll_interval_sports_data_min"),
    "poll_odds_api": ("poll_interval_odds_api", "poll_interval_odds_api_min"),
    "poll_sports_api": ("poll_interval_sports_api", "poll_interval_sports_api_min"),
    "poll_espn": ("poll_interval_espn", "poll_interval_espn_min"),
    "poll_critical_check": ("poll_interval_critical_check", "poll_interval_critical_check_min"),
}


@router.get("/usage")
async def get_usage(
    session: AsyncSession = Depends(get_async_session),
    _=Depends(require_role()),
):
    """Return comprehensive API usage data: calls today, 7-day history,
    provider quota, poll intervals, and projected monthly usage.

    Accessible to all authenticated users (readonly, operator, admin).
    """
    redis = await get_redis_client()
    today = date.today()
    today_str = today.isoformat()

    # --- 1. Today's call counts from Redis ---
    today_keys = [f"api_calls:{name}:{today_str}" for name in WORKER_NAMES]
    today_vals = await redis.mget(*today_keys)
    calls_today: dict[str, int] = {
        name: int(val or 0)
        for name, val in zip(WORKER_NAMES, today_vals)
    }

    # --- 2. 7-day history from DB ---
    seven_days_ago = today - timedelta(days=7)
    result = await session.execute(
        select(ApiUsageSnapshot)
        .where(ApiUsageSnapshot.snapshot_date >= seven_days_ago)
        .where(ApiUsageSnapshot.snapshot_date < today)
        .order_by(ApiUsageSnapshot.snapshot_date)
    )
    snapshots = result.scalars().all()

    # Build history: list of {date, worker1: count, worker2: count, ...}
    history_map: dict[str, dict[str, Any]] = {}
    for snap in snapshots:
        d = snap.snapshot_date.isoformat()
        if d not in history_map:
            history_map[d] = {"date": d}
            for w in WORKER_NAMES:
                history_map[d][w] = 0
        history_map[d][snap.worker_name] = snap.call_count

    history: list[dict[str, Any]] = list(history_map.values())
    # Append today's live counts as the last entry
    today_entry: dict[str, Any] = {"date": today_str}
    today_entry.update(calls_today)
    history.append(today_entry)

    # --- 3. Quota data from Redis ---
    # Odds API quota
    odds_keys = [
        "api_quota:odds_api:remaining",
        "api_quota:odds_api:used",
        "api_quota:odds_api:updated_at",
    ]
    odds_vals = await redis.mget(*odds_keys)
    odds_quota: dict[str, Any] = {
        "remaining": int(odds_vals[0]) if odds_vals[0] else None,
        "used": int(odds_vals[1]) if odds_vals[1] else None,
        "limit": None,  # filled from system_config below if configured
        "updated_at": odds_vals[2],
    }

    # Sports API quota (per sport family)
    sports_api_quota: dict[str, Any] = {}
    for sport in SPORTS_API_FAMILIES:
        keys = [
            f"api_quota:sports_api:{sport}:remaining",
            f"api_quota:sports_api:{sport}:limit",
            f"api_quota:sports_api:{sport}:updated_at",
        ]
        vals = await redis.mget(*keys)
        sports_api_quota[sport] = {
            "remaining": int(vals[0]) if vals[0] else None,
            "limit": int(vals[1]) if vals[1] else None,
            "updated_at": vals[2],
        }

    # --- 4. Intervals + minimums + quota limits from system_config ---
    config_result = await session.execute(select(SystemConfig))
    config_rows = config_result.scalars().all()
    config_map = {row.key: row.value for row in config_rows}

    intervals: dict[str, dict[str, int]] = {}
    for worker, (interval_key, min_key) in INTERVAL_KEYS.items():
        current = int(config_map.get(interval_key, "600"))
        minimum = int(config_map.get(min_key, "30"))
        intervals[worker] = {"current": current, "minimum": minimum}

    # Fill Odds API limit from system_config if configured
    odds_limit_str = config_map.get("quota_limit_odds_api")
    if odds_limit_str:
        odds_quota["limit"] = int(odds_limit_str)

    # --- 5. Projections (computed at read time from intervals) ---
    projections: dict[str, Any] = {"per_worker": {}, "monthly_total": 0}
    for worker in WORKER_NAMES:
        interval_info = INTERVAL_KEYS.get(worker)
        if interval_info:
            interval_key = interval_info[0]
            current_interval = int(config_map.get(interval_key, "600"))
        else:
            current_interval = 600
        monthly = SECONDS_PER_MONTH // current_interval if current_interval > 0 else 0
        projections["per_worker"][worker] = monthly
        projections["monthly_total"] += monthly

    # --- 6. Source enabled toggles ---
    source_toggle_keys = ["odds_api", "sports_api", "sports_data", "espn"]
    sources_enabled: dict[str, bool] = {}
    for src in source_toggle_keys:
        val = config_map.get(f"source_enabled_{src}", "true")
        sources_enabled[src] = val.lower() != "false"

    return {
        "date": today_str,
        "calls_today": calls_today,
        "history": history,
        "quota": {
            "odds_api": odds_quota,
            "sports_api": sports_api_quota,
        },
        "intervals": intervals,
        "projections": projections,
        "sources_enabled": sources_enabled,
    }
