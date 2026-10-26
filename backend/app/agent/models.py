"""Phase 7.5 durable agent state. Personal bodies remain in domain tables."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin, WorkspaceScopedMixin

RUN_STATES = (
    "queued",
    "running",
    "waiting_customer",
    "waiting_owner",
    "waiting_approval",
    "waiting_operation",
    "sleeping",
    "completed",
    "cancelled",
    "failed",
)
ACTIVE_RUN_STATES = RUN_STATES[:-3]
STEP_STATES = (
    "claimed",
    "model_pending",
    "model_done",
    "dispatched",
    "consumed",
    "stale",
    "abandoned",
    "failed",
)
ACTION_STATES = (
    "proposed",
    "waiting_approval",
    "authorized",
    "queued",
    "in_progress",
    "succeeded",
    "failed",
    "outcome_unknown",
    "cancelled",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class AccountAgent(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "account_agents"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "social_account_id"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(_in("controller_mode", ("legacy", "agent")), name="controller_mode"),
        CheckConstraint(_in("state", ("inactive", "active", "paused")), name="state"),
        CheckConstraint("controller_epoch >= 0", name="controller_epoch"),
        CheckConstraint("config_version >= 1 AND persona_version >= 1", name="versions"),
    )

    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    controller_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="legacy")
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="inactive")
    controller_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    persona_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    goals: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    persona: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class AgentDelegation(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "agent_delegations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "social_account_id", "version"),
        UniqueConstraint("workspace_id", "social_account_id", "client_request_id"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["account_agents.workspace_id", "account_agents.social_account_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("policy_hash ~ '^[0-9a-f]{64}$'", name="policy_hash"),
        Index(
            "uq_agent_delegations_current",
            "workspace_id",
            "social_account_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    grantor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    policy: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    policy_hash: Mapped[str] = mapped_column(Text, nullable=False)
    client_request_id: Mapped[uuid.UUID | None] = mapped_column()
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentThread(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "agent_threads"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "social_account_id", "id"),
        UniqueConstraint("workspace_id", "social_account_id", "surface", "source_ref"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["account_agents.workspace_id", "account_agents.social_account_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "dm_conversation_id"],
            ["conversations.workspace_id", "conversations.social_account_id", "conversations.id"],
        ),
        CheckConstraint(_in("surface", ("dm", "comment", "owner_task")), name="surface"),
        CheckConstraint(_in("state", RUN_STATES), name="state"),
        CheckConstraint(_in("handling_mode", ("agent", "human")), name="handling_mode"),
        CheckConstraint(
            "thread_version >= 1 AND event_cursor >= 0 AND controller_epoch >= 0 "
            "AND deletion_generation >= 0",
            name="versions",
        ),
        Index(
            "ix_agent_threads_account_state_activity",
            "workspace_id",
            "social_account_id",
            "state",
            "last_activity_at",
        ),
    )

    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    surface: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)
    dm_conversation_id: Mapped[uuid.UUID | None] = mapped_column()
    customer_identity_id: Mapped[uuid.UUID | None] = mapped_column()
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    handling_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="agent")
    thread_version: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="1")
    event_cursor: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    controller_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    deletion_generation: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    current_goal_key: Mapped[str | None] = mapped_column(Text)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentEvent(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "agent_events"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "thread_id", "id"),
        UniqueConstraint("workspace_id", "social_account_id", "source_kind", "source_key"),
        UniqueConstraint("workspace_id", "thread_id", "cursor"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "thread_id"],
            ["agent_threads.workspace_id", "agent_threads.social_account_id", "agent_threads.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("cursor >= 1 AND source_version >= 1", name="versions"),
        Index("ix_agent_events_thread_cursor", "workspace_id", "thread_id", "cursor"),
    )

    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    thread_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    cursor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str | None] = mapped_column(Text)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentSession(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "agent_sessions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "thread_id", "id"),
        UniqueConstraint("workspace_id", "thread_id", "goal_key"),
        ForeignKeyConstraint(
            ["workspace_id", "thread_id"],
            ["agent_threads.workspace_id", "agent_threads.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(_in("status", RUN_STATES), name="status"),
        CheckConstraint("version >= 1 AND initiating_event_cursor >= 0", name="versions"),
        CheckConstraint(
            "model_steps >= 0 AND tool_calls >= 0 AND input_tokens >= 0 "
            "AND output_tokens >= 0 AND cost_microusd >= 0",
            name="usage",
        ),
        Index(
            "uq_agent_sessions_active_thread",
            "workspace_id",
            "thread_id",
            unique=True,
            postgresql_where=text(_in("status", ACTIVE_RUN_STATES)),
        ),
    )

    thread_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    initiating_event_cursor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    goal_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="1")
    model_steps: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    cost_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    wake_kind: Mapped[str | None] = mapped_column(Text)
    wake_ref: Mapped[str | None] = mapped_column(Text)
    wake_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentStep(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "agent_steps"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "session_id", "sequence"),
        UniqueConstraint("claim_token"),
        ForeignKeyConstraint(
            ["workspace_id", "session_id"],
            ["agent_sessions.workspace_id", "agent_sessions.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(_in("status", STEP_STATES), name="status"),
        CheckConstraint(
            "sequence >= 1 AND captured_cursor >= 0 AND captured_epoch >= 0 "
            "AND captured_deletion_generation >= 0",
            name="versions",
        ),
        CheckConstraint(
            "reserved_tokens >= 0 AND input_tokens >= 0 AND output_tokens >= 0", name="usage"
        ),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="claimed")
    claim_token: Mapped[uuid.UUID] = mapped_column(nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_cursor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    captured_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    captured_policy_version: Mapped[int | None] = mapped_column(Integer)
    captured_deletion_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    model_version: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    tool_version: Mapped[str | None] = mapped_column(Text)
    input_ref: Mapped[str | None] = mapped_column(Text)
    output_ref: Mapped[str | None] = mapped_column(Text)
    reserved_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")


class AgentAction(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "agent_actions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "social_account_id", "id"),
        UniqueConstraint("workspace_id", "thread_id", "intent_key"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "thread_id"],
            ["agent_threads.workspace_id", "agent_threads.social_account_id", "agent_threads.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "thread_id", "session_id"],
            ["agent_sessions.workspace_id", "agent_sessions.thread_id", "agent_sessions.id"],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "thread_id", "initiating_event_id"],
            ["agent_events.workspace_id", "agent_events.thread_id", "agent_events.id"],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "approval_id"],
            ["approvals.workspace_id", "approvals.id"],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "operation_id"],
            ["operations.workspace_id", "operations.social_account_id", "operations.id"],
        ),
        CheckConstraint(_in("status", ACTION_STATES), name="status"),
        CheckConstraint("version >= 1 AND initiating_cursor >= 0", name="versions"),
        CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="payload_hash"),
        Index(
            "ix_agent_actions_daily_authority",
            "workspace_id",
            "social_account_id",
            "action_type",
            "authorized_at",
        ),
    )

    thread_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    intent_key: Mapped[str] = mapped_column(Text, nullable=False)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload_ref: Mapped[uuid.UUID | None] = mapped_column()
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    target_ref: Mapped[str] = mapped_column(Text, nullable=False)
    initiating_event_id: Mapped[uuid.UUID | None] = mapped_column()
    initiating_cursor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="proposed")
    delegation_version: Mapped[int | None] = mapped_column(Integer)
    policy_grant: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    approval_id: Mapped[uuid.UUID | None] = mapped_column()
    operation_id: Mapped[uuid.UUID | None] = mapped_column()
    execute_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome_code: Mapped[str | None] = mapped_column(Text)
