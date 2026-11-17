"""Approval-ladder suggestions: one weekly "send this topic automatically?" proposal (D-02).

Revision ID: 0053
Revises: 0052
Create Date: 2026-11-16 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "delegation_suggestions"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("social_account_id", sa.Uuid(), nullable=False),
        sa.Column("week", sa.Date(), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("action_class", sa.Text(), nullable=False),
        sa.Column("counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("preview_hash", sa.Text(), nullable=True),
        sa.Column("previewed_by", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'dismissed', 'expired')",
            name=op.f("ck_delegation_suggestions_status"),
        ),
        sa.CheckConstraint(
            "preview_hash IS NULL OR preview_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_delegation_suggestions_preview_hash"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
            name="fk_delegation_suggestions_account",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            name=op.f("fk_delegation_suggestions_decided_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_delegation_suggestions_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_delegation_suggestions")),
        sa.UniqueConstraint(
            "workspace_id", "id", name=op.f("uq_delegation_suggestions_workspace_id_id")
        ),
        sa.UniqueConstraint(
            "workspace_id", "week", name=op.f("uq_delegation_suggestions_workspace_id_week")
        ),
    )
    op.create_index(op.f("ix_delegation_suggestions_workspace_id"), TABLE, ["workspace_id"])
    op.create_index(
        "ix_delegation_suggestions_class_cooldown",
        TABLE,
        ["workspace_id", "action_class", "cooldown_until"],
    )

    op.execute(sa.text(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"""
            CREATE POLICY tenant_isolation_policy ON {TABLE} FOR ALL
            USING (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
            WITH CHECK (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
            """
        )
    )
    for role in ("agentnest_app", "agentnest_worker", "agentnest_migrator"):
        op.execute(
            sa.text(
                f"""
                DO $$ BEGIN
                    IF to_regrole('{role}') IS NOT NULL THEN
                        GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLE} TO {role};
                    END IF;
                END $$;
                """
            )
        )


def downgrade() -> None:
    op.drop_table(TABLE)
