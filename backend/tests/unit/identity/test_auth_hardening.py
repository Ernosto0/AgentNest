"""Unit and integration tests for authentication hardening (P8-04 / ADR-025 §2).

Covers:
- Login throttling (per-IP and per-email exponential lockout).
- Trusted proxy handling and X-Forwarded-For spoofing prevention.
- Session listing, individual revocation, revoke-all.
- Password change with current-password verification and session invalidation.
- Session isolation between users.
"""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.audit.service import list_entries
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.security import hash_token
from app.identity.models import AuthSession, LoginThrottle
from app.identity.throttling import extract_client_ip
from tests.factories import DEFAULT_PASSWORD, create_user, login

LOGIN = "/api/v1/auth/login"
SESSIONS = "/api/v1/auth/sessions"
PASSWORD = "/api/v1/auth/password"
COOKIE = "agentnest_session"


def test_client_ip_extraction_and_proxy_trust() -> None:
    settings = Settings(
        app_env="test",
        trusted_proxy_cidrs="127.0.0.1/32,10.0.0.0/8",
    )

    # 1. Direct connection from untrusted IP: ignore XFF completely
    scope = {
        "type": "http",
        "client": ("198.51.100.5", 54321),
        "headers": [(b"x-forwarded-for", b"203.0.113.195, 1.2.3.4")],
    }
    req = Request(scope)
    assert extract_client_ip(req, settings) == "198.51.100.5"

    # 2. Connection from trusted proxy: parse XFF right-to-left
    scope_proxy = {
        "type": "http",
        "client": ("127.0.0.1", 54321),
        "headers": [(b"x-forwarded-for", b"203.0.113.195, 10.0.0.2")],
    }
    req_proxy = Request(scope_proxy)
    assert extract_client_ip(req_proxy, settings) == "203.0.113.195"

    # 3. Trusted proxy with multiple external proxies: rightmost untrusted
    scope_multi = {
        "type": "http",
        "client": ("10.0.0.1", 54321),
        "headers": [(b"x-forwarded-for", b"198.51.100.1, 203.0.113.50, 10.0.0.2")],
    }
    req_multi = Request(scope_multi)
    assert extract_client_ip(req_multi, settings) == "203.0.113.50"


def test_login_throttling_exponential_lockout(
    client: TestClient, db_session: Session, clock: FrozenClock
) -> None:
    user = create_user(db_session, email="throttle-target@example.com")

    # 4 failed attempts: not locked out yet (401 INVALID_CREDENTIALS)
    for _ in range(4):
        resp = client.post(LOGIN, json={"email": user.email, "password": "wrong-password"})
        assert resp.status_code == 401
        assert resp.json()["code"] == "INVALID_CREDENTIALS"

    # 5th failed attempt: triggers first lockout (60s)
    resp5 = client.post(LOGIN, json={"email": user.email, "password": "wrong-password"})
    assert resp5.status_code == 401

    # 6th attempt immediately: locked out with 429 RATE_LIMITED and Retry-After header
    resp_locked = client.post(LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD})
    assert resp_locked.status_code == 429
    assert resp_locked.json()["code"] == "RATE_LIMITED"
    retry_after = int(resp_locked.headers["Retry-After"])
    assert 1 <= retry_after <= 60

    # Verify audit event auth.login_throttled
    (entry,) = list_entries(db_session, action="auth.login_throttled", system_level=True)
    assert entry.metadata_["retry_after"] == retry_after

    # Advance clock 61 seconds: lockout expires
    clock.advance(seconds=61)
    # Next failure escalates to 300s (5m)
    resp_fail6 = client.post(LOGIN, json={"email": user.email, "password": "wrong-password"})
    assert resp_fail6.status_code == 401

    resp_locked2 = client.post(LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD})
    assert resp_locked2.status_code == 429
    assert int(resp_locked2.headers["Retry-After"]) > 60

    # Advance clock past 300s and log in successfully: clears the throttle
    clock.advance(seconds=301)
    resp_ok = client.post(LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD})
    assert resp_ok.status_code == 204

    # Verify throttle records cleared
    throttles = list(db_session.scalars(select(LoginThrottle)))
    assert len(throttles) == 0


def test_login_records_session_ip(client: TestClient, db_session: Session) -> None:
    user = create_user(db_session)
    resp = client.post(
        LOGIN,
        json={"email": user.email, "password": DEFAULT_PASSWORD},
        headers={"user-agent": "TestAgent/1.0"},
    )
    assert resp.status_code == 204
    token = client.cookies[COOKIE]
    session_row = db_session.scalars(
        select(AuthSession).where(AuthSession.token_hash == hash_token(token))
    ).one()
    assert session_row.ip_address is not None
    assert session_row.user_agent == "TestAgent/1.0"


