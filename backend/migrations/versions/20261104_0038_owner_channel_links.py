"""Owner channel links and linking codes tables (Phase 9 Session 01 / P9-01).

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-04 00:00:00.000000

P9-01 / ADR-012 / ADR-025:
- Creates channel_links table for owner messaging channel identity linking.
- Creates channel_link_codes table for one-time code redemption.
- Adds partial unique indexes for single active channel link per channel identity and workspace user.
- Enables and forces PostgreSQL Row-Level Security (RLS) on both Category C tables.
- Updates agent_owner_tasks check constraint source_channel to include 'telegram'.
- Defines pre-context SECURITY DEFINER resolution helpers for webhook ingress.
- Grants runtime privileges to agentnest_app and agentnest_worker.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create channel_links table
    op.create_table(
        "channel_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("channel_user_id", sa.Text(), nullable=False),
        sa.Column("channel_chat_id", sa.Text(), nullable=False),
        sa.Column("channel_username", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel_links")),
        sa.UniqueConstraint("workspace_id", "id", name=op.f("uq_channel_links_workspace_id_id")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_channel_links_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_channel_links_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("channel IN ('telegram')", name=op.f("ck_channel_links_channel")),
        sa.CheckConstraint(
            "status IN ('active', 'unlinked')", name=op.f("ck_channel_links_status")
        ),
    )

    op.create_index(
        op.f("ix_channel_links_workspace_id"),
        "channel_links",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_channel_links_user_id"),
        "channel_links",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "uq_channel_links_active_channel_user",
        "channel_links",
        ["channel", "channel_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "uq_channel_links_active_workspace_user_channel",
        "channel_links",
        ["workspace_id", "user_id", "channel"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    # 2. Create channel_link_codes table
    op.create_table(
        "channel_link_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel_link_codes")),
        sa.UniqueConstraint(
            "workspace_id", "id", name=op.f("uq_channel_link_codes_workspace_id_id")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_channel_link_codes_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_channel_link_codes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("channel IN ('telegram')", name=op.f("ck_channel_link_codes_channel")),
    )

    op.create_index(
        op.f("ix_channel_link_codes_workspace_id"),
        "channel_link_codes",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_channel_link_codes_user_id"),
        "channel_link_codes",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_channel_link_codes_code_hash"),
        "channel_link_codes",
        ["code_hash"],
        unique=False,
    )
    op.create_index(
        "ix_channel_link_codes_workspace_user",
        "channel_link_codes",
        ["workspace_id", "user_id"],
        unique=False,
    )

    # 3. Update agent_owner_tasks check constraint source_channel to include 'telegram'
    op.drop_constraint(
        "ck_agent_owner_tasks_source_channel",
        "agent_owner_tasks",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_owner_tasks_source_channel",
        "agent_owner_tasks",
        "source_channel IN ('api', 'telegram')",
    )

    # 4. Enable & Force Row-Level Security on both Category C tables
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for tbl in ("channel_links", "channel_link_codes"):
            op.execute(sa.text(f"ALTER TABLE public.{tbl} ENABLE ROW LEVEL SECURITY"))
            op.execute(sa.text(f"ALTER TABLE public.{tbl} FORCE ROW LEVEL SECURITY"))
            op.execute(
                sa.text(
                    f"""
                    CREATE POLICY tenant_isolation_policy ON public.{tbl}
                        FOR ALL
                        USING (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
                        WITH CHECK (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
                    """
                )
            )

        # 5. Narrow pre-context SECURITY DEFINER helper functions
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION public.resolve_channel_link_code_by_hash(
                    p_channel text,
                    p_code_hash text
                )
                RETURNS TABLE (
                    id uuid,
                    workspace_id uuid,
                    user_id uuid,
                    channel text,
                    expires_at timestamptz,
                    used_at timestamptz
                )
                LANGUAGE sql
                SECURITY DEFINER
                SET search_path = public, pg_temp
                STABLE
                AS $$
                    SELECT c.id, c.workspace_id, c.user_id, c.channel, c.expires_at, c.used_at
                    FROM public.channel_link_codes c
                    WHERE c.channel = p_channel
                      AND c.code_hash = p_code_hash
                    LIMIT 1;
                $$;

                GRANT EXECUTE ON FUNCTION public.resolve_channel_link_code_by_hash(text, text) TO PUBLIC;

                CREATE OR REPLACE FUNCTION public.resolve_channel_link_by_channel_user(
                    p_channel text,
                    p_channel_user_id text
                )
                RETURNS TABLE (
                    id uuid,
                    workspace_id uuid,
                    user_id uuid,
                    channel text,
                    channel_user_id text,
                    channel_chat_id text,
                    channel_username text,
                    status text,
                    linked_at timestamptz,
                    unlinked_at timestamptz
                )
                LANGUAGE sql
                SECURITY DEFINER
                SET search_path = public, pg_temp
                STABLE
                AS $$
                    SELECT l.id, l.workspace_id, l.user_id, l.channel, l.channel_user_id,
                           l.channel_chat_id, l.channel_username, l.status, l.linked_at, l.unlinked_at
                    FROM public.channel_links l
                    WHERE l.channel = p_channel
                      AND l.channel_user_id = p_channel_user_id
                      AND l.status = 'active'
                    LIMIT 1;
                $$;

                GRANT EXECUTE ON FUNCTION public.resolve_channel_link_by_channel_user(text, text) TO PUBLIC;
                """
            )
        )

        # 6. Runtime privilege grants
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_app') THEN
                    GRANT USAGE ON SCHEMA public TO agentnest_app;
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.channel_links TO agentnest_app;
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.channel_link_codes TO agentnest_app;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_worker') THEN
                    GRANT USAGE ON SCHEMA public TO agentnest_worker;
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.channel_links TO agentnest_worker;
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.channel_link_codes TO agentnest_worker;
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "DROP FUNCTION IF EXISTS public.resolve_channel_link_by_channel_user(text, text)"
            )
        )
        op.execute(
            sa.text("DROP FUNCTION IF EXISTS public.resolve_channel_link_code_by_hash(text, text)")
        )

        for tbl in ("channel_link_codes", "channel_links"):
            op.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation_policy ON public.{tbl}"))
            op.execute(sa.text(f"ALTER TABLE public.{tbl} NO FORCE ROW LEVEL SECURITY"))
            op.execute(sa.text(f"ALTER TABLE public.{tbl} DISABLE ROW LEVEL SECURITY"))

    # Revert agent_owner_tasks check constraint
    op.drop_constraint(
        "ck_agent_owner_tasks_source_channel",
        "agent_owner_tasks",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_owner_tasks_source_channel",
        "agent_owner_tasks",
        "source_channel IN ('api')",
    )

    op.drop_index(
        "ix_channel_link_codes_workspace_user",
        table_name="channel_link_codes",
    )
    op.drop_index(
        op.f("ix_channel_link_codes_code_hash"),
        table_name="channel_link_codes",
    )
    op.drop_index(
        op.f("ix_channel_link_codes_user_id"),
        table_name="channel_link_codes",
    )
    op.drop_index(
        op.f("ix_channel_link_codes_workspace_id"),
        table_name="channel_link_codes",
    )
    op.drop_table("channel_link_codes")

    op.drop_index(
        "uq_channel_links_active_workspace_user_channel",
        table_name="channel_links",
    )
    op.drop_index(
        "uq_channel_links_active_channel_user",
        table_name="channel_links",
    )
    op.drop_index(
        op.f("ix_channel_links_user_id"),
        table_name="channel_links",
    )
    op.drop_index(
        op.f("ix_channel_links_workspace_id"),
        table_name="channel_links",
    )
    op.drop_table("channel_links")
