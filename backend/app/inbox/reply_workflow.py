"""From a drafting plan to a stored reply draft (workflows.md §C step 3, parts 7 and 8).

``persist_plan`` is the third transaction of the draft job: the model has already been called
(outside any transaction), so this re-checks that the world did not move, asks the policy engine
for a decision, and stores the draft together with whatever the decision needs (an approval
request, a policy grant plus a queued send, a notification). All of it commits or none of it.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals import service as approvals
from app.approvals.grants import record_policy_grant
from app.audit import service as audit
from app.core.clock import Clock
from app.core.logging import get_logger
from app.inbox import attention, drafts
from app.inbox.approval_payload import approval_payload, approval_summary
from app.inbox.context import DraftContext
from app.inbox.drafting import DraftPlan, disclosure_suffix
from app.inbox.models import Conversation, Message, ReplyDraft
from app.inbox.payloads import SendReplyPayload
from app.inbox.transitions import initial_status
from app.jobs.queue import enqueue
from app.knowledge import impact
from app.notifications import service as notifications
from app.policy import service as policy_service
from app.policy.classes import effective_mode, required_facts_usable
from app.policy.engine import Decision, evaluate_reply
from app.policy.rules_reply import APPROVAL, AUTO, BLOCKED, HUMAN, WINDOW_MARGIN, ReplyPolicyInput

log = get_logger(__name__)

APPROVAL_TTL = timedelta(hours=24)
SEND_MARGIN = timedelta(seconds=60)  # no send is attempted this close to the window's end


def deadlines(window_end: datetime, now: datetime) -> tuple[datetime, datetime]:
    """``(approval expires at, send must happen before)`` (ADR-014)."""
    return min(window_end - WINDOW_MARGIN, now + APPROVAL_TTL), window_end - SEND_MARGIN


def policy_input(
    context: DraftContext, plan: DraftPlan, modes: dict[str, str], now: datetime
) -> ReplyPolicyInput:
    rendered_keys = [r["key"] for r in plan.validation.get("rendered", [])]
    responded = plan.intent is not None
    mode = effective_mode(modes, plan.intent, rendered_keys)
    return ReplyPolicyInput(
        now=now,
        account_status=context.account_status,
        account_can_message=context.account_capabilities.get("messaging") is True,
        window_end=context.window_end,
        handling_mode=context.handling_mode,  # R3 also covers an explicit "suggest reply"
        language_supported=not plan.language_unsupported,
        keyword_flags=frozenset(plan.keyword_flags),
        escalation_keyword=plan.escalation_keyword,
        injection_suspected=plan.injection,
        attachment_only=plan.attachment_only,
        intent=plan.intent,
        model_flags=frozenset(plan.model_flags),
        model_responded=responded,
        model_needs_human=plan.model_needs_human,
        model_can_answer=plan.can_answer,
        llm_error=plan.llm_error,
        required_facts_usable=required_facts_usable(
            plan.intent,
            plan.usable_keys,
            price_disclosure=context.price_disclosure,
            approved_answer_used=plan.approved_answer_id is not None,
            model_can_answer=plan.can_answer or not responded,
            unusable_keys=context.unusable_keys,
        ),
        render_failed=plan.render_failed,
        grounding_failed=plan.grounding_failed,
        automation_mode=mode.mode,
        automation_mode_class=mode.action_class,
        readiness_level=context.readiness_level,
        auto_replies_last_hour=context.auto_replies_last_hour,
    )


def decide(
    context: DraftContext, plan: DraftPlan, modes: dict[str, str], now: datetime
) -> Decision:
    """The policy decision, guarded: a reply without sendable text can never be approved or
    automatic, whatever the rules said."""
    decision = evaluate_reply(policy_input(context, plan, modes, now))
    if decision.outcome in (APPROVAL, AUTO) and not plan.has_sendable_text:
        return Decision(HUMAN, ("MODEL_REQUESTED_HUMAN",))
    return decision


def _newest_inbound_id(
    session: Session, workspace_id: uuid.UUID, conversation_id: uuid.UUID
) -> uuid.UUID | None:
    return session.scalar(
        select(Message.id)
        .where(
            Message.workspace_id == workspace_id,
            Message.conversation_id == conversation_id,
            Message.direction == "inbound",
        )
        .order_by(Message.provider_timestamp.desc(), Message.created_at.desc(), Message.id)
        .limit(1)
    )


def newer_inbound_arrived(session: Session, context: DraftContext) -> bool:
    """True if a customer message newer than the one the plan covers is stored.

    Call it right after ``persist_plan`` in the same transaction: the conversation row is still
    locked, and inbound processing locks it before storing a message, so the answer cannot
    change before the commit.
    """
    newest = _newest_inbound_id(session, context.workspace_id, context.conversation_id)
    return newest is not None and newest != context.covers_through_message_id


def persist_plan(
    session: Session,
    clock: Clock,
    context: DraftContext,
    plan: DraftPlan,
    *,
    correlation_id: uuid.UUID | None,
) -> ReplyDraft | None:
    """Store the draft for ``plan``. Returns ``None`` if the plan is out of date (a newer
    message arrived, or another draft appeared), in which case the newer work supersedes it.
    No commit."""
    ctx = context.ctx
    now = clock.now()
    conversation = session.scalars(
        select(Conversation)
        .where(
            Conversation.workspace_id == context.workspace_id,
            Conversation.id == context.conversation_id,
        )
        .with_for_update()
    ).one_or_none()
    if conversation is None:
        return None
    if (
        _newest_inbound_id(session, conversation.workspace_id, conversation.id)
        != context.covers_through_message_id
    ):
        log.info("draft_discarded", reason="newer_message", conversation_id=str(conversation.id))
        return None
    if drafts.get_open_draft(session, context.workspace_id, conversation.id) is not None:
        log.info("draft_discarded", reason="open_draft", conversation_id=str(conversation.id))
        return None

    modes = policy_service.get_policies(session, context.workspace_id)
    decision = decide(context, plan, modes, now)
    status = initial_status(decision.outcome)
    suffix = disclosure_suffix(context) if decision.outcome == AUTO else ""
    sendable = decision.outcome in (APPROVAL, AUTO)
    validation = dict(plan.validation)
    text = (plan.text + suffix) if sendable and plan.text is not None else None
    if text is not None and suffix and plan.text is not None:
        validation["suffix_span"] = [len(plan.text), len(text)]
    # Whatever a person may reuse: the failed text with its issues marked, or a passing text
    # that policy withheld (for example a drafted answer to a complaint).
    suggestion = None if sendable else (plan.suggestion_text or plan.text)

    draft = ReplyDraft(
        workspace_id=context.workspace_id,
        conversation_id=conversation.id,
        covers_through_message_id=context.covers_through_message_id,
        source=plan.source,
        language=plan.language,
        intent=plan.intent,
        flags=sorted(
            {*plan.model_flags, *plan.keyword_flags}
            | ({"injection_suspected"} if plan.injection else set())
        ),
        template=plan.template,
        text=text,
        suggestion_text=suggestion,
        validation=validation,
        decision=decision.outcome,
        decision_reasons=list(decision.reasons),
        status=status,
        approval_id=None,
        agent_run_id=plan.agent_run_ids[-1] if plan.agent_run_ids else None,
        created_by_actor_type="agent" if plan.agent_run_ids else "system",
        is_simulated=context.is_simulated,
        created_at=now,
    )
    session.add(draft)
    session.flush()
    if sendable:
        impact.replace_references(session, ctx, "reply_draft", draft.id, plan.used_facts)
        _attach_approval(
            session, clock, context, conversation, draft, decision, now, correlation_id
        )
    audit.record(
        session,
        ctx,
        "reply_draft.created",
        "reply_draft",
        draft.id,
        {
            "conversation_id": conversation.id,
            "decision": decision.outcome,
            "reasons": list(decision.reasons),
            "status": status,
            "intent": plan.intent,
        },
        is_simulated=draft.is_simulated,
        correlation_id=correlation_id,
        clock=clock,
    )
    if decision.outcome == HUMAN:
        notifications.notify_permission_holders(
            session,
            clock,
            ctx,
            permission="reply.approve",
            type="conversation.needs_human",
            severity="attention",
            params={"conversation_id": str(conversation.id), "reasons": list(decision.reasons)},
            subject_type="conversation",
            subject_id=conversation.id,
            dedup_key=f"needs-human:{conversation.id}",
            is_simulated=draft.is_simulated,
        )
    attention.refresh(session, conversation)
    return draft


def _attach_approval(
    session: Session,
    clock: Clock,
    context: DraftContext,
    conversation: Conversation,
    draft: ReplyDraft,
    decision: Decision,
    now: datetime,
    correlation_id: uuid.UUID | None,
) -> None:
    """The authorization that binds the send to this exact text (INV-16)."""
    if context.window_end is None or decision.outcome == BLOCKED:
        return
    expires_at, execute_before = deadlines(context.window_end, now)
    arguments = {
        "action": "reply.send",
        "subject_type": drafts.SUBJECT_TYPE,
        "subject_id": draft.id,
        "subject_version": draft.version,
        "payload": approval_payload(draft, conversation),
        "summary": approval_summary(
            draft.id, conversation.id, list(decision.reasons), context.window_end.isoformat()
        ),
        "required_permission": "reply.approve",
        "expires_at": expires_at,
        "execute_before": execute_before,
        "is_simulated": draft.is_simulated,
    }
    if decision.outcome == AUTO:
        approval = record_policy_grant(session, clock, context.ctx, **arguments)  # type: ignore[arg-type]
        draft.approval_id = approval.id
        enqueue(
            session,
            "send_reply",
            SendReplyPayload(reply_draft_id=draft.id),
            workspace_id=draft.workspace_id,
            correlation_id=correlation_id,
            dedup_key=f"send_reply:{draft.id}",
            clock=clock,
        )
    else:
        approval = approvals.request(
            session,
            clock,
            context.ctx,
            kind="authorization",
            **arguments,  # type: ignore[arg-type]
        )
        draft.approval_id = approval.id
    session.flush()
