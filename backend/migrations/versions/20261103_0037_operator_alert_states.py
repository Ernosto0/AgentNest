"""Create operator_alert_states table for durable alert tracking.

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-03 21:00:00.000000

P8-07 / ADR-025 §4.3:
- Creates operator_alert_states table for durable alert deduplication, cooldowns, and recovery.
- Category B: cross-boundary system table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create operator_alert_states table (Category B: cross-boundary system table)
    op.create_table(
        "operator_alert_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("alert_key", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False, server_default="warning"),
        sa.Column("status", sa.Text(), nullable=False, server_default="firing"),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("first_triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notification_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('firing', 'resolved')",
            name=op.f("ck_operator_alert_states_status"),
        ),
        sa.CheckConstraint(
            "severity IN ('critical', 'warning', 'info')",
            name=op.f("ck_operator_alert_states_severity"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_operator_alert_states_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operator_alert_states")),
        sa.UniqueConstraint("alert_key", name=op.f("uq_operator_alert_states_alert_key")),
    )

    op.create_index(
        op.f("ix_operator_alert_states_status"),
        "operator_alert_states",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_operator_alert_states_category"),
        "operator_alert_states",
        ["category"],
        unique=False,
    )
    op.create_index(
        op.f("ix_operator_alert_states_cooldown_until"),
        "operator_alert_states",
        ["cooldown_until"],
        unique=False,
    )

    # 2. Runtime privilege grants
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_app') THEN
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE operator_alert_states TO agentnest_app;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_worker') THEN
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE operator_alert_states TO agentnest_worker;
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_operator_alert_states_cooldown_until"),
        table_name="operator_alert_states",
    )
    op.drop_index(
        op.f("ix_operator_alert_states_category"),
        table_name="operator_alert_states",
    )
    op.drop_index(
        op.f("ix_operator_alert_states_status"),
        table_name="operator_alert_states",
    )
    op.drop_table("operator_alert_states")
