"""Add opticodds_status column to events table."""

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("opticodds_status", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "opticodds_status")
