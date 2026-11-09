"""Add Instagram Insights tables.

Revision ID: 0044
Revises: 0043
Create Date: 2026-11-10 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_insight_daily",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("social_account_id", sa.Uuid(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "social_account_id", "local_date", "metric", name="uq_account_insight_daily_metric"
        ),
    )
    op.create_index(
        "ix_account_insight_daily_ws_date",
        "account_insight_daily",
        ["workspace_id", "local_date"],
    )

    op.create_table(
        "media_insight_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("social_account_id", sa.Uuid(), nullable=False),
        sa.Column("content_item_id", sa.Uuid(), nullable=True),
        sa.Column("ig_media_id", sa.Text(), nullable=False),
        sa.Column("media_kind", sa.Text(), nullable=False),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["content_item_id"],
            ["content_items.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_media_insight_snapshots_media",
        "media_insight_snapshots",
        ["workspace_id", "social_account_id", "ig_media_id"],
    )
    op.create_index(
        "ix_media_insight_snapshots_content_item",
        "media_insight_snapshots",
        ["workspace_id", "content_item_id"],
    )

    op.create_table(
        "audience_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("social_account_id", sa.Uuid(), nullable=False),
        sa.Column("captured_on", sa.Date(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "social_account_id",
            "captured_on",
            "kind",
            name="uq_audience_snapshots_account_day_kind",
        ),
    )

    for table in ("account_insight_daily", "media_insight_snapshots", "audience_snapshots"):
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])
        op.create_unique_constraint(f"uq_{table}_workspace_id_id", table, ["workspace_id", "id"])
        op.execute(sa.text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(f"""
            CREATE POLICY tenant_isolation_policy ON public.{table} FOR ALL
            USING (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
            WITH CHECK (workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid)
        """)
        )
        for role in ("agentnest_app", "agentnest_worker", "agentnest_migrator"):
            op.execute(
                sa.text(f"""
                DO $$ BEGIN
                    IF to_regrole('{role}') IS NOT NULL THEN
                        GRANT SELECT, INSERT, UPDATE, DELETE ON public.{table} TO {role};
                    END IF;
                END $$;
            """)
            )


def downgrade() -> None:
    op.drop_table("audience_snapshots")
    op.drop_index("ix_media_insight_snapshots_content_item", table_name="media_insight_snapshots")
    op.drop_index("ix_media_insight_snapshots_media", table_name="media_insight_snapshots")
    op.drop_table("media_insight_snapshots")
    op.drop_index("ix_account_insight_daily_ws_date", table_name="account_insight_daily")
    op.drop_table("account_insight_daily")
