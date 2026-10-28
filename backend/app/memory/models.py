"""Account-scoped bodies and content-free generation/source tombstones."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPrimaryKeyMixin, WorkspaceScopedMixin


def identity_fk() -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["workspace_id", "social_account_id", "customer_identity_id"],
        [
            "customer_identities.workspace_id",
            "customer_identities.social_account_id",
            "customer_identities.id",
        ],
    )


class CustomerIdentity(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "customer_identities"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "social_account_id", "id"),
        UniqueConstraint("workspace_id", "social_account_id", "provider_subject_hash"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
        ),
        CheckConstraint("generation >= 0 AND revision >= 0", name="versions"),
    )
    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    provider_subject_hash: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_kind: Mapped[str] = mapped_column(Text, nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    source_cutoff: Mapped[datetime | None]
    created_at: Mapped[datetime]


class SourceFence(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "customer_source_fences"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "social_account_id", "customer_identity_id", "source_key"),
        identity_fk(),
    )
    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    customer_identity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    source_key: Mapped[str] = mapped_column(Text, nullable=False)


class CustomerMemory(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "customer_memories"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "social_account_id", "customer_identity_id", "id"),
        UniqueConstraint("workspace_id", "social_account_id", "customer_identity_id", "topic"),
        identity_fk(),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("kind IN ('preference','customer_claim','open_goal')", name="kind"),
        CheckConstraint(
            "topic IN ('size','schedule','service','language','contact')", name="topic"
        ),
    )
    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    customer_identity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="1")
    source_cutoff: Mapped[datetime | None]
    updated_at: Mapped[datetime]
    expires_at: Mapped[datetime]


class MemoryVersion(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "customer_memory_versions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "memory_id", "version"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "customer_identity_id", "memory_id"],
            [
                "customer_memories.workspace_id",
                "customer_memories.social_account_id",
                "customer_memories.customer_identity_id",
                "customer_memories.id",
            ],
        ),
    )
    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    customer_identity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    memory_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[str] = mapped_column(Text, nullable=False)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime]


class MemorySource(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "customer_memory_sources"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "memory_id", "source_key"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "customer_identity_id", "memory_id"],
            [
                "customer_memories.workspace_id",
                "customer_memories.social_account_id",
                "customer_memories.customer_identity_id",
                "customer_memories.id",
            ],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "message_id"],
            ["messages.workspace_id", "messages.social_account_id", "messages.id"],
        ),
    )
    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    customer_identity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    memory_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    message_id: Mapped[uuid.UUID | None]
    source_key: Mapped[str] = mapped_column(Text, nullable=False)
    memory_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    removed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    observed_at: Mapped[datetime]


class SummaryVersion(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "customer_summary_versions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "thread_id", "version"),
        identity_fk(),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "thread_id"],
            ["agent_threads.workspace_id", "agent_threads.social_account_id", "agent_threads.id"],
        ),
    )
    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    customer_identity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    thread_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_cursor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    query_hash: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]
