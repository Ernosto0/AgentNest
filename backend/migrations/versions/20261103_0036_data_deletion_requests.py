"""Create data_deletion_requests table for Meta callback tracking.

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-03 02:00:00.000000

P8-05 / ADR-025 §3.4:
- Creates data_deletion_requests table for Meta callback tracking and status endpoints.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create data_deletion_requests table (Category B: cross-boundary system table)
    op.create_table(
        "data_deletion_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("confirmation_code", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False, server_default="meta"),
        sa.Column("provider_user_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'not_found_or_already_erased')",
            name=op.f("ck_data_deletion_requests_status"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_data_deletion_requests_workspace_id_workspaces"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_deletion_requests")),
    )

    op.create_index(
        op.f("ix_data_deletion_requests_confirmation_code"),
        "data_deletion_requests",
        ["confirmation_code"],
        unique=True,
    )
    op.create_index(
        op.f("ix_data_deletion_requests_provider_user"),
        "data_deletion_requests",
        ["provider", "provider_user_id"],
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
                    GRANT SELECT, INSERT, UPDATE ON TABLE data_deletion_requests TO agentnest_app;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_worker') THEN
                    GRANT SELECT, INSERT, UPDATE ON TABLE data_deletion_requests
                        TO agentnest_worker;
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_data_deletion_requests_provider_user"),
        table_name="data_deletion_requests",
    )
    op.drop_index(
        op.f("ix_data_deletion_requests_confirmation_code"),
        table_name="data_deletion_requests",
    )
    op.drop_table("data_deletion_requests")
