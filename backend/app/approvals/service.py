"""Approvals (workflows.md §D, ADR-014, INV-04, INV-16).

An approval is bound to an exact subject version and payload hash, is decided only by an
explicit action of a human who holds the permission (or, for a ``confirmation``, is the
requester), is single-use, and expires. Free text never approves.

Transaction rules: ``request``, ``cancel_for_subject`` and ``expire_one`` write inside the
caller's transaction and never commit. ``decide`` and ``expire_due`` own theirs. The decided
callback runs in the **same transaction** as the decision, so a failing callback rolls the
decision back and the approval stays pending.
"""

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.approvals import callbacks
from app.approvals import repository as repo
from app.approvals.guards import ApprovalFacts, decision_blocker, may_decide
from app.approvals.models import Approval
from app.approvals.transitions import apply_approval_event
from app.audit import service as audit
from app.core.canonical import payload_hash as compute_payload_hash
from app.core.clock import Clock
from app.core.context import ActorRef, WorkspaceContext
from app.core.errors import AppError
from app.notifications import service as notifications

DECISIONS = {"approve": "approve", "reject": "reject"}
_RESULT_STATUS = {"approve": "approved", "reject": "rejected"}


def _facts(approval: Approval) -> ApprovalFacts:
    return ApprovalFacts(
        kind=approval.kind,
        status=approval.status,
        required_permission=approval.required_permission,
        requested_by_actor_type=approval.requested_by_actor_type,
        requested_by_actor_id=approval.requested_by_actor_id,
        payload_hash=approval.payload_hash,
        subject_version=approval.subject_version,
        expires_at=approval.expires_at,
    )


def _system(ctx: WorkspaceContext) -> WorkspaceContext:
    """The same workspace, acting as the system (expiry has no human actor)."""
    return WorkspaceContext(
        ctx.workspace_id,
        ActorRef.system("approvals.expire"),
        None,
        ctx.timezone,
        ctx.locale,
        ctx.is_demo,
    )


def can_decide(approval: Approval, ctx: WorkspaceContext, now: datetime) -> bool:
    """Whether the UI should offer the decision buttons to ``ctx``'s actor."""
    return (
        approval.status == "pending"
        and now < approval.expires_at
        and may_decide(_facts(approval), ctx.actor, ctx.role)
    )


def _audit(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    action: str,
    approval: Approval,
    **extra: Any,
) -> None:
    audit.record(
        session,
        ctx,
        action,
        "approval",
        approval.id,
        {
            "action": approval.action,
            "kind": approval.kind,
            "subject_type": approval.subject_type,
            "subject_id": approval.subject_id,
            **extra,
        },
        is_simulated=approval.is_simulated,
        clock=clock,
    )


# --- request --------------------------------------------------------------------------------


def request(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    kind: str,
    action: str,
    subject_type: str,
    subject_id: uuid.UUID,
    subject_version: int,
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
    required_permission: str,
    expires_at: datetime,
    execute_before: datetime | None = None,
    is_simulated: bool = False,
) -> Approval:
    """Create a pending approval for exactly ``payload`` (in the caller's transaction).

    ``authorization`` approvals notify everyone who may decide them; a ``confirmation`` does
    not, because its requester is looking at the card. One pending approval per subject: a
    second ``request`` is a ``CONFLICT_STATE``.
    """
    approval = Approval(
        workspace_id=ctx.workspace_id,
        kind=kind,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        subject_version=subject_version,
        payload_hash=compute_payload_hash(payload),
        summary=dict(summary),
        required_permission=required_permission,
        status=apply_approval_event(None, "request"),
        requested_by_actor_type=ctx.actor.type,
        requested_by_actor_id=ctx.actor.id,
        expires_at=expires_at,
        execute_before=execute_before,
        is_simulated=is_simulated,
        created_at=clock.now(),
    )
    try:
        with session.begin_nested():
            session.add(approval)
    except IntegrityError as exc:  # the partial unique index: already one pending
        raise AppError(
            "CONFLICT_STATE", reason="approval_pending", subject_type=subject_type
        ) from exc
    _audit(session, clock, ctx, "approval.requested", approval, expires_at=expires_at)
    if kind == "authorization":
        notifications.notify_permission_holders(
            session,
            clock,
            ctx,
            permission=required_permission,
            type="approval.requested",
            severity="attention",
            params={"action": action, "summary": approval.summary},
            subject_type="approval",
            subject_id=approval.id,
            dedup_key=f"approval:{approval.id}",
            is_simulated=is_simulated,
        )
    return approval


# --- expiry ---------------------------------------------------------------------------------


