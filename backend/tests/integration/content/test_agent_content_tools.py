"""Agent content uses the same transactional ledger and reconciliation as manual content."""

import uuid

import pytest
from sqlalchemy import select

from app.agent import delegation, owner_tasks
from app.agent.content import result
from app.agent.models import AccountAgent, AgentAction, AgentSession
from app.agent.tools.broker import BrokerContext, build_default_broker
from app.approvals import service as approvals
from app.approvals.models import Approval
from app.content import service
from app.content.models import MediaAsset
from app.core.errors import AppError
from app.identity.models import WorkspaceMember
from app.knowledge.formatting import format_value
from tests.factories import create_fact


def arm(pub, *, mode="automatic"):
    db = pub.session
    agent = db.scalar(select(AccountAgent).where(AccountAgent.social_account_id == pub.account.id))
    rules = {name: delegation.ActionRule(mode="off") for name in delegation.ACTIONS}
    for name in ("content.prepare", "content.schedule", "content.cancel"):
        rules[name] = delegation.ActionRule(mode="automatic")
    rules["content.publish"] = delegation.ActionRule(mode=mode)
    delegation.apply(
        db,
        pub.clock,
        pub.ctx,
        pub.account.id,
        delegation.DelegationChange(
            expected_config_version=agent.config_version,
            client_request_id=uuid.uuid4(),
            policy=delegation.DelegationPolicy(actions=rules),
        ),
    )
    agent.state, agent.controller_mode = "active", "agent"
    db.commit()
    task = owner_tasks.submit(
        db, pub.clock, pub.ctx, pub.account.id, "Publish an image", uuid.uuid4()
    )
    goal = AgentSession(
        workspace_id=pub.workspace.id,
        thread_id=task.thread_id,
        initiating_event_cursor=1,
        goal_key=str(task.id),
        status="queued",
    )
    db.add(goal)
    db.commit()
    return BrokerContext(pub.ctx, pub.account.id, task.thread_id, "owner_task", "owner_task")


def tool(pub, ctx, name, **arguments):
    response = build_default_broker().dispatch(
        pub.session, pub.clock, ctx, name=name, version="v1", arguments=arguments
    )
    pub.session.commit()
    assert response.ok, response
    return response.data


def submit(pub, ctx, item, *, scheduled=False):
    tool(pub, ctx, "content.read", kind="content", limit=10, cursor=None)
    args = {"content_id": str(item.id), "expected_version": item.version}
    if scheduled:
        args.update(local_date="2026-01-15", local_time="19:00")
    return tool(pub, ctx, "content.schedule" if scheduled else "content.publish", **args)


@pytest.mark.parametrize("mode", ["automatic", "ask"])
def test_agent_publish_version_two_uses_ledger_exactly_once(pub, mode):
    ctx = arm(pub, mode=mode)
    item = pub.draft()
    service.update(
        pub.session, pub.clock, pub.ctx, item.id, expected_version=1, fields={"caption": "Merhaba"}
    )
    response = submit(pub, ctx, item)
    if mode == "ask":
        approval = pub.session.get(Approval, uuid.UUID(response["approval_id"]))
        approvals.decide(
            pub.session,
            pub.clock,
            pub.ctx,
            approval.id,
            decision="approve",
            payload_hash=approval.payload_hash,
        )
    assert pub.execute(item).kind == "published"
    assert pub.execute(item).kind == "skipped"
    assert len(pub.posts()) == 1
    pub.session.expire_all()
    action = pub.session.get(AgentAction, item.agent_action_id)
    assert result(pub.session, action)["status"] == "succeeded"
    assert result(pub.session, action)["content_status"] == "published"


def test_agent_timeout_then_revocation_reconciles_without_second_post(pub):
    ctx = arm(pub)
    item = pub.draft()
    submit(pub, ctx, item)
    pub.fail("publish", "timeout_after_success")
    assert pub.execute(item).kind == "unknown"
    op = pub.operation(item)
    action = pub.session.get(AgentAction, item.agent_action_id)
    assert result(pub.session, action)["status"] == "outcome_unknown"
    agent = pub.session.scalar(
        select(AccountAgent).where(AccountAgent.social_account_id == pub.account.id)
    )
    agent.state = "paused"
    pub.session.commit()
    assert pub.reconcile(op).kind == "published"
    assert len(pub.posts()) == 1
    assert pub.operation(item).status == "succeeded"


