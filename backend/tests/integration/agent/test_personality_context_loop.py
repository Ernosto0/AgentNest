"""Persistent voice APIs and the actual coordinator context/repair path."""

import uuid

import pytest
from sqlalchemy import select

from app.agent.coordinator import claim, fresh, run_activation
from app.agent.models import AccountAgent, AgentSession, AgentThread
from app.agent.personality import Personality, PersonalityChange, change_personality
from app.agent.repository import add_event_and_wake
from app.agent.tools.broker import build_default_broker
from app.audit.models import AuditLog
from app.identity.models import Workspace
from tests.factories import knowledge_ctx, workspace_with_members
from tests.helpers.env import build_env
from tests.integration.agent.test_context_grounding import scenario
from tests.integration.agent.test_coordinator import deps, result
from tests.integration.agent.test_delegation import _account


def test_personality_api_versions_roles_audit_and_isolation(db_session, make_client, clock):
    env = build_env(db_session, make_client, clock)
    social, agent = _account(env)
    body = {"expected_version": 1, "personality": {"tone": "direct", "emoji": "sparse"}}
    path = f"/accounts/{social.id}/agent/personality"
    assert env.call(env.staff, "PATCH", path, json=body).status_code == 403
    changed = env.call(env.manager, "PATCH", path, json=body)
    assert changed.status_code == 200 and changed.json()["version"] == 2
    assert changed.json()["personality"]["tone"] == "direct"
    assert env.call(env.owner, "PATCH", path, json=body).status_code == 409
    assert env.call(env.staff, "GET", path).json()["version"] == 2
    assert (
        env.call(env.owner, "GET", f"/accounts/{uuid.uuid4()}/agent/personality").status_code == 404
    )
    assert (
        env.call(
            env.owner,
            "PATCH",
            path,
            json={
                "expected_version": 2,
                "personality": {"delegation": {"dm.send": "automatic"}},
            },
        ).status_code
        == 422
    )
    audit = db_session.scalar(
        select(AuditLog).where(AuditLog.action == "agent.personality_changed")
    )
    assert audit is not None and audit.actor_id == str(env.manager.user.id)
    db_session.refresh(agent)
    assert agent.state == "inactive" and agent.controller_mode == "legacy"


@pytest.mark.commits
def test_personality_changed_during_pending_step_fences_result(session_factory, clock):
    from tests.integration.agent.test_coordinator import seed

    workspace_id, thread_id = seed(session_factory, clock)
    runner = deps(session_factory, clock)
    captured = claim(runner, workspace_id, thread_id)
    with session_factory() as db:
        thread = db.get(AgentThread, thread_id)
        account = db.scalar(
            select(AccountAgent).where(AccountAgent.social_account_id == thread.social_account_id)
        )
        account.persona_version += 1
        db.commit()
    with session_factory() as db:
        assert fresh(db, runner, captured) is None
        db.commit()


@pytest.mark.commits
@pytest.mark.parametrize("repaired", [True, False])
def test_real_loop_uses_scoped_personality_turns_and_one_grounding_repair(
    session_factory, clock, repaired
):
    from app.integrations.llm.fake import FakeLLMProvider

    with session_factory() as db:
        context, workspace, message = scenario(db, clock)
        account = db.scalar(
            select(AccountAgent).where(AccountAgent.social_account_id == context.account_id)
        )
        account.state, account.controller_mode = "active", "agent"
        account.persona = {"tone": "direct", "emoji": "sparse"}
        account.persona_version = 4
        add_event_and_wake(
            db,
            workspace_id=workspace.id,
            account_id=context.account_id,
            thread_id=context.thread_id,
            kind="customer_message",
            source_kind="message",
            source_key=str(message.id),
            source_id=str(message.id),
            source_version=1,
            clock=clock,
        )
        db.commit()
    fake = FakeLLMProvider()
    for text in ["It costs 7000 TL", "Hello! How can I help?" if repaired else "It costs 9000 TL"]:
        fake.queue_step(
            result(
                "tool",
                tool_name="reply.validate",
                tool_arguments={
                    "template": text,
                    "language": "en",
                    "fact_sources": [],
                    "customer_clarification": None,
                },
            )
        )
    if repaired:
        fake.queue_step(result())
    run_activation(
        deps(session_factory, clock, fake), workspace.id, context.thread_id, build_default_broker()
    )
    assert len(fake.step_calls) == (3 if repaired else 2)
    user_data = fake.step_calls[0].messages[0].content
    assert message.text in user_data and '"persona_version": 4' in user_data
    assert '"tone": "direct"' in user_data and '"reply_language": "en"' in user_data
    assert fake.step_calls[1].observations[0].result["data"]["valid"] is False
    with session_factory() as db:
        goal = db.scalar(select(AgentSession))
        if repaired:
            assert goal.validation_failures == 1 and goal.status == "completed"
        else:
            assert goal.validation_failures == 2 and goal.outcome_code == "AGENT_GROUNDING_REJECTED"


def test_owner_manager_service_voice_change_does_not_grant_authority(db_session, clock):
    workspace, users = workspace_with_members(db_session, roles=("owner", "manager", "staff"))
    from tests.integration.agent.test_tools import _seed

    # Service checks the *current supplied membership context*, not a model-owned field.
    context = _seed(db_session)
    account = db_session.scalar(
        select(AccountAgent).where(AccountAgent.social_account_id == context.account_id)
    )
    other_workspace = db_session.get(Workspace, context.workspace.workspace_id)
    with pytest.raises(Exception, match="NOT_FOUND"):
        change_personality(
            db_session,
            clock,
            knowledge_ctx(workspace, users["owner"], "owner"),
            account.social_account_id,
            PersonalityChange(expected_version=1, personality=Personality()),
        )
    assert other_workspace.id != workspace.id
