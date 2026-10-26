"""Inbox tables (data-model.md §3.5): ``inbound_events``, ``conversations``, ``messages``,
``reply_drafts``.

Every tenant child references its parent through a composite foreign key
``(workspace_id, parent_id)`` (INV-01). ``inbound_events`` is the one table that may exist
before the workspace is known (an unknown receiving account), so its workspace and account
columns are nullable.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin, WorkspaceScopedMixin

EVENT_TYPES = ("message", "echo", "delete", "reaction", "read", "postback", "other")
EVENT_STATUSES = ("received", "processed", "ignored", "failed")
# Why an event was stored but not processed (observability.md §4.1).
IGNORE_REASONS = ("UNKNOWN_ACCOUNT", "ACCOUNT_DISCONNECTED", "UNSUPPORTED_EVENT")

HANDLING_MODES = ("automatic", "human")
ATTENTION_STATES = ("none", "needs_approval", "needs_human", "failed")
DIRECTIONS = ("inbound", "outbound")
SENDER_KINDS = ("customer", "business_app", "business_native")
DRAFT_SOURCES = ("ai", "approved_answer", "owner")
DRAFT_DECISIONS = ("auto", "approval_required", "human_required", "blocked")
DRAFT_STATUSES = (
    "pending_approval",
    "needs_human",
    "queued",
    "sending",
    "outcome_unknown",
    "sent",
    "failed",
    "rejected",
    "expired",
    "superseded",
    "cancelled",
    "blocked",
)
# At most one of these per conversation (the "open draft").
OPEN_DRAFT_STATUSES = ("pending_approval", "needs_human", "queued", "sending", "outcome_unknown")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class InboundEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "inbound_events"
    __table_args__ = (
        UniqueConstraint("dedup_key"),
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(_in("provider_kind", ("mock", "meta")), name="provider_kind"),
        CheckConstraint(_in("event_type", EVENT_TYPES), name="event_type"),
        CheckConstraint(_in("status", EVENT_STATUSES), name="status"),
        CheckConstraint(
            f"ignore_reason IS NULL OR {_in('ignore_reason', IGNORE_REASONS)}",
            name="ignore_reason",
        ),
        Index("ix_inbound_events_status_received", "status", "received_at"),
        Index("ix_inbound_events_workspace_received", "workspace_id", "received_at"),
    )

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    social_account_id: Mapped[uuid.UUID | None] = mapped_column()
    provider_kind: Mapped[str] = mapped_column(Text, nullable=False)
    dedup_key: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    # The single webhook item (never the whole body). Nulled by the retention job after 30 days.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="received")
    ignore_reason: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "social_account_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("social_account_id", "customer_external_id"),
        CheckConstraint(_in("handling_mode", HANDLING_MODES), name="handling_mode"),
        CheckConstraint(_in("attention", ATTENTION_STATES), name="attention"),
        Index(
            "ix_conversations_attention",
            "workspace_id",
            "attention",
            sql_text("last_message_at DESC"),
        ),
    )

    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    customer_external_id: Mapped[str] = mapped_column(Text, nullable=False)
    customer_handle: Mapped[str | None] = mapped_column(Text)
    handling_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="automatic")
    attention: Mapped[str] = mapped_column(Text, nullable=False, server_default="none")
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_outbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class Message(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
            ondelete="CASCADE",
        ),
        # A draft and its message reference each other; this side is added after both exist.
        ForeignKeyConstraint(
            ["workspace_id", "reply_draft_id"],
            ["reply_drafts.workspace_id", "reply_drafts.id"],
            name="fk_messages_reply_draft",
            use_alter=True,
        ),
        CheckConstraint(_in("direction", DIRECTIONS), name="direction"),
        CheckConstraint(_in("sender_kind", SENDER_KINDS), name="sender_kind"),
        # INV-06: one row per provider message id and account.
        Index(
            "uq_messages_account_external_id",
            "social_account_id",
            "external_message_id",
            unique=True,
            postgresql_where=sql_text("external_message_id IS NOT NULL"),
        ),
        Index("ix_messages_conversation_time", "conversation_id", "provider_timestamp"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    sender_kind: Mapped[str] = mapped_column(Text, nullable=False)
    external_message_id: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")
    )
    provider_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reply_draft_id: Mapped[uuid.UUID | None] = mapped_column()
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReplyDraft(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "reply_drafts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "covers_through_message_id"],
            ["messages.workspace_id", "messages.id"],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "approval_id"], ["approvals.workspace_id", "approvals.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "agent_run_id"], ["agent_runs.workspace_id", "agent_runs.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "agent_action_id"], ["agent_actions.workspace_id", "agent_actions.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "operation_id"], ["operations.workspace_id", "operations.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "superseded_by_id"],
            ["reply_drafts.workspace_id", "reply_drafts.id"],
        ),
        CheckConstraint(_in("source", DRAFT_SOURCES), name="source"),
        CheckConstraint(_in("origin", ("legacy", "agent")), name="origin"),
        CheckConstraint(
            "(origin = 'legacy' AND agent_action_id IS NULL) OR "
            "(origin = 'agent' AND agent_action_id IS NOT NULL)",
            name="agent_origin",
        ),
        CheckConstraint(_in("decision", DRAFT_DECISIONS), name="decision"),
        CheckConstraint(_in("status", DRAFT_STATUSES), name="status"),
        CheckConstraint("version >= 1", name="version"),
        # One open draft per conversation (workflows.md §C).
        Index(
            "uq_reply_drafts_open_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=sql_text(
                f"status IN ({', '.join(repr(s) for s in OPEN_DRAFT_STATUSES)})"
            ),
        ),
        # Idempotent manual replies: one draft per author and client request.
        Index(
            "uq_reply_drafts_client_request",
            "workspace_id",
            "created_by_actor_id",
            "client_request_id",
            unique=True,
            postgresql_where=sql_text("client_request_id IS NOT NULL"),
        ),
        Index("ix_reply_drafts_conversation_created", "conversation_id", "created_at"),
        Index("ix_reply_drafts_status", "status"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    covers_through_message_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False, server_default="legacy")
    agent_action_id: Mapped[uuid.UUID | None] = mapped_column()
    language: Mapped[str | None] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(Text)
    flags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=sql_text("'{}'")
    )
    template: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    # A failed grounding keeps the marked-up text here; it is never sendable (INV-02).
    suggestion_text: Mapped[str | None] = mapped_column(Text)
    validation: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")
    )
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    decision_reasons: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=sql_text("'{}'")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql_text("1"))
    approval_id: Mapped[uuid.UUID | None] = mapped_column()
    operation_id: Mapped[uuid.UUID | None] = mapped_column()
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column()
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column()
    # The reason code of a terminal state other than ``sent``: failed, superseded, cancelled,
    # expired (e.g. NEW_INBOUND, FACT_CHANGED, OUTCOME_UNCONFIRMED).
    failure_code: Mapped[str | None] = mapped_column(Text)
    created_by_actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_actor_id: Mapped[str | None] = mapped_column(Text)
    client_request_id: Mapped[str | None] = mapped_column(Text)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
