"""Content tables (data-model.md §3.6): ``media_assets`` now, ``content_items`` in P5-02."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import CHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin, WorkspaceScopedMixin

MEDIA_STATUSES = ("uploaded", "ready", "rejected", "deleted")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class MediaAsset(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    """An uploaded image, already validated and re-encoded as a baseline sRGB JPEG."""

    __tablename__ = "media_assets"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("storage_backend", "storage_key"),
        CheckConstraint(_in("status", MEDIA_STATUSES), name="status"),
        CheckConstraint("byte_size >= 0 AND width > 0 AND height > 0", name="dimensions"),
    )

    storage_backend: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(Text)  # sanitised; display only
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)  # after conversion
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)  # of the stored output
    status: Mapped[str] = mapped_column(Text, nullable=False)
    rejection_code: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
