"""Add espn_status column to events

Revision ID: 005
Revises: 004
Create Date: 2026-02-27
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("espn_status", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "espn_status")
