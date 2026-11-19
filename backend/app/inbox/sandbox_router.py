"""The owner's test chat routes (api-design.md §2.6a): "try your assistant" before anything is
live. Owner and manager only (``assistant.test``). Every route is workspace-scoped (INV-01), and
a member sees only their own test chat. Nothing here sends, approves or counts anything."""

from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_auth, get_app_settings, get_clock, require_membership
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.identity.service import AuthenticatedSession
from app.inbox import sandbox
from app.inbox.models import AssistantTestTurn
from app.inbox.schemas import (
    AssistantChatDraftOut,
    AssistantChatMessageIn,
    AssistantChatOut,
    AssistantChatResetOut,
    AssistantChatTurnOut,
    FactUsedOut,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/assistant/test-chat", tags=["assistant"])


def _turn_out(
    turn: AssistantTestTurn,
    controller_mode: Literal["legacy", "agent"] = "legacy",
) -> AssistantChatTurnOut:
    ready = turn.status == "ready" and turn.decision is not None
    turn_mode: Literal["legacy", "agent"] = (
        "agent"
        if turn.source == "agent"
        else ("legacy" if turn.source in ("template", "model") else controller_mode)
    )
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
        controller_mode=turn_mode,
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
    mode = sandbox.get_controller_mode(db, ctx.workspace_id)
    hour, day = sandbox.remaining_messages(db, clock, settings, ctx.workspace_id)
    return AssistantChatOut(
        items=[_turn_out(t, mode) for t in sandbox.list_turns(db, ctx, auth.user.id)],
        remaining_this_hour=hour,
        remaining_today=day,
        controller_mode=mode,
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
    mode = sandbox.get_controller_mode(db, ctx.workspace_id)
    turn = sandbox.submit_message(db, clock, settings, ctx, auth.user.id, body.text)
    return _turn_out(turn, mode)


@router.post("/reset", response_model=AssistantChatResetOut)
def reset_test_chat(
    ctx: WorkspaceContext = Depends(require_membership("assistant.test")),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> AssistantChatResetOut:
    """Clear the signed-in user's chat. Does not give back any of the rate limit."""
    return AssistantChatResetOut(cleared=sandbox.reset(db, clock, ctx, auth.user.id))
