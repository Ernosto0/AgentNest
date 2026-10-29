"""Scoped, exact public-effect proposals. No provider calls occur here."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.delegation import authorize_action
from app.agent.grounding import ReplyValidationArgs, validate_reply
from app.agent.models import ACTIVE_RUN_STATES, AgentAction, AgentEvent, AgentSession
from app.agent.repository import admit_action, scoped_account, scoped_thread
from app.agent.tools.broker import BrokerContext, ToolInputError
from app.comments.models import PublicComment, PublicCommentAction, PublicMedia
from app.core.canonical import payload_hash
from app.core.clock import Clock
from app.jobs.queue import enqueue


class PublicReplyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment_id: uuid.UUID
    comment_version: int = Field(ge=1)
    reply: ReplyValidationArgs


class ModerateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment_id: uuid.UUID
    comment_version: int = Field(ge=1)
    effect: Literal["hide", "unhide", "delete"]


def payload(effect: PublicCommentAction) -> dict[str, object]:
    return {
        "comment_id": str(effect.comment_id),
        "comment_version": effect.comment_version,
        "media_version": effect.media_version,
        "effect": effect.effect,
        "text": effect.text,
        "proposal": effect.proposal,
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


def propose(db: Session, clock: Clock, ctx: BrokerContext, args: BaseModel) -> dict[str, object]:
    request = (
        PublicReplyArgs.model_validate(args)
        if isinstance(args, PublicReplyArgs)
        else ModerateArgs.model_validate(args)
    )
    scoped_account(db, ctx.workspace.workspace_id, ctx.account_id, lock=True)
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
        )
    )
    goal = db.scalar(
        select(AgentSession).where(
            AgentSession.thread_id == thread.id,
            AgentSession.status.in_(ACTIVE_RUN_STATES),
        )
    )
    if event is None or goal is None:
        raise ToolInputError("no current customer comment obligation")
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
        db, thread.workspace_id, thread.social_account_id, comment.id
    ):
        raise ToolInputError("manual moderation pending or unresolved")
    if comment is None or comment.version != request.comment_version or comment.is_owner:
        raise ToolInputError("target unavailable or stale")
    media = db.scalar(
        select(PublicMedia).where(
            PublicMedia.id == comment.media_id,
            PublicMedia.workspace_id == thread.workspace_id,
            PublicMedia.social_account_id == thread.social_account_id,
        )
    )
    if media is None or media.state == "deleted" or media.ownership_state != "verified_synthetic":
        raise ToolInputError("media ownership unavailable")
    effect_name = "reply" if isinstance(request, PublicReplyArgs) else request.effect
    if (effect_name in {"reply", "hide", "delete"} and comment.state != "visible") or (
        effect_name == "unhide" and comment.state != "hidden"
    ):
        raise ToolInputError("target state invalid")
    pending = db.scalar(
        select(AgentAction)
        .where(
            AgentAction.workspace_id == thread.workspace_id,
            AgentAction.social_account_id == thread.social_account_id,
            AgentAction.target_ref == str(comment.id),
            AgentAction.action_type.in_(
                ("comment.reply", "comment.hide", "comment.unhide", "comment.delete")
            ),
            AgentAction.status.in_(
                (
                    "proposed",
                    "waiting_approval",
                    "authorized",
                    "queued",
                    "in_progress",
                    "outcome_unknown",
                )
            ),
        )
        .order_by(AgentAction.created_at.desc())
        .limit(1)
    )
    if pending is not None:
        return result(db, pending)
    if effect_name == "reply":
        repeated = db.scalar(
            select(AgentAction)
            .where(
                AgentAction.workspace_id == thread.workspace_id,
                AgentAction.social_account_id == thread.social_account_id,
                AgentAction.target_ref == str(comment.id),
                AgentAction.action_type == "comment.reply",
                AgentAction.status == "succeeded",
            )
            .limit(1)
        )
        if repeated is not None:
            return result(db, repeated)
    validated = None
    proposal = None
    if isinstance(request, PublicReplyArgs):
        validated = validate_reply(db, clock, ctx, request.reply)
        if not validated.valid:
            return {"valid": False, "errors": list(validated.errors)}
        proposal = request.reply.model_dump(mode="json")
    body = {
        "comment_id": str(comment.id),
        "comment_version": comment.version,
        "media_version": media.version,
        "effect": effect_name,
        "text": validated.text if validated else None,
        "proposal": proposal,
    }
    action = admit_action(
        db,
        workspace_id=thread.workspace_id,
        account_id=thread.social_account_id,
        thread_id=thread.id,
        session_id=goal.id,
        source_event_id=event.id,
        action_type=f"comment.{effect_name}",
        target_ref=str(comment.id),
        semantic_slot="public_response" if effect_name == "reply" else "moderation",
        payload_hash=payload_hash(body),
        clock=clock,
    )
    if action.payload_ref:
        return result(db, action)
    subject = PublicCommentAction(
        workspace_id=thread.workspace_id,
        social_account_id=thread.social_account_id,
        comment_id=comment.id,
        agent_action_id=action.id,
        effect=effect_name,
        text=validated.text if validated else None,
        proposal=proposal,
        comment_version=comment.version,
        media_version=media.version,
        created_at=clock.now(),
    )
    db.add(subject)
    db.flush()
    action.payload_ref = subject.id
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
    elif decision.kind == "automatic":
        queue(db, clock, action)
    return result(db, action)


def queue(db: Session, clock: Clock, action: AgentAction) -> None:
    from app.operations.public_comments import PublicEffectPayload

    action.status = "queued"
    enqueue(
        db,
        "public_comment_effect",
        PublicEffectPayload(action_id=action.id),
        workspace_id=action.workspace_id,
        correlation_id=action.id,
        dedup_key=f"public_comment_effect:{action.id}",
        clock=clock,
    )


def revalidate(db: Session, clock: Clock, action: AgentAction) -> bool:
    from app.core.context import ActorRef, WorkspaceContext
    from app.identity.models import Workspace

    subject = db.get(PublicCommentAction, action.payload_ref)
    if (
        subject is None
        or subject.agent_action_id != action.id
        or payload_hash(payload(subject)) != action.payload_hash
    ):
        return False
    thread = scoped_thread(db, action.workspace_id, action.social_account_id, action.thread_id)
    comment = db.get(PublicComment, subject.comment_id)
    media = db.get(PublicMedia, comment.media_id) if comment else None
    if (
        comment is None
        or media is None
        or comment.workspace_id != action.workspace_id
        or comment.social_account_id != action.social_account_id
        or comment.thread_id != thread.public_thread_id
        or comment.version != subject.comment_version
        or media.version != subject.media_version
        or media.state == "deleted"
        or media.ownership_state != "verified_synthetic"
        or comment.is_owner
    ):
        return False
    if (subject.effect in {"reply", "hide", "delete"} and comment.state != "visible") or (
        subject.effect == "unhide" and comment.state != "hidden"
    ):
        return False
    if subject.effect == "reply":
        workspace = db.get(Workspace, action.workspace_id)
        if workspace is None or subject.proposal is None:
            return False
        ctx = BrokerContext(
            WorkspaceContext(
                workspace.id,
                ActorRef.system("public_effect"),
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
        validated = validate_reply(
            db, clock, ctx, ReplyValidationArgs.model_validate(subject.proposal)
        )
        return validated.valid and validated.text == subject.text
    return True
