"""One-shot comment-to-private-reply admission and identity evidence."""

import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select, true
from sqlalchemy.orm import Session

from app.agent.delegation import authorize_action
from app.agent.grounding import ReplyValidationArgs, validate_reply
from app.agent.models import ACTIVE_RUN_STATES, AgentAction, AgentEvent, AgentSession, AgentThread
from app.agent.repository import admit_action, scoped_account, scoped_thread
from app.agent.tools.broker import BrokerContext, ToolInputError
from app.comments.models import PrivateReplyOpportunity, PublicComment, PublicMedia
from app.comments.ownership import media_ownership_ok
from app.comments.private_reply_rules import refusal
from app.core.canonical import payload_hash
from app.core.clock import Clock
from app.core.config import get_settings
from app.inbox.models import Conversation
from app.integrations.instagram.base import META_PRIVATE_REPLY_WINDOW, MOCK_PRIVATE_REPLY_WINDOW
from app.integrations.instagram.models import SocialAccount
from app.jobs.queue import enqueue
from app.plans import service as usage


class PrivateReplyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment_id: uuid.UUID
    comment_version: int = Field(ge=1)
    reply: ReplyValidationArgs


def exact_payload(row: PrivateReplyOpportunity) -> dict[str, object]:
    return {
        "comment_id": str(row.comment_id),
        "comment_version": row.comment_version,
        "media_version": row.media_version,
        "text": row.text,
        "proposal": row.proposal,
        "eligibility_expires_at": row.eligibility_expires_at.isoformat(),
    }


def result(db: Session, action: AgentAction) -> dict[str, object]:
    from app.operations.models import Operation

    if action.operation_id:
        op = db.get(Operation, action.operation_id)
        if op is not None:
            action.status = op.status if op.status != "pending" else "queued"
    return {
        "action_id": str(action.id),
        "status": action.status,
        "approval_id": str(action.approval_id) if action.status == "waiting_approval" else None,
        "operation_id": str(action.operation_id) if action.operation_id else None,
    }


def eligibility(db: Session, clock: Clock, action: AgentAction) -> bool:
    """Recheck source and policy-bound opportunity before any dispatch."""
    from app.core.context import ActorRef, WorkspaceContext
    from app.identity.models import Workspace

    row = db.get(PrivateReplyOpportunity, action.payload_ref)
    if row is None or row.agent_action_id != action.id or row.status != "reserved":
        return False
    if payload_hash(exact_payload(row)) != action.payload_hash:
        return False
    comment = db.get(PublicComment, row.comment_id)
    media = db.get(PublicMedia, comment.media_id) if comment else None
    thread = db.get(AgentThread, action.thread_id)
    if (
        comment is None
        or media is None
        or thread is None
        or comment.workspace_id != action.workspace_id
        or comment.social_account_id != action.social_account_id
        or comment.thread_id != thread.public_thread_id
        or comment.version != row.comment_version
        or comment.state != "visible"
        or comment.is_owner
        or media.version != row.media_version
        or media.state != "visible"
        or not media_ownership_ok(media, comment.is_simulated)
        or clock.now() >= row.eligibility_expires_at
    ):
        return False
    account = db.get(SocialAccount, action.social_account_id)
    if (
        account is not None
        and account.provider_kind == "meta"
        and real_refusal(db, clock, comment, exclude=row.id)
    ):
        return False
    workspace = db.get(Workspace, action.workspace_id)
    if workspace is None or row.proposal is None:
        return False
    ctx = BrokerContext(
        WorkspaceContext(
            workspace.id,
            ActorRef.system("private_reply"),
            None,
            workspace.timezone,
            workspace.default_locale,
            workspace.is_demo,
        ),
        action.social_account_id,
        thread.id,
        "comment",
        "customer",
    )
    checked = validate_reply(db, clock, ctx, ReplyValidationArgs.model_validate(row.proposal))
    if not (checked.valid and checked.text == row.text):
        return False
    if action.policy_grant is not None:
        from app.agent.knowledge import prices_shared
        from app.agent.policy import classify_request

        proposal_dict = row.proposal if isinstance(row.proposal, dict) else {}
        re_check = classify_request(
            action_type="comment.private_reply",
            surface="comment",
            inbound_text=comment.text,
            template=proposal_dict.get("template"),
            prices_shared=prices_shared(db, clock, ctx.workspace),
            recent_transcript=False,
        )
        if not re_check.is_basic or re_check.is_blocked:
            return False
    return True


