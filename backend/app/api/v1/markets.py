import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.constants import RoleEnum
from app.db.session import get_async_session
from app.models.event import Event
from app.models.market import Market
from app.schemas.market import MarketConfigUpdate, MarketListResponse, MarketResponse

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get(
    "",
    response_model=MarketListResponse,
    dependencies=[Depends(require_role(RoleEnum.readonly, RoleEnum.operator, RoleEnum.admin))],
)
async def list_markets(session: AsyncSession = Depends(get_async_session)):
    """Return all markets with current liquidity, threshold settings, and event name."""
    total_q = await session.execute(select(func.count()).select_from(Market))
    total = total_q.scalar_one()
    rows_q = await session.execute(
        select(Market, Event.name.label("event_name"))
        .outerjoin(Event, Market.event_id == Event.id)
        .order_by(Event.name.asc(), Market.name.asc())
    )
    markets_out = [
        MarketResponse.model_validate(market).model_copy(update={"event_name": event_name})
        for market, event_name in rows_q.all()
    ]
    return MarketListResponse(total=total, markets=markets_out)


@router.patch(
    "/{market_id}/config",
    response_model=MarketResponse,
    dependencies=[Depends(require_role(RoleEnum.admin))],
)
async def update_market_config(
    market_id: str,
    body: MarketConfigUpdate,
    session: AsyncSession = Depends(get_async_session),
):
    """Update per-market liquidity threshold. Set to null to restore global default fallback."""
    try:
        market_uuid = uuid.UUID(market_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid market ID format")

    market = await session.get(Market, market_uuid)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    market.min_liquidity_threshold = body.min_liquidity_threshold
    await session.commit()
    await session.refresh(market)
    return market
