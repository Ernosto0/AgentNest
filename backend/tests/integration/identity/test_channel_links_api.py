"""Integration tests for owner channel REST API (ADR-012, Phase 9 Session 02 / P9-01)."""

import uuid
from collections.abc import Callable
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.identity.channels import redeem_link_code
from tests.factories import (
    create_user,
    login,
    workspace_with_members,
)


def test_channel_link_code_generation_and_throttling(
    client: TestClient,
    db_session: Session,
    clock: FrozenClock,
) -> None:
    ws, users = workspace_with_members(db_session)
    owner = users["owner"]
    headers = login(client, owner)

    test_settings = Settings(
        _env_file=None,
        telegram_bot_username="AgentNestTestBot",
    )
    client.app.dependency_overrides[get_app_settings] = lambda: test_settings
    try:
        # 1. Generate code
        res = client.post(
            f"/api/v1/workspaces/{ws.id}/channels/link-code",
            json={"channel": "telegram"},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert len(data["code"]) == 8
        assert data["code"].isupper()
        assert data["bot_username"] == "AgentNestTestBot"
        assert data["deep_link_url"] == f"https://t.me/AgentNestTestBot?start={data['code']}"

        # 2. Generate 2nd and 3rd codes
        res2 = client.post(
            f"/api/v1/workspaces/{ws.id}/channels/link-code",
            json={"channel": "telegram"},
            headers=headers,
        )
        assert res2.status_code == 200

        res3 = client.post(
            f"/api/v1/workspaces/{ws.id}/channels/link-code",
            json={"channel": "telegram"},
            headers=headers,
        )
        assert res3.status_code == 200

        # 3. 4th active code should be throttled (max 3 active codes)
        res4 = client.post(
            f"/api/v1/workspaces/{ws.id}/channels/link-code",
            json={"channel": "telegram"},
            headers=headers,
        )
        assert res4.status_code == 429
        assert res4.json()["code"] == "TOO_MANY_ACTIVE_CODES"

        # Advance clock past expiry (15 mins), should allow generating again
        clock.advance(timedelta(minutes=16))
        res5 = client.post(
            f"/api/v1/workspaces/{ws.id}/channels/link-code",
            json={"channel": "telegram"},
            headers=headers,
        )
        assert res5.status_code == 200
    finally:
        client.app.dependency_overrides.pop(get_app_settings, None)


def test_channel_links_list_and_unlink(
    make_client: Callable[[], TestClient],
    db_session: Session,
    clock: FrozenClock,
) -> None:
    client_owner = make_client()
    client_staff = make_client()

    ws, users = workspace_with_members(db_session, roles=("owner", "manager", "staff"))
    owner = users["owner"]
    staff = users["staff"]
    owner_headers = login(client_owner, owner)
    staff_headers = login(client_staff, staff)

    # Initially empty
    res = client_owner.get(f"/api/v1/workspaces/{ws.id}/channels/links", headers=owner_headers)
    assert res.status_code == 200
    assert res.json() == []

    # Generate code for owner and redeem it
    code_res = client_owner.post(
        f"/api/v1/workspaces/{ws.id}/channels/link-code",
        json={"channel": "telegram"},
        headers=owner_headers,
    )
    assert code_res.status_code == 200, code_res.text
    code = code_res.json()["code"]

    link = redeem_link_code(
        db_session,
        clock,
        channel="telegram",
        channel_user_id="tg_12345",
        channel_chat_id="chat_12345",
        raw_code=code,
        channel_username="owner_telegram",
    )
    db_session.flush()

    # List shows active link for owner
    res = client_owner.get(f"/api/v1/workspaces/{ws.id}/channels/links", headers=owner_headers)
    assert res.status_code == 200
    links = res.json()
    assert len(links) == 1
    assert links[0]["id"] == str(link.id)
    assert links[0]["channel"] == "telegram"
    assert links[0]["channel_username"] == "owner_telegram"
    assert links[0]["status"] == "active"

    # Staff listing sees their own (currently empty)
    res_staff = client_staff.get(
        f"/api/v1/workspaces/{ws.id}/channels/links", headers=staff_headers
    )
    assert res_staff.status_code == 200
    assert res_staff.json() == []

    # Staff cannot unlink owner's link (FORBIDDEN)
    res_del_unauth = client_staff.delete(
        f"/api/v1/workspaces/{ws.id}/channels/links/{link.id}",
        headers=staff_headers,
    )
    assert res_del_unauth.status_code == 403
    assert res_del_unauth.json()["code"] == "FORBIDDEN"

    # Owner unlinks
    res_del = client_owner.delete(
        f"/api/v1/workspaces/{ws.id}/channels/links/{link.id}",
        headers=owner_headers,
    )
    assert res_del.status_code == 204

    # Now links list is empty
    res_after = client_owner.get(
        f"/api/v1/workspaces/{ws.id}/channels/links", headers=owner_headers
    )
    assert res_after.status_code == 200
    assert res_after.json() == []

    # Second delete returns 404 CHANNEL_LINK_NOT_FOUND
    res_del2 = client_owner.delete(
        f"/api/v1/workspaces/{ws.id}/channels/links/{link.id}",
        headers=owner_headers,
    )
    assert res_del2.status_code == 404
    assert res_del2.json()["code"] == "CHANNEL_LINK_NOT_FOUND"


def test_non_member_cannot_access_channel_routes(
    client: TestClient,
    db_session: Session,
) -> None:
    ws, _ = workspace_with_members(db_session)
    outsider = create_user(db_session, email="outsider@example.com")
    outsider_headers = login(client, outsider)

    # 404 on link-code
    res1 = client.post(
        f"/api/v1/workspaces/{ws.id}/channels/link-code",
        json={"channel": "telegram"},
        headers=outsider_headers,
    )
    assert res1.status_code == 404

    # 404 on links
    res2 = client.get(
        f"/api/v1/workspaces/{ws.id}/channels/links",
        headers=outsider_headers,
    )
    assert res2.status_code == 404

    # 404 on delete
    res3 = client.delete(
        f"/api/v1/workspaces/{ws.id}/channels/links/{uuid.uuid4()}",
        headers=outsider_headers,
    )
    assert res3.status_code == 404
