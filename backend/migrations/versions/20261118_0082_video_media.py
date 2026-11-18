"""Video media assets. Revision 0082, parent 0081."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0082"
down_revision: str | None = "0081"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIDEO_FIELDS_CHECK = """(kind = 'video' AND duration_ms IS NOT NULL AND duration_ms > 0
AND video_codec IS NOT NULL AND container IS NOT NULL AND container IN ('mp4','mov')
AND frame_rate IS NOT NULL AND frame_rate > 0) OR
(kind != 'video' AND duration_ms IS NULL AND video_codec IS NULL AND audio_codec IS NULL
AND frame_rate IS NULL AND bitrate_bps IS NULL AND container IS NULL
AND video_warnings IS NULL AND thumbnail_media_asset_id IS NULL)"""


def upgrade() -> None:
    op.add_column(
        "media_assets", sa.Column("kind", sa.Text(), nullable=False, server_default="image")
    )
    for name, typ in (
        ("duration_ms", sa.Integer()),
        ("video_codec", sa.Text()),
        ("audio_codec", sa.Text()),
        ("frame_rate", sa.Numeric(7, 3)),
        ("bitrate_bps", sa.BigInteger()),
        ("container", sa.Text()),
        ("video_warnings", postgresql.JSONB()),
        ("thumbnail_media_asset_id", sa.Uuid()),
    ):
        op.add_column("media_assets", sa.Column(name, typ, nullable=True))
    op.create_check_constraint(
        op.f("ck_media_assets_kind"),
        "media_assets",
        "kind IN ('image', 'video', 'video_thumbnail')",
    )
    op.create_check_constraint(
        op.f("ck_media_assets_video_fields"), "media_assets", VIDEO_FIELDS_CHECK
    )
    op.create_foreign_key(
        op.f("fk_media_assets_workspace_id_thumbnail_media_asset_id_media_assets"),
        "media_assets",
        "media_assets",
        ["workspace_id", "thumbnail_media_asset_id"],
        ["workspace_id", "id"],
    )
    op.create_index("ix_media_assets_workspace_kind", "media_assets", ["workspace_id", "kind"])


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM media_assets WHERE kind != 'image')"))
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade 0082 while non-image media assets exist")
    op.drop_index("ix_media_assets_workspace_kind", table_name="media_assets")
    op.drop_constraint(
        op.f("fk_media_assets_workspace_id_thumbnail_media_asset_id_media_assets"),
        "media_assets",
        type_="foreignkey",
    )
    op.drop_constraint(op.f("ck_media_assets_video_fields"), "media_assets", type_="check")
    op.drop_constraint(op.f("ck_media_assets_kind"), "media_assets", type_="check")
    for name in (
        "thumbnail_media_asset_id",
        "video_warnings",
        "container",
        "bitrate_bps",
        "frame_rate",
        "audio_codec",
        "video_codec",
        "duration_ms",
        "kind",
    ):
        op.drop_column("media_assets", name)
