"""Action tokens table for single-use approval buttons (Phase 9 Session 06 / ADR-012, ADR-014, INV-16).

Revision ID: 0041
Revises: 0040
Create Date: 2026-11-04 03:00:00.000000

P9-04 / ADR-012 / ADR-014 / INV-16:
- Creates action_tokens table for single-use owner channel approval action tokens.
- Adds foreign keys to workspaces, approvals, and users with ON DELETE CASCADE.
- Enforces decision check constraint ('approved', 'rejected').
- Enables and forces PostgreSQL Row-Level Security (RLS) with tenant isolation.
- Adds resolve_action_token_by_hash SECURITY DEFINER helper function for webhook ingress.
- Grants runtime privileges to agentnest_app, agentnest_worker, and agentnest_migrator.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create action_tokens table
    op.create_table(
        "action_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action_tokens")),
        sa.UniqueConstraint(
            "workspace_id", "id", name=op.f("uq_action_tokens_workspace_id_id")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_action_tokens_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["approval_id"],
            ["approvals.id"],
            name=op.f("fk_action_tokens_approval_id_approvals"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_action_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "decision IN ('approved', 'rejected')",
            name=op.f("ck_action_tokens_decision"),
        ),
    )

    # 2. Indexes
    op.create_index(
        op.f("ix_action_tokens_token_hash"),
        "action_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_action_tokens_workspace_id"),
        "action_tokens",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_action_tokens_approval_id"),
        "action_tokens",
        ["approval_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_action_tokens_user_id"),
        "action_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_action_tokens_expires_at"),
        "action_tokens",
        ["expires_at"],
        unique=False,
    )

    # 3. Row-Level Security
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE public.action_tokens ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text("ALTER TABLE public.action_tokens FORCE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                """
                CREATE POLICY tenant_isolation_policy ON public.action_tokens
                    FOR ALL
                    USING (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
                    WITH CHECK (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
                """
            )
        )

        # 4. Ingress SECURITY DEFINER lookup helper function
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION public.resolve_action_token_by_hash(
                    p_token_hash text
                )
                RETURNS TABLE (
                    id uuid,
                    workspace_id uuid,
                    approval_id uuid,
                    decision text,
                    user_id uuid,
                    payload_hash text,
                    expires_at timestamptz,
                    used_at timestamptz
                )
                LANGUAGE sql
                SECURITY DEFINER
                SET search_path = public, pg_temp
                STABLE
                AS $$
                    SELECT a.id, a.workspace_id, a.approval_id, a.decision, a.user_id,
                           a.payload_hash, a.expires_at, a.used_at
                    FROM public.action_tokens a
                    WHERE a.token_hash = p_token_hash
                    LIMIT 1;
                $$;

                GRANT EXECUTE ON FUNCTION public.resolve_action_token_by_hash(text) TO PUBLIC;
                """
            )
        )

        # 5. Table grants for least-privilege runtime roles
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_app') THEN
                    GRANT USAGE ON SCHEMA public TO agentnest_app;
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.action_tokens TO agentnest_app;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_worker') THEN
                    GRANT USAGE ON SCHEMA public TO agentnest_worker;
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.action_tokens TO agentnest_worker;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_migrator') THEN
                    GRANT ALL ON TABLE public.action_tokens TO agentnest_migrator;
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text("DROP FUNCTION IF EXISTS public.resolve_action_token_by_hash(text)")
        )
        op.execute(
            sa.text("DROP POLICY IF EXISTS tenant_isolation_policy ON public.action_tokens")
        )
        op.execute(sa.text("ALTER TABLE public.action_tokens NO FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text("ALTER TABLE public.action_tokens DISABLE ROW LEVEL SECURITY"))

    op.drop_index(
        op.f("ix_action_tokens_expires_at"),
        table_name="action_tokens",
    )
    op.drop_index(
        op.f("ix_action_tokens_user_id"),
        table_name="action_tokens",
    )
    op.drop_index(
        op.f("ix_action_tokens_approval_id"),
        table_name="action_tokens",
    )
    op.drop_index(
        op.f("ix_action_tokens_workspace_id"),
        table_name="action_tokens",
    )
    op.drop_index(
        op.f("ix_action_tokens_token_hash"),
        table_name="action_tokens",
    )
    op.drop_table("action_tokens")
