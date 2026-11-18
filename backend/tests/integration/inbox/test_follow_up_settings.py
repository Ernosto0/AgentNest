import uuid

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from tests.integration.inbox.conftest import InboxEnv

BODY = {"enabled": True, "hours": 6, "text": {"tr": "", "en": ""}}


def test_get_defaults_and_put_preserves_settings(inbox: InboxEnv) -> None:
    env = inbox.env
    before = env.call(env.owner, "GET", "/follow-up-settings")
    assert before.status_code == 200
    assert before.json()["enabled"] is False
    assert before.json()["hours"] == 6
    assert before.json()["default_text"]["tr"]
    env.workspace.settings = {"daily_report_hour": 12}
    inbox.session.commit()
    body = {**BODY, "text": {"tr": "", "en": "Can we help further?"}}
    assert env.call(env.owner, "PUT", "/follow-up-settings", json=body).status_code == 200
    inbox.session.refresh(env.workspace)
    assert env.workspace.settings["daily_report_hour"] == 12
    audit = inbox.session.scalars(
        select(AuditLog).where(AuditLog.action == "follow_up.settings_changed")
    ).one()
    assert "Can we help" not in str(audit.__dict__)


@pytest.mark.parametrize("role", ["manager", "staff"])
def test_owner_only_write(inbox: InboxEnv, role: str) -> None:
    actor = getattr(inbox.env, role)
    assert inbox.env.call(actor, "GET", "/follow-up-settings").status_code == 200
    assert inbox.env.call(actor, "PUT", "/follow-up-settings", json=BODY).status_code == 403


@pytest.mark.parametrize(
    ("template", "code"),
    [
        ("500 TL", "LITERAL_VALUE"),
        ("Call +905321234567", "LITERAL_VALUE"),
        ("https://example.com", "LITERAL_VALUE"),
        ("{{fact:booking.missing}}", "UNKNOWN_FACT"),
    ],
)
def test_template_validation(inbox: InboxEnv, template: str, code: str) -> None:
    response = inbox.env.call(
        inbox.env.owner,
        "PUT",
        "/follow-up-settings",
        json={**BODY, "text": {"tr": template, "en": ""}},
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == code
    assert response.json()["errors"][0]["field"] == "text.tr"


@pytest.mark.parametrize("hours", [0, 21])
def test_hours_bounds(inbox: InboxEnv, hours: int) -> None:
    assert (
        inbox.env.call(
            inbox.env.owner, "PUT", "/follow-up-settings", json={**BODY, "hours": hours}
        ).status_code
        == 422
    )


def test_generic_patch_and_foreign_workspace(inbox: InboxEnv) -> None:
    env = inbox.env
    assert (
        env.call(env.owner, "PATCH", "", json={"settings": {"follow_up_enabled": True}}).status_code
        == 422
    )
    for method in ["GET", "PUT"]:
        response = env.owner.client.request(
            method,
            f"/api/v1/workspaces/{uuid.uuid4()}/follow-up-settings",
            headers=env.owner.headers,
            **({"json": BODY} if method == "PUT" else {}),
        )
        assert response.status_code == 404
