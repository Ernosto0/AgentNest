"""Identity tables (data-model.md §3.1): users, sessions, workspaces, workspace_members."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    WorkspaceScopedMixin,
    workspace_unique_constraint,
)

ROLES = ("owner", "manager", "staff")
LOCALES = ("tr", "en")
# ADR-023: every small business on Instagram; the category only selects an optional preset.
BUSINESS_CATEGORIES = (
    "beauty_wellness",
    "food_beverage",
    "retail",
    "fitness",
    "health_clinic",
    "education",
    "hospitality",
    "services",
    "other",
)
MARKETS = ("tr", "global")
WORKSPACE_STATUSES = ("active", "deleting")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(btrim(email))", name="email_normalised"),
        CheckConstraint(_in("ui_locale", LOCALES), name="ui_locale"),
    )

    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    ui_locale: Mapped[str] = mapped_column(Text, nullable=False, server_default="tr")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sessions"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(Text)


IDENTIFIER_TYPES = ("email", "ip")


class LoginThrottle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "login_throttles"
    __table_args__ = (
        CheckConstraint(_in("identifier_type", IDENTIFIER_TYPES), name="identifier_type"),
        UniqueConstraint("identifier_type", "identifier_hash"),
    )

    identifier_type: Mapped[str] = mapped_column(Text, nullable=False)
    identifier_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    first_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class Workspace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"
    __table_args__ = (
        CheckConstraint(_in("business_category", BUSINESS_CATEGORIES), name="business_category"),
        CheckConstraint(_in("market", MARKETS), name="market"),
        CheckConstraint(_in("default_locale", LOCALES), name="default_locale"),
        CheckConstraint(_in("status", WORKSPACE_STATUSES), name="status"),
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug_format"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_format"),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    business_category: Mapped[str] = mapped_column(Text, nullable=False)
    market: Mapped[str] = mapped_column(Text, nullable=False)
    default_locale: Mapped[str] = mapped_column(Text, nullable=False)
    reply_languages: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{tr}'")
    )
    timezone: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deletion_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deletion_requested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (CheckConstraint(_in("role", ROLES), name="role"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Invite(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    """``invites`` (data-model.md §3.1): a one-time membership link. Only the sha256 of the
    token is stored; the token itself is returned once, at creation."""

    __tablename__ = "invites"
    __table_args__ = (
        CheckConstraint(_in("role", ROLES), name="role"),
        UniqueConstraint("token_hash"),
    )

    role: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PasswordResetToken(UUIDPrimaryKeyMixin, Base):
    """Global user-scoped password reset tokens (ADR-025 §1.3, Category A)."""

    __tablename__ = "password_reset_tokens"
    __table_args__ = (UniqueConstraint("token_hash"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


CHANNEL_TYPES = ("telegram",)
CHANNEL_LINK_STATUSES = ("active", "unlinked")


class ChannelLink(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, TimestampMixin, Base):
    """``channel_links``: owner messaging channel identity linking (ADR-012, Phase 9)."""

    __tablename__ = "channel_links"
    __table_args__ = (
        workspace_unique_constraint(),
        CheckConstraint(_in("channel", CHANNEL_TYPES), name="channel"),
        CheckConstraint(_in("status", CHANNEL_LINK_STATUSES), name="status"),
        Index(
            "uq_channel_links_active_channel_user",
            "channel",
            "channel_user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "uq_channel_links_active_workspace_user_channel",
            "workspace_id",
            "user_id",
            "channel",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    channel_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    channel_chat_id: Mapped[str] = mapped_column(Text, nullable=False)
    channel_username: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    unlinked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChannelLinkCode(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    """``channel_link_codes``: one-time linking codes for owner channels (ADR-012, Phase 9)."""

    __tablename__ = "channel_link_codes"
    __table_args__ = (
        workspace_unique_constraint(),
        CheckConstraint(_in("channel", CHANNEL_TYPES), name="channel"),
        Index("ix_channel_link_codes_code_hash", "code_hash"),
        Index("ix_channel_link_codes_workspace_user", "workspace_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
