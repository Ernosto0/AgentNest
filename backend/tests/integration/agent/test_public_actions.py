"""Offline public effects with committed ledger and scoped source fences."""

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from app.agent.coordinator import claim, run_activation
from app.agent.models import AgentAction, AgentDelegation
from app.agent.tools.broker import build_default_broker
from app.approvals import service as approvals
from app.approvals.models import Approval
from app.comments.actions import ModerateArgs, PublicReplyArgs
from app.comments.models import PublicComment, SimCommentEffect
from app.integrations.instagram.models import SimFailureRule, SocialAccount
from app.integrations.llm.fake import FakeLLMProvider
from app.operations.models import Operation
from app.operations.public_comments import execute, reconcile
from tests.integration.agent.test_comments import context, deliver
from tests.integration.agent.test_coordinator import deps, result
from tests.integration.agent.test_dm import setup

pytestmark = pytest.mark.commits


def ready(factory, clock, effect: str, mode: str = "automatic"):
    world = setup(factory, clock)
    with factory() as db:
        account = db.get(SocialAccount, world[1])
        account.capabilities = {
            **account.capabilities,
            "comment_reply": True,
            "comment_moderate": True,
        }
        delegation = db.scalar(
            select(AgentDelegation).where(AgentDelegation.social_account_id == account.id)
        )
        policy = dict(delegation.policy)
        actions = dict(policy["actions"])
        actions[f"comment.{effect}"] = {**actions[f"comment.{effect}"], "mode": mode}
        delegation.policy = {**policy, "actions": actions}
        db.commit()
    deliver(factory, clock, world, media_verified=True)
    with factory() as db:
        ctx = context(db, world)
        comment = db.scalar(
            select(PublicComment).where(
                PublicComment.external_id == "root",
                PublicComment.social_account_id == world[1],
            )
        )
        target = (comment.id, comment.version)
    claimed = claim(deps(factory, clock, FakeLLMProvider()), world[0].workspace_id, ctx.thread_id)
    assert claimed is not None
    return world, ctx, target


def propose(factory, clock, ctx, target, effect: str):
    broker = build_default_broker()
    if effect == "reply":
        args = PublicReplyArgs(
            comment_id=target[0],
            comment_version=target[1],
            reply={"template": "Thanks for reaching out.", "language": "en"},
        ).model_dump(mode="json")
        name = "comment.reply"
    else:
        args = ModerateArgs(
            comment_id=target[0],
            comment_version=target[1],
            effect=effect,
        ).model_dump(mode="json")
        name = "comment.moderate"
    with factory() as db:
        result = broker.dispatch(db, clock, ctx, name=name, version="v1", arguments=args)
        assert result.ok, result.error
        db.commit()
        return result.data


def test_public_reply_once_and_noop_completion(session_factory, clock):
    world, ctx, target = ready(session_factory, clock, "reply")
    first = propose(session_factory, clock, ctx, target, "reply")
    again = propose(session_factory, clock, ctx, target, "reply")
    assert first["action_id"] == again["action_id"]
    execute(session_factory, clock, world[3], world[0].workspace_id, uuid.UUID(first["action_id"]))
    execute(session_factory, clock, world[3], world[0].workspace_id, uuid.UUID(first["action_id"]))
    with session_factory() as db:
        assert len(db.scalars(select(SimCommentEffect)).all()) == 1
        assert db.scalar(select(AgentAction)).status == "succeeded"
        assert db.scalar(select(Operation)).status == "succeeded"


def test_moderation_and_timeout_after_success_reconciles_without_resend(session_factory, clock):
    world, ctx, target = ready(session_factory, clock, "hide")
    action = propose(session_factory, clock, ctx, target, "hide")
    with session_factory() as db:
        db.add(
            SimFailureRule(
                workspace_id=world[0].workspace_id,
                social_account_id=world[1],
                operation="comment_hide",
                mode="timeout_after_success",
                remaining=1,
                created_at=clock.now(),
                updated_at=clock.now(),
            )
        )
        db.commit()
    action_id = uuid.UUID(action["action_id"])
    execute(session_factory, clock, world[3], world[0].workspace_id, action_id)
    with session_factory() as db:
        op = db.scalar(select(Operation))
        assert op.status == "outcome_unknown"
        operation_id = op.id
    execute(session_factory, clock, world[3], world[0].workspace_id, action_id)
    reconcile(session_factory, clock, world[3], world[0].workspace_id, operation_id)
    with session_factory() as db:
        assert db.scalar(select(Operation)).status == "succeeded"
        assert (
            db.scalar(select(PublicComment).where(PublicComment.id == target[0])).state == "hidden"
        )
        assert len(db.scalars(select(SimCommentEffect)).all()) == 1


