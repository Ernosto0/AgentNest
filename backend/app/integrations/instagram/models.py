"""Tables owned by the Instagram integration (data-model.md §3.7 and §3.9).

``social_accounts`` is the connection; ``sim_*`` tables are the stateful simulator behind the
mock provider (ADR-010) and are written **only** by ``MockInstagramProvider`` and the
simulator that builds its inbound webhooks. A real provider never touches them.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin, WorkspaceScopedMixin

PLATFORMS = ("instagram",)
PROVIDER_KINDS = ("mock", "meta")
ACCOUNT_STATUSES = ("connected", "needs_reauth", "degraded", "disconnected")
# `lookup` is the conversation lookup used by reconciliation (`find_recent_outbound`).
FAILURE_OPERATIONS = (
    "send",
    "lookup",
    "echo",
    "create_container",
    "container_status",
    "publish",
    "refresh",
    "profile",
    "any",
)
CONTAINER_MEDIA_TYPES = ("IMAGE", "STORIES")
CONTAINER_STATUSES = ("IN_PROGRESS", "FINISHED", "ERROR", "EXPIRED", "PUBLISHED")
FAILURE_MODES = (
    "transient",
    "rate_limited",
    "auth_revoked",
    "permission_missing",
    "invalid_media",
    "timeout_after_success",
    "window_closed",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class SocialAccount(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "social_accounts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        CheckConstraint(_in("platform", PLATFORMS), name="platform"),
        CheckConstraint(_in("provider_kind", PROVIDER_KINDS), name="provider_kind"),
        CheckConstraint(_in("status", ACCOUNT_STATUSES), name="status"),
        CheckConstraint("consecutive_failures >= 0", name="consecutive_failures"),
        # Only a real (Meta) connection holds a token; the mock never has one (INV-10).
        CheckConstraint("provider_kind = 'meta' OR token_ciphertext IS NULL", name="mock_no_token"),
        # One active account per workspace, and one workspace per external account.
        Index(
            "uq_social_accounts_active_workspace",
            "workspace_id",
            unique=True,
            postgresql_where=text("status <> 'disconnected'"),
        ),
        Index(
            "uq_social_accounts_active_external",
            "provider_kind",
            "external_account_id",
            unique=True,
            postgresql_where=text("status <> 'disconnected'"),
        ),
    )

    platform: Mapped[str] = mapped_column(Text, nullable=False, server_default="instagram")
    provider_kind: Mapped[str] = mapped_column(Text, nullable=False)
    external_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="connected")
    capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    granted_scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    token_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    token_key_id: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    degraded_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Start of the window the circuit breaker counts transient failures in (plan H10).
    failure_window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(Text)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_simulated(self) -> bool:
        """INV-09: derived from the provider kind and copied to every row the account yields."""
        return self.provider_kind == "mock"


class OAuthState(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    """Hashed, user-bound single-use authorization, invalidated by disconnect."""

    __tablename__ = "oauth_states"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("state_hash"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("purpose IN ('connect', 'reconnect')", name="purpose"),
        CheckConstraint(
            "(purpose = 'connect' AND social_account_id IS NULL) OR "
            "(purpose = 'reconnect' AND social_account_id IS NOT NULL)",
            name="purpose_account",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    state_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    social_account_id: Mapped[uuid.UUID | None] = mapped_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SimInboundMessage(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    """A customer message the simulator delivered. The mock derives the 24 h messaging window
    from these rows, independently of the application's own ``messages`` table."""

    __tablename__ = "sim_inbound_messages"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("social_account_id", "mid"),
        Index("ix_sim_inbound_account_sender", "social_account_id", "sender_id", "received_at"),
    )

    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    sender_id: Mapped[str] = mapped_column(Text, nullable=False)
    mid: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SimSentMessage(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    """What the mock "sent" to a customer: the evidence that exactly one message went out."""

    __tablename__ = "sim_sent_messages"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("message_id"),
        Index("ix_sim_sent_account_recipient", "social_account_id", "recipient_id", "sent_at"),
    )

    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    message_id: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_id: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SimFailureRule(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    """A scripted failure for the mock: the next ``remaining`` matching calls fail in ``mode``."""

    __tablename__ = "sim_failure_rules"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(_in("operation", FAILURE_OPERATIONS), name="operation"),
        CheckConstraint(_in("mode", FAILURE_MODES), name="mode"),
        CheckConstraint("remaining IS NULL OR remaining >= 0", name="remaining"),
        Index("ix_sim_failure_rules_account", "social_account_id"),
    )

    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    remaining: Mapped[int | None] = mapped_column(Integer)  # NULL = every matching call
    retry_after_s: Mapped[int | None] = mapped_column(Integer)


class SimContainer(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    """A media container the mock created. ``status`` stores only what the provider decided
    (``IN_PROGRESS``, then ``ERROR`` or ``PUBLISHED``); ``FINISHED`` and ``EXPIRED`` are derived
    from ``ready_at`` / ``expires_at`` and the injected clock when it is read."""

    __tablename__ = "sim_containers"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("container_id"),
        CheckConstraint(_in("media_type", CONTAINER_MEDIA_TYPES), name="media_type"),
        CheckConstraint(_in("status", CONTAINER_STATUSES), name="status"),
        Index("ix_sim_containers_account", "social_account_id", "created_at"),
    )

    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    container_id: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    media_url: Mapped[str] = mapped_column(Text, nullable=False)
    caption: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="IN_PROGRESS")
    ready_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_media_id: Mapped[str | None] = mapped_column(Text)


class SimPublishedMedia(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    """What the mock "published": the evidence that exactly one post went out. ``container_id``
    is unique, so a container can never publish twice (a duplicate is a database error)."""

    __tablename__ = "sim_published_media"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("container_id"),
        UniqueConstraint("media_id"),
        Index("ix_sim_published_account", "social_account_id", "published_at"),
    )

    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    media_id: Mapped[str] = mapped_column(Text, nullable=False)
    container_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sim_containers.container_id", ondelete="CASCADE"), nullable=False
    )
    permalink: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
