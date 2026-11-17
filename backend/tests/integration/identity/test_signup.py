import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from app.core.email import email_outbox
from app.core.security import verify_password
from app.identity import service
from app.identity.legal import TERMS_VERSION
from app.identity.models import User

PAYLOAD = {
    "email": "new@example.com",
    "password": "a-new-secure-password",
    "name": "New Owner",
    "accepted_terms_version": TERMS_VERSION,
    "ui_locale": "en",
}
BASE = "/api/v1/auth"


@pytest.fixture
def signup_client(build_app):
    email_outbox.clear()
    with TestClient(build_app(signup_enabled=True, smtp_url=SecretStr(""))) as client:
        yield client
    email_outbox.clear()


def token():
    body = email_outbox.get_messages()[-1].text_body
    return re.search(r"/verify-email/(\S+)", body).group(1)


def register(client):
    response = client.post(f"{BASE}/register", json=PAYLOAD)
    assert response.status_code == 202, response.text
    return token()


def login(client):
    assert (
        client.post(
            f"{BASE}/login", json={"email": PAYLOAD["email"], "password": PAYLOAD["password"]}
        ).status_code
        == 204
    )
    return client.get(f"{BASE}/me").json()


def test_signup_verify_then_workspace(signup_client, db_session, clock):
    client = signup_client
    raw = register(client)
    row = db_session.scalar(select(User).where(User.email == PAYLOAD["email"]))
    assert not row.email_verified
    assert row.accepted_terms_version == TERMS_VERSION
    assert row.terms_accepted_at == clock.now()
    assert raw.encode() != row.verification_token_hash
    assert verify_password(row.password_hash, PAYLOAD["password"])
    me = login(client)
    assert me["user"]["email_verified"] is False
    assert me["memberships"] == []
    headers = {"X-CSRF-Token": me["csrf_token"]}
    for method, path, body in [
        ("GET", "/api/v1/workspaces", None),
        ("POST", "/api/v1/workspaces", {}),
        ("GET", f"{BASE}/sessions", None),
        ("PATCH", f"{BASE}/me", {"display_name": "Bypass"}),
        ("POST", f"{BASE}/password", {"current_password": "x", "new_password": "y"}),
    ]:
        response = client.request(method, path, json=body, headers=headers)
        assert response.status_code == 403, response.text
        assert response.json()["code"] == "EMAIL_NOT_VERIFIED"
    assert client.get("/api/v1/meta").status_code == 200
    assert client.post(f"{BASE}/verify-email", json={"token": raw}).status_code == 204
    assert client.get(f"{BASE}/me").json()["user"]["email_verified"] is True
    assert client.get("/api/v1/workspaces").status_code == 200
    assert client.post(f"{BASE}/verify-email", json={"token": raw}).status_code == 400
    assert client.post(f"{BASE}/logout", headers=headers).status_code == 204


def test_duplicate_registration_is_generic_and_does_not_overwrite(signup_client, db_session):
    register(signup_client)
    user = db_session.scalar(select(User).where(User.email == PAYLOAD["email"]))
    original = user.password_hash, user.verification_token_hash, user.terms_accepted_at
    response = signup_client.post(
        f"{BASE}/register",
        json={
            **PAYLOAD,
            "email": " NEW@EXAMPLE.COM ",
            "name": "Attacker",
            "password": "different-password",
        },
    )
    assert response.status_code == 202
    assert response.json() is None
    db_session.refresh(user)
    assert (user.password_hash, user.verification_token_hash, user.terms_accepted_at) == original
    assert user.display_name == "New Owner"
    assert "already have an account" in email_outbox.get_messages()[-1].subject
    assert "verify-email" not in email_outbox.get_messages()[-1].text_body


def test_resend_supersedes_token_and_unknown_is_generic(signup_client):
    old = register(signup_client)
    assert (
        signup_client.post(
            f"{BASE}/resend-verification", json={"email": PAYLOAD["email"]}
        ).status_code
        == 202
    )
    new = token()
    assert new != old
    assert signup_client.post(f"{BASE}/verify-email", json={"token": old}).status_code == 400
    assert signup_client.post(f"{BASE}/verify-email", json={"token": new}).status_code == 204
    response = signup_client.post(
        f"{BASE}/resend-verification", json={"email": "unknown@example.com"}
    )
    assert response.status_code == 202 and response.json() is None


