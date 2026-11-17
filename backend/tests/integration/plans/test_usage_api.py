"""GET /workspaces/{id}/usage: who sees it, and what it says."""

from collections.abc import Callable
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.plans import service
from tests.factories import create_user, login
from tests.helpers.env import Env, build_env


@pytest.fixture
def env(db_session: Session, make_client: Callable[[], TestClient], clock: FrozenClock) -> Env:
    return build_env(db_session, make_client, clock)


def test_owner_and_manager_see_the_default_plan(env: Env) -> None:
    for role in (env.owner, env.manager):
        response = env.call(role, "GET", "/usage")
        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["plan"], body["status"], body["state"]) == ("growth", "trial", "normal")
        assert (body["monthly_quota"], body["quota"], body["quota_override"]) == (2500, 2500, None)
        assert (body["used"], body["grace_limit"]) == (0, 2750)
        assert body["period_end"] > body["period_start"]


def test_staff_may_not_see_it(env: Env) -> None:
    assert env.call(env.staff, "GET", "/usage").status_code == 403


def test_a_stranger_gets_404_and_nobody_gets_in_without_signing_in(
    env: Env, make_client: Callable[[], TestClient], db_session: Session
) -> None:
    stranger = create_user(db_session, display_name="Stranger")
    client = make_client()
    login(client, stranger)
    assert client.get(f"{env.base}/usage").status_code == 404
    assert make_client().get(f"{env.base}/usage").status_code == 401


def test_the_numbers_follow_the_counter_and_an_override(env: Env, clock: FrozenClock) -> None:
    row = service.get_plan(env.session, clock, env.workspace.id)
    row.quota_override = 100
    for i in range(85):
        service.consume(env.session, clock, env.workspace.id, f"draft-{i}")
    body = env.call(env.owner, "GET", "/usage").json()
    assert (body["quota"], body["monthly_quota"], body["quota_override"]) == (100, 2500, 100)
    assert (body["used"], body["grace_limit"], body["state"]) == (85, 110, "warning")
    for i in range(85, 120):
        service.consume(env.session, clock, env.workspace.id, f"draft-{i}")
    body = env.call(env.owner, "GET", "/usage").json()
    assert (body["used"], body["state"]) == (110, "paused")


def test_reading_the_usage_rolls_an_ended_period_over(env: Env, clock: FrozenClock) -> None:
    for i in range(5):
        service.consume(env.session, clock, env.workspace.id, f"draft-{i}")
    assert env.call(env.owner, "GET", "/usage").json()["used"] == 5
    row = service.get_plan(env.session, clock, env.workspace.id)
    row.period_end = clock.now() - timedelta(days=1)  # the period ended yesterday
    row.period_start = row.period_end - timedelta(days=30)
    body = env.call(env.owner, "GET", "/usage").json()
    assert body["used"] == 0
