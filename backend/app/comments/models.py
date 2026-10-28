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
