"""Command queries. Every function takes a ``WorkspaceContext`` (INV-01); the requester-scoped
ones also filter by user, because commands are private to the person who typed them."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.commands.models import OwnerCommand
from app.core.context import WorkspaceContext
from app.core.db import set_tenant_context


def get_command(
    session: Session,
    ctx: WorkspaceContext,
    command_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None = None,
    lock: bool = False,
) -> OwnerCommand | None:
    statement = select(OwnerCommand).where(
        OwnerCommand.workspace_id == ctx.workspace_id, OwnerCommand.id == command_id
    )
    if user_id is not None:
        statement = statement.where(OwnerCommand.user_id == user_id)
    if lock:
        statement = statement.with_for_update()
    return session.scalars(statement).one_or_none()


def get_by_client_request_id(
    session: Session, user_id: uuid.UUID, client_request_id: str
) -> OwnerCommand | None:
    return session.scalars(
        select(OwnerCommand).where(
            OwnerCommand.user_id == user_id, OwnerCommand.client_request_id == client_request_id
        )
    ).one_or_none()


def list_commands(
    session: Session, ctx: WorkspaceContext, user_id: uuid.UUID, *, limit: int = 20
) -> Sequence[OwnerCommand]:
    return session.scalars(
        select(OwnerCommand)
        .where(OwnerCommand.workspace_id == ctx.workspace_id, OwnerCommand.user_id == user_id)
        .order_by(OwnerCommand.created_at.desc(), OwnerCommand.id)
        .limit(min(max(limit, 1), 100))
    ).all()


def due_clarifications(session: Session, now: datetime, *, limit: int) -> Sequence[OwnerCommand]:
    """For the expiry job only: waiting-for-answer commands whose time is up, any workspace."""
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        rows = session.execute(
            text("SELECT id, workspace_id FROM public.discover_expired_command_ids(:now, :limit)"),
            {"now": now, "limit": limit},
        ).all()
        result: list[OwnerCommand] = []
        for cmd_id, ws_id in rows:
            set_tenant_context(session, ws_id)
            cmd = session.get(OwnerCommand, cmd_id, with_for_update=True)
            if cmd is not None:
                result.append(cmd)
        return result
    return session.scalars(
        select(OwnerCommand)
        .where(OwnerCommand.status == "needs_clarification", OwnerCommand.expires_at <= now)
        .order_by(OwnerCommand.expires_at, OwnerCommand.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
