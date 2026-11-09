"""Instagram Insights models (P5-Insights).

Stores daily account metric snapshots, individual story and post performance snapshots,
and audience snapshots. All tables enforce workspace_id isolation (INV-01) and track
is_simulated for offline/demo fidelity.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    WorkspaceScopedMixin,
    workspace_unique_constraint,
)


class AccountInsightDaily(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    """Daily metric record for a social account (reach, views, interactions, follower_count)."""

    __tablename__ = "account_insight_daily"
    __table_args__ = (
        workspace_unique_constraint(),
        UniqueConstraint(
            "social_account_id", "local_date", "metric", name="uq_account_insight_daily_metric"
        ),
        Index("ix_account_insight_daily_ws_date", "workspace_id", "local_date"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
            ondelete="CASCADE",
        ),
    )

    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    metric: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class MediaInsightSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    """Snapshot of metrics for a single piece of published media (post or story)."""

    __tablename__ = "media_insight_snapshots"
    __table_args__ = (
        workspace_unique_constraint(),
        Index(
            "ix_media_insight_snapshots_media", "workspace_id", "social_account_id", "ig_media_id"
        ),
        Index("ix_media_insight_snapshots_content_item", "workspace_id", "content_item_id"),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
            ondelete="CASCADE",
        ),
    )

    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    content_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_items.id", ondelete="SET NULL"), nullable=True
    )
    ig_media_id: Mapped[str] = mapped_column(Text, nullable=False)
    media_kind: Mapped[str] = mapped_column(Text, nullable=False)  # "feed_image", "story_image"
    metric: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AudienceSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    """Weekly snapshot of audience demographics or hourly follower activity."""

    __tablename__ = "audience_snapshots"
    __table_args__ = (
        workspace_unique_constraint(),
        UniqueConstraint(
            "social_account_id",
            "captured_on",
            "kind",
            name="uq_audience_snapshots_account_day_kind",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "social_account_id"],
            ["social_accounts.workspace_id", "social_accounts.id"],
            ondelete="CASCADE",
        ),
    )

    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    captured_on: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # "online_followers", "demographics"
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
