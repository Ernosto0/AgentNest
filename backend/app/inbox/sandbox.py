"""The owner's "try your assistant" chat (F-02): test customer messages answered with the draft the
assistant would produce, the decision and the facts behind it, and **nothing else**.

The drafting pipeline is the real one: the same facts, the same language choice, the same model
task (``drafting.make_plan``), the same claim validator and the same policy engine
(``reply_workflow.decide``). What is different is what happens to the result. A real draft becomes
a ``reply_drafts`` row with an approval, a send job, a notification and a customer memory; a test
turn becomes one ``assistant_test_turns`` row and stops there. The sandbox never touches
``conversations``, ``messages``, ``reply_drafts``, ``approvals``, ``operations``,
``notifications`` or the memory tables, and it needs no ``social_accounts`` row, so it works
before an account is connected and can never be linked to a real one (INV-09, INV-15).

Drafting is asynchronous like every other draft: ``submit_message`` stores the turn as
``pending`` and enqueues ``assistant_test_draft``; the screen polls ``list_turns``.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity.models import Workspace
from app.inbox.context import (
    MESSAGING_WINDOW,
    DraftContext,
    InboundText,
    gather_workspace_inputs,
)
from app.inbox.drafting import DraftPlan, disclosure_suffix
from app.inbox.models import AssistantTestTurn
from app.inbox.payloads import AssistantTestDraftPayload
from app.inbox.reply_workflow import decide
from app.inbox.system import system_context
from app.jobs.queue import enqueue
from app.knowledge.sources import fact_sources, unique_sources
from app.policy import service as policy_service
from app.policy.rules_reply import APPROVAL, AUTO

MAX_MESSAGE_CHARS = 500
HISTORY_TURNS = 5  # earlier test messages shown to the model as the conversation so far
MAX_PENDING = 3  # test messages waiting for their draft, per workspace
PENDING_STALE_AFTER = timedelta(minutes=10)  # an older pending turn no longer blocks new ones
RETENTION = timedelta(days=2)  # turns older than this (and the rate window) are deleted
VISIBLE_TURNS = 50
# The sandbox has no Instagram account: the channel is assumed healthy, so that the decision shown
# is about what the assistant would say, not about connection state.
NO_ACCOUNT = uuid.UUID(int=0)


# --- the owner's side: submit, read, reset -------------------------------------------------------


def _count_since(session: Session, workspace_id: uuid.UUID, since: datetime) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(AssistantTestTurn)
            .where(
                AssistantTestTurn.workspace_id == workspace_id,
                AssistantTestTurn.created_at >= since,
            )
        )
        or 0
    )


def _oldest_since(session: Session, workspace_id: uuid.UUID, since: datetime) -> datetime | None:
    return session.scalar(
        select(func.min(AssistantTestTurn.created_at)).where(
            AssistantTestTurn.workspace_id == workspace_id, AssistantTestTurn.created_at >= since
        )
    )


def _rate_limited(retry_after: float) -> AppError:
    seconds = max(1, int(retry_after) + 1)
    return AppError(
        "TEST_CHAT_RATE_LIMITED", headers={"Retry-After": str(seconds)}, retry_after=seconds
    )


def enforce_rate_limits(
    session: Session, clock: Clock, settings: Settings, workspace_id: uuid.UUID
) -> None:
    """Per **workspace** (not per user), counted from rows a reset does not delete, so neither a
    second member nor a reset buys more calls. Raises ``TEST_CHAT_RATE_LIMITED`` (429)."""
    now = clock.now()
    windows = (
        (timedelta(hours=1), settings.test_chat_max_messages_per_hour),
        (timedelta(days=1), settings.test_chat_max_messages_per_day),
    )
    for window, limit in windows:
        since = now - window
        if _count_since(session, workspace_id, since) >= limit:
            oldest = _oldest_since(session, workspace_id, since) or now
            raise _rate_limited((oldest + window - now).total_seconds())
    pending = session.scalar(
        select(func.count())
        .select_from(AssistantTestTurn)
        .where(
            AssistantTestTurn.workspace_id == workspace_id,
            AssistantTestTurn.status == "pending",
            AssistantTestTurn.created_at >= now - PENDING_STALE_AFTER,
        )
    )
    if (pending or 0) >= MAX_PENDING:
        raise _rate_limited(10)


def remaining_messages(
    session: Session, clock: Clock, settings: Settings, workspace_id: uuid.UUID
) -> tuple[int, int]:
    """``(left this hour, left today)`` for the workspace, for the screen's counter."""
    now = clock.now()
    hour = _count_since(session, workspace_id, now - timedelta(hours=1))
    day = _count_since(session, workspace_id, now - timedelta(days=1))
    return (
        max(0, settings.test_chat_max_messages_per_hour - hour),
        max(0, settings.test_chat_max_messages_per_day - day),
    )


