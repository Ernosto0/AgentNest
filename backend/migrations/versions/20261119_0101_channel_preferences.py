"""channel_preferences table (Session 02). Revision 0101, parent 0100."""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0101"
down_revision: str | None = "0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "channel_preferences"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
            "channel IN ('telegram', 'whatsapp')",
            name=op.f("ck_channel_preferences_channel"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_channel_preferences_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_channel_preferences_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel_preferences")),
        sa.UniqueConstraint("workspace_id", "id", name=op.f("uq_channel_preferences_workspace_id_id")),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            "channel",
            name=op.f("uq_channel_preferences_workspace_id_user_id_channel"),
        ),
    )
    op.create_index(op.f("ix_channel_preferences_workspace_id"), TABLE, ["workspace_id"])
    op.create_index("ix_channel_preferences_user", TABLE, ["workspace_id", "user_id"])

    # Seed active links as enabled=true so existing linked owners keep receiving notifications
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
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
        op.execute(
            sa.text(
                f"""
                INSERT INTO {TABLE} (id, workspace_id, user_id, channel, enabled, created_at, updated_at)
                SELECT gen_random_uuid(), workspace_id, user_id, channel, true, now(), now()
                FROM channel_links
                WHERE status = 'active'
                ON CONFLICT (workspace_id, user_id, channel) DO NOTHING
                """
            )
        )


def downgrade() -> None:
    op.drop_index("ix_channel_preferences_user", table_name=TABLE)
    op.drop_index(op.f("ix_channel_preferences_workspace_id"), table_name=TABLE)
    op.drop_table(TABLE)

