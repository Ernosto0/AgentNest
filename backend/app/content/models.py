"""Content tables (data-model.md §3.6): ``media_assets`` and ``content_items``.

Every tenant child references its parent through a composite foreign key
``(workspace_id, parent_id)`` (INV-01).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import CHAR, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin, WorkspaceScopedMixin

MEDIA_STATUSES = ("uploaded", "ready", "rejected", "deleted")
CONTENT_TYPES = ("feed_image", "story_image")
# state-machines.md section 5.
CONTENT_STATUSES = (
    "draft",
    "pending_approval",
    "scheduled",
    "publishing",
    "retry_scheduled",
    "on_hold",
    "published",
    "rejected",
    "failed",
    "cancelled",
)


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


class ContentItem(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    """A planned Instagram post. ``status`` changes only through ``content.transitions.apply``."""

    __tablename__ = "content_items"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "media_asset_id"],
            ["media_assets.workspace_id", "media_assets.id"],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "approval_id"], ["approvals.workspace_id", "approvals.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "agent_run_id"], ["agent_runs.workspace_id", "agent_runs.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "agent_action_id"],
            ["agent_actions.workspace_id", "agent_actions.social_account_id", "agent_actions.id"],
        ),
        # Idempotent creation: one item per author and client request (plan.md G7).
        UniqueConstraint(
            "workspace_id",
            "created_by_user_id",
            "client_request_id",
            name="uq_content_items_client_request",
        ),
        CheckConstraint(_in("content_type", CONTENT_TYPES), name="content_type"),
        CheckConstraint(_in("status", CONTENT_STATUSES), name="status"),
        CheckConstraint("origin IN ('legacy', 'agent')", name="origin"),
        CheckConstraint(
            "(origin = 'legacy' AND agent_action_id IS NULL) OR "
            "(origin = 'agent' AND agent_action_id IS NOT NULL AND social_account_id IS NOT NULL)",
            name="agent_origin",
        ),
        CheckConstraint("version >= 1", name="version"),
        Index(
            "ix_content_items_workspace_status_scheduled", "workspace_id", "status", "scheduled_at"
        ),
    )

    social_account_id: Mapped[uuid.UUID | None] = mapped_column()  # required at submit
    origin: Mapped[str] = mapped_column(Text, nullable=False, server_default="legacy")
    agent_action_id: Mapped[uuid.UUID | None] = mapped_column()
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # Increments on every payload change (caption, overlay suggestions, media) and on re-approval.
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql_text("1"))
    title: Mapped[str] = mapped_column(Text, nullable=False)  # internal label
    objective: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)  # the rendered text (plan.md G6)
    overlay_text_suggestions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )
    visual_notes: Mapped[str | None] = mapped_column(Text)
    media_asset_id: Mapped[uuid.UUID | None] = mapped_column()
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    schedule_input: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    approval_id: Mapped[uuid.UUID | None] = mapped_column()  # the current (or latest) approval
    hold_reason: Mapped[str | None] = mapped_column(Text)
    rejection_note: Mapped[str | None] = mapped_column(Text)
    validation: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_media_id: Mapped[str | None] = mapped_column(Text)
    external_permalink: Mapped[str | None] = mapped_column(Text)
    last_error_code: Mapped[str | None] = mapped_column(Text)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column()
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    client_request_id: Mapped[str | None] = mapped_column(Text)
    is_simulated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("false")
    )