def test_session_listing_and_revocation(client: TestClient, db_session: Session) -> None:
    user = create_user(db_session)
    auth_headers = login(client, user)

    # Open a second session with another client
    second_client = TestClient(client.app)
    second_client.post(LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD})
    assert COOKIE in second_client.cookies

    # List sessions from the first client
    resp = client.get(SESSIONS, headers=auth_headers)
    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) == 2

    current_sessions = [s for s in sessions if s["is_current"]]
    other_sessions = [s for s in sessions if not s["is_current"]]
    assert len(current_sessions) == 1
    assert len(other_sessions) == 1

    # Revoke the other session
    other_id = other_sessions[0]["id"]
    del_resp = client.delete(f"{SESSIONS}/{other_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    # Other client is now logged out
    check_other = second_client.get("/api/v1/auth/me")
    assert check_other.status_code == 401

    # First client still active
    check_first = client.get("/api/v1/auth/me", headers=auth_headers)
    assert check_first.status_code == 200


def test_cannot_revoke_foreign_session(client: TestClient, db_session: Session) -> None:
    user1 = create_user(db_session)
    user2 = create_user(db_session)

    headers1 = login(client, user1)
    client2 = TestClient(client.app)
    headers2 = login(client2, user2)

    sessions_u2 = client2.get(SESSIONS, headers=headers2).json()
    u2_session_id = sessions_u2[0]["id"]

    # User 1 tries to delete User 2's session -> 404 NOT_FOUND
    resp = client.delete(f"{SESSIONS}/{u2_session_id}", headers=headers1)
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_revoke_all_sessions(client: TestClient, db_session: Session) -> None:
    user = create_user(db_session)
    headers1 = login(client, user)

    client2 = TestClient(client.app)
    login(client2, user)
    client3 = TestClient(client.app)
    login(client3, user)

    # Client 1 revokes all other sessions (include_current=False)
    resp = client.post(f"{SESSIONS}/revoke-all", json={"include_current": False}, headers=headers1)
    assert resp.status_code == 204

    # Clients 2 and 3 are revoked
    assert client2.get("/api/v1/auth/me").status_code == 401
    assert client3.get("/api/v1/auth/me").status_code == 401

    # Client 1 is still logged in
    assert client.get("/api/v1/auth/me", headers=headers1).status_code == 200

    # Client 1 revokes all including current
    resp_all = client.post(
        f"{SESSIONS}/revoke-all", json={"include_current": True}, headers=headers1
    )
    assert resp_all.status_code == 204
    # Cookie is cleared
    assert client.get("/api/v1/auth/me").status_code == 401


def test_password_change_hardening(client: TestClient, db_session: Session) -> None:
    user = create_user(db_session)
    headers = login(client, user)

    # 1. Wrong current password -> 401 INVALID_CREDENTIALS
    bad_current = client.post(
        PASSWORD,
        json={"current_password": "not-my-password", "new_password": "a-strong-new-password-123"},
        headers=headers,
    )
    assert bad_current.status_code == 401
    assert bad_current.json()["code"] == "INVALID_CREDENTIALS"

    # 2. Too short (< 12 chars) -> 422 VALIDATION_FAILED
    short_pwd = client.post(
        PASSWORD,
        json={"current_password": DEFAULT_PASSWORD, "new_password": "short123"},
        headers=headers,
    )
    assert short_pwd.status_code == 422
    assert short_pwd.json()["code"] == "VALIDATION_FAILED"

    # 3. Too common -> 422 VALIDATION_FAILED
    common_pwd = client.post(
        PASSWORD,
        json={"current_password": DEFAULT_PASSWORD, "new_password": "password1234"},
        headers=headers,
    )
    assert common_pwd.status_code == 422
    assert common_pwd.json()["code"] == "VALIDATION_FAILED"

    # Open a second session to prove it gets revoked
    client2 = TestClient(client.app)
    login(client2, user)
    assert client2.get("/api/v1/auth/me").status_code == 200

    # 4. Valid password change
    NEW_PASSWORD = "brand-new-super-secure-passphrase-2026"
    good_pwd = client.post(
        PASSWORD,
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
        headers=headers,
    )
    assert good_pwd.status_code == 204

    # Current session remains valid
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    # Other session is revoked!
    assert client2.get("/api/v1/auth/me").status_code == 401

    # Old password no longer works for new login
    fail_old = client2.post(LOGIN, json={"email": user.email, "password": DEFAULT_PASSWORD})
    assert fail_old.status_code == 401

    # New password works for new login
    login_new = client2.post(LOGIN, json={"email": user.email, "password": NEW_PASSWORD})
    assert login_new.status_code == 204
