"""Add status_source and ws_delivered_at columns for WS authority model."""

import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("status_source", sa.String(20), nullable=True))
    op.add_column("events", sa.Column("ws_delivered_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "ws_delivered_at")
    op.drop_column("events", "status_source")
