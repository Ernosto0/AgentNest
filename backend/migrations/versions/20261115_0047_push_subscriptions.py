"""Web Push subscriptions: one row per device a user can be notified on (F-01).

Revision ID: 0047
Revises: 0046
Create Date: 2026-11-15 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "push_subscriptions"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("endpoint_hash", sa.Text(), nullable=False),
        sa.Column("p256dh_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("auth_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_id", sa.Text(), nullable=False),
        sa.Column("device_label", sa.Text(), server_default="", nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
            ["user_id"],
            ["users.id"],
            name=op.f("fk_push_subscriptions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_push_subscriptions_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_subscriptions")),
        sa.UniqueConstraint(
            "workspace_id", "id", name=op.f("uq_push_subscriptions_workspace_id_id")
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            "endpoint_hash",
            name=op.f("uq_push_subscriptions_workspace_id_user_id_endpoint_hash"),
        ),
    )
    op.create_index(op.f("ix_push_subscriptions_workspace_id"), TABLE, ["workspace_id"])
    op.create_index("ix_push_subscriptions_user", TABLE, ["workspace_id", "user_id"])
    op.create_index("ix_push_subscriptions_endpoint_hash", TABLE, ["endpoint_hash"])

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