def test_changed_target_blocks_queued_effect(session_factory, clock):
    world, ctx, target = ready(session_factory, clock, "delete")
    action = propose(session_factory, clock, ctx, target, "delete")
    with session_factory() as db:
        comment = db.get(PublicComment, target[0])
        comment.version += 1
        db.commit()
    execute(session_factory, clock, world[3], world[0].workspace_id, uuid.UUID(action["action_id"]))
    with session_factory() as db:
        assert db.scalar(select(AgentAction)).status == "cancelled"
        assert db.scalar(select(SimCommentEffect)) is None


def test_ask_requires_exact_human_approval(session_factory, clock):
    world, ctx, target = ready(session_factory, clock, "delete", "ask")
    action = propose(session_factory, clock, ctx, target, "delete")
    assert action["status"] == "waiting_approval"
    execute(session_factory, clock, world[3], world[0].workspace_id, uuid.UUID(action["action_id"]))
    with session_factory() as db:
        assert db.scalar(select(SimCommentEffect)) is None
        approval = db.get(Approval, uuid.UUID(action["approval_id"]))
        approvals.decide(
            db, clock, world[0], approval.id, decision="approve", payload_hash=approval.payload_hash
        )
    execute(session_factory, clock, world[3], world[0].workspace_id, uuid.UUID(action["action_id"]))
    with session_factory() as db:
        assert db.scalar(select(Operation)).status == "succeeded"
        assert (
            db.scalar(select(PublicComment).where(PublicComment.id == target[0])).state == "deleted"
        )


def test_unhide_after_verified_hide(session_factory, clock):
    world, ctx, target = ready(session_factory, clock, "hide")
    first = propose(session_factory, clock, ctx, target, "hide")
    execute(session_factory, clock, world[3], world[0].workspace_id, uuid.UUID(first["action_id"]))
    with session_factory() as db:
        comment = db.get(PublicComment, target[0])
        assert comment.state == "hidden"
        version = comment.version
        delegation = db.scalar(
            select(AgentDelegation).where(AgentDelegation.social_account_id == world[1])
        )
        policy = dict(delegation.policy)
        actions = dict(policy["actions"])
        actions["comment.unhide"] = {**actions["comment.unhide"], "mode": "automatic"}
        delegation.policy = {**policy, "actions": actions}
        db.commit()
    second = propose(session_factory, clock, ctx, (target[0], version), "unhide")
    execute(session_factory, clock, world[3], world[0].workspace_id, uuid.UUID(second["action_id"]))
    with session_factory() as db:
        assert db.get(PublicComment, target[0]).state == "visible"
        assert len(db.scalars(select(SimCommentEffect)).all()) == 2


def test_inconclusive_readback_keeps_unknown_and_blocks_duplicate(session_factory, clock):
    world, ctx, target = ready(session_factory, clock, "reply")
    action = propose(session_factory, clock, ctx, target, "reply")
    with session_factory() as db:
        db.add(
            SimFailureRule(
                workspace_id=world[0].workspace_id,
                social_account_id=world[1],
                operation="comment_reply",
                mode="timeout_after_success",
                remaining=1,
            )
        )
        db.add(
            SimFailureRule(
                workspace_id=world[0].workspace_id,
                social_account_id=world[1],
                operation="comment_lookup",
                mode="transient",
                remaining=1,
            )
        )
        db.commit()
    action_id = uuid.UUID(action["action_id"])
    execute(session_factory, clock, world[3], world[0].workspace_id, action_id)
    with session_factory() as db:
        operation_id = db.scalar(select(Operation)).id
        assert db.scalar(select(AgentAction)).status == "outcome_unknown"
    reconcile(session_factory, clock, world[3], world[0].workspace_id, operation_id)
    assert propose(session_factory, clock, ctx, target, "reply")["action_id"] == action["action_id"]
    with session_factory() as db:
        assert db.scalar(select(Operation)).status == "outcome_unknown"
        assert len(db.scalars(select(SimCommentEffect)).all()) == 1


