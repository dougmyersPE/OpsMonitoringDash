import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    prophetx_event_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    sport: Mapped[str] = mapped_column(String(50), nullable=False)
    league: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    home_team: Mapped[str | None] = mapped_column(String(255), nullable=True)
    away_team: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scheduled_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # UNCONFIRMED — must be validated against live API in 02-02
    prophetx_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    odds_api_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sports_api_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sdio_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    espn_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status_match: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_prophetx_poll: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_real_world_poll: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
