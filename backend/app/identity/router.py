"""Auth and workspace routes. Thin: validate, call the service, map to a response model."""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import (
    SESSION_COOKIE,
    clear_session_cookie,
    current_auth,
    get_app_settings,
    get_clock,
    require_membership,
    set_session_cookie,
)
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError
from app.identity import repository as repo
from app.identity import service
from app.identity.models import User, Workspace, WorkspaceMember
from app.identity.schemas import (
    LoginRequest,
    MemberOut,
    MembershipOut,
    MeResponse,
    MeUpdate,
    Page,
    UserOut,
    WorkspaceCreate,
    WorkspaceOut,
    WorkspacePatch,
    WorkspaceSettings,
)
from app.identity.service import AuthenticatedSession

auth_router = APIRouter(prefix="/auth", tags=["auth"])
workspaces_router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _user_out(user: User) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)


def _membership_out(member: WorkspaceMember, workspace: Workspace) -> MembershipOut:
    return MembershipOut(
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        role=member.role,
        is_demo=workspace.is_demo,
    )


def _workspace_out(workspace: Workspace) -> WorkspaceOut:
    return WorkspaceOut(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        business_category=workspace.business_category,
        market=workspace.market,
        default_locale=workspace.default_locale,
        reply_languages=workspace.reply_languages,
        timezone=workspace.timezone,
        currency=workspace.currency,
        is_demo=workspace.is_demo,
        status=workspace.status,
        settings=WorkspaceSettings.model_validate(workspace.settings),
        created_at=workspace.created_at,
    )


def _me(db: Session, auth: AuthenticatedSession) -> MeResponse:
    return MeResponse(
        user=_user_out(auth.user),
        csrf_token=auth.session.csrf_token,
        memberships=[_membership_out(m, w) for m, w in repo.list_memberships(db, auth.user.id)],
    )


# --- /auth ----------------------------------------------------------------------------------


@auth_router.post("/login", status_code=204)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    clock: Clock = Depends(get_clock),
) -> None:
    result = service.login(
        db,
        clock,
        session_ttl_hours=settings.session_ttl_hours,
        email=body.email,
        password=body.password,
        user_agent=request.headers.get("user-agent"),
        previous_token=request.cookies.get(SESSION_COOKIE),
    )
    if result is None:
        raise AppError("INVALID_CREDENTIALS")  # generic: never says which part was wrong
    set_session_cookie(response, settings, result.token)


@auth_router.post("/logout", status_code=204)
def logout(
    response: Response,
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    clock: Clock = Depends(get_clock),
) -> None:
    service.logout(db, clock, auth)
    clear_session_cookie(response, settings)


@auth_router.get("/me", response_model=MeResponse)
def get_me(
    auth: AuthenticatedSession = Depends(current_auth), db: Session = Depends(get_db)
) -> MeResponse:
    return _me(db, auth)


@auth_router.patch("/me", response_model=MeResponse)
def patch_me(
    body: MeUpdate,
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
) -> MeResponse:
    service.update_me(db, auth.user, display_name=body.display_name, ui_locale=body.ui_locale)
    return _me(db, auth)


# --- /workspaces ----------------------------------------------------------------------------


@workspaces_router.get("", response_model=Page[MembershipOut])
def list_workspaces(
    auth: AuthenticatedSession = Depends(current_auth), db: Session = Depends(get_db)
) -> Page[MembershipOut]:
    return Page(items=[_membership_out(m, w) for m, w in repo.list_memberships(db, auth.user.id)])


@workspaces_router.post("", response_model=WorkspaceOut, status_code=201)
def create_workspace(
    body: WorkspaceCreate,
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> WorkspaceOut:
    return _workspace_out(service.create_workspace(db, clock, auth.user, body))


@workspaces_router.get("/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(
    ctx: WorkspaceContext = Depends(require_membership()), db: Session = Depends(get_db)
) -> WorkspaceOut:
    workspace = repo.get_workspace(db, ctx)
    if workspace is None:
        raise AppError("NOT_FOUND")
    return _workspace_out(workspace)


@workspaces_router.patch("/{workspace_id}", response_model=WorkspaceOut)
def patch_workspace(
    body: WorkspacePatch,
    ctx: WorkspaceContext = Depends(require_membership("workspace.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> WorkspaceOut:
    return _workspace_out(service.update_workspace(db, clock, ctx, body))


@workspaces_router.get("/{workspace_id}/members", response_model=Page[MemberOut])
def list_members(
    ctx: WorkspaceContext = Depends(require_membership()), db: Session = Depends(get_db)
) -> Page[MemberOut]:
    return Page(
        items=[
            MemberOut(
                user_id=user.id,
                email=user.email,
                display_name=user.display_name,
                role=member.role,
                joined_at=member.created_at,
            )
            for member, user in repo.list_members(db, ctx)
        ]
    )
