"""Reels. Revision 0083, parent 0082."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0083"
down_revision: str | None = "0082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Snapshot prior simulator checks; migrations must not import mutable app models.
PRIOR_OPERATIONS = (
    "send",
    "lookup",
    "echo",
    "create_container",
    "create_carousel_item",
    "create_carousel_container",
    "container_status",
    "publish",
    "refresh",
    "profile",
    "comment_reply",
    "comment_hide",
    "comment_unhide",
    "comment_delete",
    "comment_lookup",
    "comment_private_reply",
    "private_reply_lookup",
    "any",
)
PRIOR_MODES = (
    "transient",
    "rate_limited",
    "auth_revoked",
    "permission_missing",
    "invalid_media",
    "timeout_after_success",
    "window_closed",
)


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(repr(v) for v in values)


def _sim_checks(reels: bool) -> None:
    op.drop_constraint(op.f("ck_sim_containers_media_type"), "sim_containers", type_="check")
    media_types = ("IMAGE", "STORIES", "CAROUSEL") + (("REELS",) if reels else ())
    op.create_check_constraint(
        op.f("ck_sim_containers_media_type"),
        "sim_containers",
        f"media_type IN ({_quoted(media_types)})",
    )

    op.drop_constraint(op.f("ck_sim_failure_rules_operation"), "sim_failure_rules", type_="check")
    operations = PRIOR_OPERATIONS + (("create_reel_container",) if reels else ())
    op.create_check_constraint(
        op.f("ck_sim_failure_rules_operation"),
        "sim_failure_rules",
        f"operation IN ({_quoted(operations)})",
    )

    op.drop_constraint(op.f("ck_sim_failure_rules_mode"), "sim_failure_rules", type_="check")
    modes = PRIOR_MODES + (("slow_processing", "processing_error") if reels else ())
    op.create_check_constraint(
        op.f("ck_sim_failure_rules_mode"),
        "sim_failure_rules",
        f"mode IN ({_quoted(modes)})",
    )


def upgrade() -> None:
    op.drop_constraint(op.f("ck_content_items_content_type"), "content_items", type_="check")
    op.create_check_constraint(
        op.f("ck_content_items_content_type"),
        "content_items",
        "content_type IN ('feed_image', 'story_image', 'feed_carousel', 'reel')",
    )
    op.add_column("content_items", sa.Column("cover_media_asset_id", sa.Uuid(), nullable=True))
    op.add_column("content_items", sa.Column("thumb_offset_ms", sa.Integer(), nullable=True))
    op.add_column("content_items", sa.Column("share_to_feed", sa.Boolean(), nullable=True))
    op.create_foreign_key(
        op.f("fk_content_items_workspace_id_cover_media_asset_id_media_assets"),
        "content_items",
        "media_assets",
        ["workspace_id", "cover_media_asset_id"],
        ["workspace_id", "id"],
    )
    op.create_check_constraint(
        op.f("ck_content_items_thumb_offset_ms"),
        "content_items",
        "thumb_offset_ms IS NULL OR thumb_offset_ms >= 0",
    )
    op.create_check_constraint(
        op.f("ck_content_items_reel_fields_only"),
        "content_items",
        "content_type = 'reel' OR "
        "(cover_media_asset_id IS NULL AND thumb_offset_ms IS NULL AND share_to_feed IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_content_items_reel_cover_exclusive"),
        "content_items",
        "cover_media_asset_id IS NULL OR thumb_offset_ms IS NULL",
    )
    op.create_check_constraint(
        op.f("ck_content_items_reel_share_to_feed"),
        "content_items",
        "content_type != 'reel' OR share_to_feed IS NOT NULL",
    )

    op.execute(
        sa.text(
            "UPDATE social_accounts SET capabilities = capabilities || "
            "jsonb_build_object('publish_reel', "
            "COALESCE(capabilities->'publish_feed_image', 'false'::jsonb))"
        )
    )

    _sim_checks(True)
    for col, typ in (
        ("cover_url", sa.Text()),
        ("thumb_offset_ms", sa.Integer()),
        ("share_to_feed", sa.Boolean()),
        ("error_subcode", sa.Integer()),
    ):
        op.add_column("sim_containers", sa.Column(col, typ, nullable=True))

    op.add_column("sim_failure_rules", sa.Column("delay_s", sa.Integer(), nullable=True))
    op.add_column("sim_failure_rules", sa.Column("error_subcode", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_sim_failure_rules_delay_s"),
        "sim_failure_rules",
        "delay_s IS NULL OR delay_s >= 0",
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM content_items WHERE content_type = 'reel')")
    ):
        raise RuntimeError("Reel archival is required before downgrade")

    op.execute(sa.text("DELETE FROM sim_containers WHERE media_type = 'REELS'"))
    op.execute(
        sa.text(
            "DELETE FROM sim_failure_rules WHERE operation = 'create_reel_container' "
            "OR mode IN ('slow_processing', 'processing_error')"
        )
    )
    _sim_checks(False)
    op.drop_constraint(op.f("ck_sim_failure_rules_delay_s"), "sim_failure_rules", type_="check")
    op.drop_column("sim_failure_rules", "error_subcode")
    op.drop_column("sim_failure_rules", "delay_s")
    for col in ("error_subcode", "share_to_feed", "thumb_offset_ms", "cover_url"):
        op.drop_column("sim_containers", col)

    op.execute(
        sa.text("UPDATE social_accounts SET capabilities = capabilities - 'publish_reel'")
    )

    op.drop_constraint(
        op.f("ck_content_items_reel_share_to_feed"), "content_items", type_="check"
    )
    op.drop_constraint(
        op.f("ck_content_items_reel_cover_exclusive"), "content_items", type_="check"
    )
    op.drop_constraint(
        op.f("ck_content_items_reel_fields_only"), "content_items", type_="check"
    )
    op.drop_constraint(op.f("ck_content_items_thumb_offset_ms"), "content_items", type_="check")
    op.drop_constraint(
        op.f("fk_content_items_workspace_id_cover_media_asset_id_media_assets"),
        "content_items",
        type_="foreignkey",
    )
    op.drop_column("content_items", "share_to_feed")
    op.drop_column("content_items", "thumb_offset_ms")
    op.drop_column("content_items", "cover_media_asset_id")
    op.drop_constraint(op.f("ck_content_items_content_type"), "content_items", type_="check")
    op.create_check_constraint(
        op.f("ck_content_items_content_type"),
        "content_items",
        "content_type IN ('feed_image', 'story_image', 'feed_carousel')",
    )
