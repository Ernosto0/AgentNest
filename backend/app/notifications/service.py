"""In-app notifications (data-model.md §3.8, api-design.md §2.8).

``notify`` writes inside the caller's transaction and never commits, so a notification and the
state change that caused it succeed or fail together. An unread notification with the same
``dedup_key`` for the same recipient is never created twice (the partial unique index decides,
so concurrent callers cannot both insert).
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity import repository as identity_repo
from app.identity.permissions import has_permission
from app.notifications.catalog import spec_for
from app.notifications.models import Notification

DEFAULT_LIMIT = 50
MAX_LIMIT = 100


def notify(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    recipient_user_id: uuid.UUID,
    type: str,
    severity: str | None = None,
    params: dict[str, Any] | None = None,
    subject_type: str | None = None,
    subject_id: uuid.UUID | None = None,
    dedup_key: str | None = None,
    is_simulated: bool = False,
) -> Notification | None:
    """Create one notification, or return ``None`` when an unread duplicate exists.

    The type must be in the catalog (``ValueError`` otherwise); the severity is the catalog's
    (a caller that passes another one is a programming error).
    """
    spec = spec_for(type)
    if severity is not None and severity != spec.severity:
        raise ValueError(f"{type} has severity {spec.severity}, not {severity}")
    severity = spec.severity
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "workspace_id": ctx.workspace_id,
        "recipient_user_id": recipient_user_id,
        "type": type,
        "severity": severity,
        "params": params or {},
        "subject_type": subject_type,
        "subject_id": subject_id,
        "dedup_key": dedup_key,
        "is_simulated": is_simulated,
        "created_at": clock.now(),
        "updated_at": clock.now(),
    }
    statement = pg_insert(Notification).values(**values)
    if dedup_key is not None:
        statement = statement.on_conflict_do_nothing(
            index_elements=[Notification.recipient_user_id, Notification.dedup_key],
            index_where=text("read_at IS NULL AND dedup_key IS NOT NULL"),
        )
    inserted = session.execute(statement.returning(Notification.id)).scalar_one_or_none()
    if inserted is None:
        return None
    return session.get(Notification, inserted)


def notify_permission_holders(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    permission: str,
    type: str,
    severity: str | None = None,
    params: dict[str, Any] | None = None,
    subject_type: str | None = None,
    subject_id: uuid.UUID | None = None,
    dedup_key: str | None = None,
    is_simulated: bool = False,
    exclude_user_id: uuid.UUID | None = None,
) -> list[Notification]:
    """Notify every active member whose role holds ``permission`` (deduped per recipient),
    except ``exclude_user_id`` (usually the person who caused the event)."""
    spec_for(type)  # an unknown type fails even when nobody would be notified
    created: list[Notification] = []
    for member, user in identity_repo.list_members(session, ctx):
        if not user.is_active or not has_permission(member.role, permission):
            continue
        if user.id == exclude_user_id:
            continue
        notification = notify(
            session,
            clock,
            ctx,
            recipient_user_id=user.id,
            type=type,
            severity=severity,
            params=params,
            subject_type=subject_type,
            subject_id=subject_id,
            dedup_key=dedup_key,
            is_simulated=is_simulated,
        )
        if notification is not None:
            created.append(notification)
    return created


def list_notifications(
    session: Session,
    ctx: WorkspaceContext,
    user_id: uuid.UUID,
    *,
    unread_only: bool = False,
    limit: int = DEFAULT_LIMIT,
) -> Sequence[Notification]:
    """The recipient's own notifications in this workspace, newest first."""
    statement = (
        select(Notification)
        .where(
            Notification.workspace_id == ctx.workspace_id,
            Notification.recipient_user_id == user_id,
        )
        .order_by(Notification.created_at.desc(), Notification.id)
        .limit(min(max(limit, 1), MAX_LIMIT))
    )
    if unread_only:
        statement = statement.where(Notification.read_at.is_(None))
    return session.scalars(statement).all()


def unread_count(session: Session, ctx: WorkspaceContext, user_id: uuid.UUID) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.workspace_id == ctx.workspace_id,
                Notification.recipient_user_id == user_id,
                Notification.read_at.is_(None),
            )
        )
        or 0
    )


def mark_read(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    user_id: uuid.UUID,
    notification_id: uuid.UUID,
) -> Notification:
    """Mark one of the user's own notifications read (someone else's is a 404). Idempotent."""
    notification = session.scalar(
        select(Notification)
        .where(
            Notification.workspace_id == ctx.workspace_id,
            Notification.id == notification_id,
            Notification.recipient_user_id == user_id,
        )
        .with_for_update()
    )
    if notification is None:
        raise AppError("NOT_FOUND")
    if notification.read_at is None:
        notification.read_at = clock.now()
    session.commit()
    return notification


def mark_all_read(session: Session, clock: Clock, ctx: WorkspaceContext, user_id: uuid.UUID) -> int:
    result = session.execute(
        update(Notification)
        .where(
            Notification.workspace_id == ctx.workspace_id,
            Notification.recipient_user_id == user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=clock.now())
        .execution_options(synchronize_session=False)
    )
    session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]
