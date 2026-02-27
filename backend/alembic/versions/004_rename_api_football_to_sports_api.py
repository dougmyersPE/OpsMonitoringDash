"""Rename api_football_status column to sports_api_status

Revision ID: 004
Revises: 003
Create Date: 2026-02-26
"""
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("events", "api_football_status", new_column_name="sports_api_status")


def downgrade() -> None:
    op.alter_column("events", "sports_api_status", new_column_name="api_football_status")
