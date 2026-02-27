"""Replace real_world_status with per-source status columns

Revision ID: 003
Revises: 002
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("odds_api_status", sa.String(50), nullable=True))
    op.add_column("events", sa.Column("api_football_status", sa.String(50), nullable=True))
    op.add_column("events", sa.Column("sdio_status", sa.String(50), nullable=True))
    # Migrate existing real_world_status data to odds_api_status (Odds API was the active source)
    op.execute("UPDATE events SET odds_api_status = real_world_status")
    op.drop_column("events", "real_world_status")


def downgrade() -> None:
    op.add_column("events", sa.Column("real_world_status", sa.String(50), nullable=True))
    op.execute("UPDATE events SET real_world_status = odds_api_status")
    op.drop_column("events", "sdio_status")
    op.drop_column("events", "api_football_status")
    op.drop_column("events", "odds_api_status")
