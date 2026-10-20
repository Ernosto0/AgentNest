"""Actions of people on conversations and drafts (api-design.md §2.6, state-machines.md §4).

Manual replies, edits and cancellations are the human side of the reply workflow. Every send
still needs an approval bound to its exact text: someone who may approve records their own
(``self_approved``, one request), anyone else asks for one (ADR-014).
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals import service as approvals
from app.approvals.grants import record_policy_grant
from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity.models import Workspace
from app.identity.permissions import has_permission
from app.inbox import attention, drafts
from app.inbox.approval_payload import approval_payload, approval_summary
from app.inbox.context import MESSAGING_WINDOW
from app.inbox.language import choose_reply_language
from app.inbox.models import Conversation, Message, ReplyDraft
from app.inbox.payloads import DraftReplyPayload, SendReplyPayload, draft_reply_key
from app.inbox.reply_workflow import SEND_MARGIN, deadlines
from app.inbox.schemas import ValidationIssueOut
from app.inbox.views import issue_out
from app.integrations.instagram import queries
from app.jobs.queue import enqueue
from app.knowledge import impact
from app.knowledge import service as knowledge_service
from app.knowledge.claims import validate_claims
from app.knowledge.render import RenderResult

MAX_REPLY_BYTES = 1000


# --- reading -------------------------------------------------------------------------------------


def get_conversation(
    session: Session, ctx: WorkspaceContext, conversation_id: uuid.UUID, *, lock: bool = False
) -> Conversation:
    stmt = select(Conversation).where(
        Conversation.workspace_id == ctx.workspace_id, Conversation.id == conversation_id
    )
    conversation = session.scalars(stmt.with_for_update() if lock else stmt).one_or_none()
    if conversation is None:
        raise AppError("NOT_FOUND")
    return conversation


def get_draft(session: Session, ctx: WorkspaceContext, draft_id: uuid.UUID) -> ReplyDraft:
    draft = drafts.get_draft(session, ctx.workspace_id, draft_id)
    if draft is None:
        raise AppError("NOT_FOUND")
    return draft


def list_conversations(
    session: Session, ctx: WorkspaceContext, *, attention_filter: str | None, limit: int = 50
) -> list[Conversation]:
    stmt = select(Conversation).where(Conversation.workspace_id == ctx.workspace_id)
    if attention_filter and attention_filter != "any":
        stmt = stmt.where(Conversation.attention == attention_filter)
    return list(
        session.scalars(
            stmt.order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.id).limit(
                limit
            )
        )
    )


def recent_messages(
    session: Session, ctx: WorkspaceContext, conversation: Conversation, limit: int = 100
) -> list[Message]:
    rows = session.scalars(
        select(Message)
        .where(Message.workspace_id == ctx.workspace_id, Message.conversation_id == conversation.id)
        .order_by(Message.provider_timestamp.desc(), Message.created_at.desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))


# --- warnings for a person's own text -----------------------------------------------------


def text_warnings(
    session: Session, clock: Clock, ctx: WorkspaceContext, text: str, language: str
) -> list[ValidationIssueOut]:
    """The claim validator on a person's own words. Never blocking (a person may write what they
    like), but a number that is not a verified value is shown so it is a conscious choice."""
    report = validate_claims(text, RenderResult(text=text), language)
    displays = [
        f.display for f in knowledge_service.usable_facts(session, clock, ctx, locale=language)
    ]
    return [
        issue_out(issue.to_dict(), matches_verified=any(issue.text in d for d in displays))
        for issue in report.issues
    ]


def _check_text(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise AppError(
            "VALIDATION_FAILED", errors=[{"field": "text", "code": "required", "params": {}}]
        )
    if len(stripped.encode("utf-8")) > MAX_REPLY_BYTES:
        raise AppError(
            "VALIDATION_FAILED",
            errors=[
                {"field": "text", "code": "too_long", "params": {"max_bytes": MAX_REPLY_BYTES}}
            ],
        )
    return stripped


def _window_end(conversation: Conversation) -> datetime:
    if conversation.last_inbound_at is None:
        raise AppError("MESSAGING_WINDOW_CLOSED")
    return conversation.last_inbound_at + MESSAGING_WINDOW


def _check_sendable(
    session: Session, clock: Clock, ctx: WorkspaceContext, conversation: Conversation
) -> datetime:
    """The account must be usable and the window open; returns the window end."""
    account = queries.get_account_in_workspace(
        session, ctx.workspace_id, conversation.social_account_id
    )
    if (
        account is None
        or account.status != "connected"
        or account.capabilities.get("messaging") is not True
    ):
        raise AppError("ACCOUNT_NOT_CONNECTED")
    end = _window_end(conversation)
    if clock.now() >= end - SEND_MARGIN - timedelta(minutes=1):
        raise AppError("MESSAGING_WINDOW_CLOSED")
    return end


def _newest_message_id(session: Session, conversation: Conversation) -> uuid.UUID:
    message_id = session.scalar(
        select(Message.id)
        .where(
            Message.workspace_id == conversation.workspace_id,
            Message.conversation_id == conversation.id,
        )
        .order_by(Message.provider_timestamp.desc(), Message.created_at.desc())
        .limit(1)
    )
    if message_id is None:
        raise AppError("CONFLICT_STATE", entity="conversation", reason="no_messages")
    return message_id


def _newest_inbound_id(session: Session, conversation: Conversation) -> uuid.UUID | None:
    return session.scalar(
        select(Message.id)
        .where(
            Message.workspace_id == conversation.workspace_id,
            Message.conversation_id == conversation.id,
            Message.direction == "inbound",
        )
        .order_by(Message.provider_timestamp.desc(), Message.created_at.desc())
        .limit(1)
    )


def _reply_language(session: Session, ctx: WorkspaceContext, text: str) -> str:
    workspace = session.get(Workspace, ctx.workspace_id)
    default = workspace.default_locale if workspace else "tr"
    chosen = choose_reply_language([text], default_locale=default, reply_languages=["tr", "en"])
    return chosen.code or default


# --- sending a person's own reply ----------------------------------------------------------------


def _authorise(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    draft: ReplyDraft,
    conversation: Conversation,
    window_end: datetime,
    *,
    approve: bool,
) -> None:
    """Attach the approval for ``draft``: self-approved and queued when the person may approve and
    wants to send, otherwise a pending request for someone who may."""
    now = clock.now()
    expires_at, execute_before = deadlines(window_end, now)
    arguments = {
        "action": "reply.send",
        "subject_type": drafts.SUBJECT_TYPE,
        "subject_id": draft.id,
        "subject_version": draft.version,
        "payload": approval_payload(draft, conversation),
        "summary": approval_summary(
            draft.id, conversation.id, ["OWNER_REPLY"], window_end.isoformat()
        ),
        "required_permission": "reply.approve",
        "expires_at": expires_at,
        "execute_before": execute_before,
        "is_simulated": draft.is_simulated,
    }
    if approve and ctx.role is not None and has_permission(ctx.role, "reply.approve"):
        approval = record_policy_grant(session, clock, ctx, self_approved=True, **arguments)  # type: ignore[arg-type]
        draft.approval_id = approval.id
        if draft.status == "pending_approval":
            drafts.transition(session, clock, ctx, draft, "approve")
        enqueue(
            session,
            "send_reply",
            SendReplyPayload(reply_draft_id=draft.id),
            workspace_id=draft.workspace_id,
            correlation_id=None,
            dedup_key=f"send_reply:{draft.id}",
            clock=clock,
        )
    else:
        approval = approvals.request(session, clock, ctx, kind="authorization", **arguments)  # type: ignore[arg-type]
        draft.approval_id = approval.id
    session.flush()


def submit_manual_reply(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    conversation_id: uuid.UUID,
    *,
    text: str,
    client_request_id: str,
    from_draft_id: uuid.UUID | None,
) -> tuple[ReplyDraft, list[ValidationIssueOut]]:
    """A reply written by a person. Idempotent per author and ``client_request_id``. Commits."""
    conversation = get_conversation(session, ctx, conversation_id, lock=True)
    existing = session.scalars(
        select(ReplyDraft).where(
            ReplyDraft.workspace_id == ctx.workspace_id,
            ReplyDraft.created_by_actor_id == ctx.actor.id,
            ReplyDraft.client_request_id == client_request_id,
        )
    ).first()
    if existing is not None:
        return existing, [issue_out(i) for i in existing.validation.get("issues", [])]

    text = _check_text(text)
    window_end = _check_sendable(session, clock, ctx, conversation)
    if from_draft_id is not None:
        source = get_draft(session, ctx, from_draft_id)
        if source.conversation_id != conversation.id:
            raise AppError("NOT_FOUND")
    open_draft = drafts.get_open_draft(session, ctx.workspace_id, conversation.id)
    if open_draft is not None and open_draft.status in ("sending", "outcome_unknown"):
        raise AppError("CONFLICT_STATE", entity="reply_draft", reason="reply_in_flight")
    closed = drafts.close_open_drafts(
        session,
        clock,
        ctx,
        conversation,
        reason="MANUAL_REPLY",
        events={"pending_approval": "supersede", "needs_human": "supersede", "queued": "cancel"},
    )

    language = _reply_language(session, ctx, text)
    warnings = text_warnings(session, clock, ctx, text, language)
    can_approve = ctx.role is not None and has_permission(ctx.role, "reply.approve")
    draft = ReplyDraft(
        workspace_id=ctx.workspace_id,
        conversation_id=conversation.id,
        covers_through_message_id=_newest_message_id(session, conversation),
        source="owner",
        language=language,
        text=text,
        validation={
            "passed": not warnings,
            "issues": [w.model_dump() for w in warnings],
            "rendered": [],
        },
        decision="approval_required",
        decision_reasons=["OWNER_REPLY"],
        status="queued" if can_approve else "pending_approval",
        created_by_actor_type=ctx.actor.type,
        created_by_actor_id=ctx.actor.id,
        client_request_id=client_request_id,
        is_simulated=conversation.is_simulated,
        created_at=clock.now(),
    )
    session.add(draft)
    session.flush()
    for old in closed:
        old.superseded_by_id = draft.id
    _authorise(session, clock, ctx, draft, conversation, window_end, approve=True)
    audit.record(
        session,
        ctx,
        "reply_draft.created",
        "reply_draft",
        draft.id,
        {
            "conversation_id": conversation.id,
            "decision": draft.decision,
            "reasons": ["OWNER_REPLY"],
            "status": draft.status,
            "source": "owner",
            "warnings": [w.code for w in warnings],
        },
        is_simulated=draft.is_simulated,
        clock=clock,
    )
    attention.refresh(session, conversation)
    session.commit()
    return draft, warnings


def edit_draft(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    draft_id: uuid.UUID,
    *,
    text: str,
    expected_version: int,
    approve: bool,
) -> tuple[ReplyDraft, list[ValidationIssueOut]]:
    """Change the text of a draft that still waits for approval. The old approval is withdrawn
    and a new one is bound to the new text (INV-16). Commits."""
    draft = drafts.get_draft(session, ctx.workspace_id, draft_id, lock=True)
    if draft is None:
        raise AppError("NOT_FOUND")
    if draft.version != expected_version:
        raise AppError("VERSION_CONFLICT", expected=expected_version, current=draft.version)
    if draft.status != "pending_approval":
        raise AppError("CONFLICT_STATE", entity="reply_draft", status=draft.status)
    conversation = get_conversation(session, ctx, draft.conversation_id, lock=True)
    text = _check_text(text)
    window_end = _check_sendable(session, clock, ctx, conversation)

    approvals.cancel_for_subject(
        session, clock, ctx, drafts.SUBJECT_TYPE, draft.id, "SUBJECT_EDITED"
    )
    language = draft.language or _reply_language(session, ctx, text)
    warnings = text_warnings(session, clock, ctx, text, language)
    draft.text = text
    draft.source = "owner"  # no longer the grounded rendering of a template
    draft.template = None
    draft.suggestion_text = None
    draft.language = language
    draft.validation = {
        "passed": not warnings,
        "issues": [w.model_dump() for w in warnings],
        "rendered": [],
    }
    draft.decision_reasons = ["OWNER_EDIT"]
    drafts.transition(session, clock, ctx, draft, "edit")  # version + 1
    impact.replace_references(session, ctx, "reply_draft", draft.id, [])
    _authorise(session, clock, ctx, draft, conversation, window_end, approve=approve)
    attention.refresh(session, conversation)
    session.commit()
    return draft, warnings


def cancel_draft(
    session: Session, clock: Clock, ctx: WorkspaceContext, draft_id: uuid.UUID
) -> ReplyDraft:
    """Withdraw a reply that is queued but not yet sent. Commits."""
    draft = drafts.get_draft(session, ctx.workspace_id, draft_id, lock=True)
    if draft is None:
        raise AppError("NOT_FOUND")
    if draft.status != "queued":
        raise AppError("CONFLICT_STATE", entity="reply_draft", status=draft.status)
    drafts.transition(session, clock, ctx, draft, "cancel", reason="OWNER_CANCELLED")
    attention.refresh(session, get_conversation(session, ctx, draft.conversation_id, lock=True))
    session.commit()
    return draft


# --- handling mode -------------------------------------------------------------------------------


def takeover(
    session: Session, clock: Clock, ctx: WorkspaceContext, conversation_id: uuid.UUID
) -> Conversation:
    """The person takes over: no drafts are made, and a waiting draft is withdrawn. Commits."""
    conversation = get_conversation(session, ctx, conversation_id, lock=True)
    if conversation.handling_mode != "human":
        conversation.handling_mode = "human"
        drafts.close_open_drafts(
            session,
            clock,
            ctx,
            conversation,
            reason="HUMAN_TAKEOVER",
            events=drafts.ON_TAKEOVER,
        )
        audit.record(
            session, ctx, "conversation.takeover", "conversation", conversation.id, {},
            is_simulated=conversation.is_simulated, clock=clock,
        )  # fmt: skip
        attention.refresh(session, conversation)
    session.commit()
    return conversation


def release(
    session: Session, clock: Clock, ctx: WorkspaceContext, conversation_id: uuid.UUID
) -> Conversation:
    """Back to automatic handling; a customer message still waiting is drafted. Commits."""
    conversation = get_conversation(session, ctx, conversation_id, lock=True)
    if conversation.handling_mode != "automatic":
        conversation.handling_mode = "automatic"
        audit.record(
            session, ctx, "conversation.release", "conversation", conversation.id, {},
            is_simulated=conversation.is_simulated, clock=clock,
        )  # fmt: skip
        newest = _newest_inbound_id(session, conversation)
        answered = (
            conversation.last_outbound_at is not None
            and conversation.last_inbound_at is not None
            and conversation.last_outbound_at >= conversation.last_inbound_at
        )
        if newest is not None and not answered:
            enqueue(
                session,
                "draft_reply",
                DraftReplyPayload(conversation_id=conversation.id),
                workspace_id=conversation.workspace_id,
                correlation_id=None,
                dedup_key=draft_reply_key(conversation.id),
                clock=clock,
            )
        attention.refresh(session, conversation)
    session.commit()
    return conversation


def suggest_reply(
    session: Session, clock: Clock, ctx: WorkspaceContext, conversation_id: uuid.UUID
) -> None:
    """Ask for a draft now, also in human mode (an explicit request). Commits."""
    conversation = get_conversation(session, ctx, conversation_id, lock=True)
    newest = _newest_inbound_id(session, conversation)
    if newest is None:
        raise AppError("CONFLICT_STATE", entity="conversation", reason="no_customer_message")
    open_draft = drafts.get_open_draft(session, ctx.workspace_id, conversation.id)
    if open_draft is not None and open_draft.status in ("queued", "sending", "outcome_unknown"):
        raise AppError("CONFLICT_STATE", entity="reply_draft", reason="reply_in_flight")
    drafts.close_open_drafts(
        session,
        clock,
        ctx,
        conversation,
        reason="SUGGEST_REQUESTED",
        events={"pending_approval": "supersede", "needs_human": "supersede"},
    )
    enqueue(
        session,
        "draft_reply",
        DraftReplyPayload(conversation_id=conversation.id, requested=True),
        workspace_id=conversation.workspace_id,
        correlation_id=None,
        dedup_key=draft_reply_key(conversation.id, requested=True),
        clock=clock,
    )
    attention.refresh(session, conversation)
    session.commit()
