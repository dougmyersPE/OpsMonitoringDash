from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MarketResponse(BaseModel):
    id: UUID
    prophetx_market_id: str
    event_id: UUID
    event_name: str | None = None
    name: str
    current_liquidity: Decimal
    min_liquidity_threshold: Decimal | None  # None = use global default
    status: str
    last_polled: datetime | None
    model_config = ConfigDict(from_attributes=True)


class MarketConfigUpdate(BaseModel):
    min_liquidity_threshold: Decimal | None = None  # None clears per-market threshold


class MarketListResponse(BaseModel):
    total: int
    markets: list[MarketResponse]
