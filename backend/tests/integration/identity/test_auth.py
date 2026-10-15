from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import list_entries
from app.core.clock import FrozenClock
from app.core.security import hash_token
from app.identity.models import AuthSession, User
from tests.factories import DEFAULT_PASSWORD, add_member, create_user, create_workspace, login

LOGIN = "/api/v1/auth/login"
COOKIE = "agentnest_session"


def credentials(user: User, password: str = DEFAULT_PASSWORD) -> dict[str, str]:
    return {"email": user.email, "password": password}


def session_row(db: Session, token: str) -> AuthSession:
    return db.scalars(select(AuthSession).where(AuthSession.token_hash == hash_token(token))).one()


# --- login ---------------------------------------------------------------------------------


def test_login_succeeds_with_204_and_an_http_only_cookie(
    client: TestClient, db_session: Session
) -> None:
    user = create_user(db_session)
    response = client.post(LOGIN, json=credentials(user))
    assert response.status_code == 204
    assert response.content == b""
    cookie = response.headers["set-cookie"].lower()
    assert f"{COOKIE}=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie
    assert "max-age=1209600" in cookie  # 336 h
    assert "secure" not in cookie.replace("samesite", "")  # COOKIE_SECURE=false in test


def test_cookie_is_secure_when_configured(
    build_app: Callable[..., FastAPI], db_session: Session
) -> None:
    user = create_user(db_session)
    secure_client = TestClient(build_app(cookie_secure=True))
    response = secure_client.post(LOGIN, json=credentials(user))
    assert "; secure" in response.headers["set-cookie"].lower()


def test_only_the_token_hash_is_stored(client: TestClient, db_session: Session) -> None:
    user = create_user(db_session)
    client.post(LOGIN, json=credentials(user))
    token = client.cookies[COOKIE]
    row = session_row(db_session, token)
    assert row.token_hash == hash_token(token)
    assert token.encode() not in bytes(row.token_hash)
    assert row.csrf_token != token


def test_passwords_are_stored_as_argon2id(db_session: Session) -> None:
    assert create_user(db_session).password_hash.startswith("$argon2id$")


