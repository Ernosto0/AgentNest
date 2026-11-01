"""Identity use cases: authentication, sessions, workspaces. Services commit (ADR-003)."""

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any
from zoneinfo import available_timezones

from babel import Locale
from babel.numbers import get_territory_currencies
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import ActorRef, WorkspaceContext
from app.core.errors import AppError
from app.core.security import (
    generate_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    password_policy_problems,
    verify_password,
)
from app.identity import repository as repo
from app.identity.models import AuthSession, User, Workspace, WorkspaceMember
from app.identity.schemas import (
    SessionOut,
    WorkspaceCreate,
    WorkspacePatch,
    WorkspaceSettings,
)
from app.identity.throttling import (
    check_login_throttle,
    record_login_failure,
    record_login_success,
)

# A request extends the sliding session (and the cookie) at most this often.
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)
USER_AGENT_MAX = 200


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _email_fingerprint(normalised_email: str) -> str:
    """Short hash so repeated failures on one account correlate without storing the email."""
    return hashlib.sha256(normalised_email.encode()).hexdigest()[:16]


def _validation_error(field: str, code: str, **params: Any) -> AppError:
    return AppError("VALIDATION_FAILED", errors=[{"field": field, "code": code, "params": params}])


# --- users --------------------------------------------------------------------------------


def create_user(
    session: Session,
    *,
    email: str,
    password: str,
    display_name: str,
    ui_locale: str = "tr",
) -> User:
    """Create a user (CLI and seed). Enforces the password policy (>= 10 characters)."""
    problems = password_policy_problems(password)
    if problems:
        raise _validation_error("password", problems[0])
    normalised = normalize_email(email)
    if "@" not in normalised or len(normalised) > 320:
        raise _validation_error("email", "invalid_format")
    if repo.get_user_by_email(session, normalised) is not None:
        raise _validation_error("email", "already_exists")
    user = User(
        email=normalised,
        password_hash=hash_password(password),
        display_name=display_name.strip(),
        ui_locale=ui_locale,
    )
    repo.add_user(session, user)
    session.commit()
    return user


# --- authentication -------------------------------------------------------------------------


@dataclass(frozen=True)
class LoginResult:
    user: User
    token: str
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True)
class AuthenticatedSession:
    user: User
    session: AuthSession
    refreshed: bool  # expiry was extended: the cookie should be re-issued


def login(
    session: Session,
    clock: Clock,
    *,
    session_ttl_hours: int,
    email: str,
    password: str,
    user_agent: str | None,
    previous_token: str | None,
    ip_address: str | None = None,
) -> LoginResult | None:
    """Verify credentials and open a new session. Returns ``None`` on any failure.

    The failure audit entry is committed here, so the caller can simply raise the generic
    ``INVALID_CREDENTIALS`` (no distinction between unknown user, wrong password, inactive).
    """
    effective_ip = ip_address or "127.0.0.1"
    check_login_throttle(session, clock, email=email, ip_address=effective_ip)

    now = clock.now()
    normalised = normalize_email(email)
    user = repo.get_user_by_email(session, normalised)
    password_ok = verify_password(user.password_hash if user else None, password)

    if user is None or not password_ok or not user.is_active:
        record_login_failure(session, clock, email=normalised, ip_address=effective_ip)
        reason = (
            "unknown_user" if user is None else "bad_password" if not password_ok else "inactive"
        )
        audit.record(
            session,
            None,
            "auth.login_failed",
            "user",
            None,
            {"reason": reason, "email_sha256": _email_fingerprint(normalised)},
            clock=clock,
        )
        session.commit()
        return None

    record_login_success(session, email=normalised, ip_address=effective_ip)

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    if previous_token:  # session rotation: the old session never survives a login
        repo.revoke_auth_session(session, hash_token(previous_token), now)

    token = generate_token()
    csrf_token = generate_token()
    expires_at = now + timedelta(hours=session_ttl_hours)
    repo.add_auth_session(
        session,
        AuthSession(
            user_id=user.id,
            token_hash=hash_token(token),
            csrf_token=csrf_token,
            expires_at=expires_at,
            last_seen_at=now,
            user_agent=(user_agent or "")[:USER_AGENT_MAX] or None,
            ip_address=ip_address,
        ),
    )
    user.last_login_at = now
    audit.record(
        session,
        None,
        "auth.login",
        "user",
        user.id,
        actor=ActorRef.user(user.id),
        clock=clock,
    )
    session.commit()
    return LoginResult(user=user, token=token, csrf_token=csrf_token, expires_at=expires_at)


