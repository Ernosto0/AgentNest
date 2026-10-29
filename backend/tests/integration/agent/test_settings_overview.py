"""Settings projection and goal editing retain isolation/version/role contracts."""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agent.context import assemble
from app.agent.models import AgentThread
from app.agent.tools.broker import BrokerContext
from app.core.clock import FrozenClock
from app.integrations.instagram.models import SocialAccount
from tests.factories import create_workspace
from tests.helpers.env import Env, build_env
from tests.integration.agent.test_delegation import _account


@pytest.fixture
def env(db_session: Session, make_client: Callable[[], TestClient], clock: FrozenClock) -> Env:
    return build_env(db_session, make_client, clock)


def test_overview_is_body_free_and_scoped(env: Env) -> None:
    social, agent = _account(env)
    base = f"/accounts/{social.id}/agent"
    for role in (env.owner, env.manager, env.staff):
        response = env.call(role, "GET", base)
        assert response.status_code == 200
        assert response.json() == {
            "state": "inactive",
            "controller_mode": "legacy",
            "config_version": 1,
            "controller_epoch": 0,
            "is_simulated": True,
            "session_counts": {},
            "pending_questions": 0,
            "pending_approvals": 0,
            "recent_actions": [],
        }
    assert env.call(env.owner, "GET", f"/accounts/{uuid.uuid4()}/agent").status_code == 404
    foreign_workspace = create_workspace(env.session, slug="foreign-agent-overview")
    foreign = SocialAccount(
        workspace_id=foreign_workspace.id,
        provider_kind="mock",
        external_account_id=uuid.uuid4().hex,
    )
    env.session.add(foreign)
    env.session.flush()
    assert env.call(env.owner, "GET", f"/accounts/{foreign.id}/agent").status_code == 404
    assert (
        env.call(env.owner, "GET", f"/accounts/{foreign.id}/agent/personality").status_code == 404
    )
    agent.goals = {"control_request": {"id": "private-control-id"}}
    env.session.flush()
    assert "private-control-id" not in env.call(env.owner, "GET", base).text


def test_goals_and_personality_share_optimistic_version(env: Env) -> None:
    social, agent = _account(env)
    path = f"/accounts/{social.id}/agent/personality"
    body = {"expected_version": 1, "personality": {}, "goals": "  Help customers  "}
    assert env.call(env.staff, "PATCH", path, json=body).status_code == 403
    response = env.call(env.manager, "PATCH", path, json=body)
    assert response.status_code == 200
    assert response.json()["goals"] == "Help customers"
    assert response.json()["version"] == 2
    assert env.call(env.owner, "PATCH", path, json=body).status_code == 409
    assert env.call(env.owner, "GET", path).json()["goals"] == "Help customers"
    assert agent.controller_mode == "legacy"
    thread = AgentThread(
        workspace_id=env.workspace.id,
        social_account_id=social.id,
        surface="comment",
        source_ref=str(uuid.uuid4()),
    )
    env.session.add(thread)
    env.session.flush()
    model = assemble(
        env.session,
        env.clock,
        BrokerContext(env.ctx(env.manager), social.id, thread.id, "comment", "customer"),
    )
    assert '"goal_instructions": "Help customers"' in model.messages[0].content
    assert "Help customers" not in model.system
    body["expected_version"] = 2
    body["goals"] = "x" * 501
    assert env.call(env.owner, "PATCH", path, json=body).status_code == 422