def test_expired_tampered_and_reset_tokens_rejected(signup_client, clock):
    raw = register(signup_client)
    assert signup_client.post(f"{BASE}/verify-email", json={"token": raw + "x"}).status_code == 400
    assert (
        signup_client.post(
            f"{BASE}/password-reset/confirm",
            json={"token": raw, "new_password": "replacement-password"},
        ).status_code
        == 400
    )
    clock.advance(timedelta(hours=24))
    assert signup_client.post(f"{BASE}/verify-email", json={"token": raw}).status_code == 400


@pytest.mark.parametrize("path", ["register", "resend-verification"])
def test_email_and_ip_throttle(signup_client, clock, path):
    payload = PAYLOAD if path == "register" else {"email": PAYLOAD["email"]}
    for _ in range(5):
        assert signup_client.post(f"{BASE}/{path}", json=payload).status_code == 202
    response = signup_client.post(f"{BASE}/{path}", json={**payload, "email": "other@example.com"})
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    clock.advance(timedelta(minutes=16))
    assert signup_client.post(f"{BASE}/{path}", json=payload).status_code == 202


def test_disabled_signup_hides_routes_and_meta(client):
    assert client.get("/api/v1/meta").json()["signup_enabled"] is False
    for path in ("register", "resend-verification"):
        assert (
            client.post(
                f"{BASE}/{path}",
                json=PAYLOAD if path == "register" else {"email": PAYLOAD["email"]},
            ).status_code
            == 404
        )
        assert client.post(f"{BASE}/{path}", json={}).status_code == 404


def test_existing_cli_users_unaffected(client, db_session):
    user = service.create_user(
        db_session, email=PAYLOAD["email"], password=PAYLOAD["password"], display_name="Existing"
    )
    assert user.email_verified
    assert user.terms_accepted_at is None  # Do not invent consent for existing accounts.
    me = login(client)
    assert me["user"]["email_verified"] is True
    assert client.get("/api/v1/workspaces").status_code == 200


def test_requires_current_legal_version_and_valid_fields(signup_client, db_session):
    for patch in (
        {"accepted_terms_version": "old"},
        {"email": "not-email"},
        {"name": " "},
        {"password": "password123"},
    ):
        assert signup_client.post(f"{BASE}/register", json={**PAYLOAD, **patch}).status_code in (
            400,
            422,
        )
    assert db_session.scalar(select(User).where(User.email == PAYLOAD["email"])) is None


def test_unverified_user_can_logout_and_issued_link_survives_flag_off(signup_client):
    raw = register(signup_client)
    me = login(signup_client)
    signup_client.app.state.settings.signup_enabled = False
    assert (
        signup_client.post(
            f"{BASE}/resend-verification", json={"email": PAYLOAD["email"]}
        ).status_code
        == 404
    )
    assert (
        signup_client.post(f"{BASE}/logout", headers={"X-CSRF-Token": me["csrf_token"]}).status_code
        == 204
    )
    assert signup_client.post(f"{BASE}/verify-email", json={"token": raw}).status_code == 204


def test_unverified_user_cannot_accept_an_invite_and_public_auth_routes_still_work(
    signup_client, db_session
):
    from tests.factories import login as factory_login
    from tests.factories import workspace_with_members

    ws, users = workspace_with_members(db_session)
    owner = TestClient(signup_client.app)
    headers = factory_login(owner, users["owner"])
    invite = owner.post(
        f"/api/v1/workspaces/{ws.id}/invites", json={"role": "staff"}, headers=headers
    ).json()
    invite_token = invite["invite_path"].split("/")[-1]

    register(signup_client)
    me = login(signup_client)
    response = signup_client.post("/api/v1/invites/accept", json={"token": invite_token})
    assert response.status_code == 403
    assert response.json()["code"] == "EMAIL_NOT_VERIFIED"
    # Pre-auth endpoints are not blocked by a stale unverified session cookie.
    response = signup_client.post(
        f"{BASE}/password-reset/request", json={"email": PAYLOAD["email"]}
    )
    assert response.status_code == 202
    assert me["user"]["email_verified"] is False