def test_conflicting_moderation_waits_for_reply_and_foreign_target_fails(session_factory, clock):
    world, ctx, target = ready(session_factory, clock, "reply")
    reply = propose(session_factory, clock, ctx, target, "reply")
    with session_factory() as db:
        account = db.get(SocialAccount, world[1])
        delegation = db.scalar(
            select(AgentDelegation).where(AgentDelegation.social_account_id == account.id)
        )
        policy = dict(delegation.policy)
        actions = dict(policy["actions"])
        actions["comment.delete"] = {**actions["comment.delete"], "mode": "automatic"}
        delegation.policy = {**policy, "actions": actions}
        db.commit()
    assert propose(session_factory, clock, ctx, target, "delete")["action_id"] == reply["action_id"]
    foreign = ModerateArgs(comment_id=uuid.uuid4(), comment_version=1, effect="delete")
    with session_factory() as db:
        denied = build_default_broker().dispatch(
            db,
            clock,
            ctx,
            name="comment.moderate",
            version="v1",
            arguments=foreign.model_dump(mode="json"),
        )
        assert (denied.ok, denied.error) == (False, "TOOL_ARGUMENT_INVALID")


def test_contextual_no_action_completes_without_effect(session_factory, clock):
    world = setup(session_factory, clock)
    deliver(
        session_factory, clock, world, media_verified=True, text="Just sharing feedback, thanks."
    )
    with session_factory() as db:
        ctx = context(db, world)
    fake = FakeLLMProvider()
    fake.queue_step(result())
    run_activation(
        deps(session_factory, clock, fake),
        world[0].workspace_id,
        ctx.thread_id,
        build_default_broker(),
    )
    with session_factory() as db:
        assert db.scalar(select(AgentAction)) is None
        assert db.scalar(select(Operation)) is None


def test_two_workers_and_revoked_grant(session_factory, clock):
    world, ctx, target = ready(session_factory, clock, "hide")
    action = propose(session_factory, clock, ctx, target, "hide")
    action_id = uuid.UUID(action["action_id"])
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
        assert len(db.scalars(select(SimCommentEffect)).all()) == 1
    # A separately queued action cannot execute after delegation revocation.
    world2, ctx2, target2 = ready(session_factory, clock, "reply")
    queued = propose(session_factory, clock, ctx2, target2, "reply")
    with session_factory() as db:
        delegation = db.scalar(
            select(AgentDelegation).where(
                AgentDelegation.social_account_id == world2[1],
            )
        )
        delegation.revoked_at = clock.now()
        db.commit()
    execute(
        session_factory, clock, world2[3], world2[0].workspace_id, uuid.UUID(queued["action_id"])
    )
    with session_factory() as db:
        assert db.get(AgentAction, uuid.UUID(queued["action_id"])).status == "cancelled"
        assert (
            db.scalar(
                select(SimCommentEffect).where(
                    SimCommentEffect.social_account_id == world2[1],
                )
            )
            is None
        )


def test_remote_target_missing_is_failure_not_verified_delete(session_factory, clock):
    world, ctx, target = ready(session_factory, clock, "delete")
    action = propose(session_factory, clock, ctx, target, "delete")
    from app.comments.models import SimPublicComment

    with session_factory() as db:
        remote = db.scalar(
            select(SimPublicComment).where(
                SimPublicComment.social_account_id == world[1],
                SimPublicComment.external_id == "root",
            )
        )
        remote.value = {**remote.value, "state": "deleted"}
        db.commit()
    execute(session_factory, clock, world[3], world[0].workspace_id, uuid.UUID(action["action_id"]))
    with session_factory() as db:
        op = db.scalar(select(Operation))
        assert (op.status, op.last_error_code) == ("failed", "COMMENT_NOT_FOUND")
        assert db.get(PublicComment, target[0]).state == "visible"
