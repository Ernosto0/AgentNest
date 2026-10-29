"""Manual moderation uses the same ledger/provider/readback boundary as agent moderation."""

import uuid

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agent.repository import scoped_account
from app.audit.service import record
from app.comments.models import PublicComment, PublicMedia
from app.core.clock import Clock
from app.core.config import Settings, get_settings
from app.identity.models import User, Workspace, WorkspaceMember
from app.identity.permissions import has_permission
from app.integrations.instagram import queries
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


class ManualCommentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: uuid.UUID


def _queue_reconcile(db: Session, clock: Clock, op: Operation) -> None:
    enqueue(
        db,
        "reconcile_manual_comment",
        ManualCommentPayload(operation_id=op.id),
        workspace_id=op.workspace_id,
        correlation_id=op.id,
        dedup_key=f"reconcile_manual_comment:{op.id}",
        clock=clock,
    )


def _audit(db: Session, clock: Clock, op: Operation) -> None:
    record(
        db,
        None,
        f"operation.{op.status}"
        if op.status in {"succeeded", "failed", "outcome_unknown"}
        else "operation.started",
        "operation",
        op.id,
        {"status": op.status},
        workspace_id=op.workspace_id,
        is_simulated=op.is_simulated,
        clock=clock,
    )


def _finish(
    db: Session, clock: Clock, op: Operation, result: object, error: Exception | None
) -> None:
    from app.integrations.instagram.base import PublicEffectResult

    if op.status not in {"in_progress", "outcome_unknown"}:
        return
    if isinstance(result, PublicEffectResult):
        set_operation(clock, op, "succeed")
        op.result = {"provider_id": result.provider_id, "state": result.state}
        target = db.scalar(
            select(PublicComment)
            .where(
                PublicComment.id == op.subject_id,
                PublicComment.workspace_id == op.workspace_id,
                PublicComment.social_account_id == op.social_account_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            target is not None
            and target.workspace_id == op.workspace_id
            and target.social_account_id == op.social_account_id
            and target.version == op.provider_ref.get("comment_version")
        ):
            target.version += 1
            target.state = result.state or "unknown"
            target.updated_at = clock.now()
            if op.provider_ref.get("effect") == "delete":
                from app.comments.privacy import redact_receipts

                target.text = None
                redact_receipts(db, op.workspace_id, op.social_account_id, target.external_id)
    elif (
        isinstance(error, ProviderError)
        and not isinstance(error, ProviderOutcomeUnknown)
        and op.status == "in_progress"
    ):
        set_operation(
            clock,
            op,
            "fail",
            code=error.request_code if isinstance(error, ProviderInvalidRequest) else error.code,
        )
    else:
        if op.status == "in_progress":
            set_operation(clock, op, "unknown", code="OUTCOME_UNKNOWN")
        _queue_reconcile(db, clock, op)
    _audit(db, clock, op)


def execute(
    factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
    workspace: uuid.UUID,
    operation_id: uuid.UUID,
) -> None:
    with factory() as db:
        op = db.scalar(
            select(Operation).where(
                Operation.workspace_id == workspace,
                Operation.id == operation_id,
                Operation.subject_type == "public_comment",
            )
        )
        if op is None:
            return
        scoped_account(db, workspace, op.social_account_id, lock=True)
        db.refresh(op, with_for_update=True)
        if op.status in {"in_progress", "outcome_unknown"}:
            if op.status == "in_progress":
                set_operation(clock, op, "unknown", code="WORKER_INTERRUPTED")
            _queue_reconcile(db, clock, op)
            db.commit()
            return
        if op.status != "pending":
            return
        account = queries.get_account_in_workspace(db, workspace, op.social_account_id)
        target = db.scalar(
            select(PublicComment)
            .where(
                PublicComment.workspace_id == workspace,
                PublicComment.social_account_id == op.social_account_id,
                PublicComment.id == op.subject_id,
            )
            .with_for_update()
        )
        media = db.get(PublicMedia, target.media_id) if target else None
        actor_id = uuid.UUID(op.provider_ref["actor_id"])
        user = db.get(User, actor_id)
        workspace_row = db.get(Workspace, workspace)
        member = db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace, WorkspaceMember.user_id == actor_id
            )
        )
        effect = str(op.provider_ref["effect"])
        valid = (
            account is not None
            and account.provider_kind == "mock"
            and account.status in {"connected", "degraded"}
            and account.capabilities.get("comment_moderate") is True
            and user is not None
            and user.is_active
            and member is not None
            and workspace_row is not None
            and workspace_row.status == "active"
            and has_permission(member.role, "comments.moderate")
            and target is not None
            and not target.is_owner
            and target.version == op.provider_ref.get("comment_version")
            and media is not None
            and media.version == op.provider_ref.get("media_version")
            and media.ownership_state == "verified_synthetic"
            and media.state != "deleted"
            and target.state == ("hidden" if effect == "unhide" else "visible")
            and op.deadline_at is not None
            and clock.now() < op.deadline_at
        )
        if not valid:
            set_operation(clock, op, "cancel", code="APPROVAL_STALE")
            record(
                db,
                None,
                "operation.failed",
                "operation",
                op.id,
                {"status": "cancelled", "reason": "APPROVAL_STALE"},
                workspace_id=op.workspace_id,
                is_simulated=op.is_simulated,
                clock=clock,
            )
            db.commit()
            return
        if account is None or target is None:
            return
        ref = account_ref(account, settings)
        external, key = target.external_id, op.idempotency_key
        set_operation(clock, op, "start")
        op.attempts += 1
        op.started_at = clock.now()
        db.commit()
    provider = get_provider("mock", settings=settings, session_factory=factory, clock=clock)
    result = None
    error = None
    try:
        result = provider.perform_comment_effect(ref, external, effect, None, key)
    except Exception as exc:
        error = exc
    with factory() as db:
        op = db.scalar(
            select(Operation)
            .where(Operation.workspace_id == workspace, Operation.id == operation_id)
            .with_for_update()
        )
        if op is not None:
            _finish(db, clock, op, result, error)
        db.commit()


