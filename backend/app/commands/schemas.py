"""API schemas for commands (api-design.md §2.4). Responses are explicit allow-lists (INV-10):
the stored ``interpreted`` / ``resolution`` JSON and the clarification's server-side values are
never exposed."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.approvals.schemas import ApprovalOut

CommandStatus = Literal[
    "interpreting",
    "needs_clarification",
    "awaiting_confirmation",
    "executing",
    "completed",
    "unsupported",
    "failed",
    "cancelled",
    "expired",
]


class CommandCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    client_request_id: str


class ClarificationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: str


class ClarificationOptionOut(BaseModel):
    id: str
    label: str


class ClarificationOut(BaseModel):
    question_key: str
    params: dict[str, Any]
    options: list[ClarificationOptionOut]


class CommandResultOut(BaseModel):
    message_key: str
    params: dict[str, Any]
    links: list[dict[str, Any]]


class CommandOut(BaseModel):
    id: uuid.UUID
    status: CommandStatus
    raw_text: str
    command_type: str | None
    result: CommandResultOut | None
    clarification: ClarificationOut | None
    approval: ApprovalOut | None
    error_code: str | None
    created_at: datetime
    expires_at: datetime | None
    completed_at: datetime | None
