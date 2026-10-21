"""``GET /workspaces/{ws}/system-health`` (api-design.md section 2.8, plan H13): counts and codes
from the workspace's own tables, plus the labelled system-wide signature-failure count."""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI

from app.ai.models import AgentRun
from app.audit import service as audit
from app.inbox.models import InboundEvent
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.operations.models import Operation
from tests.factories import workspace_with_members
from tests.helpers.content import connect_account
from tests.helpers.env import Env

PRICES = '{"model-a": {"input_per_mtok": 2.0, "output_per_mtok": 10.0}}'
TOP_KEYS = {"generated_at", "window_hours", "accounts", "operations", "jobs", "webhooks", "ai"}


def _operation(env: Env, account: SocialAccount, workspace_id: uuid.UUID, **fields: Any) -> None:
    values: dict[str, Any] = {
        "workspace_id": workspace_id,
        "operation_type": "send_reply",
        "idempotency_key": f"k:{uuid.uuid4()}",
        "subject_type": "reply_draft",
        "subject_id": uuid.uuid4(),
        "social_account_id": account.id,
        "provider_kind": "mock",
        "status": "succeeded",
        "attempts": 1,
        "is_simulated": True,
        "created_at": env.clock.now() - timedelta(hours=1),
        "completed_at": env.clock.now() - timedelta(minutes=50),
    }
    env.session.add(Operation(**{**values, **fields}))


def _job(env: Env, workspace_id: uuid.UUID, **fields: Any) -> None:
    values: dict[str, Any] = {
        "workspace_id": workspace_id,
        "job_type": "send_reply",
        "payload": {},
        "status": "queued",
        "run_at": env.clock.now(),
        "max_attempts": 3,
    }
    env.session.add(Job(**{**values, **fields}))


def _event(env: Env, workspace_id: uuid.UUID, status: str, **fields: Any) -> None:
    values: dict[str, Any] = {
        "workspace_id": workspace_id,
        "provider_kind": "mock",
        "dedup_key": f"d:{uuid.uuid4()}",
        "event_type": "message",
        "status": status,
        "correlation_id": uuid.uuid4(),
        "is_simulated": True,
        "received_at": env.clock.now() - timedelta(hours=2),
    }
    env.session.add(InboundEvent(**{**values, **fields}))


def _run(env: Env, workspace_id: uuid.UUID, **fields: Any) -> None:
    values: dict[str, Any] = {
        "workspace_id": workspace_id,
        "task": "draft_reply",
        "model": "model-a",
        "status": "succeeded",
        "input_tokens": 1_000_000,
        "output_tokens": 100_000,
        "created_at": env.clock.now() - timedelta(hours=3),
    }
    env.session.add(AgentRun(**{**values, **fields}))


def _signature_failure(env: Env) -> None:
    audit.record(
        env.session,
        None,
        "webhook.signature_invalid",
        None,
        None,
        {"provider_kind": "mock"},
        is_simulated=True,
        clock=env.clock,
    )


def _get(env: Env, role: str = "owner") -> Any:
    return env.call(getattr(env, role), "GET", "/system-health")


def test_the_shape_of_an_empty_workspace(env: Env) -> None:
    body = _get(env).json()
    assert set(body) == TOP_KEYS
    assert body["window_hours"] == 24
    assert body["accounts"] == []
    assert body["operations"] == {"counts": [], "latest_failures": []}
    assert body["jobs"] == {"queued": 0, "oldest_queued_age_seconds": None, "dead_24h": 0}
    assert body["webhooks"] == {
        "received_24h": 0,
        "ignored_24h": 0,
        "failed_24h": 0,
        "signature_failures_24h_system_wide": 0,
    }
    assert body["ai"]["total"] == 0 and body["ai"]["failure_rate"] == 0.0
    assert body["ai"]["estimated_cost_usd"] is None
    assert body["ai"]["budget_limit"] == 500