def reconcile(
    factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
    workspace: uuid.UUID,
    operation_id: uuid.UUID,
) -> None:
    with factory() as db:
        op = db.scalar(
            select(Operation).where(
                Operation.workspace_id == workspace,
                Operation.id == operation_id,
                Operation.subject_type == "public_comment",
                Operation.status == "outcome_unknown",
            )
        )
        if op is None:
            return
        account = queries.get_account_in_workspace(db, workspace, op.social_account_id)
        if account is None or account.provider_kind != "mock":
            return
        ref, key = account_ref(account, settings), op.idempotency_key
    provider = get_provider("mock", settings=settings, session_factory=factory, clock=clock)
    try:
        result = provider.find_comment_effect(ref, key)
    except Exception:
        return
    if result is None:
        return
    with factory() as db:
        op = db.scalar(
            select(Operation)
            .where(Operation.workspace_id == workspace, Operation.id == operation_id)
            .with_for_update()
        )
        if op is not None:
            _finish(db, clock, op, result, None)
        db.commit()


@job_handler("manual_comment_effect", ManualCommentPayload, max_attempts=3)
def execute_job(job: JobContext) -> None:
    if isinstance(job.payload, ManualCommentPayload) and job.workspace_id:
        execute(
            job.session_factory,
            job.clock,
            get_settings(),
            job.workspace_id,
            job.payload.operation_id,
        )


@job_handler("reconcile_manual_comment", ManualCommentPayload, max_attempts=3)
def reconcile_job(job: JobContext) -> None:
    if isinstance(job.payload, ManualCommentPayload) and job.workspace_id:
        reconcile(
            job.session_factory,
            job.clock,
            get_settings(),
            job.workspace_id,
            job.payload.operation_id,
        )
