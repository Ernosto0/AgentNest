"""Test data factories. Workspace-owned rows always require an explicit workspace."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.identity.models import User, Workspace, WorkspaceMember

DEFAULT_PASSWORD = "correct-horse-battery"
_DEFAULT_HASH = hash_password(DEFAULT_PASSWORD)  # argon2 is slow on purpose: hash once


def create_user(
    session: Session,
    *,
    email: str | None = None,
    display_name: str = "Test User",
    password: str | None = None,
    ui_locale: str = "tr",
    is_active: bool = True,
) -> User:
    user = User(
        email=email or f"user-{uuid.uuid4().hex[:10]}@example.test",
        password_hash=_DEFAULT_HASH if password is None else hash_password(password),
        display_name=display_name,
        ui_locale=ui_locale,
        is_active=is_active,
    )
    session.add(user)
    session.flush()
    return user


def create_workspace(
    session: Session,
    *,
    name: str = "Test Workspace",
    slug: str | None = None,
    business_category: str = "gym",
    market: str = "tr",
    default_locale: str = "tr",
    timezone: str = "Europe/Istanbul",
    currency: str = "TRY",
    is_demo: bool = False,
) -> Workspace:
    workspace = Workspace(
        name=name,
        slug=slug or f"ws-{uuid.uuid4().hex[:10]}",
        business_category=business_category,
        market=market,
        default_locale=default_locale,
        reply_languages=[default_locale],
        timezone=timezone,
        currency=currency,
        is_demo=is_demo,
        settings={},
    )
    session.add(workspace)
    session.flush()
    return workspace


def add_member(
    session: Session, workspace: Workspace, user: User, role: str = "owner"
) -> WorkspaceMember:
    member = WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=role)
    session.add(member)
    session.flush()
    return member


def workspace_with_members(
    session: Session, *, roles: tuple[str, ...] = ("owner",), **workspace_kwargs: object
) -> tuple[Workspace, dict[str, User]]:
    """A workspace plus one user per role, e.g. ``{"owner": User, "staff": User}``."""
    workspace = create_workspace(session, **workspace_kwargs)  # type: ignore[arg-type]
    users = {}
    for role in roles:
        users[role] = create_user(session, display_name=f"{role.title()} User")
        add_member(session, workspace, users[role], role)
    return workspace, users


def login(client: TestClient, user: User, password: str = DEFAULT_PASSWORD) -> dict[str, str]:
    """Sign ``user`` in on ``client`` and return the headers for state-changing requests."""
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 204, response.text
    csrf = client.get("/api/v1/auth/me").json()["csrf_token"]
    return {"X-CSRF-Token": csrf}
