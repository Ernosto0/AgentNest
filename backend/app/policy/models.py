"""``automation_policies`` (data-model.md §3.4): one row per (workspace, action class).

A missing row means the default, ``approval``. Rows are written only through
``policy.service.set_policies``.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.policy.classes import ACTION_CLASSES, MODES


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class AutomationPolicy(Base):
    __tablename__ = "automation_policies"
    __table_args__ = (
        CheckConstraint(_in("action_class", ACTION_CLASSES), name="action_class"),
        CheckConstraint(_in("mode", MODES), name="mode"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    action_class: Mapped[str] = mapped_column(Text, primary_key=True)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
