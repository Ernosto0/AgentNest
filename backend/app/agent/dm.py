"""Agent proposals reuse ReplyDraft and the existing send operation ledger."""

import uuid
from datetime import timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.delegation import authorize_action, record_effect_grant
from app.agent.grounding import ReplyValidationArgs, validate_reply
from app.agent.models import ACTIVE_RUN_STATES, AgentAction, AgentEvent, AgentSession, AgentThread
from app.agent.repository import admit_action, scoped_thread
from app.agent.tools.broker import BrokerContext, ToolInputError
from app.core.canonical import payload_hash
from app.core.clock import Clock
from app.inbox.approval_payload import approval_payload
from app.inbox.models import Conversation, Message, ReplyDraft
from app.inbox.payloads import SendReplyPayload
from app.jobs.queue import enqueue
from app.knowledge import impact
from app.operations.models import Operation


def action_result(db: Session, action: AgentAction) -> dict[str, Any]:
    draft = db.get(ReplyDraft, action.payload_ref) if action.payload_ref else None
    if draft is not None:
        action.operation_id = draft.operation_id
        if draft.operation_id:
            op = db.get(Operation, draft.operation_id)
            if op is not None:
                action.status = {
                    "succeeded": "succeeded",
                    "failed": "failed",
                    "cancelled": "cancelled",
                    "in_progress": "in_progress",
                    "outcome_unknown": "outcome_unknown",
                }.get(op.status, "queued")
        elif draft.status in {"cancelled", "superseded", "expired", "failed"}:
            action.status = "cancelled" if draft.status != "failed" else "failed"
    return {
        "action_id": str(action.id),
        "status": action.status,
        "approval_id": str(action.approval_id) if action.status == "waiting_approval" else None,
        "operation_id": str(action.operation_id) if action.operation_id else None,
    }


