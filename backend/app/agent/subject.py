"""Exact-action approval callback for account-agent effects."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import delegation
from app.agent.models import AgentAction
from app.approvals import callbacks
from app.approvals.models import Approval
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError


def _action(session: Session, ctx: WorkspaceContext, action_id: uuid.UUID) -> AgentAction | None:
    candidate = session.scalar(
        select(AgentAction).where(
            AgentAction.workspace_id == ctx.workspace_id, AgentAction.id == action_id
        )
    )
    if candidate is None:
        return None
    from app.agent.repository import scoped_account

    scoped_account(session, ctx.workspace_id, candidate.social_account_id, lock=True)
    return session.scalar(
        select(AgentAction)
        .where(
            AgentAction.workspace_id == ctx.workspace_id,
            AgentAction.id == action_id,
        )
        .with_for_update()
    )


def on_decided(session: Session, clock: Clock, ctx: WorkspaceContext, approval: Approval) -> None:
    action = _action(session, ctx, approval.subject_id)
    if action is None:
        raise AppError("NOT_FOUND")
    if action.status != "waiting_approval" or action.version != approval.subject_version:
        if approval.status == "expired":
            return
        raise AppError("APPROVAL_STALE")
    if (
        action.approval_id != approval.id
        or approval.summary.get("payload_hash") != action.payload_hash
        or approval.payload_hash != action.payload_hash
    ):
        raise AppError("APPROVAL_STALE")
    if approval.status == "approved":
        # This also verifies revocation, pause, takeover and grantor membership. Do not
        # dispatch here: the coordinator must project the exact domain subject first.
        delegation.fence_action(
            session, clock, ctx.workspace_id, action.id, allow_waiting_approval=True
        )
        # An explicit approval does not enlarge the delegation's daily limit.
        # _action already holds the account serialization lock across this reservation.
        from datetime import UTC, datetime, time

        from sqlalchemy import func

        current = delegation.current_delegation(session, ctx.workspace_id, action.social_account_id)
        policy = delegation.DelegationPolicy.model_validate(current.policy) if current else None
        rule = (
            next(
                (rule for name, rule in policy.actions.items() if name == action.action_type), None
            )
            if policy
            else None
        )
        if rule is None:
            raise AppError("APPROVAL_STALE")
        limit = rule.max_per_day
        if limit is not None:
            day_start = datetime.combine(clock.now().astimezone(UTC).date(), time.min, tzinfo=UTC)
            used = (
                session.scalar(
                    select(func.count(AgentAction.id)).where(
                        AgentAction.workspace_id == action.workspace_id,
                        AgentAction.social_account_id == action.social_account_id,
                        AgentAction.action_type == action.action_type,
                        AgentAction.authorized_at >= day_start,
                        AgentAction.status.in_(
                            ("authorized", "queued", "in_progress", "succeeded", "outcome_unknown")
                        ),
                    )
                )
                or 0
            )
            if used >= limit:
                raise AppError("APPROVAL_STALE")
        action.status = "authorized"
        action.authorized_at = clock.now()
        if action.action_type == "comment.private_reply":
            from app.comments.private_reply import eligibility, queue

            if not eligibility(session, clock, action):
                raise AppError("APPROVAL_STALE")
            queue(session, clock, action)
        if action.action_type in {
            "comment.reply",
            "comment.hide",
            "comment.unhide",
            "comment.delete",
        }:
            from app.comments.actions import queue
            from app.comments.actions import revalidate as revalidate_public

            if not revalidate_public(session, clock, action):
                raise AppError("APPROVAL_STALE")
            queue(session, clock, action)
        if action.action_type == "dm.send" and action.payload_ref:
            from app.agent.dm import queue_send, revalidate
            from app.inbox.models import Conversation, ReplyDraft

            draft = session.get(ReplyDraft, action.payload_ref)
            if draft is None or draft.agent_action_id != action.id:
                raise AppError("APPROVAL_STALE")
            conversation = session.get(Conversation, draft.conversation_id)
            if (
                draft.status != "pending_approval"
                or conversation is None
                or not revalidate(session, clock, draft, conversation)
            ):
                raise AppError("APPROVAL_STALE")
            queue_send(session, clock, draft, action)
    elif approval.status in ("rejected", "expired"):
        action.status = "cancelled"
        if action.action_type == "comment.private_reply" and action.payload_ref:
            from app.comments.models import PrivateReplyOpportunity

            row = session.get(PrivateReplyOpportunity, action.payload_ref)
            if row is not None and row.status == "reserved":
                row.status, row.text, row.proposal = "cancelled", None, None
        if action.action_type == "dm.send" and action.payload_ref:
            from app.inbox import drafts
            from app.inbox.models import ReplyDraft

            draft = session.get(ReplyDraft, action.payload_ref)
            if draft is not None and draft.status == "pending_approval":
                drafts.transition(
                    session,
                    clock,
                    ctx,
                    draft,
                    "reject" if approval.status == "rejected" else "expire",
                )
    else:
        return
    from app.agent.jobs import wake

    wake(
        session,
        clock,
        action.workspace_id,
        action.thread_id,
        f"approval:{approval.id}:{approval.status}",
    )


def current_version(session: Session, ctx: WorkspaceContext, action_id: uuid.UUID) -> int | None:
    action = _action(session, ctx, action_id)
    return (
        action.version
        if action is not None
        and action.status == "waiting_approval"
        and delegation.current_action_authority(session, action)
        else None
    )


def status_of(session: Session, ctx: WorkspaceContext, action_id: uuid.UUID) -> str | None:
    action = _action(session, ctx, action_id)
    return action.status if action is not None else None


callbacks.register(
    "agent_action",
    on_decided,
    current_version=current_version,
    status_of=status_of,
)
