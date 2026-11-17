import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPrimaryKeyMixin, WorkspaceScopedMixin, workspace_unique_constraint


class WorkspacePlan(Base):
    __tablename__ = "workspace_plans"
    __table_args__ = (
        CheckConstraint(
            "monthly_quota > 0 AND (quota_override IS NULL OR quota_override > 0)",
            name="positive_quota",
        ),
        CheckConstraint("used >= 0", name="used"),
        CheckConstraint("period_end > period_start", name="period"),
        CheckConstraint("status IN ('trial', 'active', 'past_due', 'cancelled')", name="status"),
        CheckConstraint("plan IN ('starter', 'growth', 'pro')", name="plan"),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    plan: Mapped[str] = mapped_column(Text)
    monthly_quota: Mapped[int] = mapped_column(Integer)
    quota_override: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    anchor_day: Mapped[int] = mapped_column(Integer)
    period_id: Mapped[uuid.UUID]
    used: Mapped[int] = mapped_column(Integer, default=0)
    warned_80: Mapped[bool] = mapped_column(default=False)
    warned_100: Mapped[bool] = mapped_column(default=False)
    warned_paused: Mapped[bool] = mapped_column(default=False)


class ReplyUsage(UUIDPrimaryKeyMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "reply_usage"
    __table_args__ = (UniqueConstraint("workspace_id", "draft_key"), workspace_unique_constraint())
    draft_key: Mapped[str] = mapped_column(Text)
    period_id: Mapped[uuid.UUID]
    state: Mapped[str] = mapped_column(Text)  # reserved | consumed | released
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
