"""Identity tables (data-model.md §3.1): users, sessions, workspaces, workspace_members."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin, WorkspaceScopedMixin

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
