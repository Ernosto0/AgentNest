"""Members and invites (plan H14): the accept flow, the last-owner rule, role change and
removal, audit entries, and the single INVITE_INVALID code for every dead token."""

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import list_entries
from app.core.clock import FrozenClock
from app.core.security import hash_token
from app.identity.models import Invite
from tests.factories import (
    add_member,
    create_user,
    create_workspace,
    login,
    workspace_with_members,
)

BASE = "/api/v1/workspaces"
ACCEPT = "/api/v1/invites/accept"


def _create_invite(
    client: TestClient, ws_id: str, headers: dict[str, str], role: str = "manager"
) -> dict:
    response = client.post(f"{BASE}/{ws_id}/invites", json={"role": role}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _token(invite: dict) -> str:
    return invite["invite_path"].split("/")[-1]


def _accept_body(token: str, *, email: str, display_name: str, password: str) -> dict:
    return {"token": token, "email": email, "display_name": display_name, "password": password}


def _entry(db: Session, ws_id: str, action: str):
    return list_entries(db, workspace_id=uuid.UUID(ws_id), action=action)


# --- create ----------------------------------------------------------------------------------


def test_owner_creates_an_invite_with_a_one_time_link(
    client: TestClient, db_session: Session, clock: FrozenClock
) -> None:
    ws, users = workspace_with_members(db_session)
    headers = login(client, users["owner"])

    invite = _create_invite(client, str(ws.id), headers, role="staff")
    assert set(invite) == {"id", "role", "expires_at", "invite_path", "invite_url", "created_at"}
    assert invite["role"] == "staff"
    assert invite["invite_path"].startswith("/invite/")
    assert invite["invite_url"] == "http://localhost:8000" + invite["invite_path"]
    assert invite["expires_at"] == (clock.now() + timedelta(days=7)).isoformat().replace("+00:00", "Z")

    token = _token(invite)
    row = db_session.scalars(select(Invite).where(Invite.id == uuid.UUID(invite["id"]))).one()
    # Only the sha256 is stored; the raw token never reaches the database.
    assert row.token_hash == hash_token(token)
    assert token.encode() not in bytes(row.token_hash)

    (audit,) = _entry(db_session, str(ws.id), "member.invited")
    assert audit.metadata_["role"] == "staff"
    assert audit.metadata_["invite_id"] == invite["id"]
    assert audit.actor_id == str(users["owner"].id)


def test_pending_invites_are_listed_without_their_token(
    client: TestClient, db_session: Session
) -> None:
    ws, users = workspace_with_members(db_session)
    headers = login(client, users["owner"])
    invite = _create_invite(client, str(ws.id), headers)

    listing = client.get(f"{BASE}/{ws.id}/invites", headers=headers)
    assert listing.status_code == 200
    (item,) = listing.json()["items"]
    assert set(item) == {"id", "role", "expires_at", "created_at"}
    assert item["id"] == invite["id"]
    assert "invite_path" not in item and "invite_url" not in item
    assert _token(invite) not in listing.text  # the token is never re-shown


def test_staff_cannot_manage_members_or_invites(client: TestClient, db_session: Session) -> None:
    ws, users = workspace_with_members(db_session, roles=("owner", "staff"))
    headers = login(client, users["staff"])
    member_url = f"{BASE}/{ws.id}/members/{users['owner'].id}"

    assert client.patch(member_url, json={"role": "manager"}, headers=headers).status_code == 403
    assert client.delete(member_url, headers=headers).status_code == 403
    assert (
        client.post(f"{BASE}/{ws.id}/invites", json={"role": "staff"}, headers=headers).status_code
        == 403
    )
    assert client.get(f"{BASE}/{ws.id}/invites", headers=headers).status_code == 403


# --- accept ----------------------------------------------------------------------------------


def test_accept_as_a_new_user_signs_them_in(
    client: TestClient, make_client, db_session: Session
) -> None:
    ws, users = workspace_with_members(db_session)
    headers = login(client, users["owner"])
    invite = _create_invite(client, str(ws.id), headers, role="manager")
    token = _token(invite)

    joiner = make_client()
    response = joiner.post(
        ACCEPT,
        json=_accept_body(
            token,
            email="  New@Example.Test ",
            display_name="Yeni Üye",
            password="correct-horse-battery",
        ),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {"workspace_id": str(ws.id), "workspace_name": ws.name, "role": "manager"}

    me = joiner.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "new@example.test"  # normalised
    assert me.json()["user"]["display_name"] == "Yeni Üye"
    assert me.json()["memberships"][0]["role"] == "manager"

    row = db_session.scalars(select(Invite).where(Invite.id == uuid.UUID(invite["id"]))).one()
    assert row.accepted_at is not None and row.accepted_by_user_id is not None
    (joined,) = _entry(db_session, str(ws.id), "member.joined")
    assert joined.metadata_ == {"role": "manager", "source": "invite"}
    assert joined.actor_id == me.json()["user"]["id"]


def test_accept_as_an_existing_signed_in_user(
    client: TestClient, make_client, db_session: Session
) -> None:
    ws, users = workspace_with_members(db_session)
    headers = login(client, users["owner"])
    invite = _create_invite(client, str(ws.id), headers, role="staff")

    member = create_user(db_session)
    member_client = make_client()
    member_headers = login(member_client, member)
    response = member_client.post(ACCEPT, json={"token": _token(invite)}, headers=member_headers)
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "staff"
    assert member_client.get("/api/v1/auth/me").json()["memberships"][0]["role"] == "staff"


def test_accept_with_an_existing_email_while_signed_out_is_409(
    client: TestClient, make_client, db_session: Session
) -> None:
    ws, users = workspace_with_members(db_session)
    headers = login(client, users["owner"])
    invite = _create_invite(client, str(ws.id), headers)

    existing = create_user(db_session, email="taken@example.test")
    joiner = make_client()
    response = joiner.post(
        ACCEPT,
        json=_accept_body(
            _token(invite), email=existing.email, display_name="X", password="correct-horse-battery"
        ),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT_STATE"
    assert response.json()["params"] == {"reason": "email_taken"}


def test_accept_when_already_a_member_is_409(client: TestClient, db_session: Session) -> None:
    ws, users = workspace_with_members(db_session, roles=("owner", "manager"))
    headers = login(client, users["owner"])
    invite = _create_invite(client, str(ws.id), headers)

    response = client.post(ACCEPT, json={"token": _token(invite)}, headers=headers)
    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT_STATE"
    assert response.json()["params"] == {"reason": "already_member"}


def test_every_dead_token_returns_the_same_invite_invalid(
    client: TestClient, make_client, db_session: Session, clock: FrozenClock
) -> None:
    ws, users = workspace_with_members(db_session)
    headers = login(client, users["owner"])
    invite = _create_invite(client, str(ws.id), headers)
    token = _token(invite)

    # Reused: accept once, then the same token is dead.
    first = make_client()
    first.post(
        ACCEPT,
        json=_accept_body(
            token, email="a@b.test", display_name="A", password="correct-horse-battery"
        ),
    )

    reused = make_client()
    reused_resp = reused.post(
        ACCEPT,
        json=_accept_body(
            token, email="c@d.test", display_name="C", password="correct-horse-battery"
        ),
    )

    # Revoked.
    invite2 = _create_invite(client, str(ws.id), headers)
    assert (
        client.post(f"{BASE}/{ws.id}/invites/{invite2['id']}/revoke", headers=headers).status_code
        == 204
    )
    revoked_resp = make_client().post(
        ACCEPT,
        json=_accept_body(
            _token(invite2), email="e@f.test", display_name="E", password="correct-horse-battery"
        ),
    )

    # Expired (frozen clock).
    invite3 = _create_invite(client, str(ws.id), headers)
    clock.advance(days=8)
    expired_resp = make_client().post(
        ACCEPT,
        json=_accept_body(
            _token(invite3), email="g@h.test", display_name="G", password="correct-horse-battery"
        ),
    )

    # Unknown.
    unknown_resp = make_client().post(
        ACCEPT,
        json=_accept_body(
            "not-a-real-token", email="i@j.test", display_name="I", password="correct-horse-battery"
        ),
    )

    expected = {
        "type": "about:blank",
        "title": "Bad Request",
        "status": 400,
        "code": "INVITE_INVALID",
        "params": {},
    }
    for response in (reused_resp, revoked_resp, expired_resp, unknown_resp):
        assert response.status_code == 400, response.text
        body = response.json()
        assert {k: v for k, v in body.items() if k != "request_id" and k != "detail"} == expected
        assert body["detail"].strip() != ""  # localised text, never the raw token


def test_revoking_an_accepted_invite_is_409(
    client: TestClient, make_client, db_session: Session
) -> None:
    ws, users = workspace_with_members(db_session)
    headers = login(client, users["owner"])
    invite = _create_invite(client, str(ws.id), headers)
    joiner = make_client()
    assert (
        joiner.post(
            ACCEPT,
            json=_accept_body(
                _token(invite), email="n@o.test", display_name="N", password="correct-horse-battery"
            ),
        ).status_code
        == 200
    )

    response = client.post(f"{BASE}/{ws.id}/invites/{invite['id']}/revoke", headers=headers)
    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT_STATE"


def test_revoking_is_audited_and_idempotent(client: TestClient, db_session: Session) -> None:
    ws, users = workspace_with_members(db_session)
    headers = login(client, users["owner"])
    invite = _create_invite(client, str(ws.id), headers)
    url = f"{BASE}/{ws.id}/invites/{invite['id']}/revoke"

    assert client.post(url, headers=headers).status_code == 204
    assert client.post(url, headers=headers).status_code == 204  # idempotent
    (audit,) = _entry(db_session, str(ws.id), "member.invite_revoked")
    assert audit.metadata_["invite_id"] == invite["id"]
    assert client.get(f"{BASE}/{ws.id}/invites", headers=headers).json()["items"] == []


# --- roles and removal -----------------------------------------------------------------------


def test_role_change_is_applied_and_audited(client: TestClient, db_session: Session) -> None:
    ws, users = workspace_with_members(db_session, roles=("owner", "staff"))
    headers = login(client, users["owner"])

    response = client.patch(
        f"{BASE}/{ws.id}/members/{users['staff'].id}", json={"role": "manager"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["role"] == "manager"
    (audit,) = _entry(db_session, str(ws.id), "member.role_changed")
    assert audit.metadata_ == {"from_role": "staff", "to_role": "manager"}
    assert audit.resource_id == users["staff"].id


def test_the_last_owner_cannot_be_demoted_or_removed(
    client: TestClient, db_session: Session
) -> None:
    ws, users = workspace_with_members(db_session)
    headers = login(client, users["owner"])
    url = f"{BASE}/{ws.id}/members/{users['owner'].id}"

    demote = client.patch(url, json={"role": "manager"}, headers=headers)
    assert (demote.status_code, demote.json()["code"]) == (409, "LAST_OWNER_REQUIRED")
    remove = client.delete(url, headers=headers)
    assert (remove.status_code, remove.json()["code"]) == (409, "LAST_OWNER_REQUIRED")


def test_owner_transfer_works_and_removal_is_audited(
    client: TestClient, db_session: Session
) -> None:
    ws, users = workspace_with_members(db_session, roles=("owner", "manager"))
    headers = login(client, users["owner"])
    member_url = f"{BASE}/{ws.id}/members/{users['manager'].id}"
    owner_url = f"{BASE}/{ws.id}/members/{users['owner'].id}"

    # Promote the manager, then demote the old owner (J1 owner transfer).
    assert client.patch(member_url, json={"role": "owner"}, headers=headers).status_code == 200
    assert client.patch(owner_url, json={"role": "manager"}, headers=headers).status_code == 200

    members = client.get(f"{BASE}/{ws.id}/members").json()["items"]
    roles = {m["user_id"]: m["role"] for m in members}
    assert roles == {str(users["owner"].id): "manager", str(users["manager"].id): "owner"}

    # Now the (new) owner removes the old owner.
    new_headers = login(client, users["manager"])
    assert client.delete(owner_url, headers=new_headers).status_code == 204
    (removed,) = _entry(db_session, str(ws.id), "member.removed")
    assert removed.resource_id == users["owner"].id
    assert removed.metadata_ == {"role": "manager"}


def test_removing_a_non_owner_and_a_foreign_user_is_404(
    client: TestClient, db_session: Session
) -> None:
    ws, users = workspace_with_members(db_session, roles=("owner", "staff"))
    headers = login(client, users["owner"])
    assert (
        client.delete(f"{BASE}/{ws.id}/members/{users['staff'].id}", headers=headers).status_code
        == 204
    )
    # A user who is not a member of this workspace reads as 404, not 403.
    outsider = create_user(db_session)
    assert (
        client.delete(f"{BASE}/{ws.id}/members/{outsider.id}", headers=headers).status_code == 404
    )
    # A member of another workspace is a foreign id.
    other = create_workspace(db_session)
    add_member(db_session, other, outsider, "owner")
    assert (
        client.patch(
            f"{BASE}/{ws.id}/members/{outsider.id}", json={"role": "owner"}, headers=headers
        ).status_code
        == 404
    )