def resolve_session(
    session: Session, clock: Clock, *, session_ttl_hours: int, token: str
) -> AuthenticatedSession | None:
    """Return the live session for a cookie token, extending its sliding expiry."""
    found = repo.get_auth_session_with_user(session, hash_token(token))
    if found is None:
        return None
    auth_session, user = found
    now = clock.now()
    if auth_session.revoked_at is not None or auth_session.expires_at <= now or not user.is_active:
        return None
    refreshed = False
    if now - auth_session.last_seen_at >= SESSION_TOUCH_INTERVAL:
        auth_session.last_seen_at = now
        auth_session.expires_at = now + timedelta(hours=session_ttl_hours)
        session.commit()
        refreshed = True
    return AuthenticatedSession(user=user, session=auth_session, refreshed=refreshed)


def logout(session: Session, clock: Clock, authenticated: AuthenticatedSession) -> None:
    authenticated.session.revoked_at = clock.now()
    audit.record(
        session,
        None,
        "auth.logout",
        "user",
        authenticated.user.id,
        actor=ActorRef.user(authenticated.user.id),
        clock=clock,
    )
    session.commit()


def update_me(
    session: Session, user: User, *, display_name: str | None, ui_locale: str | None
) -> User:
    if display_name is not None:
        user.display_name = display_name
    if ui_locale is not None:
        user.ui_locale = ui_locale
    session.commit()
    return user


def list_user_sessions(
    session: Session,
    clock: Clock,
    user_id: uuid.UUID,
    current_session_id: uuid.UUID,
) -> list[SessionOut]:
    now = clock.now()
    rows = list(
        session.scalars(
            select(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
            .order_by(AuthSession.last_seen_at.desc(), AuthSession.created_at.desc())
        )
    )
    return [
        SessionOut(
            id=row.id,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
            user_agent=row.user_agent,
            ip_address=row.ip_address,
            is_current=(row.id == current_session_id),
        )
        for row in rows
    ]


def revoke_user_session(
    session: Session,
    clock: Clock,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
) -> bool:
    """Revoke a single session owned by user_id. Returns False if not found."""
    row = session.scalars(
        select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
        )
    ).first()
    if row is None:
        return False
    if row.revoked_at is None:
        row.revoked_at = clock.now()
        audit.record(
            session,
            None,
            "auth.session_revoked",
            "user",
            user_id,
            {"session_id": str(session_id)},
            actor=ActorRef.user(user_id),
            clock=clock,
        )
        session.commit()
    return True


def revoke_all_user_sessions(
    session: Session,
    clock: Clock,
    user_id: uuid.UUID,
    current_session_id: uuid.UUID,
    *,
    include_current: bool = False,
) -> int:
    """Revoke active sessions for user_id. Returns number of sessions revoked."""
    now = clock.now()
    stmt = update(AuthSession).where(
        AuthSession.user_id == user_id,
        AuthSession.revoked_at.is_(None),
        AuthSession.expires_at > now,
    )
    if not include_current:
        stmt = stmt.where(AuthSession.id != current_session_id)
    stmt = stmt.values(revoked_at=now)
    result = session.execute(stmt)
    count = int(getattr(result, "rowcount", 0))
    audit.record(
        session,
        None,
        "auth.sessions_revoked_all",
        "user",
        user_id,
        {"include_current": include_current, "revoked_count": count},
        actor=ActorRef.user(user_id),
        clock=clock,
    )
    session.commit()
    return count


def change_password(
    session: Session,
    clock: Clock,
    user: User,
    *,
    current_password: str,
    new_password: str,
    current_session_id: uuid.UUID,
) -> None:
    """Verify current password, validate new password (>=12 chars), update hash,
    and revoke other sessions.
    """
    if not verify_password(user.password_hash, current_password):
        audit.record(
            session,
            None,
            "auth.password_change_failed",
            "user",
            user.id,
            {"reason": "bad_current_password"},
            actor=ActorRef.user(user.id),
            clock=clock,
        )
        session.commit()
        raise AppError("INVALID_CREDENTIALS")

    if len(new_password) < 12:
        raise AppError(
            "VALIDATION_FAILED",
            errors=[{"field": "new_password", "code": "too_short", "params": {"min_length": 12}}],
        )

    policy_errs = password_policy_problems(new_password)
    if policy_errs:
        raise AppError(
            "VALIDATION_FAILED",
            errors=[{"field": "new_password", "code": err, "params": {}} for err in policy_errs],
        )

    now = clock.now()
    user.password_hash = hash_password(new_password)

    # Invalidate all other active sessions for that user in the same transaction (ADR-025 §2.2)
    session.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == user.id,
            AuthSession.id != current_session_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
        .values(revoked_at=now)
    )

    audit.record(
        session,
        None,
        "auth.password_changed",
        "user",
        user.id,
        actor=ActorRef.user(user.id),
        clock=clock,
    )
    session.commit()


# --- workspaces -------------------------------------------------------------------------------


@lru_cache
def valid_timezones() -> frozenset[str]:
    return frozenset(available_timezones())


