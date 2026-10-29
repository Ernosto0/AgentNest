"""API schemas for approvals (api-design.md §2.5). Responses are explicit allow-lists (INV-10)."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

ApprovalKind = Literal["confirmation", "authorization"]
ApprovalStatus = Literal["pending", "approved", "rejected", "expired", "cancelled"]
ApprovalAction = Literal[
    "command.update_fact",
    "command.update_brand_voice",
    "command.cancel_content",
    "reply.send",
    "content.publish",
    "comments.approve",
    "content.prepare",
    "content.schedule",
    "content.cancel",
]


class DecisionIn(BaseModel):
    """What the user saw and chose. The hash must be the one the client displayed."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
    payload_hash: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    note: Annotated[str, StringConstraints(max_length=500)] | None = None


class SubjectLinkOut(BaseModel):
    """Structured so the API stays free of frontend routes."""

    target: str
    id: uuid.UUID


class SubjectOut(BaseModel):
    type: str
    id: uuid.UUID
    version: int
    status: str | None
    link: SubjectLinkOut


class ApprovalOut(BaseModel):
    id: uuid.UUID
    kind: ApprovalKind
    action: ApprovalAction
    status: ApprovalStatus
    summary: dict[str, Any]
    payload_hash: str
    subject: SubjectOut
    expires_at: datetime
    execute_before: datetime | None
    required_permission: str
    can_decide: bool
    is_simulated: bool
    created_at: datetime
    decided_at: datetime | None
    cancel_reason: str | None
