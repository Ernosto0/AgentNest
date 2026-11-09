"""Schemas for Instagram Insights API."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class SparklinePoint(BaseModel):
    date: str
    reach: int | None
    views: int | None


class InsightsSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: uuid.UUID
    range: Literal["7d", "28d"]
    status: Literal["ok", "partial", "not_granted", "below_threshold", "syncing"]
    current_days_covered: int = 0
    previous_days_covered: int = 0
    updated_at: datetime | None
    reach: int | None
    reach_delta_pct: int | None
    views: int | None
    views_delta_pct: int | None
    interactions: int | None
    interactions_delta_pct: int | None
    follower_count: int | None
    follower_delta: int | None
    sparkline: list[SparklinePoint]
    is_simulated: bool


class InsightsContentItemOut(BaseModel):
    content_item_id: uuid.UUID | None
    ig_media_id: str
    media_kind: str
    title: str | None
    published_at: datetime | None
    reach: int
    views: int
    total_interactions: int
    metrics: dict[str, int]
    is_simulated: bool


class InsightsContentListOut(BaseModel):
    items: list[InsightsContentItemOut]


class AudienceOut(BaseModel):
    status: Literal["ok", "below_threshold", "not_granted"]
    follower_count: int | None
    online_hours: dict[str, int] | None
    best_posting_window: str | None
    demographics: dict[str, Any] | None
