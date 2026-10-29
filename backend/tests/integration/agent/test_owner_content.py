"""Session 13: durable member authority and exact content effects, through the broker."""

import uuid

import pytest
from sqlalchemy import func, select

from app.agent import delegation, owner_tasks
from app.agent.coordinator import claim, run_activation
from app.agent.models import AccountAgent, AgentAction, AgentEvent, AgentSession
from app.agent.tools.broker import BrokerContext, build_default_broker
from app.ai.runner import RunnerDeps
from app.approvals import service as approvals
from app.approvals.models import Approval
from app.content import service
from app.content.models import ContentItem
from app.core.errors import AppError
from app.identity.models import WorkspaceMember
from app.integrations.llm.base import LLMUsage
from app.integrations.llm.fake import FakeLLMProvider
from app.integrations.llm.steps import LLMStepResult
from tests.helpers.content import connect_account, make_media, submittable_item
from tests.helpers.env import build_env


@pytest.fixture
def setup(db_session, make_client, clock, settings):
    env = build_env(db_session, make_client, clock)
    social = connect_account(env)
    agent = db_session.scalar(
        select(AccountAgent).where(AccountAgent.social_account_id == social.id)
    )
    actions = {name: delegation.ActionRule(mode="off") for name in delegation.ACTIONS}
    for name in ("content.prepare", "content.schedule", "content.publish", "content.cancel"):
        actions[name] = delegation.ActionRule(mode="automatic", sources=frozenset({"owner_task"}))
    delegation.apply(
        db_session,
        clock,
        env.ctx(env.owner),
        social.id,
        delegation.DelegationChange(
            expected_config_version=agent.config_version,
            client_request_id=uuid.uuid4(),
            policy=delegation.DelegationPolicy(actions=actions),
        ),
    )
    agent.state, agent.controller_mode = "active", "agent"
    db_session.commit()
    return env, social, agent


def task_context(setup, role="owner"):
    env, social, _ = setup
    ctx = env.ctx(getattr(env, role))
    task = owner_tasks.submit(
        env.session,
        env.clock,
        ctx,
        social.id,
        "Prepare and schedule an existing image",
        uuid.uuid4(),
    )
    goal = AgentSession(
        workspace_id=env.workspace.id,
        thread_id=task.thread_id,
        initiating_event_cursor=1,
        goal_key=f"task:{task.id}",
        status="running",
    )
    env.session.add(goal)
    env.session.flush()
    return task, BrokerContext(ctx, social.id, task.thread_id, "owner_task", "owner_task")


def tool(setup, ctx, name, **args):
    env, _, _ = setup
    return build_default_broker().dispatch(
        env.session, env.clock, ctx, name=name, version="v1", arguments=args
    )


def read(setup, ctx, kind="content"):
    return tool(setup, ctx, "content.read", kind=kind, cursor=None, limit=10)


def change_mode(setup, name, mode):
    env, social, agent = setup
    current = delegation.current_delegation(env.session, env.workspace.id, social.id)
    policy = delegation.DelegationPolicy.model_validate(current.policy)
    policy.actions[name] = delegation.ActionRule(mode=mode, sources=frozenset({"owner_task"}))
    delegation.apply(
        env.session,
        env.clock,
        env.ctx(env.owner),
        social.id,
        delegation.DelegationChange(
            expected_config_version=agent.config_version,
            expected_delegation_version=current.version,
            client_request_id=uuid.uuid4(),
            policy=policy,
        ),
    )
    env.session.flush()


def decide(setup, action_id):
    env, _, _ = setup
    action = env.session.get(AgentAction, uuid.UUID(action_id))
    approval = env.session.get(Approval, action.approval_id)
    return approvals.decide(
        env.session,
        env.clock,
        env.ctx(env.owner),
        approval.id,
        decision="approve",
        payload_hash=approval.payload_hash,
    )


