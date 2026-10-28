"""One committed private reply attempt; ambiguous outcomes never release the reservation."""

import uuid
from datetime import timedelta

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agent.delegation import fence_action
from app.agent.models import AgentAction
from app.approvals.models import Approval
from app.audit.service import record
from app.comments.models import PrivateReplyOpportunity, PublicComment
from app.comments.private_reply import eligibility
from app.core.clock import Clock
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.ids import new_id
from app.integrations.instagram import queries
from app.integrations.instagram.base import AccountRef, PrivateReplyResult
from app.integrations.instagram.errors import (
    ProviderError,
    ProviderInvalidRequest,
    ProviderOutcomeUnknown,
)
from app.integrations.instagram.registry import account_ref, get_provider
from app.jobs.queue import enqueue
from app.jobs.registry import JobContext, job_handler
from app.operations.models import Operation
from app.operations.resolution import set_operation


class PrivateReplyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: uuid.UUID


class ReconcilePrivateReplyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: uuid.UUID


def _wake(factory: sessionmaker[Session], clock: Clock, action_id: uuid.UUID) -> None:
    from app.agent.jobs import wake

    with factory() as db:
        action = db.get(AgentAction, action_id)
        if action is not None:
            wake(
                db,
                clock,
                action.workspace_id,
                action.thread_id,
                f"private-reply:{action.id}:{action.status}",
            )
            db.commit()


def _terminal(
    db: Session,
    clock: Clock,
    action: AgentAction,
    row: PrivateReplyOpportunity,
    status: str,
    code: str,
) -> None:
    action.status, action.outcome_code = status, code
    row.status = status
    row.text = None
    row.proposal = None
    record(
        db,
        None,
        "agent.action_transition",
        "agent_action",
        action.id,
        {"status": status, "code": code},
        workspace_id=action.workspace_id,
        clock=clock,
    )


def _queue_reconcile(db: Session, clock: Clock, op: Operation) -> None:
    enqueue(
        db,
        "reconcile_private_comment_reply",
        ReconcilePrivateReplyPayload(operation_id=op.id),
        workspace_id=op.workspace_id,
        correlation_id=op.id,
        run_at=clock.now() + timedelta(seconds=2),
        dedup_key=f"reconcile_private_comment_reply:{op.id}",
        clock=clock,
    )


def _prepare(
    db: Session, clock: Clock, settings: Settings, workspace_id: uuid.UUID, action_id: uuid.UUID
) -> tuple[uuid.UUID, str, AccountRef, str, str] | None:
    candidate = db.scalar(
        select(AgentAction).where(
            AgentAction.id == action_id, AgentAction.workspace_id == workspace_id
        )
    )
    if candidate is None:
        return None
    from app.agent.repository import scoped_account

    scoped_account(db, workspace_id, candidate.social_account_id, lock=True)
    action = db.scalar(
        select(AgentAction)
        .where(AgentAction.id == action_id, AgentAction.workspace_id == workspace_id)
        .with_for_update()
    )
    if action is None or action.status not in {
        "queued",
        "authorized",
        "in_progress",
        "outcome_unknown",
    }:
        return None
    row = db.get(PrivateReplyOpportunity, action.payload_ref)
    if row is None or row.agent_action_id != action.id:
        return None
    key = f"private_comment_reply:{row.comment_id}"
    op = db.scalar(select(Operation).where(Operation.idempotency_key == key).with_for_update())
    if op is not None:
        action.operation_id = op.id
        if op.status in {"in_progress", "outcome_unknown"}:
            if op.status == "in_progress":
                set_operation(clock, op, "unknown", code="WORKER_INTERRUPTED")
                action.status, row.status = "outcome_unknown", "outcome_unknown"
                _queue_reconcile(db, clock, op)
            return None
        if op.status in {"succeeded", "failed", "cancelled"}:
            action.status, row.status = op.status, op.status
            return None
    account = queries.get_account_in_workspace(db, workspace_id, action.social_account_id)
    if account is None or account.provider_kind != "mock":
        _terminal(db, clock, action, row, "failed", "PRIVATE_REPLY_NOT_VERIFIED")
        return None
    if (
        account.status not in {"connected", "degraded"}
        or account.capabilities.get("comment_private_reply") is not True
    ):
        _terminal(db, clock, action, row, "cancelled", "CAPABILITY_MISSING")
        return None
    try:
        fence_action(
            db,
            clock,
            workspace_id,
            action.id,
            expected_action="comment.private_reply",
            payload_hash_value=action.payload_hash,
        )
        if not eligibility(db, clock, action):
            raise AppError("APPROVAL_STALE")
        if action.policy_grant is None:
            approval = db.get(Approval, action.approval_id) if action.approval_id else None
            if (
                approval is None
                or approval.status != "approved"
                or approval.subject_type != "agent_action"
                or approval.subject_id != action.id
                or approval.subject_version != action.version
                or approval.payload_hash != action.payload_hash
                or (approval.execute_before is not None and clock.now() >= approval.execute_before)
            ):
                raise AppError("APPROVAL_STALE")
    except AppError:
        _terminal(db, clock, action, row, "cancelled", "APPROVAL_STALE")
        return None
    source = db.get(PublicComment, row.comment_id)
    if source is None or row.text is None:
        _terminal(db, clock, action, row, "cancelled", "SOURCE_MISSING")
        return None
    if op is None:
        op = Operation(
            id=new_id(),
            workspace_id=workspace_id,
            social_account_id=account.id,
            operation_type="comment_private_reply",
            idempotency_key=key,
            subject_type="private_reply_opportunity",
            subject_id=row.id,
            provider_kind=account.provider_kind,
            status="pending",
            attempts=0,
            max_attempts=1,
            deadline_at=min(
                row.eligibility_expires_at, action.execute_before or row.eligibility_expires_at
            ),
            is_simulated=account.is_simulated,
            created_at=clock.now(),
        )
        db.add(op)
        db.flush()
    action.operation_id = op.id
    if action.policy_grant is None and action.approval_id:
        approval = db.get(Approval, action.approval_id)
        if approval is None or (
            approval.operation_id is not None and approval.operation_id != op.id
        ):
            _terminal(db, clock, action, row, "cancelled", "APPROVAL_STALE")
            return None
        approval.operation_id = op.id
    set_operation(clock, op, "start")
    op.attempts += 1
    op.started_at = clock.now()
    op.provider_ref = {"comment_id": source.external_id, "comment_version": row.comment_version}
    action.status = "in_progress"
    return op.id, key, account_ref(account, settings), source.external_id, row.text


