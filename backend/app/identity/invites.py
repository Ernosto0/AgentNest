"""Members and invites (plan H14, api-design.md §2.2).

The invite token is generated here (``secrets.token_urlsafe(32)``), returned to the caller once,
and stored only as its SHA-256. Roles are ``owner``/``manager``/``staff``; a workspace always
keeps at least one owner. Services commit (ADR-003).
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import ActorRef, WorkspaceContext
from app.core.errors import AppError
from app.core.security import generate_token, hash_password, hash_token, password_policy_problems
from app.identity import repository as repo
from app.identity import service as identity_service
from app.identity.models import AuthSession, Invite, User, Workspace, WorkspaceMember
from app.notifications import service as notifications

INVITE_TTL = timedelta(days=7)


@dataclass(frozen=True)
class AcceptResult:
    workspace: Workspace
    role: str
    session_token: str | None  # set when a new user was created and signed in


def _get_member(session: Session, ctx: WorkspaceContext, user_id: uuid.UUID) -> WorkspaceMember:
    member = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == ctx.workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    if member is None:
        raise AppError("NOT_FOUND")
    return member


def _owner_count(session: Session, ctx: WorkspaceContext) -> int:
    return len([1 for member, _ in repo.list_members(session, ctx) if member.role == "owner"])


def _notify_owners(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    type: str,
    params: dict[str, object],
    dedup_key: str,
    exclude_user_id: uuid.UUID | None,
) -> None:
    """Notify the active owners (a role, not a permission, so it cannot use the permission
    helper)."""
    for member, user in repo.list_members(session, ctx):
        if member.role != "owner" or not user.is_active or user.id == exclude_user_id:
            continue
        notifications.notify(
            session,
            clock,
            ctx,
            recipient_user_id=user.id,
            type=type,
            params=params,
            subject_type="user",
            subject_id=exclude_user_id,
            dedup_key=dedup_key,
        )


# --- invites --------------------------------------------------------------------------------


def create_invite(
    session: Session, clock: Clock, ctx: WorkspaceContext, *, role: str
) -> tuple[Invite, str]:
    """Create a one-time invite. Returns the invite and the raw token (shown exactly once)."""
    token = generate_token()
    created_by = uuid.UUID(ctx.actor.id) if ctx.actor.type == "user" and ctx.actor.id else None
    invite = Invite(
        workspace_id=ctx.workspace_id,
        role=role,
        token_hash=hash_token(token),
        created_by_user_id=created_by,
        expires_at=clock.now() + INVITE_TTL,
    )
    session.add(invite)
    session.flush()
    audit.record(
        session,
        ctx,
        "member.invited",
        "workspace",
        ctx.workspace_id,
        {"role": role, "invite_id": invite.id},
        clock=clock,
    )
    session.commit()
    return invite, token


def list_pending_invites(session: Session, clock: Clock, ctx: WorkspaceContext) -> list[Invite]:
    """Invites that are neither revoked nor accepted and have not expired."""
    now = clock.now()
    return list(
        session.scalars(
            select(Invite)
            .where(
                Invite.workspace_id == ctx.workspace_id,
                Invite.revoked_at.is_(None),
                Invite.accepted_at.is_(None),
                Invite.expires_at > now,
            )
            .order_by(Invite.created_at, Invite.id)
        ).all()
    )


def _get_invite(session: Session, ctx: WorkspaceContext, invite_id: uuid.UUID) -> Invite:
    invite = session.scalar(
        select(Invite).where(
            Invite.workspace_id == ctx.workspace_id,
            Invite.id == invite_id,
        )
    )
    if invite is None:
        raise AppError("NOT_FOUND")
    return invite


def revoke_invite(
    session: Session, clock: Clock, ctx: WorkspaceContext, invite_id: uuid.UUID
) -> None:
    """Revoke a pending invite. An already accepted invite cannot be revoked (409)."""
    invite = _get_invite(session, ctx, invite_id)
    if invite.accepted_at is not None:
        raise AppError("CONFLICT_STATE", reason="already_accepted")
    if invite.revoked_at is not None:  # idempotent
        return
    invite.revoked_at = clock.now()
    audit.record(
        session,
        ctx,
        "member.invite_revoked",
        "workspace",
        ctx.workspace_id,
        {"role": invite.role, "invite_id": invite.id},
        clock=clock,
    )
    session.commit()


def accept_invite(
    session: Session,
    clock: Clock,
    *,
    token: str,
    signed_in_user: User | None,
    email: str | None,
    display_name: str | None,
    password: str | None,
    session_ttl_hours: int,
    user_agent: str | None,
) -> AcceptResult:
    """Accept an invite: ``signed_in_user`` becomes a member, or a new user is created and
    signed in. Unknown, expired, used or revoked tokens all raise the one code INVITE_INVALID."""
    invite = session.scalar(select(Invite).where(Invite.token_hash == hash_token(token)))
    now = clock.now()
    if (
        invite is None
        or invite.expires_at <= now
        or invite.revoked_at is not None
        or invite.accepted_at is not None
    ):
        raise AppError("INVITE_INVALID")

    if signed_in_user is not None:
        user = signed_in_user
        session_token = None
    else:
        if email is None or display_name is None or password is None:
            missing = [
                field
                for field, value in (
                    ("email", email),
                    ("display_name", display_name),
                    ("password", password),
                )
                if value is None
            ]
            raise AppError(
                "VALIDATION_FAILED",
                errors=[{"field": field, "code": "required", "params": {}} for field in missing],
            )
        normalised = identity_service.normalize_email(email)
        if "@" not in normalised or len(normalised) > 320:
            raise AppError(
                "VALIDATION_FAILED",
                errors=[{"field": "email", "code": "invalid_format", "params": {}}],
            )
        problems = password_policy_problems(password)
        if problems:
            raise AppError(
                "VALIDATION_FAILED",
                errors=[{"field": "password", "code": problems[0], "params": {}}],
            )
        if repo.get_user_by_email(session, normalised) is not None:
            raise AppError("CONFLICT_STATE", reason="email_taken")
        user = User(
            email=normalised,
            password_hash=hash_password(password),
            display_name=display_name.strip(),
            ui_locale="tr",
        )
        repo.add_user(session, user)
        session_token = generate_token()
        csrf_token = generate_token()
        repo.add_auth_session(
            session,
            AuthSession(
                user_id=user.id,
                token_hash=hash_token(session_token),
                csrf_token=csrf_token,
                expires_at=now + timedelta(hours=session_ttl_hours),
                last_seen_at=now,
                user_agent=(user_agent or "")[: identity_service.USER_AGENT_MAX] or None,
            ),
        )
        user.last_login_at = now

    workspace = session.get(Workspace, invite.workspace_id)
    if workspace is None:
        raise AppError("NOT_FOUND")
    already_member = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if already_member is not None:
        raise AppError("CONFLICT_STATE", reason="already_member")

    repo.add_member(
        session,
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role=invite.role,
            invited_by_user_id=invite.created_by_user_id,
        ),
    )
    invite.accepted_by_user_id = user.id
    invite.accepted_at = now

    ctx = identity_service.workspace_context(workspace, ActorRef.user(user.id), invite.role)
    audit.record(
        session,
        ctx,
        "member.joined",
        "user",
        user.id,
        {"role": invite.role, "source": "invite"},
        clock=clock,
    )
    _notify_owners(
        session,
        clock,
        ctx,
        type="member.joined",
        params={"user_id": str(user.id), "display_name": user.display_name, "role": invite.role},
        dedup_key=f"member.joined:{user.id}",
        exclude_user_id=user.id,
    )
    session.commit()
    return AcceptResult(workspace=workspace, role=invite.role, session_token=session_token)


# --- members --------------------------------------------------------------------------------


def change_member_role(
    session: Session, clock: Clock, ctx: WorkspaceContext, *, user_id: uuid.UUID, role: str
) -> WorkspaceMember:
    member = _get_member(session, ctx, user_id)
    if member.role == role:
        return member  # a no-op: nothing changes, nothing is audited
    if member.role == "owner" and _owner_count(session, ctx) == 1:
        raise AppError("LAST_OWNER_REQUIRED")
    from_role = member.role
    member.role = role
    audit.record(
        session,
        ctx,
        "member.role_changed",
        "user",
        user_id,
        {"from_role": from_role, "to_role": role},
        clock=clock,
    )
    session.commit()
    return member


def remove_member(
    session: Session, clock: Clock, ctx: WorkspaceContext, *, user_id: uuid.UUID
) -> None:
    member = _get_member(session, ctx, user_id)
    if member.role == "owner" and _owner_count(session, ctx) == 1:
        raise AppError("LAST_OWNER_REQUIRED")
    role = member.role
    session.delete(member)
    audit.record(
        session,
        ctx,
        "member.removed",
        "user",
        user_id,
        {"role": role},
        clock=clock,
    )
    session.commit()
