"""Drop sports_api_status column from events table."""

import sqlalchemy as sa
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("events", "sports_api_status")


def downgrade() -> None:
    op.add_column("events", sa.Column("sports_api_status", sa.String(50), nullable=True))
