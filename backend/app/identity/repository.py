"""Identity queries. Never commits (services do).

Workspace-owned reads take a ``WorkspaceContext``. The functions that run *before* a context
exists (``get_membership``, ``list_memberships``) are the tenancy boundary itself: they are
keyed by the authenticated user's id and are used only by ``require_membership`` and auth.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.core.context import WorkspaceContext
from app.identity.models import AuthSession, User, Workspace, WorkspaceMember

# --- users and sessions ------------------------------------------------------------------


def get_user(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)


def get_user_by_email(session: Session, normalised_email: str) -> User | None:
    return session.scalars(select(User).where(User.email == normalised_email)).one_or_none()


def add_user(session: Session, user: User) -> User:
    session.add(user)
    session.flush()
    return user


def add_auth_session(session: Session, auth_session: AuthSession) -> AuthSession:
    session.add(auth_session)
    session.flush()
    return auth_session


def get_auth_session_with_user(
    session: Session, token_hash: bytes
) -> tuple[AuthSession, User] | None:
    row = session.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(AuthSession.token_hash == token_hash)
    ).one_or_none()
    return (row[0], row[1]) if row else None


def revoke_auth_session(session: Session, token_hash: bytes, now: datetime) -> None:
    found = session.scalars(
        select(AuthSession).where(AuthSession.token_hash == token_hash)
    ).one_or_none()
    if found is not None and found.revoked_at is None:
        found.revoked_at = now
        session.flush()


# --- memberships and workspaces ------------------------------------------------------------


def get_membership(
    session: Session, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[WorkspaceMember, Workspace] | None:
    row = session.execute(
        select(WorkspaceMember, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)
    ).one_or_none()
    return (row[0], row[1]) if row else None


def list_memberships(
    session: Session, user_id: uuid.UUID
) -> Sequence[tuple[WorkspaceMember, Workspace]]:
    rows = session.execute(
        select(WorkspaceMember, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .where(WorkspaceMember.user_id == user_id, Workspace.status == "active")
        .order_by(func.lower(Workspace.name), Workspace.id)
    ).all()
    return [(r[0], r[1]) for r in rows]


def get_workspace(session: Session, ctx: WorkspaceContext) -> Workspace | None:
    return session.scalars(select(Workspace).where(Workspace.id == ctx.workspace_id)).one_or_none()


def get_workspace_by_slug(session: Session, slug: str) -> Workspace | None:
    """For internal callers that have no context yet (seed, CLI). Not for request handling."""
    return session.scalars(select(Workspace).where(Workspace.slug == slug)).one_or_none()


def list_members(session: Session, ctx: WorkspaceContext) -> Sequence[tuple[WorkspaceMember, User]]:
    rows = session.execute(
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == ctx.workspace_id)
        .order_by(WorkspaceMember.created_at, User.id)
    ).all()
    return [(r[0], r[1]) for r in rows]


def member_names(
    session: Session, ctx: WorkspaceContext, user_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Display names of the given users, limited to members of this workspace (INV-01)."""
    if not user_ids:
        return {}
    rows = session.execute(
        select(User.id, User.display_name)
        .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.workspace_id == ctx.workspace_id, User.id.in_(list(user_ids)))
    ).all()
    return {row[0]: row[1] for row in rows}


def slug_exists(session: Session, slug: str) -> bool:
    return session.scalar(select(exists().where(Workspace.slug == slug))) is True


def add_workspace(session: Session, workspace: Workspace) -> Workspace:
    session.add(workspace)
    session.flush()
    return workspace


def add_member(session: Session, member: WorkspaceMember) -> WorkspaceMember:
    session.add(member)
    session.flush()
    return member
