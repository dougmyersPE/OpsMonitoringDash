"""
AuditLog model — INSERT-only.

INSERT-only. REVOKE at DB level prevents UPDATE/DELETE from app user.
Never call session.delete() on this model.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        server_default=text("now()"),
    )
    action_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        # values: "status_update", "flag_event", "manual_sync", "liquidity_alert"
    )
    actor: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        # "system" or user email
    )
    entity_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        # "event" or "market"
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    before_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
