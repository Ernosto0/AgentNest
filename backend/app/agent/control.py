"""Account-first controller ownership. Approval cleanup is always deferred."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agent.jobs import enqueue_cleanup, wake
from app.agent.models import AccountAgent, AgentSession, AgentStep, AgentThread
from app.agent.repository import scoped_account
from app.audit.service import record
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.inbox.models import Conversation


class ControllerChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_config_version: int = Field(ge=1)
    client_request_id: uuid.UUID
    mode: Literal["legacy", "agent"] = "agent"


def change_controller(
    db: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account_id: uuid.UUID,
    change: ControllerChange,
) -> AccountAgent:
    if ctx.actor.type != "user" or ctx.role != "owner":
        raise AppError("FORBIDDEN", permission="agent.control")
    account = scoped_account(db, ctx.workspace_id, account_id, lock=True)
    prior = account.goals.get("control_request", {})
    if prior.get("id") == str(change.client_request_id):
        if prior.get("mode") != change.mode:
            raise AppError("VERSION_CONFLICT")
        return account
    if account.config_version != change.expected_config_version:
        raise AppError("VERSION_CONFLICT")
    account.controller_mode = change.mode
    account.state = "active" if change.mode == "agent" else "inactive"
    account.controller_epoch += 1
    account.config_version += 1
    account.cutover_generation += 1
    account.goals = {
        **account.goals,
        "control_request": {
            "id": str(change.client_request_id),
            "mode": change.mode,
        },
    }
    adopt_threads(db, clock, account)
    enqueue_cleanup(db, clock, ctx.workspace_id, account_id, account.controller_epoch)
    record(
        db,
        ctx,
        "agent.state_changed",
        "account_agent",
        account.id,
        {"controller_mode": change.mode, "controller_epoch": account.controller_epoch},
        clock=clock,
    )
    return account


def adopt_threads(db: Session, clock: Clock, account: AccountAgent) -> None:
    """Fence old claims before adopting a new epoch; never restore an old action grant."""
    threads = db.scalars(
        select(AgentThread)
        .where(
            AgentThread.workspace_id == account.workspace_id,
            AgentThread.social_account_id == account.social_account_id,
        )
        .with_for_update()
    ).all()
    for thread in threads:
        thread.controller_epoch = account.controller_epoch
        thread.ownership_generation += 1
        db.flush()
        invalidate_steps(db, clock, thread)
        for goal in db.scalars(
            select(AgentSession).where(
                AgentSession.thread_id == thread.id,
                AgentSession.status.in_(
                    (
                        "running",
                        "waiting_customer",
                        "waiting_approval",
                        "waiting_operation",
                        "queued",
                    )
                ),
            )
        ):
            queue_replan(db, clock, goal, thread)
            goal.activation_started_at = None
        if (
            account.controller_mode == "agent"
            and account.state == "active"
            and thread.handling_mode == "agent"
        ):
            wake(db, clock, thread.workspace_id, thread.id, f"epoch:{account.controller_epoch}")


def invalidate_steps(db: Session, clock: Clock, thread: AgentThread) -> None:
    goals = select(AgentSession.id).where(AgentSession.thread_id == thread.id)
    for step in db.scalars(
        select(AgentStep).where(
            AgentStep.session_id.in_(goals),
            AgentStep.status.in_(("claimed", "model_pending", "model_done", "dispatched")),
        )
    ):
        from app.agent.transitions import transition_step

        transition_step(
            db,
            workspace_id=thread.workspace_id,
            step_id=step.id,
            claim_token=step.claim_token,
            expected_status=step.status,
            next_status="stale",
            clock=clock,
        )


def ensure_thread(db: Session, conversation: Conversation, account: AccountAgent) -> AgentThread:
    thread = db.scalar(
        select(AgentThread)
        .where(
            AgentThread.workspace_id == conversation.workspace_id,
            AgentThread.social_account_id == conversation.social_account_id,
            AgentThread.surface == "dm",
            AgentThread.source_ref == str(conversation.id),
        )
        .with_for_update()
    )
    if thread is None:
        thread = AgentThread(
            workspace_id=conversation.workspace_id,
            social_account_id=conversation.social_account_id,
            surface="dm",
            source_ref=str(conversation.id),
            dm_conversation_id=conversation.id,
            controller_epoch=account.controller_epoch,
            handling_mode="human" if conversation.handling_mode == "human" else "agent",
        )
        db.add(thread)
        db.flush()
    return thread


def takeover_thread(db: Session, clock: Clock, conversation: Conversation, *, human: bool) -> bool:
    account = scoped_account(
        db, conversation.workspace_id, conversation.social_account_id, lock=True
    )
    if account.controller_mode != "agent":
        return False
    thread = ensure_thread(db, conversation, account)
    thread.handling_mode = "human" if human else "agent"
    thread.ownership_generation += 1
    db.flush()
    invalidate_steps(db, clock, thread)
    if not human:
        from app.agent.models import ACTIVE_RUN_STATES
        from app.agent.repository import add_event_and_wake
        from app.agent.transitions import transition_session, transition_thread
        from app.inbox.models import Message

        def latest_direction(direction: str) -> Message | None:
            return db.scalar(
                select(Message)
                .where(
                    Message.workspace_id == conversation.workspace_id,
                    Message.conversation_id == conversation.id,
                    Message.social_account_id == conversation.social_account_id,
                    Message.direction == direction,
                    Message.is_deleted.is_(False),
                )
                .order_by(
                    Message.provider_timestamp.desc(), Message.created_at.desc(), Message.id.desc()
                )
                .limit(1)
            )

        latest = latest_direction("inbound")
        outbound = latest_direction("outbound")
        unanswered = latest is not None and (
            outbound is None
            or (latest.provider_timestamp, latest.created_at, latest.id)
            > (outbound.provider_timestamp, outbound.created_at, outbound.id)
        )
        goals = list(
            db.scalars(
                select(AgentSession).where(
                    AgentSession.thread_id == thread.id,
                    AgentSession.status.in_(ACTIVE_RUN_STATES),
                )
            )
        )
        if unanswered:
            if latest is not None:
                add_event_and_wake(
                    db,
                    workspace_id=conversation.workspace_id,
                    account_id=conversation.social_account_id,
                    thread_id=thread.id,
                    kind="customer_message",
                    source_kind="message",
                    source_key=str(latest.id),
                    source_id=str(latest.id),
                    source_version=1,
                    clock=clock,
                )
            for goal in goals:
                queue_replan(db, clock, goal, thread)
                goal.activation_started_at = None
            wake(
                db,
                clock,
                conversation.workspace_id,
                thread.id,
                f"release:{thread.ownership_generation}",
            )
        else:
            # A native/manual answer already discharged this response obligation.
            # Keep unknown operation evidence; only stop the obsolete conversational goal.
            for goal in goals:
                transition_session(
                    db,
                    workspace_id=goal.workspace_id,
                    session_id=goal.id,
                    expected_status=goal.status,
                    expected_version=goal.version,
                    next_status="cancelled",
                    clock=clock,
                )
            if thread.state not in {"completed", "cancelled", "failed"}:
                transition_thread(
                    db,
                    workspace_id=thread.workspace_id,
                    thread_id=thread.id,
                    expected_status=thread.state,
                    expected_version=thread.thread_version,
                    next_status="cancelled",
                    clock=clock,
                )
                db.refresh(thread)
            thread.current_goal_key = f"event:{thread.event_cursor}"
    enqueue_cleanup(
        db,
        clock,
        account.workspace_id,
        account.social_account_id,
        f"thread:{thread.id}:{thread.ownership_generation}",
    )
    return True


def retire_stale_drafts(
    factory: sessionmaker[Session], clock: Clock, workspace_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    """After policy/cutover commit, acquire approval -> account -> draft, never the reverse."""
    from app.agent.delegation import current_action_authority
    from app.agent.models import AgentAction
    from app.approvals.models import Approval
    from app.inbox import drafts
    from app.inbox.models import ReplyDraft

    with factory() as db:
        ids = db.execute(
            select(ReplyDraft.id, ReplyDraft.approval_id)
            .join(
                Conversation,
                Conversation.id == ReplyDraft.conversation_id,
            )
            .where(
                ReplyDraft.workspace_id == workspace_id,
                Conversation.social_account_id == account_id,
                ReplyDraft.status.in_(("queued", "pending_approval")),
            )
        ).all()
    for draft_id, approval_id in ids:
        with factory() as db:
            approval = (
                db.scalar(select(Approval).where(Approval.id == approval_id).with_for_update())
                if approval_id
                else None
            )
            controller = scoped_account(db, workspace_id, account_id, lock=True)
            draft = db.scalar(select(ReplyDraft).where(ReplyDraft.id == draft_id).with_for_update())
            if draft is None or draft.status not in {"queued", "pending_approval"}:
                continue
            action = db.get(AgentAction, draft.agent_action_id) if draft.agent_action_id else None
            stale = (
                (
                    not current_action_authority(db, action)
                    or action.status in {"cancelled", "failed"}
                )
                if action
                else (
                    draft.source != "owner"
                    and (
                        controller.controller_mode == "agent"
                        or draft.validation.get("controller_cutover_generation", 0)
                        != controller.cutover_generation
                    )
                )
            )
            if stale:
                if approval is not None and approval.status == "pending":
                    from app.approvals.service import cancel_for_subject

                    cancel_for_subject(
                        db,
                        clock,
                        _context(db, workspace_id),
                        approval.subject_type,
                        approval.subject_id,
                        "CONTROLLER_CHANGED",
                    )
                drafts.transition(
                    db,
                    clock,
                    _context(db, workspace_id),
                    draft,
                    "cancel",
                    reason="CONTROLLER_CHANGED",
                )
                if action and action.status not in {"in_progress", "outcome_unknown", "succeeded"}:
                    action.status = "cancelled"
            db.commit()


def _context(db: Session, workspace_id: uuid.UUID) -> WorkspaceContext:
    from app.inbox.system import system_context

    ctx = system_context(db, workspace_id, "agent.cleanup")
    if ctx is None:
        raise ValueError("workspace missing")
    return ctx


def queue_replan(db: Session, clock: Clock, goal: AgentSession, thread: AgentThread) -> None:
    from app.agent.transitions import transition_session, transition_thread

    if goal.status != "queued":
        transition_session(
            db,
            workspace_id=goal.workspace_id,
            session_id=goal.id,
            expected_status=goal.status,
            expected_version=goal.version,
            next_status="queued",
            clock=clock,
        )
        db.refresh(goal)
    if thread.state not in {"queued", "completed", "cancelled", "failed"}:
        transition_thread(
            db,
            workspace_id=thread.workspace_id,
            thread_id=thread.id,
            expected_status=thread.state,
            expected_version=thread.thread_version,
            next_status="queued",
            clock=clock,
        )
        db.refresh(thread)
