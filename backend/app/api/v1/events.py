import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.constants import RoleEnum
from app.db.session import get_async_session
from app.models.event import Event
from app.schemas.event import EventListResponse
from app.workers.update_event_status import run as update_status_task
from app.workers.poll_prophetx import run as poll_prophetx_task
from app.workers.poll_sports_data import run as poll_sports_data_task
from app.workers.poll_odds_api import run as poll_odds_api_task
from app.workers.poll_sports_api import run as poll_sports_api_task
from app.workers.poll_espn import run as poll_espn_task

router = APIRouter(prefix="/events", tags=["events"])


@router.get(
    "",
    response_model=EventListResponse,
    dependencies=[Depends(require_role(RoleEnum.readonly, RoleEnum.operator, RoleEnum.admin))],
)
async def list_events(session: AsyncSession = Depends(get_async_session)):
    """Return all events with prophetx_status, real_world_status, status_match, and is_flagged.

    Ended events are hidden after 24 hours.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    visible = or_(
        Event.prophetx_status != "ended",
        Event.last_prophetx_poll >= cutoff,
    )
    total_q = await session.execute(select(func.count()).select_from(Event).where(visible))
    total = total_q.scalar_one()
    rows_q = await session.execute(select(Event).where(visible).order_by(Event.scheduled_start.asc()))
    events = rows_q.scalars().all()
    return EventListResponse(total=total, events=events)


@router.post(
    "/refresh-all",
    dependencies=[Depends(require_role(RoleEnum.operator, RoleEnum.admin))],
)
async def refresh_all():
    """Enqueue all poll workers to run immediately."""
    poll_prophetx_task.delay()
    poll_sports_data_task.delay()
    poll_odds_api_task.delay()
    poll_sports_api_task.delay()
    poll_espn_task.delay()
    return {"queued": True}


@router.post(
    "/{event_id}/sync-status",
    dependencies=[Depends(require_role(RoleEnum.operator, RoleEnum.admin))],
)
async def manual_sync_status(
    event_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Manually trigger status sync. Enqueues same worker as auto-sync.

    Actor is set to the requesting user's email (sub claim from JWT).
    """
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event ID format")

    event = await session.get(Event, event_uuid)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    update_status_task.delay(
        event_id=event_id,
        target_status=None,         # derive from real_world_status in worker
        actor=current_user["sub"],  # user email as actor
    )
    return {"queued": True, "event_id": event_id}