@pytest.mark.parametrize("revocation", ["pause", "member", "delegation", "media", "deadline"])
def test_agent_scheduled_dispatch_rechecks_current_authority(pub, revocation):
    ctx = arm(pub)
    item = pub.draft()
    submit(pub, ctx, item, scheduled=True)
    pub.clock.advance(hours=4)
    if revocation == "pause":
        pub.session.scalar(
            select(AccountAgent).where(AccountAgent.social_account_id == pub.account.id)
        ).state = "paused"
    elif revocation == "member":
        pub.session.get(WorkspaceMember, (pub.workspace.id, pub.owner.id)).role = "staff"
    elif revocation == "delegation":
        delegation.current_delegation(
            pub.session, pub.workspace.id, pub.account.id
        ).revoked_at = pub.clock.now()
    elif revocation == "media":
        pub.session.get(MediaAsset, item.media_asset_id).status = "deleted"
    else:
        pub.clock.advance(days=1)
    pub.session.commit()
    assert pub.execute(item).kind == "failed"
    assert not pub.posts() and "publish_container" not in pub.calls


def test_agent_future_schedule_survives_default_twenty_four_hour_action_ttl(pub):
    ctx = arm(pub)
    item = pub.draft()
    tool(pub, ctx, "content.read", kind="content", limit=10, cursor=None)
    tool(
        pub,
        ctx,
        "content.schedule",
        content_id=str(item.id),
        expected_version=1,
        local_date="2026-01-17",
        local_time="19:00",
    )
    pub.clock.advance(days=2, hours=4)
    assert pub.execute(item).kind == "published"


def test_agent_fact_version_change_with_same_display_is_stale(pub):
    create_fact(
        pub.session, pub.workspace, "policy.price_disclosure", {"value": "share"}, clock=pub.clock
    )
    fact = create_fact(
        pub.session,
        pub.workspace,
        "pricing.monthly",
        {"amount": "500", "currency": "TRY", "unit": "month"},
        clock=pub.clock,
    )
    ctx = arm(pub)
    item = pub.draft(caption=format_value(fact.value_type, fact.value, "tr", "tr"))
    response = submit(pub, ctx, item)
    assert response.get("status") == "queued", response
    # A new verified version with an identical display must still fence the old grant.
    fact.current_version += 1
    pub.session.commit()
    assert pub.execute(item).kind == "failed"
    assert not pub.posts()


def test_agent_edit_after_scheduling_cannot_reuse_old_grant(pub):
    ctx = arm(pub)
    item = pub.draft()
    submit(pub, ctx, item)
    old_version = item.version
    service.update(
        pub.session,
        pub.clock,
        pub.ctx,
        item.id,
        expected_version=old_version,
        fields={"caption": "Yeni"},
    )
    assert pub.execute(item, version=old_version).kind == "skipped"
    assert not pub.posts()


def test_deleted_media_blocks_pending_publish_approval(pub):
    ctx = arm(pub, mode="ask")
    item = pub.draft()
    response = submit(pub, ctx, item)
    approval = pub.session.get(Approval, uuid.UUID(response["approval_id"]))
    pub.session.get(MediaAsset, item.media_asset_id).status = "deleted"
    pub.session.commit()
    with pytest.raises(AppError, match="APPROVAL_STALE"):
        approvals.decide(
            pub.session,
            pub.clock,
            pub.ctx,
            approval.id,
            decision="approve",
            payload_hash=approval.payload_hash,
        )


def test_manual_resubmission_after_agent_edit_has_fresh_legacy_authority(pub):
    ctx = arm(pub)
    item = pub.draft()
    response = submit(pub, ctx, item)
    old_action = pub.session.get(AgentAction, uuid.UUID(response["action_id"]))
    service.update(
        pub.session, pub.clock, pub.ctx, item.id, expected_version=1, fields={"caption": "Yeni"}
    )
    pub.schedule(item)
    assert item.origin == "legacy" and item.agent_action_id is None
    assert result(pub.session, old_action)["status"] == "cancelled"
    pub.session.commit()
    assert pub.execute(item).kind == "published"


def test_story_publication_uses_story_capability_without_feed_capability(pub):
    ctx = arm(pub)
    pub.account.capabilities = {**pub.account.capabilities, "publish_feed_image": False}
    pub.session.commit()
    item = pub.draft("story_image")
    assert submit(pub, ctx, item)["status"] == "queued"
    assert pub.execute(item).kind == "published"
    assert pub.containers()[0].caption is None


