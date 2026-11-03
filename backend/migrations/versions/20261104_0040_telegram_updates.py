"""Telegram updates deduplication table (Phase 9 Session 04 / ADR-012, INV-06).

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-04 02:00:00.000000

P9-04 / ADR-012 / INV-06:
- Creates telegram_updates global table for webhook/polling update deduplication.
- Deduplication occurs at ingress before tenant resolution (explicit global table).
- Enforces status check constraint ('processed', 'ignored', 'failed').
- Grants runtime privileges to agentnest_app and agentnest_worker.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create telegram_updates global table
    op.create_table(
        "telegram_updates",
        sa.Column("update_id", sa.BigInteger(), nullable=False, autoincrement=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="processed"),
        sa.Column("channel_user_id", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("update_id", name=op.f("pk_telegram_updates")),
        sa.CheckConstraint(
            "status IN ('processed', 'ignored', 'failed')",
            name=op.f("ck_telegram_updates_status"),
        ),
    )

    # 2. Indexes
    op.create_index(
        op.f("ix_telegram_updates_received_at"),
        "telegram_updates",
        ["received_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_telegram_updates_channel_user_id"),
        "telegram_updates",
        ["channel_user_id"],
        unique=False,
    )

    # 3. Grants for least-privilege runtime roles
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_app') THEN
                    GRANT USAGE ON SCHEMA public TO agentnest_app;
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.telegram_updates TO agentnest_app;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentnest_worker') THEN
                    GRANT USAGE ON SCHEMA public TO agentnest_worker;
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.telegram_updates TO agentnest_worker;
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_telegram_updates_channel_user_id"),
        table_name="telegram_updates",
    )
    op.drop_index(
        op.f("ix_telegram_updates_received_at"),
        table_name="telegram_updates",
    )
    op.drop_table("telegram_updates")