def _purge_expired(session: Session, clock: Clock, workspace_id: uuid.UUID) -> None:
    """Old turns carry nothing the rate limit still needs: delete them (this workspace's only)."""
    session.execute(
        delete(AssistantTestTurn).where(
            AssistantTestTurn.workspace_id == workspace_id,
            AssistantTestTurn.created_at < clock.now() - RETENTION,
        )
    )


def submit_message(
    session: Session,
    clock: Clock,
    settings: Settings,
    ctx: WorkspaceContext,
    user_id: uuid.UUID,
    text: str,
) -> AssistantTestTurn:
    """Store a test customer message and queue its draft. Commits."""
    cleaned = text.strip()
    if not cleaned or len(cleaned) > MAX_MESSAGE_CHARS:
        raise AppError(
            "VALIDATION_FAILED", errors=[{"field": "text", "code": "invalid", "params": {}}]
        )
    # One submit at a time per workspace, so that concurrent requests cannot all pass the limit
    # check before any of them is stored (the task runner locks the workspace the same way).
    session.scalar(select(Workspace.id).where(Workspace.id == ctx.workspace_id).with_for_update())
    _purge_expired(session, clock, ctx.workspace_id)
    enforce_rate_limits(session, clock, settings, ctx.workspace_id)
    turn = AssistantTestTurn(
        workspace_id=ctx.workspace_id,
        user_id=user_id,
        status="pending",
        customer_text=cleaned,
        is_simulated=True,
        created_at=clock.now(),
    )
    session.add(turn)
    session.flush()
    enqueue(
        session,
        "assistant_test_draft",
        AssistantTestDraftPayload(turn_id=turn.id),
        workspace_id=ctx.workspace_id,
        correlation_id=None,
        dedup_key=f"assistant_test_draft:{turn.id}",
        clock=clock,
    )
    session.commit()
    return turn


def list_turns(
    session: Session, ctx: WorkspaceContext, user_id: uuid.UUID
) -> list[AssistantTestTurn]:
    """The signed-in user's turns, oldest first. Another member's test chat is not shown."""
    rows = session.scalars(
        select(AssistantTestTurn)
        .where(
            AssistantTestTurn.workspace_id == ctx.workspace_id,
            AssistantTestTurn.user_id == user_id,
            AssistantTestTurn.status != "reset",
        )
        .order_by(AssistantTestTurn.created_at.desc(), AssistantTestTurn.id.desc())
        .limit(VISIBLE_TURNS)
    ).all()
    return list(reversed(rows))


def reset(session: Session, clock: Clock, ctx: WorkspaceContext, user_id: uuid.UUID) -> int:
    """Clear the user's chat. The content goes; the rows stay as the rate limit's memory. A draft
    still being made is discarded when it arrives. Commits; returns how many turns were cleared."""
    turns = session.scalars(
        select(AssistantTestTurn)
        .where(
            AssistantTestTurn.workspace_id == ctx.workspace_id,
            AssistantTestTurn.user_id == user_id,
            AssistantTestTurn.status != "reset",
        )
        .with_for_update()
    ).all()
    for turn in turns:
        _scrub(turn)
        turn.status = "reset"
        turn.reset_at = clock.now()
    session.commit()
    return len(turns)


def _scrub(turn: AssistantTestTurn) -> None:
    turn.customer_text = None
    turn.language = turn.intent = turn.source = None
    turn.flags = []
    turn.draft_text = turn.suggestion_text = None
    turn.decision = None
    turn.decision_reasons = []
    turn.facts_used = []


# --- the worker's side: prepare, apply ------------------------------------------------------------


