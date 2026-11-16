"""F-01, Session 03: Web Push subscriptions (store, list, unsubscribe; nothing is sent).

Proves: the keys are stored as ciphertext and never returned, the endpoint and the key material
never appear in a response, a user sees and removes only their own devices, a foreign workspace
and another member's id are 404, subscribing is idempotent, a shared device moves to the newest
user, bad endpoints and keys are refused, the public key endpoint is safe without VAPID, and
subscribing is refused when push is not configured.
"""

import base64
import json
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.security import TokenCryptoError, generate_vapid_keys
from app.identity.models import WorkspaceMember
from app.jobs.models import Job
from app.notifications import push_subscriptions as service
from app.notifications.models import PushSubscription
from tests.factories import login, workspace_with_members
from tests.helpers.env import Env, Role, build_env

PUBLIC, PRIVATE = generate_vapid_keys()
TOKEN_KEYS = "k1:" + base64.b64encode(b"7" * 32).decode()
ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123-device-one"
OTHER_ENDPOINT = "https://updates.push.services.mozilla.com/wpush/v2/device-two"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


P256DH = _b64(b"\x04" + b"p" * 64)
AUTH = _b64(b"a" * 16)
OTHER_P256DH = _b64(b"\x04" + b"q" * 64)
OTHER_AUTH = _b64(b"b" * 16)
CHROME_ANDROID = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Mobile Safari/537.36"
)


def sub_body(
    endpoint: str = ENDPOINT, p256dh: str = P256DH, auth: str = AUTH, **extra: Any
) -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "expirationTime": None,
        "keys": {"p256dh": p256dh, "auth": auth},
        **extra,
    }


@pytest.fixture
def push_app(build_app: Callable[..., FastAPI]) -> FastAPI:
    return build_app(
        web_push_vapid_public_key=PUBLIC,
        web_push_vapid_private_key=SecretStr(PRIVATE),
        web_push_subject="mailto:ops@example.com",
        token_encryption_keys=SecretStr(TOKEN_KEYS),
        token_encryption_active_key_id="k1",
    )


@pytest.fixture
def push_env(db_session: Session, push_app: FastAPI, clock: FrozenClock) -> Env:
    def make() -> TestClient:
        return TestClient(push_app, base_url="https://testserver")

    return build_env(db_session, make, clock)


def subscribe(env: Env, role: Role | None = None, **kwargs: Any) -> Any:
    role = role or env.owner
    headers = {**role.headers, "User-Agent": CHROME_ANDROID}
    return role.client.post(
        f"{env.base}/push-subscriptions", json=sub_body(**kwargs), headers=headers
    )


def rows(env: Env) -> list[PushSubscription]:
    env.session.expire_all()
    return list(env.session.scalars(select(PushSubscription).order_by(PushSubscription.created_at)))


def test_subscribe_stores_ciphertext_and_returns_no_key_material(push_env: Env) -> None:
    response = subscribe(push_env)
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"id", "label", "created_at", "last_success_at"}
    assert body["label"] == "Chrome on Android"
    assert body["last_success_at"] is None
    text = response.text
    for secret in (P256DH, AUTH, ENDPOINT, "fcm.googleapis.com"):
        assert secret not in text

    (row,) = rows(push_env)
    assert row.user_id == push_env.owner.user.id
    assert row.workspace_id == push_env.workspace.id
    assert row.endpoint == ENDPOINT  # needed to send; never returned
    assert row.revoked_at is None and row.last_success_at is None
    assert row.key_id == "k1"
    assert P256DH.encode() not in row.p256dh_ciphertext and AUTH.encode() not in row.auth_ciphertext
    assert len(row.p256dh_ciphertext) == 12 + len(P256DH) + 16
    settings = Settings(token_encryption_keys=TOKEN_KEYS, token_encryption_active_key_id="k1")
    assert service.decrypt_keys(settings, row) == (P256DH, AUTH)