def propose(db: Session, clock: Clock, ctx: BrokerContext, args: BaseModel) -> dict[str, object]:
    request = PrivateReplyArgs.model_validate(args)
    scoped_account(db, ctx.workspace.workspace_id, ctx.account_id, lock=True)
    account = db.get(SocialAccount, ctx.account_id)
    real = account is not None and account.provider_kind == "meta"
    if (
        account is not None
        and real
        and (
            not account.comment_automation_enabled
            or account.capabilities.get("comment_private_reply") is not True
        )
    ):
        raise ToolInputError("CAPABILITY_MISSING")
    thread = scoped_thread(db, ctx.workspace.workspace_id, ctx.account_id, ctx.thread_id, lock=True)
    if ctx.surface != "comment" or thread.surface != "comment" or thread.handling_mode != "agent":
        raise ToolInputError("public thread unavailable")
    event = db.scalar(
        select(AgentEvent).where(
            AgentEvent.workspace_id == thread.workspace_id,
            AgentEvent.thread_id == thread.id,
            AgentEvent.cursor == thread.event_cursor,
            AgentEvent.kind == "customer_comment",
            AgentEvent.source_kind == "comment",
            AgentEvent.source_id == str(request.comment_id),
            AgentEvent.source_version == request.comment_version,
        )
    )
    goal = db.scalar(
        select(AgentSession).where(
            AgentSession.thread_id == thread.id,
            AgentSession.status.in_(ACTIVE_RUN_STATES),
        )
    )
    if event is None or goal is None:
        raise ToolInputError("no current source comment obligation")
    comment = db.scalar(
        select(PublicComment)
        .where(
            PublicComment.id == request.comment_id,
            PublicComment.workspace_id == thread.workspace_id,
            PublicComment.social_account_id == thread.social_account_id,
            PublicComment.thread_id == thread.public_thread_id,
        )
        .with_for_update()
    )
    from app.comments.reservations import unresolved

    if comment is not None and unresolved(
        db, ctx.workspace.workspace_id, ctx.account_id, comment.id
    ):
        raise ToolInputError("manual moderation pending or unresolved")
    if comment is None:
        raise ToolInputError("target unavailable")
    prior = db.scalar(
        select(PrivateReplyOpportunity).where(
            PrivateReplyOpportunity.social_account_id == thread.social_account_id,
            PrivateReplyOpportunity.comment_id == comment.id,
        )
    )
    if real:
        reason = real_refusal(db, clock, comment, comment_used=prior is not None)
        if reason:
            raise ToolInputError(reason)
    if prior is not None:
        existing = db.get(AgentAction, prior.agent_action_id)
        if existing is None:
            raise ToolInputError("private reply reserved")
        return result(db, existing)
    media = db.get(PublicMedia, comment.media_id)
    expires = (
        comment.provider_timestamp
        + (META_PRIVATE_REPLY_WINDOW if real else MOCK_PRIVATE_REPLY_WINDOW)
        if comment.provider_timestamp
        else None
    )
    if (
        comment.version != request.comment_version
        or comment.state != "visible"
        or comment.is_owner
        or media is None
        or media.state != "visible"
        or not media_ownership_ok(media, comment.is_simulated)
        or expires is None
        or clock.now() >= expires
    ):
        raise ToolInputError("private reply ineligible")
    validated = validate_reply(db, clock, ctx, request.reply)
    if not validated.valid:
        return {"valid": False, "errors": list(validated.errors)}
    if not usage.consume(
        db, clock, thread.workspace_id, f"private:{thread.id}:{thread.event_cursor}"
    ):
        return {"status": "quota_paused", "reason": usage.PAUSED_REASON}
    body = {
        "comment_id": str(comment.id),
        "comment_version": comment.version,
        "media_version": media.version,
        "text": validated.text,
        "proposal": request.reply.model_dump(mode="json"),
        "eligibility_expires_at": expires.isoformat(),
    }
    action = admit_action(
        db,
        workspace_id=thread.workspace_id,
        account_id=thread.social_account_id,
        thread_id=thread.id,
        session_id=goal.id,
        source_event_id=event.id,
        action_type="comment.private_reply",
        target_ref=str(comment.id),
        semantic_slot="private_invitation",
        payload_hash=payload_hash(body),
        clock=clock,
    )
    if action.payload_ref:
        return result(db, action)
    row = PrivateReplyOpportunity(
        workspace_id=thread.workspace_id,
        social_account_id=thread.social_account_id,
        comment_id=comment.id,
        agent_action_id=action.id,
        comment_version=comment.version,
        media_version=media.version,
        text=validated.text,
        proposal=request.reply.model_dump(mode="json"),
        status="reserved",
        eligibility_expires_at=expires,
        created_at=clock.now(),
    )
    db.add(row)
    db.flush()
    action.payload_ref = row.id
    decision = authorize_action(
        db,
        clock,
        ctx.workspace,
        action.id,
        source="customer",
        target_owned=True,
        visibility_allowed=True,
        claims_valid=True,
        quota_available=True,
    )
    if decision.kind not in {"automatic", "ask"}:
        action.status, action.outcome_code = "cancelled", decision.reason
        row.status = "cancelled"
    else:
        action.execute_before = min(action.execute_before or expires, expires)
        if decision.kind == "automatic":
            queue(db, clock, action)
    return result(db, action)


