"""Knowledge tables (data-model.md §3.3): ``business_facts``, ``fact_versions`` (append-only),
``fact_candidates``.

Every tenant child references its parent through a composite foreign key
``(workspace_id, parent_id)``, so a cross-workspace reference is impossible at the DB level
(INV-01).
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin, WorkspaceScopedMixin
from app.knowledge.constants import (
    CANDIDATE_RELATIONS,
    CANDIDATE_SOURCES,
    CANDIDATE_STATUSES,
    CATEGORIES,
    CHANGE_KINDS,
    CRITICALITIES,
    FACT_STATUSES,
    KEY_PATTERN,
    SOURCE_TYPES,
)
from app.knowledge.values import VALUE_TYPES


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class BusinessFact(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "business_facts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        CheckConstraint(f"key ~ '{KEY_PATTERN}'", name="key_format"),
        CheckConstraint(_in("category", CATEGORIES), name="category"),
        CheckConstraint(_in("value_type", VALUE_TYPES), name="value_type"),
        CheckConstraint(_in("status", FACT_STATUSES), name="status"),
        CheckConstraint(_in("criticality", CRITICALITIES), name="criticality"),
        CheckConstraint("current_version >= 1", name="current_version"),
        CheckConstraint(
            "valid_from IS NULL OR valid_until IS NULL OR valid_until >= valid_from",
            name="validity_window",
        ),
        # One live fact per key; archived facts free the key.
        Index(
            "uq_business_facts_workspace_key_active",
            "workspace_id",
            "key",
            unique=True,
            postgresql_where=text("status <> 'archived'"),
        ),
        Index("ix_business_facts_workspace_category", "workspace_id", "category"),
    )

    key: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    value_type: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    criticality: Mapped[str] = mapped_column(Text, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class FactVersion(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    """Immutable snapshot after each change. Insert-only: there is no update or delete path
    (INV-17); rows disappear only with their workspace."""

    __tablename__ = "fact_versions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "fact_id"],
            ["business_facts.workspace_id", "business_facts.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("fact_id", "version"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint(_in("status", FACT_STATUSES), name="status"),
        CheckConstraint(_in("source_type", SOURCE_TYPES), name="source_type"),
        CheckConstraint(_in("change_kind", CHANGE_KINDS), name="change_kind"),
        CheckConstraint(
            "valid_from IS NULL OR valid_until IS NULL OR valid_until >= valid_from",
            name="validity_window",
        ),
    )

    fact_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    change_kind: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FactCandidate(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "fact_candidates"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        # fact_id is nullable (MATCH SIMPLE): the pair is only checked when a fact is referenced.
        ForeignKeyConstraint(
            ["workspace_id", "fact_id"],
            ["business_facts.workspace_id", "business_facts.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(f"fact_key ~ '{KEY_PATTERN}'", name="fact_key_format"),
        CheckConstraint(_in("value_type", VALUE_TYPES), name="value_type"),
        CheckConstraint(_in("source_type", CANDIDATE_SOURCES), name="source_type"),
        CheckConstraint(_in("relation", CANDIDATE_RELATIONS), name="relation"),
        CheckConstraint(_in("status", CANDIDATE_STATUSES), name="status"),
        CheckConstraint(
            "source_excerpt IS NULL OR char_length(source_excerpt) <= 500", name="source_excerpt"
        ),
        Index("ix_fact_candidates_workspace_status", "workspace_id", "status"),
        Index(
            "ix_fact_candidates_pending_key",
            "workspace_id",
            "fact_key",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    fact_key: Mapped[str] = mapped_column(Text, nullable=False)
    fact_id: Mapped[uuid.UUID | None] = mapped_column()
    proposed_value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    value_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    relation: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    proposed_by_actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_by_actor_id: Mapped[str | None] = mapped_column(Text)
    # No FK yet: ``agent_runs`` arrives in Phase 3, which adds the constraint.
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column()
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
