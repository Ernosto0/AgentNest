"""Approval queries. Every function takes a ``WorkspaceContext`` (INV-01) except the sweep
helper, which deliberately looks across workspaces and never returns rows to a request."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals.models import Approval
from app.core.context import WorkspaceContext


def get_approval(
    session: Session, ctx: WorkspaceContext, approval_id: uuid.UUID, *, lock: bool = False
) -> Approval | None:
    statement = select(Approval).where(
        Approval.workspace_id == ctx.workspace_id, Approval.id == approval_id
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalars(statement).one_or_none()


def get_pending_for_subject(
    session: Session,
    ctx: WorkspaceContext,
    subject_type: str,
    subject_id: uuid.UUID,
    *,
    lock: bool = False,
) -> Approval | None:
    statement = select(Approval).where(
        Approval.workspace_id == ctx.workspace_id,
        Approval.subject_type == subject_type,
        Approval.subject_id == subject_id,
        Approval.status == "pending",
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalars(statement).one_or_none()


def list_approvals(
    session: Session,
    ctx: WorkspaceContext,
    *,
    status: str | None = None,
    action: str | None = None,
    limit: int = 50,
) -> Sequence[Approval]:
    statement = (
        select(Approval)
        .where(Approval.workspace_id == ctx.workspace_id)
        .order_by(Approval.created_at.desc(), Approval.id)
        .limit(min(max(limit, 1), 100))
    )
    if status is not None:
        statement = statement.where(Approval.status == status)
    if action is not None:
        statement = statement.where(Approval.action == action)
    return session.scalars(statement).all()


def due_pending(
    session: Session, ctx: WorkspaceContext, now: datetime, *, lock: bool = True
) -> Sequence[Approval]:
    """Pending approvals of this workspace whose expiry has passed (lazy expiry on reads)."""
    statement = (
        select(Approval)
        .where(
            Approval.workspace_id == ctx.workspace_id,
            Approval.status == "pending",
            Approval.expires_at <= now,
        )
        .order_by(Approval.expires_at, Approval.id)
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalars(statement).all()


def due_ids_all_workspaces(session: Session, now: datetime, *, limit: int) -> list[uuid.UUID]:
    """For the expiry sweep job only: ids of due approvals across workspaces."""
    return list(
        session.scalars(
            select(Approval.id)
            .where(Approval.status == "pending", Approval.expires_at <= now)
            .order_by(Approval.expires_at, Approval.id)
            .limit(limit)
        )
    )
