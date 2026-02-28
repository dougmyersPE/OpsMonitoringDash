from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field

from app.monitoring.mismatch_detector import compute_is_critical


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
    odds_api_status: str | None
    sports_api_status: str | None
    sdio_status: str | None
    espn_status: str | None
    status_match: bool
    is_flagged: bool
    last_prophetx_poll: datetime | None
    last_real_world_poll: datetime | None
    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def is_critical(self) -> bool:
        return compute_is_critical(
            self.prophetx_status,
            self.odds_api_status,
            self.sports_api_status,
            self.sdio_status,
            self.espn_status,
        )


class EventListResponse(BaseModel):
    total: int
    events: list[EventResponse]
