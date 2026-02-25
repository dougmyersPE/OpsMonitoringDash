"""Monitoring schema: events, markets, event_id_mappings, audit_log, notifications tables

Revision ID: 002
Revises: 001
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create events table
    op.create_table(
        "events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("prophetx_event_id", sa.String(255), nullable=False),
        sa.Column("sport", sa.String(50), nullable=False),
        sa.Column("league", sa.String(100), nullable=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("home_team", sa.String(255), nullable=True),
        sa.Column("away_team", sa.String(255), nullable=True),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=True),
        # UNCONFIRMED — must be validated against live API in 02-02
        sa.Column("prophetx_status", sa.String(50), nullable=True),
        sa.Column("real_world_status", sa.String(50), nullable=True),
        sa.Column(
            "status_match",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("last_prophetx_poll", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_real_world_poll", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_flagged",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_prophetx_event_id", "events", ["prophetx_event_id"], unique=True)

    # Create markets table
    op.create_table(
        "markets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("prophetx_market_id", sa.String(255), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column(
            "current_liquidity",
            sa.Numeric(precision=18, scale=2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("min_liquidity_threshold", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("last_polled", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_markets_prophetx_market_id", "markets", ["prophetx_market_id"], unique=True
    )

    # Create event_id_mappings table
    op.create_table(
        "event_id_mappings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("prophetx_event_id", sa.String(255), nullable=False),
        sa.Column("sdio_game_id", sa.String(255), nullable=False),
        sa.Column("sport", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "is_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_flagged",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_event_id_mappings_prophetx_event_id",
        "event_id_mappings",
        ["prophetx_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_event_id_mappings_sdio_game_id",
        "event_id_mappings",
        ["sdio_game_id"],
        unique=False,
    )

    # Create audit_log table
    op.create_table(
        "audit_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column("result", sa.String(20), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"], unique=False)
    op.create_index("ix_audit_log_entity_id", "audit_log", ["entity_id"], unique=False)

    # Create notifications table
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "is_read",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # REVOKE UPDATE/DELETE on audit_log to enforce append-only at DB level.
    # REVOKE may be a no-op if prophet_monitor is table owner (see RESEARCH.md Pitfall 5).
    # Defense-in-depth combined with ORM-level guard.
    # Wrapped in DO block so migration succeeds even when the role doesn't exist
    # (e.g., in dev/test environments where the connecting user IS the table owner).
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'prophet_monitor') THEN
                REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM prophet_monitor;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    # Drop in reverse order (foreign key safety)
    op.drop_table("notifications")
    op.drop_index("ix_audit_log_entity_id", table_name="audit_log")
    op.drop_index("ix_audit_log_timestamp", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_event_id_mappings_sdio_game_id", table_name="event_id_mappings")
    op.drop_index(
        "ix_event_id_mappings_prophetx_event_id", table_name="event_id_mappings"
    )
    op.drop_table("event_id_mappings")
    op.drop_index("ix_markets_prophetx_market_id", table_name="markets")
    op.drop_table("markets")
    op.drop_index("ix_events_prophetx_event_id", table_name="events")
    op.drop_table("events")
