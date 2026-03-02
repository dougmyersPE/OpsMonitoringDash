"""ApiUsageSnapshot model — stores daily call counts per worker.

Written by the nightly rollup worker (rollup_api_usage.py) at 02:00 UTC.
Read by the /api/v1/usage endpoint for 7-day history chart data.
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ApiUsageSnapshot(Base):
    __tablename__ = "api_usage_snapshots"
    __table_args__ = (
        UniqueConstraint("worker_name", "snapshot_date", name="uq_worker_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    worker_name: Mapped[str] = mapped_column(String(50), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
