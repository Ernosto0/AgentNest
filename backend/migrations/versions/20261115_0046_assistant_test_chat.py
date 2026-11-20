"""Assistant test chat: the owner's sandbox of test customer messages and their drafts.

Revision ID: 0046
Revises: 0045
Create Date: 2026-11-15 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "assistant_test_turns"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("customer_text", sa.Text(), nullable=True),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("intent", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column(
            "flags", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("draft_text", sa.Text(), nullable=True),
        sa.Column("suggestion_text", sa.Text(), nullable=True),
        sa.Column("decision", sa.Text(), nullable=True),
        sa.Column(
            "decision_reasons",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "facts_used",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("is_simulated", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'reset')", name=op.f("ck_assistant_test_turns_status")
        ),
        sa.CheckConstraint(
            "decision IS NULL OR decision IN "
            "('auto', 'approval_required', 'human_required', 'blocked')",
            name=op.f("ck_assistant_test_turns_decision"),
        ),
        sa.CheckConstraint(
            "status <> 'ready' OR decision IS NOT NULL",
            name=op.f("ck_assistant_test_turns_ready_has_decision"),
        ),
        sa.CheckConstraint("is_simulated", name=op.f("ck_assistant_test_turns_always_simulated")),
        sa.ForeignKeyConstraint(
            ["workspace_id", "agent_run_id"],
            ["agent_runs.workspace_id", "agent_runs.id"],
            name=op.f("fk_assistant_test_turns_workspace_id_agent_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_assistant_test_turns_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_assistant_test_turns_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_test_turns")),
        sa.UniqueConstraint(
            "workspace_id", "id", name=op.f("uq_assistant_test_turns_workspace_id_id")
        ),
    )
    op.create_index(op.f("ix_assistant_test_turns_workspace_id"), TABLE, ["workspace_id"])
    op.create_index(
        "ix_assistant_test_turns_workspace_created", TABLE, ["workspace_id", "created_at"]
    )
    op.create_index(
        "ix_assistant_test_turns_user_created", TABLE, ["workspace_id", "user_id", "created_at"]
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
    for role in ("pivoris_app", "pivoris_worker", "pivoris_migrator"):
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
