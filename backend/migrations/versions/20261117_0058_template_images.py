"""Workspace brand settings and template render provenance.

Revision ID: 0058
Revises: 0057
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0058"
down_revision: str | None = "0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
TABLE = "workspace_brand_settings"


def upgrade() -> None:
    op.add_column("media_assets", sa.Column("render_record", postgresql.JSONB(), nullable=True))
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("primary_color", sa.Text(), nullable=False),
        sa.Column("accent_color", sa.Text(), nullable=False),
        sa.Column("logo_media_asset_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id"),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "logo_media_asset_id"],
            ["media_assets.workspace_id", "media_assets.id"],
        ),
        sa.CheckConstraint("primary_color ~ '^#[0-9a-f]{6}$'", name="primary_color"),
        sa.CheckConstraint("accent_color ~ '^#[0-9a-f]{6}$'", name="accent_color"),
    )
    op.create_index(op.f("ix_workspace_brand_settings_workspace_id"), TABLE, ["workspace_id"])
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
    op.drop_column("media_assets", "render_record")