def test_the_stored_keys_are_bound_to_their_row(push_env: Env) -> None:
    subscribe(push_env)
    subscribe(push_env, endpoint=OTHER_ENDPOINT, p256dh=OTHER_P256DH, auth=OTHER_AUTH)
    first, second = rows(push_env)
    settings = Settings(token_encryption_keys=TOKEN_KEYS, token_encryption_active_key_id="k1")
    first.p256dh_ciphertext = second.p256dh_ciphertext  # a blob copied from another row
    with pytest.raises(TokenCryptoError):
        service.decrypt_keys(settings, first)


def test_list_returns_only_my_devices_without_endpoint_or_keys(push_env: Env) -> None:
    subscribe(push_env)
    subscribe(push_env, endpoint=OTHER_ENDPOINT)
    subscribe(push_env, push_env.manager, endpoint="https://web.push.apple.com/QOtherDevice")
    listed = push_env.call(push_env.owner, "GET", "/push-subscriptions")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 2
    assert all(set(i) == {"id", "label", "created_at", "last_success_at"} for i in items)
    for secret in (P256DH, AUTH, ENDPOINT, OTHER_ENDPOINT, "apple.com"):
        assert secret not in listed.text
    mine = push_env.call(push_env.manager, "GET", "/push-subscriptions").json()["items"]
    assert len(mine) == 1


def test_subscribing_twice_is_idempotent_and_refreshes_the_keys(push_env: Env) -> None:
    first = subscribe(push_env)
    second = subscribe(push_env, p256dh=OTHER_P256DH, auth=OTHER_AUTH)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    (row,) = rows(push_env)
    settings = Settings(token_encryption_keys=TOKEN_KEYS, token_encryption_active_key_id="k1")
    assert service.decrypt_keys(settings, row) == (OTHER_P256DH, OTHER_AUTH)
    created = push_env.session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "push_subscription.created")
    )
    assert created == 1


def test_unsubscribe_revokes_and_a_resubscribe_revives_the_same_row(push_env: Env) -> None:
    device = subscribe(push_env).json()["id"]
    gone = push_env.call(push_env.owner, "DELETE", f"/push-subscriptions/{device}")
    assert gone.status_code == 204
    assert push_env.call(push_env.owner, "GET", "/push-subscriptions").json()["items"] == []
    (row,) = rows(push_env)  # kept, revoked
    assert row.revoked_at is not None
    assert (
        push_env.call(push_env.owner, "DELETE", f"/push-subscriptions/{device}").status_code == 404
    )
    again = subscribe(push_env)
    assert again.status_code == 201 and again.json()["id"] == device
    assert rows(push_env)[0].revoked_at is None
    actions = set(push_env.session.scalars(select(AuditLog.action)))
    assert {"push_subscription.created", "push_subscription.revoked"} <= actions
    audited = json.dumps(list(push_env.session.scalars(select(AuditLog.metadata_))))
    assert ENDPOINT not in audited and P256DH not in audited and AUTH not in audited


def test_another_members_device_is_a_404_and_stays_untouched(push_env: Env) -> None:
    device = subscribe(push_env).json()["id"]
    for role in (push_env.manager, push_env.staff):
        assert push_env.call(role, "DELETE", f"/push-subscriptions/{device}").status_code == 404
    assert rows(push_env)[0].revoked_at is None
    assert (
        push_env.call(push_env.owner, "DELETE", f"/push-subscriptions/{uuid.uuid4()}").status_code
        == 404
    )


def test_staff_can_manage_their_own_devices(push_env: Env) -> None:
    assert subscribe(push_env, push_env.staff).status_code == 201
    assert len(push_env.call(push_env.staff, "GET", "/push-subscriptions").json()["items"]) == 1


