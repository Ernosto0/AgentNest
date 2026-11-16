"""The owner's test chat routes (api-design.md §2.6a): "try your assistant" before anything is
live. Owner and manager only (``assistant.test``). Every route is workspace-scoped (INV-01), and
a member sees only their own test chat. Nothing here sends, approves or counts anything."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import current_auth, get_app_settings, get_clock, require_membership
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.identity.service import AuthenticatedSession
from app.inbox import sandbox
from app.inbox.models import AssistantTestTurn

router = APIRouter(prefix="/workspaces/{workspace_id}/assistant/test-chat", tags=["assistant"])


class AssistantChatMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=sandbox.MAX_MESSAGE_CHARS)


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
    decision: Literal["auto", "approval_required", "human_required", "blocked"]
    reasons: list[str]  # policy reason codes, e.g. POLICY_REQUIRES_APPROVAL, INTENT_COMPLAINT
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


class AssistantChatOut(BaseModel):
    items: list[AssistantChatTurnOut]  # the signed-in user's chat, oldest first
    remaining_this_hour: int
    remaining_today: int


class AssistantChatResetOut(BaseModel):
    cleared: int


def _turn_out(turn: AssistantTestTurn) -> AssistantChatTurnOut:
    ready = turn.status == "ready" and turn.decision is not None
    draft = (
        AssistantChatDraftOut(
            text=turn.draft_text,
            suggestion_text=turn.suggestion_text,
            decision=turn.decision,
            reasons=list(turn.decision_reasons),
            facts_used=[FactUsedOut.model_validate(f) for f in turn.facts_used],
            language=turn.language,
            intent=turn.intent,
            flags=list(turn.flags),
        )
        if ready
        else None
    )
    return AssistantChatTurnOut(
        id=turn.id,
        status="ready" if ready else "pending",
        customer_text=turn.customer_text or "",
        created_at=turn.created_at,
        completed_at=turn.completed_at,
        draft=draft,
    )


@router.get("", response_model=AssistantChatOut)
def get_test_chat(
    ctx: WorkspaceContext = Depends(require_membership("assistant.test")),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> AssistantChatOut:
    """The chat so far. A turn is ``pending`` until its draft is ready: poll this."""
    hour, day = sandbox.remaining_messages(db, clock, settings, ctx.workspace_id)
    return AssistantChatOut(
        items=[_turn_out(t) for t in sandbox.list_turns(db, ctx, auth.user.id)],
        remaining_this_hour=hour,
        remaining_today=day,
    )


@router.post("/messages", response_model=AssistantChatTurnOut, status_code=202)
def send_test_message(
    body: AssistantChatMessageIn,
    ctx: WorkspaceContext = Depends(require_membership("assistant.test")),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> AssistantChatTurnOut:
    """A test customer message. Returns the ``pending`` turn at once (202); its ``id`` is the run
    id: poll ``GET`` until the turn is ``ready``. 429 ``TEST_CHAT_RATE_LIMITED`` over the limits."""
    return _turn_out(sandbox.submit_message(db, clock, settings, ctx, auth.user.id, body.text))


@router.post("/reset", response_model=AssistantChatResetOut)
def reset_test_chat(
    ctx: WorkspaceContext = Depends(require_membership("assistant.test")),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> AssistantChatResetOut:
    """Clear the signed-in user's chat. Does not give back any of the rate limit."""
    return AssistantChatResetOut(cleared=sandbox.reset(db, clock, ctx, auth.user.id))
