"""API models of the content module (api-design.md section 2.7)."""

import uuid
from datetime import date, datetime
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


class ContentGenerate(BaseModel):
    """Ask for an AI draft (plan.md G7). ``client_request_id`` is required: it makes a retry
    return the first draft instead of paying for a second generation."""

    content_type: ContentType
    objective: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
    ]
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=NOTES_MAX)] | None = (
        None
    )
    client_request_id: Annotated[str, StringConstraints(min_length=1, max_length=100)]


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
    # The value is the current display of a verified fact: it is grounded, recorded as a
    # reference of the item, and does not block a submission. Every other issue does.
    matches_verified: bool = False
    # The key of the verified fact whose display the value equals (``null`` if none). For a
    # ``PLACEHOLDER_UNRENDERED`` issue, the key the placeholder names.
    fact_key: str | None = None


class ContentCheckItemOut(BaseModel):
    """One submit rule that was broken (``errors``) or only worth a look (``warnings``)
    (plan.md G17). ``field`` names what it is about (``caption``, ``media_asset_id``,
    ``schedule``, ``scheduled_at``, ``social_account_id``, ``overlay_text_suggestions.{i}``);
    ``null`` for the claim check, whose ``params.issues`` lists the claim issues."""

    code: str
    field: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    # Localised text (the caller's locale); absent in a stored report.
    message: str | None = None


class ContentValidationOut(BaseModel):
    # No ungrounded claim: every value in the caption and the overlay suggestions is a verified
    # fact's current value (those stay in ``issues`` with ``matches_verified``).
    passed: bool
    issues: list[ContentIssueOut]
    # A fact changed since the last check; the report may be out of date (P5-07).
    stale: bool = False
    # The submit rules (G17). Filled by ``POST .../validate``; on an item, only the warnings of
    # the last successful submission (an item with errors was never submitted).
    errors: list[ContentCheckItemOut] = Field(default_factory=list)
    warnings: list[ContentCheckItemOut] = Field(default_factory=list)


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


class GenerationOut(BaseModel):
    """Where the AI draft of an item stands: the status of its ``agent_runs`` row (G7). A run
    that has succeeded counts as ``running`` until its text has been saved on the draft."""

    status: Literal["queued", "running", "succeeded", "failed"]
    # Why it failed (``LLM_UNAVAILABLE``, ``LLM_OUTPUT_INVALID``, ``LLM_REFUSED``,
    # ``LLM_BUDGET_EXCEEDED``, ``FACT_NOT_USABLE``, ``PLACEHOLDER_INVALID``, ``CONTENT_CHANGED``);
    # the draft is then an ordinary manual draft.
    error_code: str | None = None


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
    # The image was deleted when its retention ran out (media cleanup); the UI says so instead of
    # showing a broken image.
    media_deleted: bool
    scheduled_at: datetime | None
    schedule_local: ScheduleLocalOut | None
    approval_id: uuid.UUID | None
    approval: ContentApprovalStateOut | None
    operation: ContentOperationOut | None
    hold_reason: str | None
    rejection_note: str | None
    validation: ContentValidationOut
    # ``null`` for a draft nobody asked the AI for.
    generation: GenerationOut | None = None
    published_at: datetime | None
    external_media_id: str | None
    external_permalink: str | None
    last_error_code: str | None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    is_simulated: bool
    # Whether the viewer may cancel this item now (the UI only hides the button; the route decides).
    can_cancel: bool


class LocalScheduleIn(BaseModel):
    """A wall-clock time in the workspace timezone (never an instant: the server converts)."""

    local_date: date
    local_time: Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


# ``"now"`` is the whole value, not a field.
ScheduleIn = LocalScheduleIn | Literal["now"]


class SubmitIn(BaseModel):
    schedule: ScheduleIn
    self_approve: bool = False
    expected_version: int = Field(ge=1)


class ReapproveIn(BaseModel):
    schedule: ScheduleIn
    expected_version: int = Field(ge=1)


class ValidateIn(BaseModel):
    """Optional body of the dry run: with a schedule the schedule and quota rules run too."""

    schedule: ScheduleIn | None = None
    self_approve: bool = False


def empty_validation() -> dict[str, Any]:
    return {"passed": True, "issues": [], "stale": False}
