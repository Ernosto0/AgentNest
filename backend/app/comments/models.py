"""Public sources retain terminal tombstones; identities never join private customers."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPrimaryKeyMixin, WorkspaceScopedMixin


def scope() -> tuple[UniqueConstraint, UniqueConstraint, ForeignKeyConstraint]:
    return (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "social_account_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
        ),
    )


class PublicMedia(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "public_media"
    __table_args__ = (
        *scope(),
        UniqueConstraint("social_account_id", "external_id"),
        CheckConstraint("state IN ('unknown','visible','deleted')", name="state"),
        CheckConstraint("version >= 1 AND provider_version >= 0", name="versions"),
    )
    social_account_id: Mapped[uuid.UUID]
    external_id: Mapped[str] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text, default="unknown")
    ownership_state: Mapped[str] = mapped_column(Text, default="unverified")
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    provider_version: Mapped[int] = mapped_column(BigInteger, default=0)
    provider_timestamp: Mapped[datetime | None]
    updated_at: Mapped[datetime]
    is_simulated: Mapped[bool] = mapped_column(Boolean)


class PublicThread(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "public_threads"
    __table_args__ = (
        *scope(),
        UniqueConstraint("social_account_id", "root_external_id"),
        Index(
            "ix_public_threads_media_page", "workspace_id", "social_account_id", "media_id", "id"
        ),
        UniqueConstraint("workspace_id", "social_account_id", "media_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "media_id"],
            ["public_media.workspace_id", "public_media.social_account_id", "public_media.id"],
        ),
    )
    social_account_id: Mapped[uuid.UUID]
    media_id: Mapped[uuid.UUID]
    root_external_id: Mapped[str] = mapped_column(Text)


class PublicComment(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "public_comments"
    __table_args__ = (
        *scope(),
        UniqueConstraint("social_account_id", "external_id"),
        Index(
            "ix_public_comments_thread_page", "workspace_id", "social_account_id", "thread_id", "id"
        ),
        UniqueConstraint("workspace_id", "social_account_id", "media_id", "thread_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "media_id", "thread_id"],
            [
                "public_threads.workspace_id",
                "public_threads.social_account_id",
                "public_threads.media_id",
                "public_threads.id",
            ],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "media_id", "thread_id", "parent_id"],
            [
                "public_comments.workspace_id",
                "public_comments.social_account_id",
                "public_comments.media_id",
                "public_comments.thread_id",
                "public_comments.id",
            ],
        ),
        CheckConstraint("state IN ('unknown','visible','hidden','deleted')", name="state"),
        CheckConstraint("version >= 0 AND provider_version >= 0", name="versions"),
    )
    social_account_id: Mapped[uuid.UUID]
    media_id: Mapped[uuid.UUID]
    thread_id: Mapped[uuid.UUID]
    external_id: Mapped[str] = mapped_column(Text)
    parent_id: Mapped[uuid.UUID | None]
    author_external_id: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text, default="unknown")
    version: Mapped[int] = mapped_column(BigInteger, default=0)
    provider_version: Mapped[int] = mapped_column(BigInteger, default=0)
    provider_timestamp: Mapped[datetime | None]
    updated_at: Mapped[datetime]
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean)


class SimPublicComment(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    """Remote mock state, separate from received application sources."""

    __tablename__ = "sim_public_comments"
    __table_args__ = (*scope(), UniqueConstraint("social_account_id", "external_id"))
    social_account_id: Mapped[uuid.UUID]
    external_id: Mapped[str] = mapped_column(Text)
    value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime]


class PublicCommentAction(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    """Exact, version-bound public effect. Body is kept only for a pending reply."""

    __tablename__ = "public_comment_actions"
    __table_args__ = (
        *scope(),
        UniqueConstraint("agent_action_id"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "comment_id"],
            [
                "public_comments.workspace_id",
                "public_comments.social_account_id",
                "public_comments.id",
            ],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "agent_action_id"],
            ["agent_actions.workspace_id", "agent_actions.social_account_id", "agent_actions.id"],
        ),
        CheckConstraint("effect IN ('reply','hide','unhide','delete')", name="effect"),
    )
    social_account_id: Mapped[uuid.UUID]
    comment_id: Mapped[uuid.UUID]
    agent_action_id: Mapped[uuid.UUID]
    effect: Mapped[str] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    proposal: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    comment_version: Mapped[int] = mapped_column(BigInteger)
    media_version: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime]


class SimCommentEffect(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    """Mock provider evidence, independent of application operation state."""

    __tablename__ = "sim_comment_effects"
    __table_args__ = (
        *scope(),
        UniqueConstraint("social_account_id", "operation_key"),
    )
    social_account_id: Mapped[uuid.UUID]
    operation_key: Mapped[str] = mapped_column(Text)
    target_external_id: Mapped[str] = mapped_column(Text)
    effect: Mapped[str] = mapped_column(Text)
    provider_id: Mapped[str] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]


class PrivateReplyOpportunity(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    """One reserved private reply per source comment, including unknown outcomes."""

    __tablename__ = "private_reply_opportunities"
    __table_args__ = (
        *scope(),
        UniqueConstraint("social_account_id", "comment_id"),
        UniqueConstraint("agent_action_id"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "comment_id"],
            [
                "public_comments.workspace_id",
                "public_comments.social_account_id",
                "public_comments.id",
            ],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "agent_action_id"],
            ["agent_actions.workspace_id", "agent_actions.social_account_id", "agent_actions.id"],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "bound_conversation_id"],
            ["conversations.workspace_id", "conversations.social_account_id", "conversations.id"],
        ),
        CheckConstraint(
            "status IN ('reserved','succeeded','outcome_unknown','failed','cancelled')",
            name="status",
        ),
    )
    social_account_id: Mapped[uuid.UUID]
    comment_id: Mapped[uuid.UUID]
    agent_action_id: Mapped[uuid.UUID]
    comment_version: Mapped[int] = mapped_column(BigInteger)
    media_version: Mapped[int] = mapped_column(BigInteger)
    text: Mapped[str | None] = mapped_column(Text)
    proposal: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text)
    eligibility_expires_at: Mapped[datetime]
    provider_reply_id: Mapped[str | None] = mapped_column(Text)
    provider_recipient_id: Mapped[str | None] = mapped_column(Text)
    bound_conversation_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime]


class SimPrivateReply(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    """Independent mock provider record for private-reply readback."""

    __tablename__ = "sim_private_replies"
    __table_args__ = (
        *scope(),
        UniqueConstraint("social_account_id", "comment_external_id"),
        UniqueConstraint("social_account_id", "operation_key"),
    )
    social_account_id: Mapped[uuid.UUID]
    comment_external_id: Mapped[str] = mapped_column(Text)
    operation_key: Mapped[str] = mapped_column(Text)
    provider_reply_id: Mapped[str] = mapped_column(Text)
    recipient_external_id: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]
