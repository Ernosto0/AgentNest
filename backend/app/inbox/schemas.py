"""API models of the inbox (api-design.md §2.6). Response models are explicit allow-lists."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Attention = Literal["none", "needs_approval", "needs_human", "failed"]
HandlingMode = Literal["automatic", "human"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConversationOut(BaseModel):
    id: uuid.UUID
    social_account_id: uuid.UUID | None = None
    customer_handle: str | None
    customer_number: int  # for customers without a known handle: "Customer #4821"
    last_message_preview: str | None
    last_message_at: datetime | None
    attention: Attention
    handling_mode: HandlingMode
    window_ends_at: datetime | None
    # open: a normal reply; human_agent_only: only a person's own reply with the Human Agent tag,
    # until ``human_agent_until``; closed: nothing can be sent until the customer writes again.
    window_state: Literal["open", "human_agent_only", "closed"] = "closed"
    human_agent_until: datetime | None = None
    is_simulated: bool


class StoryOut(BaseModel):
    """The story a message refers to (F-04). ``known`` is true only for a story Pivoris
    published, where the stored content is shown; a reply to any other story, and every mention,
    carries just the kind (the provider's story link is short-lived and is never shown)."""

    kind: Literal["reply", "mention"]
    known: bool
    title: str | None
    lines: list[str]
    media_asset_id: uuid.UUID | None
    media_deleted: bool
    expired: bool


class TranscriptOut(BaseModel):
    """The automatic transcript of a voice note (F-03). Always shown as what it is: a machine's
    reading of what the customer said, never the customer's own typed words. The audio is not
    kept, so there is nothing to play: the owner listens to the voice note in Instagram."""

    status: Literal["pending", "succeeded", "failed"]
    # ``None`` unless the transcription succeeded (and the text was not erased by retention).
    text: str | None
    language: str | None  # tr | en | other | None
    reason_code: str | None  # why a transcript is missing, when it failed
    duration_seconds: float | None


class ImageDescriptionOut(BaseModel):
    """The automatic description of one photo or screenshot a customer sent (F-03). Always shown
    as what it is: a machine's reading of a picture, for the owner. It is never a fact and never
    used to answer the customer. The picture is not kept, so there is nothing to show: the owner
    opens the picture in Instagram."""

    attachment_index: int  # the position of the image in the message's attachments
    status: Literal["pending", "succeeded", "failed"]
    # Text only when the description succeeded (and was not erased by retention).
    looks_like: Literal["product", "price_screenshot", "location", "other"] | None
    description: str | None
    visible_text: str | None  # the text read from the picture, untrusted customer content
    # The injection heuristics matched the description or the visible text: shown with a warning.
    injection_suspected: bool
    reason_code: str | None  # why there is no description, when it failed


class MessageOut(BaseModel):
    id: uuid.UUID
    direction: Literal["inbound", "outbound"]
    sender_kind: Literal["customer", "business_app", "business_native"]
    text: str | None
    attachments: list[dict[str, Any]]
    provider_timestamp: datetime
    is_simulated: bool
    # Set only on a customer message with a voice note.
    transcript: TranscriptOut | None = None
    # One per described image attachment of a customer message (empty for any other message).
    image_descriptions: list[ImageDescriptionOut] = Field(default_factory=list)
    # Set only on a story reply or mention (F-04).
    story: StoryOut | None = None


class DraftTranscriptOut(BaseModel):
    """A voice-note transcript a reply was drafted from, so the approval view can show it."""

    message_id: uuid.UUID
    text: str | None
    language: str | None


class RenderedFactOut(BaseModel):
    fact_id: uuid.UUID
    key: str
    label: str
    display: str
    version: int
    span: list[int]
    # When the fact version this value was rendered from was verified (``None``: not recorded).
    verified_at: datetime | None


class FactSourceOut(BaseModel):
    """One verified fact a reply quotes, once, with where it comes from (D-01). The same shape as
    the test chat's ``facts_used``: the client shows it as it is."""

    key: str
    label: str
    display: str
    verified_at: datetime | None


class ValidationIssueOut(BaseModel):
    code: str
    span: list[int] | None
    text: str
    # For money-like issues in a person's own text: does it equal a verified value?
    matches_verified: bool = False


class ValidationOut(BaseModel):
    passed: bool
    issues: list[ValidationIssueOut]


class ApprovalStateOut(BaseModel):
    """Where the approval of a reply stands, for anyone who may read the conversation (staff
    cannot decide, but they see whether their reply is waiting, approved or turned down)."""

    status: Literal["pending", "approved", "rejected", "expired", "cancelled"]
    expires_at: datetime
    decided_by_name: str | None
    decided_at: datetime | None
    decision_note: str | None


class ReplyDraftOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    status: str
    source: Literal["ai", "approved_answer", "owner"]
    language: str | None
    intent: str | None
    flags: list[str]
    text: str | None
    suggestion_text: str | None
    rendered_facts: list[RenderedFactOut]
    facts_used: list[FactSourceOut]
    validation: ValidationOut
    decision: str
    decision_reasons: list[str]
    approval_id: uuid.UUID | None
    approval_state: ApprovalStateOut | None
    version: int
    failure_code: str | None
    window_ends_at: datetime | None
    created_at: datetime
    is_simulated: bool
    # ``HUMAN_AGENT`` for a person's reply that goes out after the 24-hour window.
    message_tag: Literal["HUMAN_AGENT"] | None = None
    # Non-empty when the reply was drafted from a voice-note transcript: a person must approve it.
    transcripts: list[DraftTranscriptOut] = Field(default_factory=list)


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]
    open_draft: ReplyDraftOut | None
    recent_drafts: list[ReplyDraftOut]


