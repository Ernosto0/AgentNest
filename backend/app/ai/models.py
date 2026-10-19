"""``agent_runs`` (data-model.md §3.4): one row per LLM task execution (agent-runtime.md §2).

``queued`` is added to the documented states so an endpoint can create the row (holding the
redacted input snapshot) before the job runs; budget counting ignores queued rows.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin, WorkspaceScopedMixin

AGENT_TASKS = ("interpret_command", "draft_reply", "draft_content", "extract_fact_candidates")
AGENT_RUN_STATUSES = ("queued", "running", "succeeded", "failed")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class AgentRun(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        CheckConstraint(_in("task", AGENT_TASKS), name="task"),
        CheckConstraint(_in("status", AGENT_RUN_STATUSES), name="status"),
        CheckConstraint("repair_attempts >= 0", name="repair_attempts"),
        # Budget check: runs of one workspace in a time window.
        Index("ix_agent_runs_workspace_created", "workspace_id", "created_at"),
        # The abandoned-run sweeper only looks at running rows.
        Index("ix_agent_runs_running", "started_at", postgresql_where=text("status = 'running'")),
    )

    task: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    input_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB
    )  # redacted; 30-day retention
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    validation_errors: Mapped[list[Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    repair_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    job_id: Mapped[uuid.UUID | None] = mapped_column()  # no FK: jobs are purged by retention
    correlation_id: Mapped[uuid.UUID | None] = mapped_column()
    is_fake: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


__all__ = ["AGENT_RUN_STATUSES", "AGENT_TASKS", "AgentRun"]
