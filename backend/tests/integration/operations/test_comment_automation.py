"""Owner-only opt-in endpoint: isolation, consent, idempotence and audit."""

import uuid

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from app.integrations.instagram.oauth import COMMENTS_SCOPE
from tests.integration.operations.test_accounts import new_account


def toggle(env, account, enabled=True, role="owner"):
    return env.call(
        getattr(env, role),
        "PUT",
        f"/accounts/{account.id}/comment-automation",
        json={"enabled": enabled},
    )


def test_toggle_recomputes_audits_and_is_idempotent(env):
    account = new_account(
        env.session,
        env,
        provider_kind="meta",
        granted_scopes=[COMMENTS_SCOPE],
        capabilities={"comments_permission": True},
    )
    assert account.comment_automation_enabled is False
    for _ in range(2):
        response = toggle(env, account)
        assert response.status_code == 200, response.text
        assert response.json()["comment_automation_enabled"] is True
        assert response.json()["capabilities"]["comment_private_reply"] is True
        assert response.json()["capabilities"]["comment_reply"] is False
    rows = env.session.scalars(
        select(AuditLog).where(AuditLog.action == "account.comment_automation_changed")
    ).all()
    assert len(rows) == 1
    assert toggle(env, account, False).status_code == 200
    env.session.refresh(account)
    assert not account.comment_automation_enabled and not account.capabilities["comment_read"]


@pytest.mark.parametrize("role", ["manager", "staff"])
def test_non_owner_forbidden(env, role):
    account = new_account(env.session, env, provider_kind="meta")
    assert toggle(env, account, role=role).status_code == 403


@pytest.mark.parametrize(
    ("provider", "scopes", "status"),
    [
        ("mock", [], "connected"),
        ("meta", [], "connected"),
        ("meta", [COMMENTS_SCOPE], "needs_reauth"),
    ],
)
def test_unavailable_account_refused(env, provider, scopes, status):
    account = new_account(
        env.session,
        env,
        provider_kind=provider,
        status=status,
        granted_scopes=scopes,
        capabilities={"comments_permission": bool(scopes)},
    )
    response = toggle(env, account)
    assert response.status_code == 409 and response.json()["code"] == "CONFLICT_STATE"


def test_unknown_id_404(env):
    response = env.call(
        env.owner, "PUT", f"/accounts/{uuid.uuid4()}/comment-automation", json={"enabled": True}
    )
    assert response.status_code == 404