class ManualReplyIn(StrictModel):
    text: str = Field(min_length=1, max_length=2000)
    client_request_id: str = Field(min_length=1, max_length=64)
    from_draft_id: uuid.UUID | None = None


class ReplyWithWarningsOut(BaseModel):
    draft: ReplyDraftOut
    warnings: list[ValidationIssueOut]


class DraftPatchIn(StrictModel):
    text: str = Field(min_length=1, max_length=2000)
    expected_version: int = Field(ge=1)
    # Only for someone who may approve: send it without a second step.
    approve: bool = False


class AnswerFromMessageIn(StrictModel):
    title: str | None = Field(default=None, max_length=120)
    intent: str | None = None
    example_question: str | None = Field(default=None, max_length=200)
    answer_template: str | None = Field(default=None, max_length=2000)


class ApprovedAnswerOut(BaseModel):
    id: uuid.UUID
    title: str
    intent: str
    example_questions: list[str]
    answer_template: str
    language: str
    status: str
    version: int
    created_from_message_id: uuid.UUID | None
    updated_at: datetime


class ApprovedAnswerIn(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    intent: str
    # At least one, except for the story-mention thank-you (checked by the service).
    example_questions: list[str] = Field(max_length=10)
    answer_template: str = Field(min_length=1, max_length=2000)
    language: Literal["tr", "en", "ru", "de", "ar"]


class ApprovedAnswerPatch(StrictModel):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=120)
    intent: str | None = None
    example_questions: list[str] | None = Field(default=None, max_length=10)
    answer_template: str | None = Field(default=None, max_length=2000)
    status: Literal["active", "archived"] | None = None


# --- Test Chat (F-02, Session 07) -----------------------------------------------------------------


class AssistantChatMessageIn(StrictModel):
    text: str = Field(min_length=1, max_length=500)


class FactUsedOut(BaseModel):
    key: str
    label: str
    display: str  # the value as it appears in the reply
    verified_at: datetime | None  # when the owner last verified the fact


class AssistantChatDraftOut(BaseModel):
    # What the assistant would send; null when a person has to answer (decision human_required
    # or blocked), when ``suggestion_text`` may hold wording to start from.
    text: str | None
    suggestion_text: str | None
    decision: Literal["auto", "approval_required", "human_required", "blocked", "automatic", "ask"]
    reasons: list[str]  # policy reason codes, e.g. POLICY_REQUIRES_APPROVAL, basic_verified_topic
    facts_used: list[FactUsedOut]
    language: str | None
    intent: str | None
    flags: list[str]


class AssistantChatTurnOut(BaseModel):
    id: uuid.UUID
    status: Literal["pending", "ready"]
    customer_text: str
    created_at: datetime
    completed_at: datetime | None
    draft: AssistantChatDraftOut | None  # null while pending
    is_simulated: Literal[True] = True
    controller_mode: Literal["legacy", "agent"] = "legacy"


class AssistantChatOut(BaseModel):
    items: list[AssistantChatTurnOut]  # the signed-in user's chat, oldest first
    remaining_this_hour: int
    remaining_today: int
    controller_mode: Literal["legacy", "agent"] = "legacy"


class AssistantChatResetOut(BaseModel):
    cleared: int
