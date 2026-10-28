"""Personal bodies live only in this domain, not generic events or jobs."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPrimaryKeyMixin, WorkspaceScopedMixin


class OwnerQuestion(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "owner_questions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "id", "answer_id"],
            ["owner_answers.workspace_id", "owner_answers.question_id", "owner_answers.id"],
            name="fk_owner_questions_answer",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "holding_action_id"],
            ["agent_actions.workspace_id", "agent_actions.social_account_id", "agent_actions.id"],
            name="fk_owner_questions_holding_action",
        ),
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "social_account_id", "thread_id", "id"),
        UniqueConstraint("workspace_id", "continuation_key"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "thread_id"],
            ["agent_threads.workspace_id", "agent_threads.social_account_id", "agent_threads.id"],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "thread_id", "session_id"],
            ["agent_sessions.workspace_id", "agent_sessions.thread_id", "agent_sessions.id"],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "customer_identity_id"],
            [
                "customer_identities.workspace_id",
                "customer_identities.social_account_id",
                "customer_identities.id",
            ],
        ),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "source_message_id"],
            ["messages.workspace_id", "messages.social_account_id", "messages.id"],
        ),
        CheckConstraint("state IN ('pending','answered','expired','cancelled')", name="state"),
        CheckConstraint("visibility IN ('customer_reply','private_business')", name="visibility"),
        CheckConstraint("version >= 1 AND source_cursor >= 1", name="versions"),
    )
    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    thread_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    customer_identity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column()
    source_cursor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_hash: Mapped[str] = mapped_column(Text, nullable=False)
    knowledge_fence: Mapped[str] = mapped_column(Text, nullable=False)
    ownership_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deletion_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    required_info: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(Text, nullable=False)
    continuation_key: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    answer_id: Mapped[uuid.UUID | None] = mapped_column()
    holding_action_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OwnerAnswer(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "owner_answers"
    __table_args__ = (
        UniqueConstraint("workspace_id", "question_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "candidate_id"],
            ["fact_candidates.workspace_id", "fact_candidates.id"],
            name="fk_owner_answers_candidate",
            use_alter=True,
        ),
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "question_id", "client_request_id"),
        UniqueConstraint("workspace_id", "question_id", "version"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id", "thread_id", "question_id"],
            [
                "owner_questions.workspace_id",
                "owner_questions.social_account_id",
                "owner_questions.thread_id",
                "owner_questions.id",
            ],
        ),
        CheckConstraint("kind IN ('answer','proposal','cancel')", name="kind"),
        CheckConstraint("version >= 1", name="version"),
    )
    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    thread_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    question_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    author_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    author_role: Mapped[str] = mapped_column(Text, nullable=False)
    client_request_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
