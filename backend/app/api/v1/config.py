import asyncio
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_async_session
from app.models.config import SystemConfig
from app.schemas.config import ConfigItem, ConfigUpdateRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["config"])

# Interval key -> worker key suffix (for looking up _min and updating RedBeat)
INTERVAL_WORKER_KEYS = {
    "poll_interval_prophetx": "prophetx",
    "poll_interval_sports_data": "sports_data",
    "poll_interval_odds_api": "odds_api",
    "poll_interval_espn": "espn",
    "poll_interval_critical_check": "critical_check",
}


@router.get("", response_model=List[ConfigItem], dependencies=[Depends(require_role())])
async def get_config(session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(SystemConfig))
    items = result.scalars().all()
    return [ConfigItem(key=i.key, value=i.value, description=i.description) for i in items]


async def _validate_interval(key: str, value: str, session: AsyncSession) -> int:
    """Validate a poll interval value: must be a positive integer >= per-worker minimum.

    Returns the parsed integer on success. Raises HTTPException(422) on failure.
    """
    # Parse as positive integer
    try:
        new_seconds = int(value)
        if new_seconds <= 0:
            raise ValueError
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail=f"Poll interval must be a positive integer (seconds), got: '{value}'",
        )

    # Enforce per-worker minimum from DB
    worker_key = INTERVAL_WORKER_KEYS.get(key)
    if worker_key:
        min_key = f"{key}_min"
        result = await session.execute(
            select(SystemConfig).where(SystemConfig.key == min_key)
        )
        min_row = result.scalar_one_or_none()
        if min_row is not None:
            min_seconds = int(min_row.value)
            if new_seconds < min_seconds:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Poll interval for '{key}' must be at least {min_seconds}s "
                        f"(got {new_seconds}s). Minimum enforced to prevent API abuse."
                    ),
                )

    return new_seconds


async def _propagate_to_redbeat(worker_key: str, new_seconds: float) -> None:
    """Propagate an interval change to RedBeat in Redis (async-safe wrapper).

    Uses run_in_executor because RedBeat's save() uses sync Redis client.
    Best-effort: if propagation fails, the DB is still the source of truth
    and the bootstrap will sync on next Beat restart.
    """
    try:
        # Deferred import: avoids importing celery_app at module level in the API process
        # (per STATE.md pending todo about import side effects)
        from app.workers.beat_bootstrap import update_redbeat_entry

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, update_redbeat_entry, worker_key, new_seconds)
    except Exception:
        logger.exception("Failed to propagate interval to RedBeat (will sync on next Beat restart)")


@router.patch("/{key}", response_model=ConfigItem, dependencies=[Depends(require_role())])
async def update_config(
    key: str,
    body: ConfigUpdateRequest,
    session: AsyncSession = Depends(get_async_session),
):
    # --- Source toggle validation ---
    is_source_toggle = key.startswith("source_enabled_")
    if is_source_toggle and body.value.lower() not in ("true", "false"):
        raise HTTPException(status_code=422, detail="Source toggle must be 'true' or 'false'")

    # --- Interval-specific validation ---
    worker_key = INTERVAL_WORKER_KEYS.get(key)
    is_interval_key = worker_key is not None
    is_min_key = key.startswith("poll_interval_") and key.endswith("_min")

    if is_interval_key:
        new_seconds = await _validate_interval(key, body.value, session)
    elif is_min_key:
        # Validate minimum floor values are also positive integers (but no RedBeat propagation)
        await _validate_interval(key, body.value, session)

    # --- DB upsert (existing logic) ---
    result = await session.execute(select(SystemConfig).where(SystemConfig.key == key))
    item = result.scalar_one_or_none()
    if item is None:
        item = SystemConfig(key=key, value=body.value, description=body.description)
        session.add(item)
    else:
        item.value = body.value
        if body.description is not None:
            item.description = body.description
    await session.commit()
    await session.refresh(item)

    # --- Propagate to RedBeat (after DB commit, interval keys only) ---
    if is_interval_key and worker_key:
        await _propagate_to_redbeat(worker_key, float(new_seconds))

    return ConfigItem(key=item.key, value=item.value, description=item.description)