def test_the_accounts_section_shows_status_error_and_degraded_until(env: Env) -> None:
    until = env.clock.now() + timedelta(minutes=10)
    connect_account(
        env, status="degraded", last_error_code="PROVIDER_UNAVAILABLE", degraded_until=until
    )
    env.session.commit()
    [account] = _get(env).json()["accounts"]
    assert account["username"] == "golkent.demo"
    assert account["status"] == "degraded"
    assert account["last_error_code"] == "PROVIDER_UNAVAILABLE"
    assert account["degraded_until"] is not None
    assert account["is_simulated"] is True
    assert not {"access_token", "token", "token_ciphertext"} & set(account)


def test_operation_numbers_equal_the_fixture_counts(env: Env) -> None:
    account = connect_account(env)
    wid = env.workspace.id
    old = env.clock.now() - timedelta(hours=30)
    for _ in range(3):
        _operation(env, account, wid)
    _operation(env, account, wid, status="failed", last_error_code="RATE_LIMITED")
    _operation(
        env,
        account,
        wid,
        status="outcome_unknown",
        operation_type="publish_content",
        subject_type="content_item",
        completed_at=None,
    )
    _operation(env, account, wid, created_at=old, completed_at=old)  # not counted
    env.session.commit()

    ops = _get(env).json()["operations"]
    counts = {(c["type"], c["status"]): c["count"] for c in ops["counts"]}
    assert counts == {
        ("send_reply", "succeeded"): 3,
        ("send_reply", "failed"): 1,
        ("publish_content", "outcome_unknown"): 1,
    }
    failures = {f["status"]: f for f in ops["latest_failures"]}
    assert set(failures) == {"failed", "outcome_unknown"}
    assert failures["failed"]["last_error_code"] == "RATE_LIMITED"
    assert failures["failed"]["is_simulated"] is True


def test_only_the_five_latest_failures_are_listed_newest_first(env: Env) -> None:
    account = connect_account(env)
    now = env.clock.now()
    for minutes in range(7):
        _operation(
            env,
            account,
            env.workspace.id,
            status="failed",
            last_error_code="SEND_FAILED",
            completed_at=now - timedelta(minutes=minutes),
        )
    env.session.commit()
    failures = _get(env).json()["operations"]["latest_failures"]
    assert len(failures) == 5
    times = [f["occurred_at"] for f in failures]
    assert times == sorted(times, reverse=True)


def test_job_numbers_equal_the_fixture_counts(env: Env) -> None:
    now = env.clock.now()
    wid = env.workspace.id
    _job(env, wid, run_at=now - timedelta(minutes=5))
    _job(env, wid, run_at=now - timedelta(seconds=90))
    _job(env, wid, status="running", run_at=now - timedelta(hours=1))
    _job(env, wid, status="dead", finished_at=now - timedelta(hours=2))
    _job(env, wid, status="dead", finished_at=now - timedelta(hours=2))
    _job(env, wid, status="dead", finished_at=now - timedelta(hours=40))  # outside 24 h
    env.session.commit()
    assert _get(env).json()["jobs"] == {
        "queued": 2,
        "oldest_queued_age_seconds": 300,
        "dead_24h": 2,
    }


def test_webhook_numbers_and_the_system_wide_signature_counter(env: Env) -> None:
    """AC-G4: the invalid-signature counter is visible in the health response."""
    wid = env.workspace.id
    for status in ("received", "processed", "processed", "ignored", "failed", "failed"):
        _event(env, wid, status)
    _event(env, wid, "failed", received_at=env.clock.now() - timedelta(hours=30))
    for _ in range(3):
        _signature_failure(env)
    env.session.commit()

    webhooks = _get(env).json()["webhooks"]
    assert webhooks == {
        "received_24h": 6,
        "ignored_24h": 1,
        "failed_24h": 2,
        "signature_failures_24h_system_wide": 3,
    }
    env.clock.advance(hours=25)
    assert _get(env).json()["webhooks"]["signature_failures_24h_system_wide"] == 0