def send(
    db: Session,
    clock: Clock,
    context: BrokerContext,
    args: BaseModel,
    *,
    require_human: bool = False,
    semantic_slot: str = "customer_response",
) -> dict[str, Any]:
    proposal = ReplyValidationArgs.model_validate(args)
    thread = scoped_thread(
        db, context.workspace.workspace_id, context.account_id, context.thread_id
    )
    if thread.surface != "dm" or thread.handling_mode != "agent" or not thread.dm_conversation_id:
        raise ToolInputError("DM thread unavailable")
    conversation = db.scalar(
        select(Conversation)
        .where(
            Conversation.id == thread.dm_conversation_id,
            Conversation.workspace_id == thread.workspace_id,
            Conversation.social_account_id == thread.social_account_id,
        )
        .with_for_update()
    )
    if conversation is None or conversation.handling_mode == "human":
        raise ToolInputError("conversation unavailable")
    # This check spans goals and customer events. An uncertain remote send reserves
    # the thread's response slot until reconciliation, regardless of wording.
    prior = db.scalar(
        select(AgentAction)
        .where(
            AgentAction.thread_id == thread.id,
            AgentAction.action_type == "dm.send",
            (AgentAction.initiating_cursor == thread.event_cursor)
            | AgentAction.status.in_(
                ("waiting_approval", "authorized", "queued", "in_progress", "outcome_unknown")
            ),
        )
        .order_by(AgentAction.created_at.desc())
        .limit(1)
    )
    if prior is not None:
        state = action_result(db, prior)
        if (
            prior.status not in {"succeeded", "failed", "cancelled"}
            or prior.initiating_cursor == thread.event_cursor
        ):
            return state
    validated = validate_reply(db, clock, context, proposal)
    if not validated.valid:
        return {"valid": False, "errors": list(validated.errors)}
    event = db.scalar(
        select(AgentEvent).where(
            AgentEvent.thread_id == thread.id,
            AgentEvent.cursor == thread.event_cursor,
        )
    )
    goal = db.scalar(
        select(AgentSession).where(
            AgentSession.thread_id == thread.id,
            AgentSession.status.in_(ACTIVE_RUN_STATES),
        )
    )
    owner_source = None
    if proposal.owner_answer:
        from app.owner_requests.service import evidence

        owner_source = evidence(
            db, clock, context, proposal.owner_answer.id, proposal.owner_answer.version
        )
    customer_event = (
        event is not None
        and event.source_kind in {"message", "customer_message", "inbound_message"}
        and event.kind == "customer_message"
    )
    owner_event = (
        event is not None
        and event.kind == "owner_answer"
        and event.source_kind == "owner_question"
        and owner_source is not None
        and event.source_id == str(owner_source[0].id)
        and event.source_version == owner_source[0].version
    )
    if event is None or goal is None or not (customer_event or owner_event):
        raise ToolInputError("no independently evidenced customer response obligation")
    try:
        source_message_id = owner_source[2].id if owner_source else uuid.UUID(event.source_id or "")
    except ValueError as exc:
        raise ToolInputError("invalid customer response obligation") from exc
    newest = db.scalar(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.workspace_id == thread.workspace_id,
            Message.social_account_id == thread.social_account_id,
            Message.id == source_message_id,
            Message.direction == "inbound",
            Message.is_deleted.is_(False),
        )
        .limit(1)
    )
    if newest is None:
        raise ToolInputError("no response obligation")
    if proposal.owner_answer:
        from app.inbox.context import MESSAGING_WINDOW
        from app.operations.send import SEND_MARGIN
        from app.owner_requests.service import notify

        if (
            not conversation.last_inbound_at
            or clock.now() >= conversation.last_inbound_at + MESSAGING_WINDOW - SEND_MARGIN
        ):
            if owner_source is None:
                raise ToolInputError("owner source missing")
            notify(db, clock, context.workspace, owner_source[0], "owner_question.window_closed")
            return {"valid": True, "retained": True, "status": "waiting_customer"}
    draft = ReplyDraft(
        id=uuid.uuid4(),
        workspace_id=thread.workspace_id,
        conversation_id=conversation.id,
        covers_through_message_id=newest.id,
        source="ai",
        language=proposal.language,
        template=proposal.template,
        text=validated.text,
        validation={
            "agent_proposal": proposal.model_dump(mode="json"),
            "ownership_generation": thread.ownership_generation,
            "cursor": thread.event_cursor,
            "deletion_generation": thread.deletion_generation,
        },
        version=1,
        decision="auto",
        status="queued",
        created_by_actor_type="agent",
        is_simulated=conversation.is_simulated,
        created_at=clock.now(),
    )
    action = admit_action(
        db,
        workspace_id=thread.workspace_id,
        account_id=thread.social_account_id,
        thread_id=thread.id,
        session_id=goal.id,
        source_event_id=event.id,
        action_type="dm.send",
        target_ref=str(conversation.id),
        semantic_slot=semantic_slot,
        payload_hash=payload_hash(approval_payload(draft, conversation)),
        clock=clock,
    )
    if action.payload_ref:
        return action_result(db, action)
    draft.origin, draft.agent_action_id = "agent", action.id
    action.payload_ref, action.ownership_generation = draft.id, thread.ownership_generation
    db.add(draft)
    db.flush()
    decision = authorize_action(
        db,
        clock,
        context.workspace,
        action.id,
        source="customer",
        target_owned=True,
        visibility_allowed=True,
        claims_valid=True,
        quota_available=True,
        require_human=require_human,
    )
    if decision.kind not in {"automatic", "ask"}:
        action.status, draft.status = "cancelled", "cancelled"
        action.outcome_code = decision.reason
        return action_result(db, action)
    impact.replace_references(db, context.workspace, "reply_draft", draft.id, list(validated.facts))
    if decision.kind == "automatic":
        draft.approval_id = record_effect_grant(
            db,
            clock,
            context.workspace,
            action_id=action.id,
            subject_type="reply_draft",
            subject_id=draft.id,
            subject_version=draft.version,
            payload=approval_payload(draft, conversation),
            summary={"draft_id": str(draft.id)},
            required_permission="reply.approve",
            expires_at=clock.now() + timedelta(hours=24),
        )
        queue_send(db, clock, draft, action)
    else:
        draft.decision, draft.status, draft.approval_id = (
            "approval_required",
            "pending_approval",
            action.approval_id,
        )
    db.flush()
    return action_result(db, action)


def queue_send(db: Session, clock: Clock, draft: ReplyDraft, action: AgentAction) -> None:
    draft.status, action.status = "queued", "queued"
    enqueue(
        db,
        "send_reply",
        SendReplyPayload(reply_draft_id=draft.id),
        workspace_id=draft.workspace_id,
        correlation_id=None,
        dedup_key=f"send_reply:{draft.id}",
        clock=clock,
    )


def revalidate(db: Session, clock: Clock, draft: ReplyDraft, conversation: Conversation) -> bool:
    from app.core.context import ActorRef, WorkspaceContext
    from app.identity.models import Workspace

    action = db.get(AgentAction, draft.agent_action_id)
    thread = db.get(AgentThread, action.thread_id) if action else None
    workspace = db.get(Workspace, draft.workspace_id)
    if not action or not thread or not workspace or thread.dm_conversation_id != conversation.id:
        return False
    if action.payload_ref != draft.id or action.ownership_generation != thread.ownership_generation:
        return False
    if draft.validation.get("cursor") != thread.event_cursor:
        return False
    if draft.validation.get("deletion_generation") != thread.deletion_generation:
        return False
    context = BrokerContext(
        WorkspaceContext(
            workspace.id,
            ActorRef.system("send"),
            None,
            workspace.timezone,
            workspace.default_locale,
            workspace.is_demo,
        ),
        conversation.social_account_id,
        thread.id,
        "dm",
        "customer",
    )
    try:
        proposal = ReplyValidationArgs.model_validate(draft.validation.get("agent_proposal"))
    except ValueError:
        return False
    checked = validate_reply(db, clock, context, proposal)
    return checked.valid and checked.text == draft.text
