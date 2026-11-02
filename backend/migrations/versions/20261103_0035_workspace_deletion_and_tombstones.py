"""Add workspace deletion lifecycle fields and deletion_tombstones table.

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-03 01:00:00.000000

P8-05 / ADR-025 §3.2, §3.3:
- Adds deletion_requested_at, deletion_scheduled_at, and deletion_requested_by to workspaces table.
- Creates deletion_tombstones table for cross-domain backup/restore reconciliation and audit fencing.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add deletion lifecycle columns to workspaces
    op.add_column(
        "workspaces",
        sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workspaces",
        sa.Column("deletion_scheduled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workspaces",
        sa.Column("deletion_requested_by", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_workspaces_deletion_requested_by_users"),
        "workspaces",
        "users",
        ["deletion_requested_by"],
        ["id"],
        ondelete="SET NULL",
    )

    # 2. Create deletion_tombstones table
    op.create_table(
        "deletion_tombstones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deletion_tombstones")),
    )
    op.create_index(
        op.f("ix_deletion_tombstones_entity"),
        "deletion_tombstones",
        ["entity_type", "entity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_deletion_tombstones_workspace_id"),
        "deletion_tombstones",
        ["workspace_id"],
        unique=False,
    )

    # 3. Grant runtime privileges to agentnest_app and agentnest_worker if they exist
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_app') THEN
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.deletion_tombstones TO agentnest_app;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_worker') THEN
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.deletion_tombstones TO agentnest_worker;
                END IF;
            END
            $$;
            """
        )
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_deletion_tombstones_workspace_id"), table_name="deletion_tombstones")
    op.drop_index(op.f("ix_deletion_tombstones_entity"), table_name="deletion_tombstones")
    op.drop_table("deletion_tombstones")
    op.drop_constraint(
        op.f("fk_workspaces_deletion_requested_by_users"), "workspaces", type_="foreignkey"
    )
    op.drop_column("workspaces", "deletion_requested_by")
    op.drop_column("workspaces", "deletion_scheduled_at")
    op.drop_column("workspaces", "deletion_requested_at")
