"""Owner-only controller cutover API uses scoped IDs and version/idempotency fences."""

import uuid

from tests.helpers.env import build_env
from tests.integration.agent.test_delegation import _account
from tests.integration.agent.test_tools import _seed


def test_activation_owner_version_idempotency_and_existing_foreign_account(
    db_session, make_client, clock
):
    env = build_env(db_session, make_client, clock)
    social, account = _account(env)
    path = f"/accounts/{social.id}/agent/activate"
    body = {
        "expected_config_version": account.config_version,
        "client_request_id": str(uuid.uuid4()),
        "mode": "agent",
    }
    assert env.call(env.manager, "POST", path, json=body).status_code == 403
    first = env.call(env.owner, "POST", path, json=body)
    assert first.status_code == 200 and first.json()["controller_mode"] == "agent"
    assert env.call(env.owner, "POST", path, json=body).json() == first.json()
    assert env.call(env.owner, "POST", path, json=body | {"mode": "legacy"}).status_code == 409
    foreign = _seed(db_session)
    assert (
        env.call(
            env.owner, "POST", f"/accounts/{foreign.account_id}/agent/activate", json=body
        ).status_code
        == 404
    )
    paused = env.call(
        env.owner,
        "POST",
        f"/accounts/{social.id}/agent/pause",
        json={"expected_config_version": first.json()["config_version"]},
    )
    assert paused.status_code == 200 and paused.json()["state"] == "paused"
    assert paused.json()["controller_epoch"] > first.json()["controller_epoch"]
    rollback = env.call(
        env.owner,
        "POST",
        path,
        json={
            "expected_config_version": paused.json()["config_version"],
            "client_request_id": str(uuid.uuid4()),
            "mode": "legacy",
        },
    )
    assert rollback.status_code == 200 and rollback.json()["state"] == "inactive"
    assert rollback.json()["controller_epoch"] > paused.json()["controller_epoch"]
