"""P4-01: social accounts. Constraints, connect eligibility, API, readiness, audit."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.integrations.instagram import queries
from app.integrations.instagram.models import SocialAccount
from app.knowledge import readiness as readiness_module
from app.operations import accounts
from tests.factories import create_workspace
from tests.helpers.env import Env


def new_account(session: Session, env: Env, **overrides: object) -> SocialAccount:
    values: dict[str, object] = {
        "workspace_id": env.workspace.id,
        "provider_kind": "mock",
        "external_account_id": "mock-1",
        "username": "golkent.demo",
        "status": "connected",
    }
    values.update(overrides)
    account = SocialAccount(**values)
    session.add(account)
    session.flush()
    return account


def new_account_in(
    env: Env, workspace_id: uuid.UUID, external_id: str, status: str, **overrides: object
) -> SocialAccount:
    account = SocialAccount(
        workspace_id=workspace_id,
        provider_kind=str(overrides.pop("provider_kind", "mock")),
        external_account_id=external_id,
        username=external_id,
        status=status,
        **overrides,
    )
    env.session.add(account)
    env.session.flush()
    return account


def reconnect(env: Env, account_id: uuid.UUID, role: str = "owner"):  # type: ignore[no-untyped-def]
    return env.call(getattr(env, role), "POST", f"/social-accounts/{account_id}/reconnect")


# --- database constraints ---------------------------------------------------------------------


def test_one_active_account_per_workspace(env: Env) -> None:
    new_account(env.session, env)
    with pytest.raises(IntegrityError), env.session.begin_nested():
        new_account(env.session, env, external_account_id="mock-2")


def test_a_disconnected_account_frees_the_workspace(env: Env) -> None:
    first = new_account(env.session, env)
    first.status = "disconnected"
    env.session.flush()
    second = new_account(env.session, env, external_account_id="mock-2")
    assert second.id != first.id


def test_an_external_account_belongs_to_one_workspace(env: Env) -> None:
    other = create_workspace(env.session, name="Other")
    new_account(env.session, env, external_account_id="shared-id")
    with pytest.raises(IntegrityError), env.session.begin_nested():
        new_account(env.session, env, workspace_id=other.id, external_account_id="shared-id")


def test_a_mock_account_can_never_hold_a_token(env: Env) -> None:
    with pytest.raises(IntegrityError), env.session.begin_nested():
        new_account(env.session, env, token_ciphertext=b"secret")


def test_is_simulated_is_derived_from_the_provider_kind(env: Env) -> None:
    assert new_account(env.session, env).is_simulated is True


# --- connect eligibility ----------------------------------------------------------------------


def ctx_for(env: Env, *, is_demo: bool) -> WorkspaceContext:
    base = env.ctx(env.owner)
    return WorkspaceContext(
        base.workspace_id, base.actor, base.role, base.timezone, base.locale, is_demo
    )


@pytest.mark.parametrize(
    ("app_env", "providers", "allow", "is_demo", "expected"),
    [
        ("development", "mock", True, False, True),
        ("test", "mock", False, False, True),
        ("development", "meta", True, True, False),  # mock not enabled
        ("production", "mock", True, True, True),  # demo workspace, simulated allowed
        ("production", "mock", True, False, False),  # real customer workspace
        ("production", "mock", False, True, False),  # simulated workspaces not allowed
        ("production", "meta,mock", True, True, True),
    ],
)
def test_mock_connect_eligibility(
    env: Env,
    settings: Settings,
    app_env: str,
    providers: str,
    allow: bool,
    is_demo: bool,
    expected: bool,
) -> None:
    candidate = settings.model_copy(
        update={
            "app_env": app_env,
            "instagram_enabled_providers": providers,
            "allow_simulated_workspaces": allow,
        }
    )
    assert accounts.mock_connect_allowed(candidate, ctx_for(env, is_demo=is_demo)) is expected


def test_connect_refuses_when_not_allowed(env: Env, settings: Settings) -> None:
    candidate = settings.model_copy(update={"instagram_enabled_providers": "meta"})
    with pytest.raises(AppError) as excinfo:
        accounts.connect_mock(env.session, env.clock, env.ctx(env.owner), candidate)
    assert excinfo.value.code == "FORBIDDEN"


# --- API ---------------------------------------------------------------------------------------


def test_owner_connects_a_mock_account_and_it_is_listed(env: Env) -> None:
    response = env.call(env.owner, "POST", "/social-accounts/mock", json={"username": "gym.demo"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["provider_kind"] == "mock"
    assert body["status"] == "connected"
    assert body["username"] == "gym.demo"
    assert body["is_simulated"] is True
    assert body["capabilities"]["messaging"] is True

    listed = env.call(env.staff, "GET", "/social-accounts").json()["items"]
    assert [a["id"] for a in listed] == [body["id"]]


def test_the_response_has_no_credential_fields(env: Env) -> None:
    body = env.call(env.owner, "POST", "/social-accounts/mock").json()
    assert set(body) == {
        "id",
        "platform",
        "provider_kind",
        "username",
        "status",
        "capabilities",
        "connection_expires_at",
        "last_error_code",
        "degraded_until",
        "is_simulated",
    }


def test_the_default_username_comes_from_the_workspace(env: Env) -> None:
    body = env.call(env.owner, "POST", "/social-accounts/mock").json()
    assert body["username"] == "golkent.demo"


def test_a_second_active_account_is_a_conflict(env: Env) -> None:
    assert env.call(env.owner, "POST", "/social-accounts/mock").status_code == 201
    second = env.call(env.owner, "POST", "/social-accounts/mock")
    assert second.status_code == 409
    assert second.json()["code"] == "CONFLICT_STATE"


@pytest.mark.parametrize("role", ["manager", "staff"])
def test_only_the_owner_manages_integrations(env: Env, role: str) -> None:
    response = env.call(getattr(env, role), "POST", "/social-accounts/mock")
    assert response.status_code == 403
    assert env.call(getattr(env, role), "GET", "/social-accounts").status_code == 200


def test_disconnect_frees_the_workspace_and_is_audited(env: Env) -> None:
    created = env.call(env.owner, "POST", "/social-accounts/mock").json()
    response = env.call(env.owner, "POST", f"/social-accounts/{created['id']}/disconnect")
    assert response.status_code == 200
    assert response.json()["status"] == "disconnected"
    again = env.call(env.owner, "POST", f"/social-accounts/{created['id']}/disconnect")
    assert again.status_code == 409  # disconnected is terminal
    assert env.call(env.owner, "POST", "/social-accounts/mock").status_code == 201

    actions = [
        (row.action, row.is_simulated)
        for row in env.session.scalars(
            select(AuditLog)
            .where(AuditLog.workspace_id == env.workspace.id)
            .where(AuditLog.action.like("social_account.%"))
            .order_by(AuditLog.occurred_at, AuditLog.id)
        )
    ]
    assert ("social_account.connected", True) in actions
    assert ("social_account.disconnected", True) in actions


def test_an_account_of_another_workspace_is_not_found(env: Env) -> None:
    other = create_workspace(env.session, name="Other")
    foreign = SocialAccount(
        workspace_id=other.id,
        provider_kind="mock",
        external_account_id="foreign",
        status="connected",
    )
    env.session.add(foreign)
    env.session.flush()
    response = env.call(env.owner, "POST", f"/social-accounts/{foreign.id}/disconnect")
    assert response.status_code == 404
    assert env.call(env.owner, "GET", "/social-accounts").json()["items"] == []


def test_reconnect_rejects_foreign_ids_other_providers_and_other_states(env: Env) -> None:
    other = create_workspace(env.session, name="Other")
    foreign = new_account_in(env, other.id, "foreign", "needs_reauth")
    assert reconnect(env, foreign.id).status_code == 404  # INV-01: a foreign id does not exist

    meta = new_account_in(env, env.workspace.id, "meta-1", "needs_reauth", provider_kind="meta")
    assert reconnect(env, meta.id).status_code == 409  # a real account reconnects via OAuth
    meta.status = "disconnected"
    env.session.flush()

    gone = new_account_in(env, env.workspace.id, "gone", "disconnected")
    assert reconnect(env, gone.id).status_code == 409  # disconnected is terminal
    assert reconnect(env, uuid.uuid4()).status_code == 404

    lapsed = new_account_in(env, env.workspace.id, "lapsed", "needs_reauth")
    assert reconnect(env, lapsed.id, role="staff").status_code == 403
    done = reconnect(env, lapsed.id)
    assert done.status_code == 200 and done.json()["status"] == "connected"
    assert "token" not in str(done.json()).lower()


def test_reconnect_is_refused_when_the_mock_provider_is_not_enabled(
    env: Env, settings: Settings
) -> None:
    account = new_account_in(env, env.workspace.id, "lapsed", "needs_reauth")
    off = settings.model_copy(update={"instagram_enabled_providers": "meta"})
    with pytest.raises(AppError) as raised:
        accounts.reconnect_mock(env.session, env.clock, env.ctx(env.owner), off, account.id)
    assert raised.value.code == "FORBIDDEN"


# --- queries and readiness ---------------------------------------------------------------------


def test_resolve_by_external_needs_the_matching_provider_kind(env: Env) -> None:
    account = new_account(env.session, env, external_account_id="ig-1")
    assert queries.resolve_by_external(env.session, "mock", "ig-1") == account
    assert queries.resolve_by_external(env.session, "meta", "ig-1") is None
    assert queries.resolve_by_external(env.session, "mock", "unknown") is None


def test_resolve_prefers_the_active_account_over_a_disconnected_one(env: Env) -> None:
    old = new_account(env.session, env, external_account_id="ig-1", status="disconnected")
    current = new_account(env.session, env, external_account_id="ig-1")
    assert queries.resolve_by_external(env.session, "mock", "ig-1") == current
    assert current.id != old.id


def test_readiness_sees_the_connection(env: Env, clock: FrozenClock) -> None:
    ctx = env.ctx(env.owner)

    def account_requirement() -> str:
        report = readiness_module.readiness(env.session, clock, ctx)
        return next(r.status for r in report.requirements if r.code == "account_connected")

    assert account_requirement() == "not_connected"
    account = new_account(env.session, env)
    assert account_requirement() == "ok"
    account.status = "needs_reauth"
    env.session.flush()
    assert account_requirement() == "not_connected"
