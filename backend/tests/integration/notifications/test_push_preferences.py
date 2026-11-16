"""F-01 part 2: per-user, per-category Web Push opt-in (API).

Proves: everything is off until the user switches it on, a user changes only their own choices,
only the categories sent change, unknown categories and fields are refused, state-changing calls
need the CSRF header, and a user outside the workspace gets a 404.
"""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.notifications.models import PushPreference
from tests.factories import add_member, create_user, create_workspace, login
from tests.helpers.env import Env

OFF = {"approvals": False, "questions": False, "failures": False}


def get(env: Env, role: str = "owner") -> Any:
    return env.call(getattr(env, role), "GET", "/push-subscriptions/preferences")


def put(env: Env, body: dict[str, Any], role: str = "owner") -> Any:
    return env.call(getattr(env, role), "PUT", "/push-subscriptions/preferences", json=body)


def test_everything_is_off_until_the_user_opts_in(env: Env) -> None:
    response = get(env)
    assert response.status_code == 200
    assert response.json() == OFF


def test_a_user_opts_in_per_category_and_only_those_sent_change(env: Env) -> None:
    assert put(env, {"approvals": True}).json() == {**OFF, "approvals": True}
    assert put(env, {"failures": True}).json() == {**OFF, "approvals": True, "failures": True}
    assert put(env, {"approvals": False}).json() == {**OFF, "failures": True}
    assert get(env).json() == {**OFF, "failures": True}
    assert put(env, {}).json() == {**OFF, "failures": True}  # nothing sent, nothing changed
    rows = env.session.scalars(select(PushPreference)).all()
    assert {(r.category, r.enabled) for r in rows} == {("approvals", False), ("failures", True)}


def test_each_member_has_their_own_choices(env: Env) -> None:
    put(env, {"questions": True}, role="owner")
    assert get(env, "manager").json() == OFF
    assert get(env, "staff").json() == OFF
    put(env, {"approvals": True}, role="manager")
    assert get(env, "owner").json() == {**OFF, "questions": True}
    assert get(env, "manager").json() == {**OFF, "approvals": True}


def test_unknown_categories_and_fields_are_refused(env: Env) -> None:
    for body in ({"everything": True}, {"approvals": "yes please", "x": 1}, {"approvals": 5}):
        assert put(env, body).status_code == 422
    assert get(env).json() == OFF


def test_a_state_changing_call_needs_the_csrf_header(env: Env) -> None:
    response = env.owner.client.put(
        f"{env.base}/push-subscriptions/preferences", json={"approvals": True}
    )
    assert response.status_code in (401, 403)
    assert get(env).json() == OFF


def test_someone_outside_the_workspace_gets_404(env: Env) -> None:
    other = create_workspace(env.session, name="Other", slug="other-prefs")
    stranger = create_user(env.session, display_name="Stranger")
    add_member(env.session, other, stranger, "owner")
    client = TestClient(env.owner.client.app, base_url="http://testserver")
    headers = login(client, stranger)
    url = f"{env.base}/push-subscriptions/preferences"
    assert client.get(url, headers=headers).status_code == 404
    assert client.put(url, json={"approvals": True}, headers=headers).status_code == 404
    assert get(env).json() == OFF