def expire_one(session: Session, clock: Clock, ctx: WorkspaceContext, approval: Approval) -> None:
    """Expire a locked, due approval and tell its subject (callback in this transaction)."""
    approval.status = apply_approval_event(approval.status, "expire")
    _audit(session, clock, ctx, "approval.expired", approval)
    handler = callbacks.get(approval.subject_type)
    if handler is not None:
        handler.on_decided(session, clock, ctx, approval)
    if approval.requested_by_actor_type == "user" and approval.requested_by_actor_id:
        notifications.notify(
            session,
            clock,
            ctx,
            recipient_user_id=uuid.UUID(approval.requested_by_actor_id),
            type="approval.expired",
            params={"action": approval.action, "summary": approval.summary},
            subject_type="approval",
            subject_id=approval.id,
            dedup_key=f"approval-expired:{approval.id}",
            is_simulated=approval.is_simulated,
        )


def expire_due_in_workspace(session: Session, clock: Clock, ctx: WorkspaceContext) -> int:
    """Lazy expiry on reads: expire this workspace's due approvals and commit."""
    due = repo.due_pending(session, ctx, clock.now())
    if not due:
        return 0
    system = _system(ctx)
    for approval in due:
        expire_one(session, clock, system, approval)
    session.commit()
    return len(due)


# --- decide ---------------------------------------------------------------------------------


def decide(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    approval_id: uuid.UUID,
    *,
    decision: str,
    payload_hash: str,
    note: str | None = None,
    channel: str = "web",
) -> Approval:
    """Approve or reject with the hash the user saw. Commits.

    409 ``APPROVAL_ALREADY_DECIDED`` / ``APPROVAL_EXPIRED`` / ``APPROVAL_STALE``, 403 without
    permission, 404 for another workspace's approval. The subject's decided-callback runs in
    this transaction; if it raises, nothing is saved.
    """
    if decision not in DECISIONS:
        raise AppError(
            "VALIDATION_FAILED", errors=[{"field": "decision", "code": "invalid", "params": {}}]
        )
    approval = repo.get_approval(session, ctx, approval_id, lock=True)
    if approval is None:
        raise AppError("NOT_FOUND")
    now = clock.now()
    handler = callbacks.get(approval.subject_type)
    subject_version = (
        handler.current_version(session, ctx, approval.subject_id) if handler else None
    )
    blocker = decision_blocker(
        _facts(approval),
        actor=ctx.actor,
        role=ctx.role,
        now=now,
        supplied_hash=payload_hash,
        subject_version=subject_version,
    )
    if blocker == "APPROVAL_EXPIRED":
        if approval.status == "pending":
            # Persist the expiry (and its callback) even though the request is refused.
            expire_one(session, clock, _system(ctx), approval)
            session.commit()
        raise AppError("APPROVAL_EXPIRED")
    if blocker == "FORBIDDEN":
        raise AppError("FORBIDDEN", permission=approval.required_permission)
    if blocker is not None:
        raise AppError(blocker)

    try:
        approval.status = apply_approval_event(approval.status, decision)
        approval.decided_by_user_id = uuid.UUID(ctx.actor.id) if ctx.actor.id else None
        approval.decided_at = now
        approval.decision_channel = channel
        approval.decision_note = note[:500] if note else None
        session.flush()
        _audit(
            session,
            clock,
            ctx,
            f"approval.{_RESULT_STATUS[decision]}",
            approval,
            channel=channel,
        )
        if handler is not None:
            handler.on_decided(session, clock, ctx, approval)
        session.commit()
    except Exception:
        session.rollback()  # no half-states: the approval stays pending
        raise
    return approval


# --- cancel and execution -------------------------------------------------------------------


def cancel_for_subject(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    subject_type: str,
    subject_id: uuid.UUID,
    reason: str,
) -> bool:
    """Cancel the subject's pending approval (edit, supersede, fact change, withdrawal).

    In the caller's transaction. Returns whether there was a pending approval to cancel.
    """
    approval = repo.get_pending_for_subject(session, ctx, subject_type, subject_id, lock=True)
    if approval is None:
        return False
    approval.status = apply_approval_event(approval.status, "cancel")
    approval.cancel_reason = reason
    _audit(session, clock, ctx, "approval.cancelled", approval, reason=reason)
    return True


def assert_executable(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    approval_id: uuid.UUID,
    subject_version: int,
    *,
    operation_id: uuid.UUID | None = None,
) -> Approval:
    """Executors call this before acting: approved, same subject version, inside the
    execution deadline, and not consumed by a different operation (INV-04, INV-16).

    With ``operation_id`` the approval is consumed by that operation (retries of the same
    operation stay covered; a new operation needs a new approval).
    """
    approval = repo.get_approval(session, ctx, approval_id, lock=True)
    if approval is None:
        raise AppError("NOT_FOUND")
    if approval.status != "approved":
        raise AppError("CONFLICT_STATE", entity="approval", status=approval.status)
    if approval.subject_version != subject_version:
        raise AppError("APPROVAL_STALE")
    if approval.execute_before is not None and clock.now() >= approval.execute_before:
        raise AppError("APPROVAL_EXPIRED")
    if operation_id is not None:
        if approval.operation_id is not None and approval.operation_id != operation_id:
            raise AppError("CONFLICT_STATE", entity="approval", reason="already_consumed")
        approval.operation_id = operation_id
    return approval