def test_a_member_of_another_workspace_gets_404(
    push_env: Env, make_client: Callable[[], TestClient], db_session: Session
) -> None:
    device = subscribe(push_env).json()["id"]
    _, users = workspace_with_members(db_session, name="Foreign", slug="foreign")
    foreign = TestClient(push_env.owner.client.app, base_url="https://testserver")
    headers = login(foreign, users["owner"])
    base = f"/api/v1/workspaces/{push_env.workspace.id}/push-subscriptions"
    assert foreign.get(base, headers=headers).status_code == 404
    assert foreign.get(f"{base}/config", headers=headers).status_code == 404
    assert foreign.post(base, json=sub_body(), headers=headers).status_code == 404
    assert foreign.delete(f"{base}/{device}", headers=headers).status_code == 404
    assert len(rows(push_env)) == 1


def test_my_own_workspace_id_does_not_reach_another_workspaces_device(
    push_env: Env, db_session: Session
) -> None:
    """A device id of workspace A used under workspace B (where the caller is a member) is 404."""
    device = subscribe(push_env).json()["id"]
    workspace_b, users = workspace_with_members(db_session, name="Second", slug="second")
    client = TestClient(push_env.owner.client.app, base_url="https://testserver")
    headers = login(client, users["owner"])
    url = f"/api/v1/workspaces/{workspace_b.id}/push-subscriptions/{device}"
    assert client.delete(url, headers=headers).status_code == 404
    assert rows(push_env)[0].revoked_at is None


def test_the_same_device_in_two_workspaces_is_two_independent_rows(
    push_env: Env, db_session: Session
) -> None:
    workspace_b, _ = workspace_with_members(db_session, name="Second", slug="second")
    # The same person owns both workspaces: reuse the first workspace's owner as B's owner.
    db_session.add(
        WorkspaceMember(workspace_id=workspace_b.id, user_id=push_env.owner.user.id, role="owner")
    )
    db_session.flush()
    assert subscribe(push_env).status_code == 201
    url_b = f"/api/v1/workspaces/{workspace_b.id}/push-subscriptions"
    headers = {**push_env.owner.headers, "User-Agent": CHROME_ANDROID}
    assert push_env.owner.client.post(url_b, json=sub_body(), headers=headers).status_code == 201
    db_session.expire_all()
    found = {r.workspace_id for r in db_session.scalars(select(PushSubscription))}
    assert found == {push_env.workspace.id, workspace_b.id}
    listed = push_env.owner.client.get(url_b).json()["items"]
    assert len(listed) == 1  # only this workspace's row


def test_a_shared_device_moves_to_the_user_who_signed_in_last(push_env: Env) -> None:
    subscribe(push_env)  # the owner enabled push on this phone
    assert subscribe(push_env, push_env.staff).status_code == 201  # then staff signed in on it
    by_user = {r.user_id: r for r in rows(push_env)}
    assert by_user[push_env.owner.user.id].revoked_at is not None
    assert by_user[push_env.staff.user.id].revoked_at is None
    assert push_env.call(push_env.owner, "GET", "/push-subscriptions").json()["items"] == []


def test_the_active_devices_per_user_are_capped_by_revoking_the_oldest(push_env: Env) -> None:
    for n in range(service.MAX_ACTIVE_PER_USER + 2):
        push_env.clock.advance(timedelta(seconds=1))
        assert (
            subscribe(push_env, endpoint=f"https://push.example.com/device-{n}").status_code == 201
        )
    active = push_env.call(push_env.owner, "GET", "/push-subscriptions").json()["items"]
    assert len(active) == service.MAX_ACTIVE_PER_USER
    revoked = [r for r in rows(push_env) if r.revoked_at is not None]
    assert {r.endpoint for r in revoked} == {
        "https://push.example.com/device-0",
        "https://push.example.com/device-1",
    }


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/abc",
        "https://127.0.0.1/hook",
        "https://[::1]/hook",
        "https://10.0.0.5/hook",
        "https://localhost/hook",
        "https://printer.local/hook",
        "https://metadata.internal/hook",
        "https://user:pass@push.example.com/x",
        "https://push.example.com:8443/x",
        "https://push.example.com/x#frag",
        "ftp://push.example.com/x",
        "javascript:alert(1)",
        "not a url",
        "https://singlelabel/x",
        "https://push.example.com/" + "a" * 2100,
    ],
)
def test_unsafe_or_malformed_endpoints_are_refused(push_env: Env, endpoint: str) -> None:
    response = subscribe(push_env, endpoint=endpoint)
    assert response.status_code == 422, response.text
    assert rows(push_env) == []


