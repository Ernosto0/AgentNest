"""Carousel content type and ordered media items. Revision 0080, parent 0071."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0080"
down_revision: str | None = "0071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
TABLE = "content_item_media"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_content_items_content_type"), "content_items", type_="check")
    op.create_check_constraint(
        op.f("ck_content_items_content_type"),
        "content_items",
        "content_type IN ('feed_image', 'story_image', 'feed_carousel')",
    )
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("content_item_id", sa.Uuid(), nullable=False),
        sa.Column("media_asset_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_item_media")),
        sa.UniqueConstraint(
            "workspace_id", "id", name=op.f("uq_content_item_media_workspace_id_id")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
            name=op.f("fk_content_item_media_workspace_id_workspaces"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "content_item_id"],
            ["content_items.workspace_id", "content_items.id"],
            ondelete="CASCADE",
            name=op.f("fk_content_item_media_workspace_id_content_item_id_content_items"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "media_asset_id"],
            ["media_assets.workspace_id", "media_assets.id"],
            name=op.f("fk_content_item_media_workspace_id_media_asset_id_media_assets"),
        ),
        sa.UniqueConstraint(
            "content_item_id",
            "position",
            deferrable=True,
            initially="DEFERRED",
            name=op.f("uq_content_item_media_content_item_id_position"),
        ),
        sa.UniqueConstraint(
            "content_item_id",
            "media_asset_id",
            name=op.f("uq_content_item_media_content_item_id_media_asset_id"),
        ),
        sa.CheckConstraint(
            "position >= 0 AND position < 20", name=op.f("ck_content_item_media_position")
        ),
    )
    op.create_index(op.f("ix_content_item_media_workspace_id"), TABLE, ["workspace_id"])
    op.create_index(
        "ix_content_item_media_workspace_content_position",
        TABLE,
        ["workspace_id", "content_item_id", "position"],
    )
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
            "UPDATE social_accounts SET capabilities = capabilities || "
            "jsonb_build_object('publish_feed_carousel', "
            "COALESCE(capabilities->'publish_feed_image', 'false'::jsonb))"
        )
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM content_items WHERE content_type = 'feed_carousel')")
    ):
        raise RuntimeError("Carousel archival is required before downgrade")
    op.drop_table(TABLE)
    op.drop_constraint(op.f("ck_content_items_content_type"), "content_items", type_="check")
    op.create_check_constraint(
        op.f("ck_content_items_content_type"),
        "content_items",
        "content_type IN ('feed_image', 'story_image')",
    )
    op.execute(
        sa.text("UPDATE social_accounts SET capabilities = capabilities - 'publish_feed_carousel'")
    )
