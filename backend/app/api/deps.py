"""Shared FastAPI dependencies: settings, clock, authentication, CSRF, workspace membership."""

import uuid
from collections.abc import Callable

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import ActorRef, WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError
from app.core.security import constant_time_equal
from app.identity import repository as identity_repo
from app.identity import service as identity_service
from app.identity.permissions import PERMISSION_MATRIX, has_permission
from app.identity.service import AuthenticatedSession

SESSION_COOKIE = "agentnest_session"
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# Unsafe /api/v1 routes that need no session (CSRF applies to everything else, by default).
# Webhooks live outside /api/v1 and are authenticated by signature instead.
CSRF_EXEMPT_PATHS = frozenset({"/api/v1/auth/login"})


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


def set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _authenticate(
    request: Request, response: Response, db: Session, settings: Settings, clock: Clock
) -> AuthenticatedSession:
    cached = getattr(request.state, "auth", None)
    if cached is not None:
        return cached  # type: ignore[no-any-return]
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise AppError("AUTH_REQUIRED")
    result = identity_service.resolve_session(
        db, clock, session_ttl_hours=settings.session_ttl_hours, token=token
    )
    if result is None:
        raise AppError("AUTH_REQUIRED")
    request.state.auth = result
    request.state.user_id = str(result.user.id)
    if result.refreshed:  # sliding session: keep the cookie as long-lived as the session
        set_session_cookie(response, settings, token)
    return result


def current_auth(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    clock: Clock = Depends(get_clock),
) -> AuthenticatedSession:
    """The authenticated user and session, or 401 ``AUTH_REQUIRED``."""
    return _authenticate(request, response, db, settings, clock)


def enforce_csrf(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    clock: Clock = Depends(get_clock),
) -> None:
    """Router-level guard: every unsafe /api/v1 request needs a session and a matching
    ``X-CSRF-Token``, so a newly added route cannot forget CSRF protection."""
    if request.method not in UNSAFE_METHODS or request.url.path in CSRF_EXEMPT_PATHS:
        return
    auth = _authenticate(request, response, db, settings, clock)
    supplied = request.headers.get(CSRF_HEADER, "")
    if not supplied or not constant_time_equal(supplied, auth.session.csrf_token):
        raise AppError("CSRF_FAILED")


def require_membership(permission: str | None = None) -> Callable[..., WorkspaceContext]:
    """Dependency factory for ``/workspaces/{workspace_id}/…`` routes (INV-01).

    Order of checks: signed in (401) -> member of this workspace (else **404**, so existence
    is not revealed) -> role holds ``permission`` (else 403). ``permission=None`` allows any
    member.
    """
    if permission is not None and permission not in PERMISSION_MATRIX:
        raise KeyError(f"Unknown permission: {permission}")

    def dependency(
        workspace_id: uuid.UUID,
        request: Request,
        auth: AuthenticatedSession = Depends(current_auth),
        db: Session = Depends(get_db),
    ) -> WorkspaceContext:
        found = identity_repo.get_membership(db, workspace_id, auth.user.id)
        if found is None or found[1].status != "active":
            raise AppError("NOT_FOUND")
        member, workspace = found
        if permission is not None and not has_permission(member.role, permission):
            raise AppError("FORBIDDEN", permission=permission)
        request.state.workspace_id = str(workspace.id)
        return identity_service.workspace_context(
            workspace, ActorRef.user(auth.user.id), member.role
        )

    return dependency