@pytest.mark.parametrize(
    ("p256dh", "auth"),
    [("", AUTH), (P256DH, ""), ("!!!", AUTH), (P256DH, "short"), (_b64(b"x" * 64), AUTH)],
)
def test_malformed_keys_are_refused(push_env: Env, p256dh: str, auth: str) -> None:
    response = subscribe(push_env, p256dh=p256dh, auth=auth)
    assert response.status_code == 422, response.text
    assert rows(push_env) == []


def test_extra_fields_are_refused(push_env: Env) -> None:
    response = push_env.owner.client.post(
        f"{push_env.base}/push-subscriptions",
        json={**sub_body(), "user_id": str(uuid.uuid4())},
        headers=push_env.owner.headers,
    )
    assert response.status_code == 422


def test_a_label_from_the_page_is_tidied_and_the_raw_user_agent_is_not_stored(
    push_env: Env,
) -> None:
    assert subscribe(push_env, label="  Ayşe'nin   telefonu  ").status_code == 201
    (row,) = rows(push_env)
    assert row.device_label == "Ayşe'nin telefonu"
    assert "Mozilla" not in row.device_label
    too_long = subscribe(push_env, endpoint=OTHER_ENDPOINT, label="x" * 61)
    assert too_long.status_code == 422
    assert len(service.device_label(None, "y" * 500)) == service.MAX_LABEL_CHARS


@pytest.mark.parametrize(
    ("agent", "label"),
    [
        (CHROME_ANDROID, "Chrome on Android"),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
            "Version/17 Mobile/15E148 Safari/604.1",
            "Safari on iPhone",
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
            "Firefox on Windows",
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/130 Safari/537.36 Edg/130",
            "Edge on Windows",
        ),
        (None, "Browser"),
        ("curl/8", "Browser"),
    ],
)
def test_device_labels(agent: str | None, label: str) -> None:
    assert service.device_label(agent) == label


def test_subscribing_sends_nothing(push_env: Env) -> None:
    subscribe(push_env)
    assert push_env.session.scalar(select(func.count()).select_from(Job)) == 0


# --- the public key ----------------------------------------------------------------------------


def test_config_returns_the_public_key_only(push_env: Env) -> None:
    response = push_env.call(push_env.staff, "GET", "/push-subscriptions/config")
    assert response.status_code == 200
    assert response.json() == {"enabled": True, "public_key": PUBLIC}
    assert PRIVATE not in response.text and "mailto" not in response.text


def test_config_is_safe_when_push_is_not_configured(env: Env) -> None:
    response = env.call(env.owner, "GET", "/push-subscriptions/config")
    assert response.status_code == 200
    assert response.json() == {"enabled": False, "public_key": None}
    assert env.call(env.owner, "GET", "/push-subscriptions").json() == {"items": []}


def test_subscribing_without_vapid_is_a_clear_conflict(env: Env) -> None:
    response = env.owner.client.post(
        f"{env.base}/push-subscriptions", json=sub_body(), headers=env.owner.headers
    )
    assert response.status_code == 409
    assert response.json()["code"] == "WEB_PUSH_NOT_CONFIGURED"
    assert rows(env) == []


def test_config_and_subscribe_need_a_session(push_env: Env) -> None:
    anonymous = TestClient(push_env.owner.client.app, base_url="https://testserver")
    base = f"{push_env.base}/push-subscriptions"
    assert anonymous.get(f"{base}/config").status_code == 401
    assert anonymous.get(base).status_code == 401
    no_csrf = push_env.owner.client.post(base, json=sub_body())
    assert no_csrf.status_code == 403
    assert rows(push_env) == []