def queue(db: Session, clock: Clock, action: AgentAction) -> None:
    from app.operations.private_reply import PrivateReplyPayload

    action.status = "queued"
    enqueue(
        db,
        "private_comment_reply",
        PrivateReplyPayload(action_id=action.id),
        workspace_id=action.workspace_id,
        correlation_id=action.id,
        dedup_key=f"private_comment_reply:{action.id}",
        clock=clock,
    )


def bind_inbound(
    db: Session, account_id: uuid.UUID, conversation: Conversation
) -> PrivateReplyOpportunity | None:
    """Link only after an actual inbound DM with the returned recipient identifier."""
    matches = list(
        db.scalars(
            select(PrivateReplyOpportunity)
            .where(
                PrivateReplyOpportunity.workspace_id == conversation.workspace_id,
                PrivateReplyOpportunity.social_account_id == account_id,
                PrivateReplyOpportunity.provider_recipient_id == conversation.customer_external_id,
                PrivateReplyOpportunity.status == "succeeded",
                PrivateReplyOpportunity.bound_conversation_id.is_(None),
            )
            .order_by(PrivateReplyOpportunity.created_at.desc())
            .limit(2)
            .with_for_update()
        )
    )
    if len(matches) != 1:
        return None
    matches[0].bound_conversation_id = conversation.id
    return matches[0]


def dm_source_context(db: Session, conversation: Conversation) -> dict[str, object] | None:
    """Private-only source provenance after provider identity and inbound are both present."""
    from app.comments.service import display_text

    row = db.scalar(
        select(PrivateReplyOpportunity)
        .where(
            PrivateReplyOpportunity.workspace_id == conversation.workspace_id,
            PrivateReplyOpportunity.social_account_id == conversation.social_account_id,
            PrivateReplyOpportunity.bound_conversation_id == conversation.id,
            PrivateReplyOpportunity.provider_recipient_id == conversation.customer_external_id,
            PrivateReplyOpportunity.status == "succeeded",
        )
        .order_by(PrivateReplyOpportunity.created_at.desc())
        .limit(1)
    )
    if row is None:
        return None
    source = db.get(PublicComment, row.comment_id)
    media = db.get(PublicMedia, source.media_id) if source else None
    if source is None or media is None or source.state != "visible" or media.state != "visible":
        return None
    return {
        "source_comment_id": str(source.id),
        "source_comment_version": source.version,
        "comment_text": display_text(source.text, 280),
        "post_caption": display_text(media.caption, 320),
        "provider_identity_evidence": str(row.id),
    }


def real_refusal(
    db: Session,
    clock: Clock,
    comment: PublicComment,
    *,
    exclude: uuid.UUID | None = None,
    comment_used: bool = False,
) -> str | None:
    used = db.scalar(
        select(PrivateReplyOpportunity.id)
        .join(PublicComment, PublicComment.id == PrivateReplyOpportunity.comment_id)
        .where(
            PrivateReplyOpportunity.workspace_id == comment.workspace_id,
            PrivateReplyOpportunity.social_account_id == comment.social_account_id,
            PublicComment.workspace_id == comment.workspace_id,
            PublicComment.social_account_id == comment.social_account_id,
            PublicComment.author_external_id == comment.author_external_id,
            PrivateReplyOpportunity.id != exclude if exclude else true(),
            or_(
                PrivateReplyOpportunity.status.in_(("succeeded", "outcome_unknown")),
                (PrivateReplyOpportunity.status == "reserved")
                & (PrivateReplyOpportunity.eligibility_expires_at > clock.now()),
            ),
        )
        .limit(1)
    )
    return refusal(
        now=clock.now(),
        posted_at=comment.provider_timestamp,
        author_id=comment.author_external_id,
        parent_id=str(comment.parent_id) if comment.parent_id else None,
        comment_used=comment_used,
        commenter_used=used is not None,
        limit_scope=get_settings().comment_private_reply_limit_scope,
    )