@lru_cache
def valid_currencies() -> frozenset[str]:
    """ISO 4217 codes in current tender use (excludes historic codes and ``XXX``)."""
    codes: set[str] = set()
    for territory in Locale("en").territories:
        # ISO 3166 alpha-2 only; skips region groups such as "001"
        if isinstance(territory, str) and len(territory) == 2:
            codes.update(get_territory_currencies(territory, tender=True, non_tender=False))
    return frozenset(codes)


_TURKISH_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def slugify(name: str) -> str:
    ascii_name = name.translate(_TURKISH_ASCII).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    return slug[:60].strip("-") or "workspace"


def _unique_slug(session: Session, base: str) -> str:
    candidate, n = base, 1
    while repo.slug_exists(session, candidate):
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def _check_timezone(value: str) -> None:
    if value not in valid_timezones():
        raise _validation_error("timezone", "invalid_timezone")


def _check_currency(value: str) -> None:
    if value not in valid_currencies():
        raise _validation_error("currency", "invalid_currency")


def workspace_context(workspace: Workspace, actor: ActorRef, role: str | None) -> WorkspaceContext:
    return WorkspaceContext(
        workspace_id=workspace.id,
        actor=actor,
        role=role,
        timezone=workspace.timezone,
        locale=workspace.default_locale,
        is_demo=workspace.is_demo,
    )


def create_workspace(
    session: Session,
    clock: Clock,
    owner: User,
    data: WorkspaceCreate,
    *,
    slug: str | None = None,
    is_demo: bool = False,
    actor: ActorRef | None = None,
) -> Workspace:
    """Create a workspace; the creator becomes its owner. Audit ``workspace.created``.

    ``slug`` and ``is_demo`` are for internal callers (seed, CLI) and are not exposed by the API.
    """
    _check_timezone(data.timezone)
    _check_currency(data.currency)
    workspace = Workspace(
        name=data.name,
        slug=slug or _unique_slug(session, slugify(data.name)),
        business_category=data.business_category,
        market=data.market,
        default_locale=data.default_locale,
        reply_languages=[data.default_locale],
        timezone=data.timezone,
        currency=data.currency,
        is_demo=is_demo,
        status="active",
        settings=WorkspaceSettings().model_dump(mode="json"),
    )
    try:
        repo.add_workspace(session, workspace)
    except IntegrityError as exc:
        session.rollback()
        raise _validation_error("slug", "already_exists") from exc
    repo.add_member(
        session, WorkspaceMember(workspace_id=workspace.id, user_id=owner.id, role="owner")
    )
    ctx = workspace_context(workspace, actor or ActorRef.user(owner.id), "owner")
    audit.record(
        session,
        ctx,
        "workspace.created",
        "workspace",
        workspace.id,
        {
            "slug": workspace.slug,
            "business_category": workspace.business_category,
            "market": workspace.market,
            "timezone": workspace.timezone,
            "currency": workspace.currency,
            "owner_user_id": owner.id,
        },
        clock=clock,
    )
    session.commit()
    return workspace


_NOT_NULLABLE = (
    "name",
    "business_category",
    "market",
    "default_locale",
    "reply_languages",
    "timezone",
    "currency",
    "settings",
)


def update_workspace(
    session: Session, clock: Clock, ctx: WorkspaceContext, patch: WorkspacePatch
) -> Workspace:
    """Apply a partial update (``workspace.manage``); audit ``workspace.updated`` if it changed."""
    workspace = repo.get_workspace(session, ctx)
    if workspace is None:
        raise AppError("NOT_FOUND")
    changes = patch.model_dump(exclude_unset=True)
    for field in _NOT_NULLABLE:
        if field in changes and changes[field] is None:
            raise _validation_error(field, "required")
    if "timezone" in changes:
        _check_timezone(changes["timezone"])
    if "currency" in changes:
        _check_currency(changes["currency"])

    changed: list[str] = []
    settings_patch = changes.pop("settings", None)
    for field, value in changes.items():
        if field == "reply_languages":
            value = list(dict.fromkeys(value))
        if getattr(workspace, field) != value:
            setattr(workspace, field, value)
            changed.append(field)
    if settings_patch:
        current = WorkspaceSettings.model_validate(workspace.settings).model_dump(mode="json")
        merged = {**current, **{k: v for k, v in settings_patch.items() if v is not None}}
        validated = WorkspaceSettings.model_validate(merged).model_dump(mode="json")
        for key in validated:
            if key != "automation_reviewed_at" and validated[key] != current[key]:
                changed.append(f"settings.{key}")
        workspace.settings = validated  # new dict: JSONB change detection

    if changed:
        audit.record(
            session,
            ctx,
            "workspace.updated",
            "workspace",
            workspace.id,
            {"changed": sorted(changed)},
            clock=clock,
        )
    if changed:
        session.commit()
    return workspace
