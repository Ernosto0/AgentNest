"""Session 15 work projections, control and report evolution boundaries."""

import uuid
from collections.abc import Callable
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.models import AgentThread
from app.core.clock import FrozenClock
from app.reporting.definitions import BY_KEY, DEFINITIONS_VERSION
from app.reporting.models import DailyReport
from tests.helpers.env import Env, build_env
from tests.integration.agent.test_delegation import _account, _action


@pytest.fixture
def env(db_session: Session, make_client: Callable[[], TestClient], clock: FrozenClock) -> Env:
    return build_env(db_session, make_client, clock)


def test_scoped_public_thread_never_projects_private_identity(env: Env) -> None:
    social, agent = _account(env)
    action = _action(env, social, agent, "comment.hide")
    path = f"/accounts/{social.id}/agent/threads"
    for member in (env.owner, env.manager, env.staff):
        page = env.call(member, "GET", path)
        assert page.status_code == 200
        assert page.json()["items"][0]["customer_id"] is None
        assert page.json()["items"][0]["actions"][0]["status"] == "proposed"
    assert env.call(env.owner, "GET", f"{path}/{uuid.uuid4()}").status_code == 404
    assert env.call(env.owner, "GET", f"{path}?cursor={uuid.uuid4()}").status_code == 404
    social.status = "disconnected"
    env.session.flush()
    other, _ = _account(env)
    assert (
        env.call(
            env.owner, "GET", f"/accounts/{other.id}/agent/threads/{action.thread_id}"
        ).status_code
        == 404
    )


def test_comment_takeover_is_versioned_and_release_requires_active_controller(env: Env) -> None:
    social, agent = _account(env)
    action = _action(env, social, agent, "comment.hide")
    thread = env.session.get(AgentThread, action.thread_id)
    assert thread is not None
    path = f"/accounts/{social.id}/agent/threads/{thread.id}/control"
    body = {
        "expected_version": thread.thread_version,
        "handling_mode": "human",
        "client_request_id": str(uuid.uuid4()),
    }
    response = env.call(env.staff, "POST", path, json=body)
    assert response.status_code == 200
    assert response.json()["handling_mode"] == "human"
    assert response.json()["customer_id"] is None
    assert env.call(env.staff, "POST", path, json=body).status_code == 200
    body["client_request_id"] = str(uuid.uuid4())
    assert env.call(env.staff, "POST", path, json=body).status_code == 409
    release = {
        "expected_version": response.json()["version"],
        "handling_mode": "agent",
        "client_request_id": str(uuid.uuid4()),
    }
    assert env.call(env.owner, "POST", path, json=release).status_code == 409
    agent.controller_mode, agent.state = "agent", "active"
    env.session.flush()
    assert env.call(env.owner, "POST", path, json=release).status_code == 200


def test_action_preview_scope_and_exact_version(env: Env) -> None:
    social, agent = _account(env)
    action = _action(env, social, agent, "comment.hide")
    response = env.call(env.owner, "GET", f"/agent-actions/{action.id}")
    assert response.status_code == 200
    assert response.json()["payload_hash"] == action.payload_hash
    assert response.json()["version"] == action.version
    assert response.json()["account_id"] == str(social.id)
    assert env.call(env.owner, "GET", f"/agent-actions/{uuid.uuid4()}").status_code == 404


def test_old_snapshot_never_gains_new_metric_keys(env: Env) -> None:
    day = (env.clock.now() - timedelta(days=1)).date()
    snapshot = DailyReport(
        workspace_id=env.workspace.id,
        local_date=day,
        revision=1,
        timezone=env.workspace.timezone,
        period_start=env.clock.now() - timedelta(days=1),
        period_end=env.clock.now() - timedelta(hours=1),
        definitions_version="1",
        generated_at=env.clock.now(),
        metrics={"inbound_messages": {"value": 7}},
        has_simulated_data=True,
        evidence_complete=True,
    )
    env.session.add(snapshot)
    env.session.flush()
    response = env.call(env.owner, "GET", f"/reports/daily?date={day}&snapshot_id={snapshot.id}")
    assert response.status_code == 200
    assert response.json()["definitions_version"] == "1"
    assert response.json()["metrics"][0]["value"] == 7
    assert all(not m["key"].startswith("agent_") for m in response.json()["metrics"])
    assert (
        env.call(
            env.owner,
            "GET",
            f"/reports/daily/{day}/metrics/agent_automatic_v1?snapshot_id={snapshot.id}",
        ).status_code
        == 404
    )
    assert DEFINITIONS_VERSION == "2"
    assert "agent_unknown_now_v1" in BY_KEY
    assert env.session.scalar(select(DailyReport).where(DailyReport.id == snapshot.id)).metrics == {
        "inbound_messages": {"value": 7}
    }


@pytest.mark.parametrize(
    "approval_action", ["comments.approve", "content.prepare", "content.schedule", "content.cancel"]
)
def test_agent_approval_actions_serialize_and_filter_at_real_api(
    env: Env, approval_action: str
) -> None:
    from app.approvals import service as approvals

    social, agent = _account(env)
    action = _action(env, social, agent, "comment.hide")
    approval = approvals.request(
        env.session,
        env.clock,
        env.ctx(env.owner),
        kind="authorization",
        action=approval_action,
        subject_type="agent_action",
        subject_id=action.id,
        subject_version=action.version,
        payload={"action_id": str(action.id)},
        summary={"action_type": action.action_type, "payload_hash": action.payload_hash},
        required_permission="comments.approve",
        expires_at=env.clock.now() + timedelta(hours=1),
        is_simulated=True,
    )
    action.approval_id = approval.id
    action.status = "waiting_approval"
    env.session.flush()
    detail = env.call(env.owner, "GET", f"/approvals/{approval.id}")
    assert detail.status_code == 200
    assert detail.json()["action"] == approval_action
    page = env.call(env.owner, "GET", f"/approvals?action={approval_action}")
    assert page.status_code == 200
    assert page.json()["items"][0]["id"] == str(approval.id)