def test_ai_numbers_and_the_cost_from_the_price_table(env: Env, app: FastAPI) -> None:
    app.state.settings = app.state.settings.model_copy(
        update={"llm_price_table": PRICES, "llm_max_calls_per_workspace_per_day": 40}
    )
    wid = env.workspace.id
    _run(env, wid)
    _run(env, wid, task="interpret_command")
    _run(env, wid, status="failed", error_code="LLM_TIMEOUT", input_tokens=None)
    _run(env, wid, model="unpriced-model")
    _run(env, wid, status="failed", error_code="LLM_BUDGET_EXCEEDED")
    _run(env, wid, created_at=env.clock.now() - timedelta(hours=30))  # outside 24 h
    env.session.commit()

    ai = _get(env).json()["ai"]
    runs = {(r["task"], r["status"]): r["count"] for r in ai["runs"]}
    assert runs == {
        ("draft_reply", "succeeded"): 2,
        ("interpret_command", "succeeded"): 1,
        ("draft_reply", "failed"): 2,
    }
    assert (ai["total"], ai["failed"], ai["failure_rate"]) == (5, 2, 0.4)
    assert ai["input_units"] == 4_000_000 and ai["output_units"] == 500_000
    # model-a: 3M input tokens and 0.4M output tokens = 6 + 4 USD; the unpriced model adds nothing.
    assert ai["estimated_cost_usd"] == pytest.approx(10.0)
    assert ai["budget_limit"] == 40
    assert ai["budget_used"] == 4  # the run that was refused for budget does not count


def test_no_price_table_means_no_cost_estimate(env: Env) -> None:
    _run(env, env.workspace.id)
    env.session.commit()
    ai = _get(env).json()["ai"]
    assert ai["input_units"] == 1_000_000 and ai["estimated_cost_usd"] is None


def test_the_manager_may_read_it_and_staff_may_not(env: Env) -> None:
    assert _get(env, "manager").status_code == 200
    denied = _get(env, "staff")
    assert denied.status_code == 403 and denied.json()["code"] == "FORBIDDEN"


def test_the_response_carries_no_payload_or_text(env: Env) -> None:
    account = connect_account(env)
    _operation(
        env,
        account,
        env.workspace.id,
        status="failed",
        last_error_code="SEND_FAILED",
        last_error_detail="provider said: token SECRET-123",
        provider_ref={"recipient_id": "customer-123"},
    )
    _event(env, env.workspace.id, "failed", payload={"text": "hello customer-123"})
    _job(env, env.workspace.id, payload={"conversation": "customer-123"})
    env.session.commit()
    text = _get(env).text
    for leaked in ("SECRET-123", "customer-123", "provider_ref", "payload", "idempotency"):
        assert leaked not in text


def test_another_workspaces_records_are_not_counted(env: Env) -> None:
    other, _ = workspace_with_members(env.session, roles=("owner",), slug="other")
    foreign_account = SocialAccount(
        workspace_id=other.id,
        platform="instagram",
        provider_kind="mock",
        external_account_id="mock-other",
        username="other.demo",
        status="connected",
        capabilities={},
    )
    env.session.add(foreign_account)
    env.session.flush()
    _operation(env, foreign_account, other.id, status="failed", last_error_code="X")
    _job(env, other.id)
    _event(env, other.id, "failed")
    _run(env, other.id)
    env.session.commit()

    body = _get(env).json()
    assert body["accounts"] == []
    assert body["operations"] == {"counts": [], "latest_failures": []}
    assert body["jobs"]["queued"] == 0
    assert body["webhooks"]["received_24h"] == 0
    assert body["ai"]["total"] == 0 and body["ai"]["input_units"] == 0

    foreign = env.owner.client.get(
        f"/api/v1/workspaces/{other.id}/system-health", headers=env.owner.headers
    )
    assert foreign.status_code == 404 and foreign.json()["code"] == "NOT_FOUND"
