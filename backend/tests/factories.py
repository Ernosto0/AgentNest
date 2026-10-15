"""Test data factories. Workspace-owned rows always require an explicit workspace."""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.clock import Clock, FrozenClock
from app.core.context import ActorRef, WorkspaceContext
from app.core.security import hash_password
from app.identity import service as identity_service
from app.identity.models import User, Workspace, WorkspaceMember
from app.knowledge import candidates as knowledge_candidates
from app.knowledge import repository as knowledge_repo
from app.knowledge import service as knowledge_service
from app.knowledge.models import BusinessFact, FactCandidate

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


# --- knowledge ------------------------------------------------------------------------------


def knowledge_ctx(
    workspace: Workspace, user: User | None = None, role: str | None = None
) -> WorkspaceContext:
    """A service-level context: for ``user`` with ``role``, or for the system when omitted."""
    actor = ActorRef.user(user.id) if user is not None else ActorRef.system("test")
    return identity_service.workspace_context(workspace, actor, role)


def money(
    amount: str = "6000", currency: str = "TRY", unit: str | None = "month"
) -> dict[str, Any]:
    value: dict[str, Any] = {"amount": amount, "currency": currency}
    if unit:
        value["unit"] = unit
    return value


def create_fact(
    session: Session,
    workspace: Workspace,
    key: str,
    value: dict[str, Any],
    *,
    verified: bool = True,
    clock: Clock | None = None,
    **kwargs: Any,
) -> BusinessFact:
    """Insert a fact through the trusted service path (seed-like), verified by default."""
    return knowledge_service.insert_trusted_fact(
        session,
        clock or FrozenClock(),
        knowledge_ctx(workspace),
        key=key,
        value=value,
        verified=verified,
        **kwargs,
    )


def create_candidate(
    session: Session,
    workspace: Workspace,
    key: str,
    value: dict[str, Any],
    *,
    source_type: str = "pasted_text",
    value_type: str = "money",
    clock: Clock | None = None,
) -> FactCandidate:
    fact = knowledge_repo.get_live_fact_by_key(session, knowledge_ctx(workspace), key)
    candidate = knowledge_candidates.propose_candidate(
        session,
        clock or FrozenClock(),
        knowledge_ctx(workspace),
        key=key,
        value_type=value_type,
        value=value,
        source_type=source_type,
        source_excerpt="Aylık üyelik 5.500 TL",
        fact=fact,
    )
    session.commit()
    return candidate