def test_login_normalises_the_email(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="owner@demo.local")
    response = client.post(
        LOGIN, json={"email": "  Owner@Demo.LOCAL ", "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 204


def test_login_records_last_login_and_audit(
    client: TestClient, db_session: Session, clock: FrozenClock
) -> None:
    user = create_user(db_session)
    client.post(LOGIN, json=credentials(user))
    assert db_session.get(User, user.id).last_login_at == clock.now()  # type: ignore[union-attr]
    (entry,) = list_entries(db_session, action="auth.login", system_level=True)
    assert (entry.actor_type, entry.actor_id) == ("user", str(user.id))
    assert entry.resource_id == user.id
    assert entry.workspace_id is None
    assert entry.occurred_at == clock.now()


@pytest.mark.parametrize("case", ["wrong_password", "unknown_user", "inactive"])
def test_failed_login_is_one_generic_error(
    client: TestClient, db_session: Session, case: str
) -> None:
    active = create_user(db_session)
    inactive = create_user(db_session, is_active=False)
    payloads = {
        "wrong_password": credentials(active, "not-the-password"),
        "unknown_user": {"email": "nobody@example.test", "password": DEFAULT_PASSWORD},
        "inactive": credentials(inactive),
    }
    response = client.post(LOGIN, json=payloads[case], headers={"Accept-Language": "en"})
    assert response.status_code == 401
    assert COOKIE not in response.headers.get("set-cookie", "")
    # Identical body for every failure: nothing reveals which part was wrong.
    body = response.json()
    assert {k: v for k, v in body.items() if k != "request_id"} == {
        "type": "about:blank",
        "title": "Unauthorized",
        "status": 401,
        "code": "INVALID_CREDENTIALS",
        "params": {},
        "detail": "Email or password is incorrect.",
    }


def test_failed_login_is_audited_at_system_level_without_secrets(
    client: TestClient, db_session: Session
) -> None:
    user = create_user(db_session)
    client.post(LOGIN, json=credentials(user, "wrong-password-123"))
    (entry,) = list_entries(db_session, action="auth.login_failed", system_level=True)
    assert entry.workspace_id is None
    assert entry.actor_type == "system"
    assert entry.metadata_["reason"] == "bad_password"
    dumped = str(entry.metadata_) + str(entry.actor_id)
    assert user.email not in dumped
    assert "wrong-password-123" not in dumped


def test_login_validation_rejects_missing_fields(client: TestClient) -> None:
    response = client.post(LOGIN, json={"email": "a@b.c"})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


# --- session rotation, expiry, revocation --------------------------------------------------


def test_login_rotates_the_session(
    client: TestClient, make_client: Callable[[], TestClient], db_session: Session
) -> None:
    user = create_user(db_session)
    client.post(LOGIN, json=credentials(user))
    first = client.cookies[COOKIE]

    client.post(LOGIN, json=credentials(user))  # presents the first cookie
    second = client.cookies[COOKIE]

    assert first != second
    assert session_row(db_session, first).revoked_at is not None
    assert session_row(db_session, second).revoked_at is None
    replay = make_client()
    replay.cookies.set(COOKIE, first)
    assert replay.get("/api/v1/auth/me").status_code == 401


def test_session_expires_after_the_ttl(
    client: TestClient, db_session: Session, clock: FrozenClock
) -> None:
    user = create_user(db_session)
    login(client, user)
    clock.advance(hours=335)
    assert client.get("/api/v1/auth/me").status_code == 200
    # The request above extended the session, so measure from there.
    clock.advance(hours=336, seconds=1)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


def test_session_expiry_is_sliding(
    client: TestClient, db_session: Session, clock: FrozenClock
) -> None:
    user = create_user(db_session)
    login(client, user)
    for _ in range(3):  # 3 x 13 days = 39 days > the 14-day TTL, but never idle for 14 days
        clock.advance(days=13)
        assert client.get("/api/v1/auth/me").status_code == 200


def test_sliding_expiry_reissues_the_cookie_but_not_on_every_request(
    client: TestClient, db_session: Session, clock: FrozenClock
) -> None:
    user = create_user(db_session)
    login(client, user)
    clock.advance(minutes=1)
    assert "set-cookie" not in client.get("/api/v1/auth/me").headers
    clock.advance(minutes=10)
    refreshed = client.get("/api/v1/auth/me")
    assert f"{COOKIE}=" in refreshed.headers["set-cookie"]


def test_deactivated_user_loses_access_immediately(client: TestClient, db_session: Session) -> None:
    user = create_user(db_session)
    login(client, user)
    user.is_active = False
    db_session.flush()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_revokes_the_session_and_clears_the_cookie(
    client: TestClient, make_client: Callable[[], TestClient], db_session: Session
) -> None:
    user = create_user(db_session)
    headers = login(client, user)
    token = client.cookies[COOKIE]

    response = client.post("/api/v1/auth/logout", headers=headers)
    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert session_row(db_session, token).revoked_at is not None

    replay = make_client()
    replay.cookies.set(COOKIE, token)  # a stolen copy of the cookie is useless now
    assert replay.get("/api/v1/auth/me").status_code == 401
    (entry,) = list_entries(db_session, action="auth.logout", system_level=True)
    assert entry.actor_id == str(user.id)


# --- CSRF ----------------------------------------------------------------------------------


def test_state_changing_requests_require_the_csrf_header(
    client: TestClient, db_session: Session
) -> None:
    user = create_user(db_session)
    headers = login(client, user)

    missing = client.post("/api/v1/auth/logout")
    assert (missing.status_code, missing.json()["code"]) == (403, "CSRF_FAILED")
    wrong = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "x" * 43})
    assert (wrong.status_code, wrong.json()["code"]) == (403, "CSRF_FAILED")
    assert client.patch("/api/v1/auth/me", json={"display_name": "N"}).status_code == 403
    assert client.get("/api/v1/auth/me").status_code == 200  # safe methods need no token

    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204


