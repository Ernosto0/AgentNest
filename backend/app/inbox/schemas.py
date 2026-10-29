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
    is_simulated: bool


class MessageOut(BaseModel):
    id: uuid.UUID
    direction: Literal["inbound", "outbound"]
    sender_kind: Literal["customer", "business_app", "business_native"]
    text: str | None
    attachments: list[dict[str, Any]]
    provider_timestamp: datetime
    is_simulated: bool


class RenderedFactOut(BaseModel):
    fact_id: uuid.UUID
    key: str
    label: str
    display: str
    version: int
    span: list[int]


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
    example_questions: list[str] = Field(min_length=1, max_length=10)
    answer_template: str = Field(min_length=1, max_length=2000)
    language: Literal["tr", "en"]


class ApprovedAnswerPatch(StrictModel):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=120)
    intent: str | None = None
    example_questions: list[str] | None = Field(default=None, max_length=10)
    answer_template: str | None = Field(default=None, max_length=2000)
    status: Literal["active", "archived"] | None = None