def prepare(
    session: Session, clock: Clock, workspace_id: uuid.UUID, turn_id: uuid.UUID
) -> DraftContext | None:
    """The drafting context of a pending turn (read-only), or ``None`` if there is nothing to do:
    the turn is gone, already answered or reset, or the workspace no longer exists."""
    turn = session.scalars(
        select(AssistantTestTurn).where(
            AssistantTestTurn.workspace_id == workspace_id, AssistantTestTurn.id == turn_id
        )
    ).one_or_none()
    ctx = system_context(session, workspace_id, "assistant_test")
    workspace = session.get(Workspace, workspace_id)
    if turn is None or turn.status != "pending" or not turn.customer_text:
        return None
    if ctx is None or workspace is None:
        return None
    now = clock.now()
    gathered = gather_workspace_inputs(session, clock, ctx, workspace, [turn.customer_text])
    return DraftContext(
        ctx=ctx,
        workspace_id=workspace_id,
        conversation_id=turn.id,
        social_account_id=NO_ACCOUNT,
        account_status="connected",
        account_capabilities={"messaging": True},
        handling_mode="automatic",
        is_simulated=True,
        requested=False,
        unanswered=[InboundText(turn.id, turn.customer_text, 0, turn.created_at)],
        covers_through_message_id=turn.id,
        history=_history(session, turn),
        language=gathered.language,
        facts=gathered.facts,
        price_disclosure=gathered.price_disclosure,
        approved_answers=gathered.approved_answers,
        brand_voice=gathered.brand_voice,
        escalation_keywords=gathered.escalation_keywords,
        disclosure=gathered.disclosure,
        window_end=now + MESSAGING_WINDOW,
        readiness_level=gathered.readiness_level,
        auto_replies_last_hour=0,
        usable_keys=frozenset(f.key for f in gathered.facts),
        unusable_keys=frozenset(gathered.unusable_keys),
    )


def _history(session: Session, turn: AssistantTestTurn) -> list[tuple[str, str]]:
    """The user's earlier turns as the conversation so far, ending with this message."""
    earlier = session.scalars(
        select(AssistantTestTurn)
        .where(
            AssistantTestTurn.workspace_id == turn.workspace_id,
            AssistantTestTurn.user_id == turn.user_id,
            AssistantTestTurn.status == "ready",
            tuple_(AssistantTestTurn.created_at, AssistantTestTurn.id)
            < tuple_(turn.created_at, turn.id),
        )
        .order_by(AssistantTestTurn.created_at.desc(), AssistantTestTurn.id.desc())
        .limit(HISTORY_TURNS)
    ).all()
    history: list[tuple[str, str]] = []
    for previous in reversed(earlier):
        if previous.customer_text:
            history.append(("customer", previous.customer_text))
        if previous.draft_text:  # only what the assistant would actually have said
            history.append(("business", previous.draft_text))
    history.append(("customer", turn.customer_text or ""))
    return history


def _facts_used(session: Session, context: DraftContext, plan: DraftPlan) -> list[dict[str, Any]]:
    """Every fact the wording quotes: key, label, the text as it appears, and when that version
    was verified. Read from the validator's record of the rendered placeholders, not from the
    model. The mapping is the one the inbox, approvals and Telegram show (``knowledge.sources``)."""
    sources = fact_sources(
        session,
        context.workspace_id,
        plan.validation.get("rendered", []),
        context.language.code or "tr",
    )
    return [
        {
            "key": source.key,
            "label": source.label,
            "display": source.display,
            "verified_at": source.verified_at.isoformat() if source.verified_at else None,
        }
        for source in unique_sources(sources)
    ]


def apply_plan(
    session: Session, clock: Clock, context: DraftContext, plan: DraftPlan
) -> AssistantTestTurn | None:
    """Store the outcome on the turn. ``None`` (and nothing stored) if the turn was reset or
    answered meanwhile. No commit."""
    turn = session.scalars(
        select(AssistantTestTurn)
        .where(
            AssistantTestTurn.workspace_id == context.workspace_id,
            AssistantTestTurn.id == context.conversation_id,
        )
        .with_for_update()
    ).one_or_none()
    if turn is None or turn.status != "pending":
        return None
    decision = decide(
        context, plan, policy_service.get_policies(session, context.workspace_id), clock.now()
    )
    sendable = decision.outcome in (APPROVAL, AUTO)
    suffix = disclosure_suffix(context) if decision.outcome == AUTO else ""
    turn.status = "ready"
    turn.language = plan.language
    turn.intent = plan.intent
    turn.source = plan.source
    turn.flags = sorted(
        {*plan.model_flags, *plan.keyword_flags}
        | ({"injection_suspected"} if plan.injection else set())
    )
    turn.draft_text = (plan.text + suffix) if sendable and plan.text is not None else None
    # What a person may reuse when the assistant would not answer on its own: the failed wording
    # with its issues marked, or a passing text that policy withheld.
    turn.suggestion_text = None if sendable else (plan.suggestion_text or plan.text)
    turn.decision = decision.outcome
    turn.decision_reasons = list(decision.reasons)
    turn.facts_used = _facts_used(session, context, plan)
    turn.agent_run_id = plan.agent_run_ids[-1] if plan.agent_run_ids else None
    turn.completed_at = clock.now()
    return turn