def _finish(
    db: Session,
    clock: Clock,
    op: Operation,
    answer: PrivateReplyResult | None,
    error: Exception | None,
) -> uuid.UUID | None:
    action = db.scalar(
        select(AgentAction).where(AgentAction.operation_id == op.id).with_for_update()
    )
    if action is None or op.status not in {"in_progress", "outcome_unknown"}:
        return None
    row = db.get(PrivateReplyOpportunity, action.payload_ref)
    if row is None:
        return None
    if answer is not None:
        set_operation(clock, op, "succeed")
        op.result = {
            "provider_reply_id": answer.reply_id,
            "recipient_known": answer.recipient_id is not None,
        }
        action.status = row.status = "succeeded"
        row.provider_reply_id, row.provider_recipient_id = answer.reply_id, answer.recipient_id
        row.text, row.proposal = None, None
    elif (
        isinstance(error, ProviderError)
        and not isinstance(error, ProviderOutcomeUnknown)
        and op.status == "in_progress"
    ):
        code = error.request_code if isinstance(error, ProviderInvalidRequest) else error.code
        set_operation(clock, op, "fail", code=code)
        _terminal(db, clock, action, row, "failed", code)
    else:
        if op.status == "in_progress":
            set_operation(clock, op, "unknown", code="OUTCOME_UNKNOWN")
        action.status = row.status = "outcome_unknown"
        row.text, row.proposal = None, None
        _queue_reconcile(db, clock, op)
    record(
        db,
        None,
        "agent.action_transition",
        "agent_action",
        action.id,
        {"status": action.status, "operation_id": op.id},
        workspace_id=action.workspace_id,
        is_simulated=op.is_simulated,
        clock=clock,
    )
    return action.id


def execute(
    factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
    workspace_id: uuid.UUID,
    action_id: uuid.UUID,
) -> None:
    with factory() as db:
        prepared = _prepare(db, clock, settings, workspace_id, action_id)
        db.commit()
    if prepared is None:
        _wake(factory, clock, action_id)
        return
    operation_id, key, account, comment_id, text = prepared
    provider = get_provider("mock", settings=settings, session_factory=factory, clock=clock)
    answer = None
    error = None
    try:
        answer = provider.send_private_reply(account, comment_id, text, key)
    except Exception as exc:
        error = exc
    with factory() as db:
        op = db.scalar(
            select(Operation)
            .where(Operation.id == operation_id, Operation.workspace_id == workspace_id)
            .with_for_update()
        )
        if op is not None:
            _finish(db, clock, op, answer, error)
        db.commit()
    _wake(factory, clock, action_id)


def reconcile(
    factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
    workspace_id: uuid.UUID,
    operation_id: uuid.UUID,
) -> None:
    with factory() as db:
        op = db.scalar(
            select(Operation).where(
                Operation.id == operation_id, Operation.workspace_id == workspace_id
            )
        )
        if op is None or op.status != "outcome_unknown":
            return
        account = queries.get_account_in_workspace(db, workspace_id, op.social_account_id)
        if account is None or account.provider_kind != "mock":
            return
        ref, key = account_ref(account, settings), op.idempotency_key
    provider = get_provider("mock", settings=settings, session_factory=factory, clock=clock)
    try:
        answer = provider.find_private_reply(ref, key)
    except Exception:
        return
    if answer is None:
        return
    with factory() as db:
        op = db.scalar(
            select(Operation)
            .where(Operation.id == operation_id, Operation.workspace_id == workspace_id)
            .with_for_update()
        )
        if op is not None and op.status == "outcome_unknown":
            action_id = _finish(db, clock, op, answer, None)
            db.commit()
            if action_id:
                _wake(factory, clock, action_id)


@job_handler("private_comment_reply", PrivateReplyPayload, max_attempts=1)
def execute_job(job: JobContext) -> None:
    if isinstance(job.payload, PrivateReplyPayload) and job.workspace_id:
        execute(
            job.session_factory, job.clock, get_settings(), job.workspace_id, job.payload.action_id
        )


@job_handler("reconcile_private_comment_reply", ReconcilePrivateReplyPayload, max_attempts=1)
def reconcile_job(job: JobContext) -> None:
    if isinstance(job.payload, ReconcilePrivateReplyPayload) and job.workspace_id:
        reconcile(
            job.session_factory,
            job.clock,
            get_settings(),
            job.workspace_id,
            job.payload.operation_id,
        )
