"""Hardening & recovery fixes: membership-checked Telegram lookup, calendar exclusion constraint, pending media table, and fixed stuck-op discovery.

Revision ID: 0045
Revises: 0044
Create Date: 2026-11-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _current_schema(bind: sa.Connection) -> str:
    return str(bind.execute(sa.text("SELECT current_schema()")).scalar_one() or "public")


def _q(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Create persistent DB table for Telegram uncaptioned pending photos (Serious 9)
    op.create_table(
        "telegram_pending_media",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("media_asset_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_telegram_pending_media_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_telegram_pending_media_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["media_asset_id"],
            ["media_assets.id"],
            name=op.f("fk_telegram_pending_media_media_asset_id_media_assets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telegram_pending_media")),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name=op.f("uq_telegram_pending_media_workspace_id_id"),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_telegram_pending_media_ws_user",
        ),
    )
    op.create_index(
        op.f("ix_telegram_pending_media_workspace_id"),
        "telegram_pending_media",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_pending_media_expires_at",
        "telegram_pending_media",
        ["expires_at"],
        unique=False,
    )

    if bind.dialect.name != "postgresql":
        return

    schema = _current_schema(bind)
    q_schema = _q(schema)

    op.execute(sa.text("ALTER TABLE telegram_pending_media ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE telegram_pending_media FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            """
            CREATE POLICY tenant_isolation_policy ON telegram_pending_media
                FOR ALL
                USING (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
                WITH CHECK (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_app') THEN
                    GRANT USAGE ON SCHEMA {q_schema} TO agentnest_app;
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE telegram_pending_media TO agentnest_app;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_worker') THEN
                    GRANT USAGE ON SCHEMA {q_schema} TO agentnest_worker;
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE telegram_pending_media TO agentnest_worker;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_migrator') THEN
                    GRANT ALL ON TABLE telegram_pending_media TO agentnest_migrator;
                END IF;
            END $$;
            """
        )
    )

    # 2. Enforce no overlapping scheduled appointments per workspace via btree_gist exclusion (Serious 5)
    ext_schema = bind.execute(
        sa.text(
            "SELECT n.nspname FROM pg_extension e "
            "JOIN pg_namespace n ON n.oid = e.extnamespace "
            "WHERE e.extname = 'btree_gist'"
        )
    ).scalar_one_or_none()
    if ext_schema is None:
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        ext_schema = schema
    q_ext = _q(str(ext_schema))
    op.execute(sa.text(f"SET LOCAL search_path TO {q_schema}, {q_ext}"))
    op.execute(
        sa.text(
            """
            ALTER TABLE calendar_appointments
            ADD CONSTRAINT ex_calendar_appointments_no_overlap
            EXCLUDE USING gist (
                workspace_id WITH =,
                tstzrange(start_at, end_at, '[)') WITH &&
            )
            WHERE (status = 'scheduled')
            """
        )
    )
    op.execute(sa.text(f"SET LOCAL search_path TO {q_schema}"))

    # 3. Require active membership and active user in resolve_channel_link_by_channel_user (Blocker 1)
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION resolve_channel_link_by_channel_user(
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
            SET search_path = {q_schema}, pg_temp
            STABLE
            AS $$
                SELECT l.id, l.workspace_id, l.user_id, l.channel, l.channel_user_id,
                       l.channel_chat_id, l.channel_username, l.status, l.linked_at, l.unlinked_at
                FROM channel_links l
                JOIN users u
                  ON u.id = l.user_id
                JOIN workspace_members m
                  ON m.workspace_id = l.workspace_id
                 AND m.user_id = l.user_id
                WHERE l.channel = p_channel
                  AND l.channel_user_id = p_channel_user_id
                  AND l.status = 'active'
                  AND u.is_active IS TRUE
                LIMIT 1;
            $$;
            """
        )
    )

    # 4. Fix discover_stuck_operations: only 'in_progress' ops ordered by clock-injected started_at (Serious 11)
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION discover_stuck_operations(
                p_cutoff timestamptz,
                p_limit int DEFAULT 100
            )
            RETURNS TABLE (
                id uuid,
                workspace_id uuid,
                subject_type text,
                status text
            )
            LANGUAGE sql
            SECURITY DEFINER
            SET search_path = {q_schema}, pg_temp
            STABLE
            AS $$
                SELECT o.id, o.workspace_id, o.subject_type, o.status
                FROM operations o
                WHERE o.status = 'in_progress'
                  AND COALESCE(o.started_at, o.created_at) <= p_cutoff
                ORDER BY COALESCE(o.started_at, o.created_at), o.id
                LIMIT p_limit;
            $$;
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        schema = _current_schema(bind)
        q_schema = _q(schema)

        # Restore prior discover_stuck_operations definition (from 0031)
        op.execute(
            sa.text(
                f"""
                CREATE OR REPLACE FUNCTION discover_stuck_operations(
                    p_cutoff timestamptz,
                    p_limit int DEFAULT 100
                )
                RETURNS TABLE (
                    id uuid,
                    workspace_id uuid,
                    subject_type text,
                    status text
                )
                LANGUAGE sql
                SECURITY DEFINER
                SET search_path = {q_schema}, pg_temp
                STABLE
                AS $$
                    SELECT o.id, o.workspace_id, o.subject_type, o.status
                    FROM operations o
                    WHERE o.status IN ('in_progress', 'outcome_unknown')
                      AND o.updated_at <= p_cutoff
                    ORDER BY o.updated_at, o.id
                    LIMIT p_limit;
                $$;
                """
            )
        )

        # Restore prior resolve_channel_link_by_channel_user definition (from 0038)
        op.execute(
            sa.text(
                f"""
                CREATE OR REPLACE FUNCTION resolve_channel_link_by_channel_user(
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
                SET search_path = {q_schema}, pg_temp
                STABLE
                AS $$
                    SELECT l.id, l.workspace_id, l.user_id, l.channel, l.channel_user_id,
                           l.channel_chat_id, l.channel_username, l.status, l.linked_at, l.unlinked_at
                    FROM channel_links l
                    WHERE l.channel = p_channel
                      AND l.channel_user_id = p_channel_user_id
                      AND l.status = 'active'
                    LIMIT 1;
                $$;
                """
            )
        )

        op.execute(
            sa.text(
                "ALTER TABLE calendar_appointments DROP CONSTRAINT IF EXISTS ex_calendar_appointments_no_overlap"
            )
        )

        op.execute(
            sa.text("DROP POLICY IF EXISTS tenant_isolation_policy ON telegram_pending_media")
        )
        op.execute(sa.text("ALTER TABLE telegram_pending_media NO FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text("ALTER TABLE telegram_pending_media DISABLE ROW LEVEL SECURITY"))

    op.drop_index("ix_telegram_pending_media_expires_at", table_name="telegram_pending_media")
    op.drop_index(
        op.f("ix_telegram_pending_media_workspace_id"),
        table_name="telegram_pending_media",
    )
    op.drop_table("telegram_pending_media")
