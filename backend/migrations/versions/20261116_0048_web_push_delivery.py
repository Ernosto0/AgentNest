"""Web Push owner channel: the ``web_push`` delivery channel and per-user push preferences (F-01).

- ``notification_deliveries.channel`` may now be ``web_push`` (the CHECK constraint is replaced).
- ``push_preferences``: one row per (workspace, user, category) saying whether that user wants
  phone pushes for the category. No row means off (opt-in). Forced RLS on ``app.workspace_id``.

Revision ID: 0048
Revises: 0047
Create Date: 2026-11-16 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "push_preferences"
CHANNEL_CHECK = "ck_notification_deliveries_channel"


def upgrade() -> None:
    op.drop_constraint(op.f(CHANNEL_CHECK), "notification_deliveries", type_="check")
    op.create_check_constraint(
        op.f(CHANNEL_CHECK),
        "notification_deliveries",
        "channel IN ('web', 'telegram', 'web_push')",
    )

    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False),
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
        sa.CheckConstraint(
            "category IN ('approvals', 'questions', 'failures')",
            name=op.f("ck_push_preferences_category"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_push_preferences_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_push_preferences_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_preferences")),
        sa.UniqueConstraint("workspace_id", "id", name=op.f("uq_push_preferences_workspace_id_id")),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            "category",
            name=op.f("uq_push_preferences_workspace_id_user_id_category"),
        ),
    )
    op.create_index(op.f("ix_push_preferences_workspace_id"), TABLE, ["workspace_id"])
    op.create_index("ix_push_preferences_user", TABLE, ["workspace_id", "user_id"])

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
    # A ledger row of the removed channel cannot satisfy the old constraint.
    op.execute(sa.text("DELETE FROM notification_deliveries WHERE channel = 'web_push'"))
    op.drop_constraint(op.f(CHANNEL_CHECK), "notification_deliveries", type_="check")
    op.create_check_constraint(
        op.f(CHANNEL_CHECK),
        "notification_deliveries",
        "channel IN ('web', 'telegram')",
    )
