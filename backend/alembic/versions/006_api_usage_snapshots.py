"""Create api_usage_snapshots table for daily call count rollup

Revision ID: 006
Revises: 005
Create Date: 2026-03-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_usage_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("worker_name", sa.String(50), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("worker_name", "snapshot_date", name="uq_worker_date"),
    )
    op.create_index("ix_api_usage_snapshots_snapshot_date", "api_usage_snapshots", ["snapshot_date"])


def downgrade() -> None:
    op.drop_index("ix_api_usage_snapshots_snapshot_date", table_name="api_usage_snapshots")
    op.drop_table("api_usage_snapshots")