def test_task_intake_dedup_requester_and_foreign_account(setup):
    env, social, agent = setup
    request_id = uuid.uuid4()
    path = f"/accounts/{social.id}/agent/tasks"
    response = env.call(
        env.owner,
        "POST",
        path,
        json={"text": "Prepare a post", "client_request_id": str(request_id)},
    )
    assert response.status_code == 202
    task_id = response.json()["id"]
    agent.state = "paused"
    env.session.flush()
    duplicate = env.call(
        env.owner,
        "POST",
        path,
        json={"text": "Prepare a post", "client_request_id": str(request_id)},
    )
    assert duplicate.json()["id"] == task_id
    assert (
        env.call(
            env.owner,
            "POST",
            path,
            json={"text": "Different", "client_request_id": str(request_id)},
        ).status_code
        == 409
    )
    assert env.call(env.staff, "GET", f"{path}/{task_id}").status_code == 404
    assert env.call(env.owner, "GET", f"/accounts/{uuid.uuid4()}/agent/tasks").status_code == 404
    assert env.session.scalar(select(func.count(AgentEvent.id))) == 1


def test_task_pagination(setup):
    env, social, _ = setup
    for _ in range(3):
        owner_tasks.submit(
            env.session, env.clock, env.ctx(env.owner), social.id, "Hello", uuid.uuid4()
        )
    path = f"/accounts/{social.id}/agent/tasks"
    first = env.call(env.owner, "GET", path, params={"limit": 2}).json()
    second = env.call(
        env.owner, "GET", path, params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert not {row["id"] for row in first["items"]} & {row["id"] for row in second["items"]}


@pytest.mark.parametrize("mode", ["automatic", "ask", "off"])
def test_schedule_requires_independent_publication_delegation(setup, mode):
    env, _, _ = setup
    change_mode(setup, "content.publish", mode)
    _, ctx = task_context(setup)
    item = submittable_item(env)
    read(setup, ctx)
    response = tool(
        setup,
        ctx,
        "content.schedule",
        content_id=str(item.id),
        expected_version=1,
        local_date="2026-01-15",
        local_time="19:00",
    )
    assert response.ok, response
    assert (
        response.data["status"]
        == {"automatic": "queued", "ask": "waiting_approval", "off": "cancelled"}[mode]
    )
    if mode == "automatic":
        assert item.status == "scheduled" and item.scheduled_at.hour == 16
        assert response.data["content_status"] == "scheduled"
        assert item.origin == "agent"
        action = env.session.get(AgentAction, item.agent_action_id)
        assert (
            action.policy_grant
            and env.session.get(Approval, item.approval_id).decision_channel == "policy"
        )
    elif mode == "ask":
        assert item.status == "draft"
        decide(setup, response.data["action_id"])
        assert item.status == "scheduled"
    else:
        assert item.status == "draft" and item.approval_id is None


@pytest.mark.parametrize("name", ["content.prepare", "content.cancel", "content.schedule"])
def test_each_content_effect_can_require_exact_approval(setup, name):
    env, _, _ = setup
    change_mode(setup, name, "ask")
    _, ctx = task_context(setup)
    if name == "content.prepare":
        media = make_media(env)
        read(setup, ctx, "media")
        args = {
            "content_type": "feed_image",
            "title": "Hello",
            "media_asset_id": str(media.id),
            "caption": {"template": "Merhaba", "language": "tr"},
        }
    else:
        item = submittable_item(env)
        read(setup, ctx)
        args = {"content_id": str(item.id), "expected_version": 1}
        if name == "content.schedule":
            args.update(local_date="2026-01-15", local_time="19:00")
    response = tool(setup, ctx, name, **args)
    assert response.data["status"] == "waiting_approval", response
    preview = env.call(
        env.owner, "GET", f"/accounts/{ctx.account_id}/agent/actions/{response.data['action_id']}"
    )
    assert preview.status_code == 200
    assert preview.json()["content"]["account_id"] == str(ctx.account_id)
    assert preview.json()["content"]["version"] == 1
    if name == "content.prepare":
        assert env.session.scalar(select(func.count(ContentItem.id))) == 0
    decide(setup, response.data["action_id"])
    action = env.session.get(AgentAction, uuid.UUID(response.data["action_id"]))
    assert action.status == "succeeded"


def test_prepare_selects_seen_asset_and_deduplicates_rewording(setup):
    env, _, _ = setup
    _, ctx = task_context(setup)
    media = make_media(env)
    args = {
        "content_type": "feed_image",
        "title": "Hello",
        "media_asset_id": str(media.id),
        "caption": {"template": "Merhaba", "language": "tr"},
    }
    assert tool(setup, ctx, "content.prepare", **args).error == "TOOL_ARGUMENT_INVALID"
    read(setup, ctx, "media")
    first = tool(setup, ctx, "content.prepare", **args)
    assert first.data["status"] == "succeeded", first
    second = tool(setup, ctx, "content.prepare", **{**args, "title": "Reworded"})
    assert first.data["content_id"] == second.data["content_id"]
    item = env.session.get(ContentItem, uuid.UUID(first.data["content_id"]))
    assert item.media_asset_id == media.id and item.is_simulated


def test_staff_can_draft_but_not_schedule_and_customer_has_no_tools(setup):
    env, _, _ = setup
    _, ctx = task_context(setup, "staff")
    item = submittable_item(env)
    read(setup, ctx)
    response = tool(setup, ctx, "content.publish", content_id=str(item.id), expected_version=1)
    assert response.data["status"] == "cancelled"
    assert response.data["outcome_code"] == "source_not_authorized"
    customer = BrokerContext(ctx.workspace, ctx.account_id, ctx.thread_id, "dm", "customer")
    assert not any(
        t.name.startswith("content.") for t in build_default_broker().available(customer)
    )
    assert (
        tool(setup, customer, "content.publish", content_id=str(item.id), expected_version=1).error
        == "TOOL_FORBIDDEN"
    )


def test_member_revocation_fences_broker_and_pending_approval(setup):
    env, _, _ = setup
    change_mode(setup, "content.publish", "ask")
    _, ctx = task_context(setup, "manager")
    item = submittable_item(env)
    read(setup, ctx)
    response = tool(setup, ctx, "content.publish", content_id=str(item.id), expected_version=1)
    member = env.session.get(WorkspaceMember, (env.workspace.id, env.manager.user.id))
    member.role = "staff"
    env.session.flush()
    assert read(setup, ctx).error == "TOOL_FORBIDDEN"
    with pytest.raises(AppError, match="APPROVAL_STALE"):
        decide(setup, response.data["action_id"])


def test_content_edit_and_deleted_media_stale_approval(setup):
    env, _, _ = setup
    change_mode(setup, "content.publish", "ask")
    _, ctx = task_context(setup)
    item = submittable_item(env)
    read(setup, ctx)
    response = tool(setup, ctx, "content.publish", content_id=str(item.id), expected_version=1)
    service.update(
        env.session,
        env.clock,
        ctx.workspace,
        item.id,
        expected_version=1,
        fields={"caption": "Yeni"},
    )
    with pytest.raises(AppError, match="APPROVAL_STALE"):
        decide(setup, response.data["action_id"])


def test_missing_media_clarification_answer_is_idempotent_and_not_approval(setup):
    env, social, _ = setup
    task, ctx = task_context(setup)
    response = tool(
        setup,
        ctx,
        "content.prepare",
        content_type="feed_image",
        title="Hello",
        media_asset_id=None,
        caption=None,
    )
    assert response.data["status"] == "needs_clarification"
    tool(setup, ctx, "task.clarify", question="Which existing image should I use?")
    request_id = uuid.uuid4()
    owner_tasks.answer(
        env.session,
        env.clock,
        ctx.workspace,
        social.id,
        task.id,
        "Use the first one",
        request_id,
        expected_version=1,
    )
    owner_tasks.answer(
        env.session,
        env.clock,
        ctx.workspace,
        social.id,
        task.id,
        "Use the first one",
        request_id,
        expected_version=1,
    )
    assert len(task.answers) == 1 and task.clarification is None
    assert env.session.scalar(select(func.count(Approval.id))) == 0


def test_coordinator_fails_closed_on_lost_requester(setup, shared_session_factory, settings):
    env, social, _ = setup
    task = owner_tasks.submit(
        env.session, env.clock, env.ctx(env.staff), social.id, "Hello", uuid.uuid4()
    )
    member = env.session.get(WorkspaceMember, (env.workspace.id, env.staff.user.id))
    env.session.delete(member)
    env.session.commit()
    deps = RunnerDeps(shared_session_factory, env.clock, FakeLLMProvider(), settings)
    assert claim(deps, env.workspace.id, task.thread_id) is None
    env.session.expire_all()
    goal = env.session.scalar(select(AgentSession).where(AgentSession.thread_id == task.thread_id))
    assert goal.outcome_code == "OWNER_TASK_AUTHORITY_LOST"


def test_real_loop_clarifies_then_resumes(setup, shared_session_factory, settings):
    env, social, _ = setup
    task = owner_tasks.submit(
        env.session, env.clock, env.ctx(env.owner), social.id, "Prepare a post", uuid.uuid4()
    )
    fake = FakeLLMProvider()
    fake.queue_step(
        LLMStepResult(
            "tool",
            LLMUsage(4, 2),
            1,
            "fake",
            "fake",
            True,
            tool_name="task.clarify",
            tool_arguments={"question": "Which image?"},
            call_id="clarify",
        )
    )
    runner = RunnerDeps(shared_session_factory, env.clock, fake, settings)
    run_activation(runner, env.workspace.id, task.thread_id, build_default_broker())
    assert "Europe/Istanbul" in fake.step_calls[0].messages[0].content
    assert "2026-01-15T15:00:00+03:00" in fake.step_calls[0].messages[0].content
    env.session.expire_all()
    assert env.session.get(type(task), task.id).clarification == "Which image?"
    owner_tasks.answer(
        env.session,
        env.clock,
        env.ctx(env.owner),
        social.id,
        task.id,
        "The first image",
        uuid.uuid4(),
        expected_version=1,
    )
    fake.queue_step(LLMStepResult("complete", LLMUsage(4, 2), 1, "fake", "fake", True))
    run_activation(runner, env.workspace.id, task.thread_id, build_default_broker())
    env.session.expire_all()
    assert owner_tasks.outcome(env.session, task)[0] == "completed"


def test_ambiguous_media_requires_requester_selection_and_stale_answers_fail(setup):
    env, social, _ = setup
    task, ctx = task_context(setup)
    first = make_media(env)
    make_media(env)
    read(setup, ctx, "media")
    args = {
        "content_type": "feed_image",
        "title": "Hello",
        "media_asset_id": str(first.id),
        "caption": {"template": "Merhaba", "language": "tr"},
    }
    assert tool(setup, ctx, "content.prepare", **args).data["reason"] == "ambiguous_media"
    tool(setup, ctx, "task.clarify", question="Select an existing image")
    path = f"/accounts/{social.id}/agent/tasks/{task.id}/answers"
    response = env.call(
        env.owner,
        "POST",
        path,
        json={
            "text": "This image",
            "client_request_id": str(uuid.uuid4()),
            "expected_version": 1,
            "media_asset_id": str(first.id),
        },
    )
    assert response.status_code == 202
    assert tool(setup, ctx, "content.prepare", **args).data["status"] == "succeeded"
    tool(setup, ctx, "task.clarify", question="Which time?")
    response = env.call(
        env.owner,
        "POST",
        path,
        json={"text": "Yes", "client_request_id": str(uuid.uuid4()), "expected_version": 1},
    )
    assert response.status_code == 409
    assert task.clarification == "Which time?"


def test_foreign_selected_media_and_unseen_content_fail_closed(setup):
    env, social, _ = setup
    from dataclasses import replace

    from tests.factories import create_workspace

    foreign_env = replace(env, workspace=create_workspace(env.session))
    foreign_media = make_media(foreign_env)
    response = env.call(
        env.owner,
        "POST",
        f"/accounts/{social.id}/agent/tasks",
        json={
            "text": "Hello",
            "client_request_id": str(uuid.uuid4()),
            "media_asset_id": str(foreign_media.id),
        },
    )
    assert response.status_code == 404
    _, ctx = task_context(setup)
    item = submittable_item(env)
    response = tool(setup, ctx, "content.publish", content_id=str(item.id), expected_version=1)
    assert response.error == "TOOL_ARGUMENT_INVALID"
    forged_customer = BrokerContext(
        ctx.workspace, ctx.account_id, ctx.thread_id, "owner_task", "customer"
    )
    assert (
        tool(
            setup, forged_customer, "content.publish", content_id=str(item.id), expected_version=1
        ).error
        == "TOOL_FORBIDDEN"
    )


def test_existing_foreign_tasks_and_composite_thread_relationship_are_isolated(setup):
    env, social, _ = setup
    from dataclasses import replace

    from sqlalchemy.exc import IntegrityError

    from app.agent.models import OwnerTask
    from tests.factories import add_member, create_workspace, knowledge_ctx

    foreign_workspace = create_workspace(env.session)
    add_member(env.session, foreign_workspace, env.owner.user)
    foreign_env = replace(env, workspace=foreign_workspace)
    foreign_social = connect_account(foreign_env, external_account_id=uuid.uuid4().hex)
    agent = env.session.scalar(
        select(AccountAgent).where(AccountAgent.social_account_id == foreign_social.id)
    )
    agent.state, agent.controller_mode = "active", "agent"
    foreign_task = owner_tasks.submit(
        env.session,
        env.clock,
        knowledge_ctx(foreign_workspace, env.owner.user, "owner"),
        foreign_social.id,
        "Foreign task",
        uuid.uuid4(),
    )
    assert (
        env.call(env.owner, "GET", f"/accounts/{foreign_social.id}/agent/tasks").status_code == 404
    )
    assert (
        env.call(
            env.owner, "GET", f"/accounts/{social.id}/agent/tasks/{foreign_task.id}"
        ).status_code
        == 404
    )
    response = env.call(
        env.owner,
        "POST",
        f"/accounts/{social.id}/agent/tasks/{foreign_task.id}/answers",
        json={"text": "Hello", "client_request_id": str(uuid.uuid4()), "expected_version": 1},
    )
    assert response.status_code == 404
    with env.session.begin_nested() as savepoint:
        env.session.add(
            OwnerTask(
                workspace_id=env.workspace.id,
                social_account_id=social.id,
                thread_id=foreign_task.thread_id,
                requester_user_id=env.owner.user.id,
                requester_role="owner",
                source_channel="api",
                client_request_id=uuid.uuid4(),
                request_text="Cross-workspace reference",
            )
        )
        with pytest.raises(IntegrityError):
            env.session.flush()
        savepoint.rollback()


def test_read_receipt_bound_cannot_evict_immutable_intake_selection(setup):
    env, social, _ = setup
    assets = [make_media(env) for _ in range(205)]
    request_id = uuid.uuid4()
    task = owner_tasks.submit(
        env.session,
        env.clock,
        env.ctx(env.owner),
        social.id,
        "Use this image",
        request_id,
        media_asset_id=assets[0].id,
    )
    ctx = BrokerContext(env.ctx(env.owner), social.id, task.thread_id, "owner_task", "owner_task")
    cursor = None
    while True:
        response = tool(setup, ctx, "content.read", kind="media", cursor=cursor, limit=10)
        assert response.ok
        cursor = response.data["next_cursor"]
        if cursor is None:
            break
    assert len(task.read_refs) <= 200
    assert task.read_refs["selected_media_id"] == str(assets[0].id)
    assert (
        owner_tasks.submit(
            env.session,
            env.clock,
            env.ctx(env.owner),
            social.id,
            "Use this image",
            request_id,
            media_asset_id=assets[0].id,
        ).id
        == task.id
    )
