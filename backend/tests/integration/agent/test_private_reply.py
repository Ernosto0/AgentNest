"""Synthetic signed comment-to-DM contract with one-shot reservation."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.agent.context import assemble
from app.agent.coordinator import claim
from app.agent.dm import send as send_dm
from app.agent.grounding import ReplyValidationArgs
from app.agent.models import AgentAction, AgentDelegation, AgentThread
from app.agent.tools.broker import BrokerContext, build_default_broker
from app.approvals import service as approvals
from app.approvals.models import Approval
from app.comments.actions import PublicReplyArgs
from app.comments.models import (
    PrivateReplyOpportunity,
    PublicComment,
    SimPrivateReply,
    SimPublicComment,
)
from app.comments.private_reply import PrivateReplyArgs, dm_source_context
from app.inbox.models import Conversation, ReplyDraft
from app.integrations.instagram.models import SimFailureRule, SocialAccount
from app.integrations.llm.fake import FakeLLMProvider
from app.operations.models import Operation
from app.operations.private_reply import execute, reconcile
from app.operations.public_comments import execute as execute_public
from app.operations.send import execute_send_reply
from tests.integration.agent.test_comments import context, deliver
from tests.integration.agent.test_comments import process as process_events
from tests.integration.agent.test_coordinator import deps
from tests.integration.agent.test_dm import deliver as deliver_dm
from tests.integration.agent.test_dm import setup

pytestmark = pytest.mark.commits


def ready(factory, clock, *, mode="automatic", author="public-person", age_days=0):
    world = setup(factory, clock)
    with factory() as db:
        account = db.get(SocialAccount, world[1])
        account.capabilities = {**account.capabilities, "comment_private_reply": True}
        delegation = db.scalar(
            select(AgentDelegation).where(AgentDelegation.social_account_id == account.id)
        )
        policy = dict(delegation.policy)
        actions = dict(policy["actions"])
        actions["comment.private_reply"] = {**actions["comment.private_reply"], "mode": mode}
        delegation.policy = {**policy, "actions": actions}
        db.commit()
    deliver(
        factory,
        clock,
        world,
        media_verified=True,
        author_id=author,
        timestamp=(clock.now() - timedelta(days=age_days)).isoformat(),
    )
    with factory() as db:
        ctx = context(db, world)
        source = db.scalar(
            select(PublicComment).where(
                PublicComment.social_account_id == world[1], PublicComment.external_id == "root"
            )
        )
        target = (source.id, source.version)
    assert claim(deps(factory, clock, FakeLLMProvider()), world[0].workspace_id, ctx.thread_id)
    return world, ctx, target


def propose(factory, clock, ctx, target):
    request = PrivateReplyArgs(
        comment_id=target[0],
        comment_version=target[1],
        reply={"template": "I can help you privately.", "language": "en"},
    )
    with factory() as db:
        answer = build_default_broker().dispatch(
            db,
            clock,
            ctx,
            name="comment.private_reply",
            version="v1",
            arguments=request.model_dump(mode="json"),
        )
        db.commit()
        return answer


def test_one_shot_and_no_inbound_window(session_factory, clock):
    world, ctx, target = ready(session_factory, clock)
    first = propose(session_factory, clock, ctx, target)
    assert first.ok, first.error
    assert propose(session_factory, clock, ctx, target).data["action_id"] == first.data["action_id"]
    action_id = uuid.UUID(first.data["action_id"])
    execute(session_factory, clock, world[3], world[0].workspace_id, action_id)
    execute(session_factory, clock, world[3], world[0].workspace_id, action_id)
    with session_factory() as db:
        assert db.get(AgentAction, action_id).status == "succeeded"
        assert len(db.scalars(select(SimPrivateReply)).all()) == 1
        assert db.scalar(select(PrivateReplyOpportunity)).provider_recipient_id == "public-person"
        assert db.scalar(select(Conversation)) is None
    assert propose(session_factory, clock, ctx, target).data["action_id"] == first.data["action_id"]


def test_ask_missing_grant_expiry_and_deleted_source(session_factory, clock):
    world, ctx, target = ready(session_factory, clock, mode="ask")
    request = propose(session_factory, clock, ctx, target)
    assert request.ok and request.data["status"] == "waiting_approval"
    execute(
        session_factory,
        clock,
        world[3],
        world[0].workspace_id,
        uuid.UUID(request.data["action_id"]),
    )
    with session_factory() as db:
        assert db.scalar(select(SimPrivateReply)) is None
        approval = db.get(Approval, uuid.UUID(request.data["approval_id"]))
        approvals.decide(
            db, clock, world[0], approval.id, decision="approve", payload_hash=approval.payload_hash
        )
    execute(
        session_factory,
        clock,
        world[3],
        world[0].workspace_id,
        uuid.UUID(request.data["action_id"]),
    )
    with session_factory() as db:
        assert db.get(AgentAction, uuid.UUID(request.data["action_id"])).status == "succeeded"
    world2, ctx2, target2 = ready(session_factory, clock, age_days=8)
    assert not propose(session_factory, clock, ctx2, target2).ok
    world3, ctx3, target3 = ready(session_factory, clock)
    queued = propose(session_factory, clock, ctx3, target3)
    with session_factory() as db:
        source = db.get(PublicComment, target3[0])
        source.state, source.version = "deleted", source.version + 1
        db.commit()
    execute(
        session_factory,
        clock,
        world3[3],
        world3[0].workspace_id,
        uuid.UUID(queued.data["action_id"]),
    )
    with session_factory() as db:
        assert db.get(AgentAction, uuid.UUID(queued.data["action_id"])).status == "cancelled"
    world4, ctx4, target4 = ready(session_factory, clock, mode="off")
    denied = propose(session_factory, clock, ctx4, target4)
    assert denied.ok and denied.data["status"] == "cancelled"
    with session_factory() as db:
        assert (
            db.scalar(select(SimPrivateReply).where(SimPrivateReply.social_account_id == world4[1]))
            is None
        )


def test_timeout_after_success_reconciles_and_unknown_holds(session_factory, clock):
    world, ctx, target = ready(session_factory, clock)
    request = propose(session_factory, clock, ctx, target)
    with session_factory() as db:
        db.add(
            SimFailureRule(
                workspace_id=world[0].workspace_id,
                social_account_id=world[1],
                operation="comment_private_reply",
                mode="timeout_after_success",
                remaining=1,
            )
        )
        db.add(
            SimFailureRule(
                workspace_id=world[0].workspace_id,
                social_account_id=world[1],
                operation="private_reply_lookup",
                mode="transient",
                remaining=1,
            )
        )
        db.commit()
    action_id = uuid.UUID(request.data["action_id"])
    execute(session_factory, clock, world[3], world[0].workspace_id, action_id)
    with session_factory() as db:
        op = db.scalar(select(Operation))
        assert op.status == "outcome_unknown"
        operation_id = op.id
    reconcile(session_factory, clock, world[3], world[0].workspace_id, operation_id)
    assert propose(session_factory, clock, ctx, target).data["action_id"] == str(action_id)
    deliver_dm(session_factory, clock, world, customer="public-person", mid="early-response")
    process_events(session_factory, clock, world)
    with session_factory() as db:
        assert db.scalar(select(Operation)).status == "outcome_unknown"
        assert len(db.scalars(select(SimPrivateReply)).all()) == 1
        assert db.scalar(select(PrivateReplyOpportunity)).bound_conversation_id is None
    reconcile(session_factory, clock, world[3], world[0].workspace_id, operation_id)
    with session_factory() as db:
        assert db.scalar(select(Operation)).status == "succeeded"
        assert db.scalar(select(PrivateReplyOpportunity)).bound_conversation_id is None
    deliver_dm(session_factory, clock, world, customer="public-person", mid="later-response")
    process_events(session_factory, clock, world)
    with session_factory() as db:
        assert db.scalar(select(PrivateReplyOpportunity)).bound_conversation_id is not None


def test_two_workers_and_unmatchable_identity(session_factory, clock):
    world, ctx, target = ready(session_factory, clock)
    request = propose(session_factory, clock, ctx, target)
    action_id = uuid.UUID(request.data["action_id"])
    with session_factory() as db:
        source = db.scalar(
            select(SimPublicComment).where(
                SimPublicComment.social_account_id == world[1],
                SimPublicComment.external_id == "root",
            )
        )
        source.value = {**source.value, "author_id": None}
        db.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(
            pool.map(
                lambda _: execute(
                    session_factory, clock, world[3], world[0].workspace_id, action_id
                ),
                range(2),
            )
        )
    with session_factory() as db:
        assert len(db.scalars(select(SimPrivateReply)).all()) == 1
        assert db.scalar(select(PrivateReplyOpportunity)).provider_recipient_id is None


def test_signed_customer_response_links_private_origin_only(session_factory, clock):
    world, ctx, target = ready(session_factory, clock)
    request = propose(session_factory, clock, ctx, target)
    execute(
        session_factory,
        clock,
        world[3],
        world[0].workspace_id,
        uuid.UUID(request.data["action_id"]),
    )
    deliver_dm(session_factory, clock, world, text="A different customer", customer="stranger")
    process_events(session_factory, clock, world)
    with session_factory() as db:
        row = db.scalar(
            select(PrivateReplyOpportunity).where(
                PrivateReplyOpportunity.social_account_id == world[1]
            )
        )
        assert row.bound_conversation_id is None
    deliver_dm(
        session_factory, clock, world, text="Yes, please tell me more", customer="public-person"
    )
    process_events(session_factory, clock, world)
    with session_factory() as db:
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.social_account_id == world[1],
                Conversation.customer_external_id == "public-person",
            )
        )
        assert conversation is not None and conversation.last_inbound_at is not None
        origin = dm_source_context(db, conversation)
        assert origin is not None and "Hello" in origin["comment_text"]
        row = db.scalar(
            select(PrivateReplyOpportunity).where(
                PrivateReplyOpportunity.social_account_id == world[1]
            )
        )
        assert row.bound_conversation_id == conversation.id
        dm_thread = db.scalar(
            select(AgentThread).where(
                AgentThread.social_account_id == world[1],
                AgentThread.surface == "dm",
                AgentThread.dm_conversation_id == conversation.id,
            )
        )
        assert dm_thread is not None
        from app.agent.tools.broker import BrokerContext

        private_context = BrokerContext(world[0], world[1], dm_thread.id, "dm", "customer")
        assert "private_origin" in assemble(db, clock, private_context).messages[0].content
        assert "private_origin" not in assemble(db, clock, ctx).messages[0].content
    dm_ctx = private_context
    assert claim(
        deps(session_factory, clock, FakeLLMProvider()), world[0].workspace_id, dm_ctx.thread_id
    )
    with session_factory() as db:
        proposed = send_dm(
            db,
            clock,
            dm_ctx,
            ReplyValidationArgs(template="Tell me what you need help with.", language="en"),
        )
        db.commit()
    assert proposed["status"] == "queued"
    with session_factory() as db:
        draft = db.get(
            ReplyDraft, db.get(AgentAction, uuid.UUID(proposed["action_id"])).payload_ref
        )
        draft_id = draft.id
    sent = execute_send_reply(session_factory, clock, world[3], world[0].workspace_id, draft_id)
    assert sent.kind == "sent"


def test_duplicate_signed_events_share_one_opportunity(session_factory, clock):
    world, ctx, target = ready(session_factory, clock)
    first = propose(session_factory, clock, ctx, target)
    assert first.ok
    assert deliver(session_factory, clock, world, media_verified=True).duplicates == 1
    process_events(session_factory, clock, world)
    assert propose(session_factory, clock, ctx, target).data["action_id"] == first.data["action_id"]
    with session_factory() as db:
        assert len(db.scalars(select(PrivateReplyOpportunity)).all()) == 1


def test_public_then_private_are_separate_authorized_effects(session_factory, clock):
    world, ctx, target = ready(session_factory, clock)
    with session_factory() as db:
        account = db.get(SocialAccount, world[1])
        account.capabilities = {**account.capabilities, "comment_reply": True}
        delegation = db.scalar(
            select(AgentDelegation).where(AgentDelegation.social_account_id == world[1])
        )
        policy = dict(delegation.policy)
        actions = dict(policy["actions"])
        actions["comment.reply"] = {**actions["comment.reply"], "mode": "automatic"}
        delegation.policy = {**policy, "actions": actions}
        db.commit()
    public_request = PublicReplyArgs(
        comment_id=target[0],
        comment_version=target[1],
        reply={"template": "I sent a private follow-up.", "language": "en"},
    )
    with session_factory() as db:
        public = build_default_broker().dispatch(
            db,
            clock,
            ctx,
            name="comment.reply",
            version="v1",
            arguments=public_request.model_dump(mode="json"),
        )
        db.commit()
    assert public.ok and public.data["status"] == "queued"
    execute_public(
        session_factory, clock, world[3], world[0].workspace_id, uuid.UUID(public.data["action_id"])
    )
    private = propose(session_factory, clock, ctx, target)
    assert private.ok and private.data["action_id"] != public.data["action_id"]
    execute(
        session_factory,
        clock,
        world[3],
        world[0].workspace_id,
        uuid.UUID(private.data["action_id"]),
    )
    with session_factory() as db:
        effects = list(
            db.scalars(
                select(Operation)
                .where(Operation.social_account_id == world[1])
                .order_by(Operation.started_at)
            )
        )
        assert [item.operation_type for item in effects] == [
            "comment_reply",
            "comment_private_reply",
        ]


def test_preexisting_conversation_requires_new_inbound_after_reply(session_factory, clock):
    world, ctx, target = ready(session_factory, clock)
    deliver_dm(session_factory, clock, world, customer="public-person", mid="before-reply")
    process_events(session_factory, clock, world)
    request = propose(session_factory, clock, ctx, target)
    execute(
        session_factory,
        clock,
        world[3],
        world[0].workspace_id,
        uuid.UUID(request.data["action_id"]),
    )
    with session_factory() as db:
        opportunity = db.scalar(select(PrivateReplyOpportunity))
        assert opportunity.status == "succeeded" and opportunity.bound_conversation_id is None
    deliver_dm(session_factory, clock, world, customer="public-person", mid="before-reply")
    process_events(session_factory, clock, world)
    with session_factory() as db:
        assert db.scalar(select(PrivateReplyOpportunity)).bound_conversation_id is None
    deliver_dm(session_factory, clock, world, customer="public-person", mid="after-reply")
    process_events(session_factory, clock, world)
    with session_factory() as db:
        assert db.scalar(select(PrivateReplyOpportunity)).bound_conversation_id is not None


def test_two_matching_opportunities_leave_identity_ambiguous(session_factory, clock):
    world, ctx, target = ready(session_factory, clock)
    first = propose(session_factory, clock, ctx, target)
    execute(
        session_factory, clock, world[3], world[0].workspace_id, uuid.UUID(first.data["action_id"])
    )
    deliver(
        session_factory,
        clock,
        world,
        id="root-two",
        root_id="root-two",
        media_verified=True,
        author_id="public-person",
    )
    with session_factory() as db:
        second_source = db.scalar(
            select(PublicComment).where(
                PublicComment.social_account_id == world[1], PublicComment.external_id == "root-two"
            )
        )
        second_thread = db.scalar(
            select(AgentThread).where(
                AgentThread.social_account_id == world[1],
                AgentThread.surface == "comment",
                AgentThread.public_thread_id == second_source.thread_id,
            )
        )
        second_ctx = BrokerContext(world[0], world[1], second_thread.id, "comment", "customer")
        second_target = (second_source.id, second_source.version)
    assert claim(
        deps(session_factory, clock, FakeLLMProvider()), world[0].workspace_id, second_ctx.thread_id
    )
    second = propose(session_factory, clock, second_ctx, second_target)
    execute(
        session_factory, clock, world[3], world[0].workspace_id, uuid.UUID(second.data["action_id"])
    )
    deliver_dm(session_factory, clock, world, customer="public-person", mid="ambiguous-reply")
    process_events(session_factory, clock, world)
    with session_factory() as db:
        rows = list(
            db.scalars(
                select(PrivateReplyOpportunity).where(
                    PrivateReplyOpportunity.social_account_id == world[1]
                )
            )
        )
        assert len(rows) == 2 and all(row.bound_conversation_id is None for row in rows)
