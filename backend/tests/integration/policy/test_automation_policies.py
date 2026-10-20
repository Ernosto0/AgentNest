"""P4-06: the automation policy API. Defaults, the readiness gate for `auto`, the review stamp
(an explicit step, server clock, once), permissions and audit."""

import pytest

from app.audit.service import list_entries
from app.integrations.instagram.models import SocialAccount
from tests.helpers.env import Env
from tests.helpers.gym import seed_gym_facts

URL = "/automation-policies"
ALL_CLASSES = {
    "reply.hours",
    "reply.location_contact",
    "reply.pricing",
    "reply.services",
    "reply.booking",
    "reply.promotions",
    "reply.general_faq",
    "content.publish",
}


def modes(response_json: dict) -> dict[str, str]:  # type: ignore[type-arg]
    return {i["action_class"]: i["mode"] for i in response_json["items"]}


def make_ready(env: Env) -> None:
    """Everything for `ready` except the review, which is a separate explicit step."""
    seed_gym_facts(env.session, env.workspace, env.clock)
    env.session.add(
        SocialAccount(
            workspace_id=env.workspace.id,
            provider_kind="mock",
            external_account_id="mock-1",
            status="connected",
        )
    )
    env.session.commit()


def test_every_class_defaults_to_approval(env: Env) -> None:
    response = env.call(env.owner, "GET", URL)
    assert response.status_code == 200
    body = response.json()
    assert set(modes(body)) == ALL_CLASSES
    assert set(modes(body).values()) == {"approval"}
    assert body["reviewed_at"] is None
    assert body["auto_allowed"] is False


def test_the_owner_saves_policies_and_saving_does_not_review(env: Env) -> None:
    env.clock.advance(hours=2)
    response = env.call(
        env.owner,
        "PUT",
        URL,
        json={
            "items": [
                {"action_class": "reply.hours", "mode": "off"},
                {"action_class": "reply.pricing", "mode": "approval"},
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert modes(body)["reply.hours"] == "off"
    assert modes(body)["reply.services"] == "approval"  # untouched classes keep the default
    assert body["reviewed_at"] is None
    assert modes(env.call(env.staff, "GET", URL).json())["reply.hours"] == "off"

    actions = [e.action for e in list_entries(env.session, workspace_id=env.workspace.id)]
    assert "policy.updated" in actions and "policy.reviewed" not in actions
    assert env.call(env.owner, "GET", URL).json()["reviewed_at"] is None


def test_the_review_stamps_once_with_the_server_clock_and_audits_once(env: Env) -> None:
    env.clock.advance(hours=2)
    response = env.call(env.owner, "POST", f"{URL}/review")
    assert response.status_code == 200, response.text
    first = response.json()["reviewed_at"]
    assert first == "2026-01-15T14:00:00+00:00"  # server clock (INV-19)
    assert env.call(env.staff, "GET", URL).json()["reviewed_at"] == first

    env.clock.advance(days=1)
    again = env.call(env.owner, "POST", f"{URL}/review")
    assert again.status_code == 200 and again.json()["reviewed_at"] == first
    env.call(
        env.owner, "PUT", URL, json={"items": [{"action_class": "reply.hours", "mode": "off"}]}
    )
    assert env.call(env.owner, "GET", URL).json()["reviewed_at"] == first

    entries = list_entries(env.session, workspace_id=env.workspace.id, action="policy.reviewed")
    assert len(entries) == 1


@pytest.mark.parametrize("role", ["manager", "staff"])
def test_only_the_owner_may_review(env: Env, role: str) -> None:
    assert env.call(getattr(env, role), "POST", f"{URL}/review").status_code == 403
    assert env.call(env.owner, "GET", URL).json()["reviewed_at"] is None
    assert list_entries(env.session, workspace_id=env.workspace.id, action="policy.reviewed") == []


def test_reviewing_another_workspace_is_a_404(env: Env) -> None:
    from tests.factories import create_workspace

    other = create_workspace(env.session, name="Other")
    response = env.owner.client.post(
        f"/api/v1/workspaces/{other.id}{URL}/review", headers=env.owner.headers
    )
    assert response.status_code == 404


def test_the_review_completes_readiness(env: Env) -> None:
    make_ready(env)
    assert env.call(env.owner, "GET", URL).json()["readiness_level"] == "ready_for_drafts"
    body = env.call(env.owner, "POST", f"{URL}/review").json()
    assert body["readiness_level"] == "ready"


def test_auto_is_refused_until_the_workspace_is_ready(env: Env) -> None:
    response = env.call(
        env.owner, "PUT", URL, json={"items": [{"action_class": "reply.hours", "mode": "auto"}]}
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "READINESS_NOT_READY"
    assert modes(env.call(env.owner, "GET", URL).json())["reply.hours"] == "approval"


def test_auto_is_allowed_once_everything_else_for_ready_is_in_place(env: Env) -> None:
    make_ready(env)
    assert env.call(env.owner, "GET", URL).json()["auto_allowed"] is True
    response = env.call(
        env.owner, "PUT", URL, json={"items": [{"action_class": "reply.hours", "mode": "auto"}]}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert modes(body)["reply.hours"] == "auto"
    assert body["readiness_level"] == "ready_for_drafts"  # still waiting for the review


def test_a_disconnected_account_takes_auto_away_again(env: Env) -> None:
    make_ready(env)
    account = env.session.query(SocialAccount).one()
    account.status = "disconnected"
    env.session.commit()
    response = env.call(
        env.owner, "PUT", URL, json={"items": [{"action_class": "reply.hours", "mode": "auto"}]}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("role", ["manager", "staff"])
def test_only_the_owner_manages_automation(env: Env, role: str) -> None:
    response = env.call(
        getattr(env, role),
        "PUT",
        URL,
        json={"items": [{"action_class": "reply.hours", "mode": "approval"}]},
    )
    assert response.status_code == 403
    assert env.call(getattr(env, role), "GET", URL).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"items": []},
        {"items": [{"action_class": "reply.unknown", "mode": "auto"}]},
        {"items": [{"action_class": "reply.hours", "mode": "sometimes"}]},
        {"items": [{"action_class": "reply.hours", "mode": "approval", "extra": 1}]},
        {"items": [{"action_class": "reply.hours", "mode": "approval"}] * 2},
        {"nothing": True},
    ],
)
def test_invalid_bodies_are_rejected(env: Env, body: dict) -> None:  # type: ignore[type-arg]
    assert env.call(env.owner, "PUT", URL, json=body).status_code == 422
    assert list_entries(env.session, workspace_id=env.workspace.id, action="policy.reviewed") == []


def test_policies_belong_to_their_workspace(env: Env) -> None:
    from tests.factories import create_workspace

    other = create_workspace(env.session, name="Other")
    response = env.owner.client.get(f"/api/v1/workspaces/{other.id}{URL}")
    assert response.status_code == 404
