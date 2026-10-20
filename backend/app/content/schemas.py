"""API models of the content module (api-design.md section 2.7)."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ContentType = Literal["feed_image", "story_image"]
ContentStatus = Literal[
    "draft",
    "pending_approval",
    "scheduled",
    "publishing",
    "retry_scheduled",
    "on_hold",
    "published",
    "rejected",
    "failed",
    "cancelled",
]
# The four tabs of the content screen (plan.md G15). ``cancelled`` is in none of them.
ContentTab = Literal["drafts", "scheduled", "published", "problems"]

# Storage guards, not product limits: the product limits (caption length, overlay length)
# are submit validation (P5-04).
TITLE_MAX = 200
CAPTION_MAX = 5000
OVERLAY_ITEM_MAX = 500
OVERLAY_ITEMS_MAX = 10
NOTES_MAX = 2000

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)]
Caption = Annotated[str, StringConstraints(max_length=CAPTION_MAX)]
OverlayList = Annotated[
    list[Annotated[str, StringConstraints(max_length=OVERLAY_ITEM_MAX)]],
    Field(max_length=OVERLAY_ITEMS_MAX),
]


class MediaAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    width: int
    height: int
    mime_type: str
    byte_size: int
    original_filename: str | None
    rejection_code: str | None
    created_at: datetime


class ContentCreate(BaseModel):
    content_type: ContentType
    title: Title
    caption: Caption | None = None
    overlay_text_suggestions: OverlayList = Field(default_factory=list)
    media_asset_id: uuid.UUID | None = None
    client_request_id: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None = None


class ContentPatch(BaseModel):
    """A field that is absent is left alone; a field sent as ``null`` is cleared (caption,
    media). ``title`` cannot be cleared."""

    expected_version: int = Field(ge=1)
    title: Title | None = None
    caption: Caption | None = None
    overlay_text_suggestions: OverlayList | None = None
    visual_notes: Annotated[str, StringConstraints(max_length=NOTES_MAX)] | None = None
    media_asset_id: uuid.UUID | None = None


class ContentIssueOut(BaseModel):
    code: str
    # Which text the issue is in: ``caption`` or ``overlay_text_suggestions.{index}``.
    field: str
    # The span is an index into that text.
    span: list[int] | None
    text: str
    # Does the value equal a verified fact (so the owner can see it is right but not grounded)?
    matches_verified: bool = False


class ContentValidationOut(BaseModel):
    passed: bool
    issues: list[ContentIssueOut]
    # A fact changed since the last check; the report may be out of date (P5-07).
    stale: bool = False


class ContentApprovalStateOut(BaseModel):
    """Where the approval of the item stands, for anyone who may read content (staff cannot
    decide, but they see whether their submission is waiting, approved or turned down)."""

    status: Literal["pending", "approved", "rejected", "expired", "cancelled"]
    # The item version the approval is bound to. If it differs from the item's, it no longer
    # authorises anything (INV-16).
    subject_version: int
    expires_at: datetime
    decided_by_name: str | None
    decided_at: datetime | None
    decision_note: str | None
    cancel_reason: str | None


class ContentOperationOut(BaseModel):
    status: str
    attempts: int
    next_attempt_at: datetime | None
    last_error_code: str | None


class ScheduleLocalOut(BaseModel):
    date: str  # YYYY-MM-DD in the workspace timezone
    time: str  # HH:MM
    timezone: str


class ContentItemOut(BaseModel):
    id: uuid.UUID
    content_type: ContentType
    status: ContentStatus
    version: int
    title: str
    objective: str | None
    caption: str | None
    overlay_text_suggestions: list[str]
    visual_notes: str | None
    social_account_id: uuid.UUID | None
    media_asset_id: uuid.UUID | None
    scheduled_at: datetime | None
    schedule_local: ScheduleLocalOut | None
    approval_id: uuid.UUID | None
    approval: ContentApprovalStateOut | None
    operation: ContentOperationOut | None
    hold_reason: str | None
    rejection_note: str | None
    validation: ContentValidationOut
    published_at: datetime | None
    external_media_id: str | None
    external_permalink: str | None
    last_error_code: str | None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    is_simulated: bool


def empty_validation() -> dict[str, Any]:
    return {"passed": True, "issues": [], "stale": False}
