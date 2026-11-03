"""Notification deliveries ledger table (Phase 9 Session 03 / ADR-012).

Revision ID: 0039
Revises: 0038
Create Date: 2026-11-04 01:00:00.000000

P9-03 / ADR-012:
- Creates notification_deliveries table for per-channel notification tracking.
- Adds foreign keys to workspaces, notifications, users, and channel_links.
- Enforces channel and delivery status check constraints.
- Enables and forces PostgreSQL Row-Level Security (RLS) with tenant isolation.
- Grants runtime privileges to agentnest_app and agentnest_worker.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create notification_deliveries table
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("channel_link_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_deliveries")),
        sa.UniqueConstraint(
            "workspace_id", "id", name=op.f("uq_notification_deliveries_workspace_id_id")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_notification_deliveries_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            name=op.f("fk_notification_deliveries_notification_id_notifications"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"],
            ["users.id"],
            name=op.f("fk_notification_deliveries_recipient_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["channel_link_id"],
            ["channel_links.id"],
            name=op.f("fk_notification_deliveries_channel_link_id_channel_links"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "channel IN ('web', 'telegram')",
            name=op.f("ck_notification_deliveries_channel"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'delivered', 'failed', 'skipped_quiet_hours')",
            name=op.f("ck_notification_deliveries_status"),
        ),
    )

    # 2. Indexes
    op.create_index(
        op.f("ix_notification_deliveries_workspace_id"),
        "notification_deliveries",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_deliveries_notification_id"),
        "notification_deliveries",
        ["notification_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_deliveries_recipient_user_id"),
        "notification_deliveries",
        ["recipient_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_deliveries_status"),
        "notification_deliveries",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_deliveries_pending"),
        "notification_deliveries",
        ["status", "created_at"],
        unique=False,
    )

    # 3. Row-Level Security
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE public.notification_deliveries ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text("ALTER TABLE public.notification_deliveries FORCE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                """
                CREATE POLICY tenant_isolation_policy ON public.notification_deliveries
                    FOR ALL
                    USING (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
                    WITH CHECK (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
                """
            )
        )

        # 4. Grants
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_app') THEN
                    GRANT USAGE ON SCHEMA public TO agentnest_app;
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.notification_deliveries TO agentnest_app;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_worker') THEN
                    GRANT USAGE ON SCHEMA public TO agentnest_worker;
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.notification_deliveries TO agentnest_worker;
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text("DROP POLICY IF EXISTS tenant_isolation_policy ON public.notification_deliveries")
        )
        op.execute(sa.text("ALTER TABLE public.notification_deliveries NO FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text("ALTER TABLE public.notification_deliveries DISABLE ROW LEVEL SECURITY"))

    op.drop_index(
        op.f("ix_notification_deliveries_pending"),
        table_name="notification_deliveries",
    )
    op.drop_index(
        op.f("ix_notification_deliveries_status"),
        table_name="notification_deliveries",
    )
    op.drop_index(
        op.f("ix_notification_deliveries_recipient_user_id"),
        table_name="notification_deliveries",
    )
    op.drop_index(
        op.f("ix_notification_deliveries_notification_id"),
        table_name="notification_deliveries",
    )
    op.drop_index(
        op.f("ix_notification_deliveries_workspace_id"),
        table_name="notification_deliveries",
    )
    op.drop_table("notification_deliveries")