def test_csrf_token_of_another_session_is_rejected(
    client: TestClient, make_client: Callable[[], TestClient], db_session: Session
) -> None:
    user = create_user(db_session)
    login(client, user)
    other = make_client()
    other_headers = login(other, user)
    response = client.patch("/api/v1/auth/me", json={"display_name": "N"}, headers=other_headers)
    assert response.status_code == 403


def test_unauthenticated_unsafe_request_is_401_not_csrf(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout")
    assert (response.status_code, response.json()["code"]) == (401, "AUTH_REQUIRED")


def test_login_itself_needs_no_csrf_token(client: TestClient, db_session: Session) -> None:
    user = create_user(db_session)
    assert client.post(LOGIN, json=credentials(user)).status_code == 204


# --- /auth/me ------------------------------------------------------------------------------


def test_me_returns_user_csrf_token_and_memberships(
    client: TestClient, db_session: Session
) -> None:
    user = create_user(db_session, display_name="Ayşe", ui_locale="tr")
    b = create_workspace(db_session, name="Bravo", is_demo=True)
    a = create_workspace(db_session, name="alpha")
    create_workspace(db_session, name="Not mine")
    add_member(db_session, b, user, "manager")
    add_member(db_session, a, user, "owner")
    login(client, user)

    body = client.get("/api/v1/auth/me").json()
    assert set(body) == {"user", "csrf_token", "memberships"}
    assert body["user"] == {
        "id": str(user.id),
        "email": user.email,
        "display_name": "Ayşe",
        "ui_locale": "tr",
    }
    assert len(body["csrf_token"]) >= 32
    assert body["memberships"] == [
        {"workspace_id": str(a.id), "workspace_name": "alpha", "role": "owner", "is_demo": False},
        {"workspace_id": str(b.id), "workspace_name": "Bravo", "role": "manager", "is_demo": True},
    ]


def test_me_exposes_no_secret_fields(client: TestClient, db_session: Session) -> None:
    user = create_user(db_session)
    login(client, user)
    text = client.get("/api/v1/auth/me").text
    assert "password" not in text
    assert "argon2" not in text
    assert "token_hash" not in text


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert (response.status_code, response.json()["code"]) == (401, "AUTH_REQUIRED")


def test_me_ignores_a_garbage_cookie(client: TestClient) -> None:
    client.cookies.set(COOKIE, "not-a-real-token")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_patch_me_updates_display_name_and_locale(client: TestClient, db_session: Session) -> None:
    user = create_user(db_session, ui_locale="tr")
    headers = login(client, user)
    response = client.patch(
        "/api/v1/auth/me", json={"display_name": "  Yeni Ad ", "ui_locale": "en"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["user"]["display_name"] == "Yeni Ad"
    assert response.json()["user"]["ui_locale"] == "en"
    assert client.get("/api/v1/auth/me").json()["user"]["ui_locale"] == "en"


@pytest.mark.parametrize(
    "payload",
    [
        {"ui_locale": "de"},
        {"display_name": ""},
        {"display_name": "x" * 101},
        {"email": "other@example.test"},  # not editable here
        {"is_active": False},
    ],
)
def test_patch_me_rejects_invalid_or_forbidden_fields(
    client: TestClient, db_session: Session, payload: dict[str, object]
) -> None:
    user = create_user(db_session)
    headers = login(client, user)
    response = client.patch("/api/v1/auth/me", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_logins_are_independent_per_client(
    client: TestClient, make_client: Callable[[], TestClient], db_session: Session
) -> None:
    one, two = create_user(db_session), create_user(db_session)
    login(client, one)
    other = make_client()
    login(other, two)
    assert client.get("/api/v1/auth/me").json()["user"]["id"] == str(one.id)
    assert other.get("/api/v1/auth/me").json()["user"]["id"] == str(two.id)
