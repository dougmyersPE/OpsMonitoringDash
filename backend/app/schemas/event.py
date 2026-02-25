from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EventResponse(BaseModel):
    id: UUID
    prophetx_event_id: str
    sport: str
    league: str | None
    name: str
    home_team: str | None
    away_team: str | None
    scheduled_start: datetime | None
    prophetx_status: str | None
    real_world_status: str | None
    status_match: bool
    is_flagged: bool
    last_prophetx_poll: datetime | None
    last_real_world_poll: datetime | None
    model_config = ConfigDict(from_attributes=True)


class EventListResponse(BaseModel):
    total: int
    events: list[EventResponse]
