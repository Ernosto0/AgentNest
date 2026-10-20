import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import list_entries
from app.core.clock import FrozenClock
from app.identity.models import Workspace, WorkspaceMember
from tests.factories import (
    add_member,
    create_user,
    create_workspace,
    login,
    workspace_with_members,
)

CREATE = {
    "name": "Gölkent Fitness & Pilates",
    "business_category": "gym",
    "market": "tr",
    "default_locale": "tr",
    "timezone": "Europe/Istanbul",
    "currency": "TRY",
}


def errors(response_json: dict[str, object]) -> dict[str, str]:
    return {e["field"]: e["code"] for e in response_json["errors"]}  # type: ignore[index, attr-defined]


# --- create --------------------------------------------------------------------------------


def test_create_workspace_makes_the_creator_the_owner(
    client: TestClient, db_session: Session, clock: FrozenClock
) -> None:
    user = create_user(db_session)
    headers = login(client, user)

    response = client.post("/api/v1/workspaces", json=CREATE, headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == "golkent-fitness-pilates"
    assert body["is_demo"] is False  # not settable through the API
    assert body["status"] == "active"
    assert body["reply_languages"] == ["tr"]
    assert body["settings"] == {
        "automation_reviewed_at": None,
        "disclosure_enabled": True,
        "disclosure_text": {"tr": "", "en": ""},
        "daily_report_hour": 20,
        "publish_max_delay_minutes": 1440,
    }

    member = db_session.get(WorkspaceMember, (uuid.UUID(body["id"]), user.id))
    assert member is not None and member.role == "owner"
    assert client.get("/api/v1/auth/me").json()["memberships"][0]["role"] == "owner"

    (entry,) = list_entries(db_session, workspace_id=uuid.UUID(body["id"]))
    assert entry.action == "workspace.created"
    assert (entry.actor_type, entry.actor_id) == ("user", str(user.id))
    assert entry.resource_id == uuid.UUID(body["id"])
    assert entry.occurred_at == clock.now()
    assert entry.metadata_["currency"] == "TRY"


def test_slugs_stay_unique(client: TestClient, db_session: Session) -> None:
    headers = login(client, create_user(db_session))
    slugs = [
        client.post("/api/v1/workspaces", json=CREATE, headers=headers).json()["slug"]
        for _ in range(3)
    ]
    assert slugs == [
        "golkent-fitness-pilates",
        "golkent-fitness-pilates-2",
        "golkent-fitness-pilates-3",
    ]


@pytest.mark.parametrize(
    ("override", "field", "code"),
    [
        ({"timezone": "Nope/Zone"}, "timezone", "invalid_timezone"),
        ({"timezone": "../etc/passwd"}, "timezone", "invalid_timezone"),
        ({"currency": "ABC"}, "currency", "invalid_currency"),
        ({"currency": "try"}, "currency", "invalid_currency"),
        ({"currency": "XXX"}, "currency", "invalid_currency"),
        ({"name": "   "}, "name", "too_short"),
        ({"market": "mars"}, "market", "invalid_choice"),
        ({"default_locale": "de"}, "default_locale", "invalid_choice"),
        ({"business_category": "casino"}, "business_category", "invalid_choice"),
    ],
)
def test_create_workspace_validation(
    client: TestClient, db_session: Session, override: dict[str, str], field: str, code: str
) -> None:
    headers = login(client, create_user(db_session))
    response = client.post("/api/v1/workspaces", json={**CREATE, **override}, headers=headers)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"
    assert errors(response.json())[field] == code
    assert db_session.scalars(select(Workspace)).first() is None  # nothing was created


def test_create_workspace_accepts_dst_timezone_and_other_currency(
    client: TestClient, db_session: Session
) -> None:
    headers = login(client, create_user(db_session))
    response = client.post(
        "/api/v1/workspaces",
        json={
            **CREATE,
            "name": "Harbor",
            "timezone": "Europe/Lisbon",
            "currency": "EUR",
            "default_locale": "en",
            "market": "global",
        },
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["reply_languages"] == ["en"]


def test_create_workspace_cannot_set_privileged_fields(
    client: TestClient, db_session: Session
) -> None:
    headers = login(client, create_user(db_session))
    for extra in ({"is_demo": True}, {"slug": "mine"}, {"status": "deleting"}):
        response = client.post("/api/v1/workspaces", json={**CREATE, **extra}, headers=headers)
        assert response.status_code == 422


# --- list and read ---------------------------------------------------------------------------


def test_list_workspaces_returns_only_my_memberships(
    client: TestClient, db_session: Session
) -> None:
    mine, users = workspace_with_members(db_session, roles=("manager",), name="Mine")
    create_workspace(db_session, name="Someone else's")
    login(client, users["manager"])

    body = client.get("/api/v1/workspaces").json()
    assert body["next_cursor"] is None
    assert [(i["workspace_name"], i["role"]) for i in body["items"]] == [("Mine", "manager")]


def test_get_workspace_as_each_role(client: TestClient, db_session: Session) -> None:
    ws, users = workspace_with_members(
        db_session, roles=("owner", "manager", "staff"), name="Gym", timezone="Europe/Lisbon"
    )
    for user in users.values():
        c = TestClient(client.app)
        login(c, user)
        response = c.get(f"/api/v1/workspaces/{ws.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(ws.id)
        assert body["timezone"] == "Europe/Lisbon"
        assert body["settings"]["daily_report_hour"] == 20  # defaults fill an empty settings blob


def test_non_member_gets_404_not_403(client: TestClient, db_session: Session) -> None:
    ws, _ = workspace_with_members(db_session)
    outsider = create_user(db_session)
    login(client, outsider)
    response = client.get(f"/api/v1/workspaces/{ws.id}")
    assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")
    # Identical to a workspace that does not exist at all: existence is not revealed.
    unknown = client.get(f"/api/v1/workspaces/{uuid.uuid4()}")
    assert unknown.status_code == 404
    assert {k: v for k, v in response.json().items() if k != "request_id"} == {
        k: v for k, v in unknown.json().items() if k != "request_id"
    }


def test_workspace_routes_require_authentication(client: TestClient, db_session: Session) -> None:
    ws, _ = workspace_with_members(db_session)
    assert client.get(f"/api/v1/workspaces/{ws.id}").status_code == 401
    assert client.get("/api/v1/workspaces").status_code == 401


def test_malformed_workspace_id_is_a_validation_error(
    client: TestClient, db_session: Session
) -> None:
    login(client, create_user(db_session))
    assert client.get("/api/v1/workspaces/not-a-uuid").status_code == 422


# --- patch -----------------------------------------------------------------------------------


def test_owner_can_patch_and_it_is_audited(
    client: TestClient, db_session: Session, clock: FrozenClock
) -> None:
    ws, users = workspace_with_members(db_session, name="Old name")
    headers = login(client, users["owner"])

    response = client.patch(
        f"/api/v1/workspaces/{ws.id}",
        json={
            "name": "New name",
            "timezone": "Europe/Lisbon",
            "settings": {"daily_report_hour": 18},
            "reply_languages": ["tr", "en", "tr"],
        },
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "New name"
    assert body["timezone"] == "Europe/Lisbon"
    assert body["reply_languages"] == ["tr", "en"]
    assert body["settings"]["daily_report_hour"] == 18
    assert body["settings"]["publish_max_delay_minutes"] == 1440  # untouched keys survive

    (entry,) = list_entries(db_session, workspace_id=ws.id, action="workspace.updated")
    assert entry.metadata_["changed"] == [
        "name",
        "reply_languages",
        "settings.daily_report_hour",
        "timezone",
    ]
    assert entry.occurred_at == clock.now()
    assert "New name" not in str(entry.metadata_)


def test_publish_max_delay_defaults_to_24_hours_and_is_limited_to_24_hours(
    client: TestClient, db_session: Session
) -> None:
    ws, users = workspace_with_members(db_session)
    headers = login(client, users["owner"])
    url = f"/api/v1/workspaces/{ws.id}"
    assert client.get(url).json()["settings"]["publish_max_delay_minutes"] == 1440

    for minutes, expected in ((1440, 200), (360, 200), (1441, 422), (0, 422)):
        response = client.patch(
            url, json={"settings": {"publish_max_delay_minutes": minutes}}, headers=headers
        )
        assert response.status_code == expected, (minutes, response.text)


def test_settings_patches_merge_nested_values(client: TestClient, db_session: Session) -> None:
    ws, users = workspace_with_members(db_session)
    headers = login(client, users["owner"])
    url = f"/api/v1/workspaces/{ws.id}"
    client.patch(
        url, json={"settings": {"disclosure_text": {"tr": "Yapay zekâ yardımcı"}}}, headers=headers
    )
    client.patch(url, json={"settings": {"disclosure_enabled": False}}, headers=headers)
    settings = client.get(url).json()["settings"]
    assert settings["disclosure_enabled"] is False
    assert settings["disclosure_text"]["tr"] == "Yapay zekâ yardımcı"


def test_noop_patch_writes_no_audit_entry(client: TestClient, db_session: Session) -> None:
    ws, users = workspace_with_members(db_session, name="Same")
    headers = login(client, users["owner"])
    response = client.patch(f"/api/v1/workspaces/{ws.id}", json={"name": "Same"}, headers=headers)
    assert response.status_code == 200
    assert list_entries(db_session, workspace_id=ws.id, action="workspace.updated") == []


@pytest.mark.parametrize("role", ["manager", "staff"])
def test_patch_needs_workspace_manage(client: TestClient, db_session: Session, role: str) -> None:
    ws, users = workspace_with_members(db_session, roles=("owner", role), name="Keep")
    headers = login(client, users[role])
    response = client.patch(f"/api/v1/workspaces/{ws.id}", json={"name": "Hacked"}, headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
    assert response.json()["params"] == {"permission": "workspace.manage"}
    assert db_session.get(Workspace, ws.id).name == "Keep"  # type: ignore[union-attr]


def test_patch_by_non_member_is_404_even_with_a_valid_csrf_token(
    client: TestClient, db_session: Session
) -> None:
    ws, _ = workspace_with_members(db_session, name="Keep")
    headers = login(client, create_user(db_session))
    response = client.patch(f"/api/v1/workspaces/{ws.id}", json={"name": "Hacked"}, headers=headers)
    assert response.status_code == 404
    assert db_session.get(Workspace, ws.id).name == "Keep"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("payload", "field", "code"),
    [
        ({"name": None}, "name", "required"),
        ({"timezone": "Mars/Base"}, "timezone", "invalid_timezone"),
        ({"currency": "ZZZ"}, "currency", "invalid_currency"),
        ({"reply_languages": []}, "reply_languages", "too_short"),
        ({"reply_languages": ["de"]}, "reply_languages.0", "invalid_choice"),
        ({"settings": {"daily_report_hour": 25}}, "settings.daily_report_hour", "invalid"),
        ({"settings": {"surprise": 1}}, "settings.surprise", "invalid"),
        ({"is_demo": True}, "is_demo", "invalid"),
        ({"slug": "x"}, "slug", "invalid"),
        ({"status": "deleting"}, "status", "invalid"),
    ],
)
def test_patch_validation(
    client: TestClient,
    db_session: Session,
    payload: dict[str, object],
    field: str,
    code: str,
) -> None:
    ws, users = workspace_with_members(db_session)
    headers = login(client, users["owner"])
    response = client.patch(f"/api/v1/workspaces/{ws.id}", json=payload, headers=headers)
    assert response.status_code == 422, response.text
    assert field in errors(response.json())


def test_patch_requires_csrf(client: TestClient, db_session: Session) -> None:
    ws, users = workspace_with_members(db_session)
    login(client, users["owner"])
    response = client.patch(f"/api/v1/workspaces/{ws.id}", json={"name": "X"})
    assert (response.status_code, response.json()["code"]) == (403, "CSRF_FAILED")


# --- members ---------------------------------------------------------------------------------


def test_any_member_can_list_members(client: TestClient, db_session: Session) -> None:
    ws, users = workspace_with_members(db_session, roles=("owner", "manager", "staff"))
    outsider = create_user(db_session)
    other_ws = create_workspace(db_session)
    add_member(db_session, other_ws, outsider, "owner")

    login(client, users["staff"])
    body = client.get(f"/api/v1/workspaces/{ws.id}/members").json()
    assert {m["role"] for m in body["items"]} == {"owner", "manager", "staff"}
    assert {m["user_id"] for m in body["items"]} == {str(u.id) for u in users.values()}
    assert str(outsider.id) not in str(body)
    assert set(body["items"][0]) == {"user_id", "email", "display_name", "role", "joined_at"}
    assert "password" not in str(body)


def test_non_member_cannot_list_members(client: TestClient, db_session: Session) -> None:
    ws, _ = workspace_with_members(db_session)
    login(client, create_user(db_session))
    assert client.get(f"/api/v1/workspaces/{ws.id}/members").status_code == 404