def test_approval_rechecks_forecast_quota_after_competing_submission(pub, monkeypatch):
    ctx = arm(pub, mode="ask")
    item = pub.draft()
    response = submit(pub, ctx, item)
    approval = pub.session.get(Approval, uuid.UUID(response["approval_id"]))
    pub.schedule(pub.draft())
    monkeypatch.setattr(
        "app.agent.content.get_settings",
        lambda: pub.settings.model_copy(update={"publish_daily_limit": 1}),
    )
    with pytest.raises(AppError, match="APPROVAL_STALE"):
        approvals.decide(
            pub.session,
            pub.clock,
            pub.ctx,
            approval.id,
            decision="approve",
            payload_hash=approval.payload_hash,
        )


def test_agent_cancel_scheduled_content_prevents_publish(pub):
    ctx = arm(pub)
    item = pub.draft()
    submit(pub, ctx, item)
    response = tool(pub, ctx, "content.cancel", content_id=str(item.id), expected_version=1)
    assert response["status"] == "succeeded" and response["content_status"] == "cancelled"
    assert pub.execute(item).kind == "skipped"
    assert not pub.posts()


def test_prepared_noncritical_fact_sources_are_preserved_until_dispatch(pub):
    fact = create_fact(
        pub.session,
        pub.workspace,
        "custom.greeting",
        {"text": "Merhaba"},
        value_type="text",
        clock=pub.clock,
    )
    ctx = arm(pub)
    media = pub.media()
    tool(pub, ctx, "content.read", kind="media", limit=10, cursor=None)
    response = tool(
        pub,
        ctx,
        "content.prepare",
        content_type="feed_image",
        title="Hello",
        media_asset_id=str(media.id),
        caption={
            "template": "{{fact:custom.greeting}}",
            "language": "tr",
            "fact_sources": [{"id": str(fact.id), "version": 1}],
        },
    )
    from app.content.models import ContentItem

    item = pub.session.get(ContentItem, uuid.UUID(response["content_id"]))
    response = submit(pub, ctx, item)
    action = pub.session.get(AgentAction, uuid.UUID(response["action_id"]))
    assert [str(fact.id), 1] in action.content_intent["fact_refs"]
    fact.current_version += 1
    pub.session.commit()
    assert pub.execute(item).kind == "failed"
    assert not pub.posts()


def test_owner_task_loop_prepares_schedules_waits_for_verified_publish_then_completes(
    pub, shared_session_factory
):
    from app.agent.coordinator import run_activation
    from app.ai.runner import RunnerDeps
    from app.content.models import ContentItem
    from app.integrations.llm.base import LLMUsage
    from app.integrations.llm.fake import FakeLLMProvider
    from app.integrations.llm.steps import LLMStepResult

    ctx = arm(pub)
    media = pub.media()

    class OwnerFake(FakeLLMProvider):
        def generate_step(self, request):
            index = len(self.step_calls)
            self.step_calls.append(request)
            if index == 0:
                name, args = "content.read", {"kind": "media", "cursor": None, "limit": 5}
            elif index == 1:
                name, args = (
                    "content.prepare",
                    {
                        "content_type": "feed_image",
                        "title": "Hello",
                        "media_asset_id": str(media.id),
                        "caption": {"template": "Merhaba", "language": "tr"},
                    },
                )
            elif index == 2:
                name, args = (
                    "content.schedule",
                    {
                        "content_id": request.observations[0].result["content_id"],
                        "expected_version": 1,
                        "local_date": "2026-01-15",
                        "local_time": "19:00",
                    },
                )
            else:
                assert request.observations[0].result["content_status"] == "published"
                return LLMStepResult("complete", LLMUsage(4, 2), 1, "fake", "fake", True)
            return LLMStepResult(
                "tool",
                LLMUsage(4, 2),
                1,
                "fake",
                "fake",
                True,
                tool_name=name,
                tool_arguments=args,
                call_id=str(index),
            )

    fake = OwnerFake()
    runner = RunnerDeps(shared_session_factory, pub.clock, fake, pub.settings)
    run_activation(runner, pub.workspace.id, ctx.thread_id, build_default_broker())
    pub.session.expire_all()
    goal = pub.session.scalar(select(AgentSession).where(AgentSession.thread_id == ctx.thread_id))
    assert goal.status == "waiting_operation"
    item = pub.session.scalar(select(ContentItem))
    assert item.status == "scheduled" and not pub.posts()
    pub.clock.advance(hours=4)
    assert pub.execute(item).kind == "published"
    run_activation(runner, pub.workspace.id, ctx.thread_id, build_default_broker())
    pub.session.expire_all()
    assert pub.session.get(AgentSession, goal.id).status == "completed"
    assert len(fake.step_calls) == 4 and len(pub.posts()) == 1
