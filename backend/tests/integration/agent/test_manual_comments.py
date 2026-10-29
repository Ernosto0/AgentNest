"""Manual moderation has real member authority and the shared committed effect ledger."""

import uuid

import pytest
from sqlalchemy import select

from app.agent.models import AgentAction
from app.comments.manual import ManualModeration, moderate
from app.comments.models import PublicComment, SimCommentEffect
from app.core.errors import AppError
from app.identity.models import WorkspaceMember
from app.integrations.instagram.models import SimFailureRule
from app.operations.manual_comments import execute, reconcile
from app.operations.models import Operation
from tests.integration.agent.test_public_actions import propose, ready

pytestmark = pytest.mark.commits


def submit(factory, clock, world, target, effect="hide", request_id=None):
    with factory() as db:
        return moderate(
            world[1],
            target[0],
            ManualModeration(
                expected_version=target[1],
                effect=effect,
                client_request_id=request_id or uuid.uuid4(),
            ),
            world[0],
            db,
            clock,
        )


def test_explicit_manual_request_replays_and_never_requires_agent_grant(session_factory, clock):
    world, ctx, target = ready(session_factory, clock, "hide", "off")
    request = uuid.uuid4()
    op = submit(session_factory, clock, world, target, request_id=request)
    assert op.status == "pending"
    assert (
        submit(session_factory, clock, world, target, request_id=request).operation_id
        == op.operation_id
    )
    with pytest.raises(AppError):
        submit(session_factory, clock, world, target, effect="delete", request_id=request)
    execute(session_factory, clock, world[3], world[0].workspace_id, op.operation_id)
    execute(session_factory, clock, world[3], world[0].workspace_id, op.operation_id)
    with session_factory() as db:
        assert db.get(Operation, op.operation_id).status == "succeeded"
        assert db.scalar(select(PublicComment)).state == "hidden"
        assert len(db.scalars(select(SimCommentEffect)).all()) == 1
        assert list(db.scalars(select(AgentAction))) == []


def test_manual_unknown_reserves_target_and_reconciles_same_operation(session_factory, clock):
    world, ctx, target = ready(session_factory, clock, "hide", "off")
    op = submit(session_factory, clock, world, target)
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
    execute(session_factory, clock, world[3], world[0].workspace_id, op.operation_id)
    with session_factory() as db:
        assert db.get(Operation, op.operation_id).status == "outcome_unknown"
    with pytest.raises(AppError):
        submit(session_factory, clock, world, target)
    execute(session_factory, clock, world[3], world[0].workspace_id, op.operation_id)
    reconcile(session_factory, clock, world[3], world[0].workspace_id, op.operation_id)
    with session_factory() as db:
        assert db.get(Operation, op.operation_id).status == "succeeded"
        assert len(db.scalars(select(SimCommentEffect)).all()) == 1


def test_member_demotion_cancels_unsubmitted_manual_effect(session_factory, clock):
    world, ctx, target = ready(session_factory, clock, "hide", "off")
    op = submit(session_factory, clock, world, target)
    with session_factory() as db:
        member = db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == world[0].workspace_id,
                WorkspaceMember.user_id == uuid.UUID(world[0].actor.id),
            )
        )
        member.role = "staff"
        db.commit()
    execute(session_factory, clock, world[3], world[0].workspace_id, op.operation_id)
    with session_factory() as db:
        assert db.get(Operation, op.operation_id).status == "cancelled"
        assert list(db.scalars(select(SimCommentEffect))) == []


def test_agent_pending_blocks_manual_and_manual_pending_blocks_agent(session_factory, clock):
    world, ctx, target = ready(session_factory, clock, "hide")
    propose(session_factory, clock, ctx, target, "hide")
    with pytest.raises(AppError):
        submit(session_factory, clock, world, target)


def test_manual_reservation_blocks_agent_proposal(session_factory, clock):
    world, ctx, target = ready(session_factory, clock, "hide")
    submit(session_factory, clock, world, target)
    with pytest.raises(AssertionError):
        propose(session_factory, clock, ctx, target, "hide")


@pytest.mark.parametrize(
    ("mode", "metric"), [("automatic", "agent_automatic_v1"), ("ask", "agent_approved_v1")]
)
def test_agent_metrics_count_verified_effects_from_ledger(session_factory, clock, mode, metric):
    from datetime import timedelta

    from app.approvals import service as approvals
    from app.approvals.models import Approval
    from app.operations.public_comments import execute as execute_agent
    from app.reporting.metrics import compute_metrics

    world, ctx, target = ready(session_factory, clock, "hide", mode)
    proposed = propose(session_factory, clock, ctx, target, "hide")
    if mode == "ask":
        with session_factory() as db:
            approval = db.get(Approval, uuid.UUID(proposed["approval_id"]))
            approvals.decide(
                db,
                clock,
                world[0],
                approval.id,
                decision="approve",
                payload_hash=approval.payload_hash,
            )
            db.commit()
    execute_agent(
        session_factory, clock, world[3], world[0].workspace_id, uuid.UUID(proposed["action_id"])
    )
    with session_factory() as db:
        metrics = compute_metrics(
            db,
            world[0],
            clock.now() - timedelta(minutes=1),
            clock.now() + timedelta(seconds=1),
            clock.now(),
        )
        assert metrics.value(metric) == 1
        assert (
            metrics.value("agent_approved_v1" if mode == "automatic" else "agent_automatic_v1") == 0
        )


@pytest.mark.parametrize("fence", ["deadline", "source_version", "disconnect"])
def test_manual_dispatch_rechecks_target_deadline_and_account(session_factory, clock, fence):
    from datetime import timedelta

    from app.integrations.instagram.models import SocialAccount

    world, ctx, target = ready(session_factory, clock, "hide", "off")
    op = submit(session_factory, clock, world, target)
    with session_factory() as db:
        if fence == "deadline":
            db.get(Operation, op.operation_id).deadline_at = clock.now() - timedelta(seconds=1)
        elif fence == "source_version":
            db.get(PublicComment, target[0]).version += 1
        else:
            db.get(SocialAccount, world[1]).status = "disconnected"
        db.commit()
    execute(session_factory, clock, world[3], world[0].workspace_id, op.operation_id)
    with session_factory() as db:
        assert db.get(Operation, op.operation_id).status == "cancelled"
        assert list(db.scalars(select(SimCommentEffect))) == []


def test_missing_manual_readback_stays_unknown_without_resend(session_factory, clock):
    world, ctx, target = ready(session_factory, clock, "hide", "off")
    op = submit(session_factory, clock, world, target)
    with session_factory() as db:
        operation = db.get(Operation, op.operation_id)
        operation.status = "in_progress"
        operation.attempts = 1
        operation.started_at = clock.now()
        db.commit()
    execute(session_factory, clock, world[3], world[0].workspace_id, op.operation_id)
    reconcile(session_factory, clock, world[3], world[0].workspace_id, op.operation_id)
    with session_factory() as db:
        assert db.get(Operation, op.operation_id).status == "outcome_unknown"
        assert list(db.scalars(select(SimCommentEffect))) == []


def test_different_members_reserve_one_target_and_concurrent_workers_call_once(
    session_factory, clock, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    from threading import Lock

    from app.core.context import ActorRef
    from app.identity.models import Workspace
    from app.integrations.instagram.mock import MockInstagramProvider
    from tests.factories import add_member, create_user

    world, _, target = ready(session_factory, clock, "hide", "off")
    with session_factory() as db:
        manager = create_user(db)
        workspace = db.get(Workspace, world[0].workspace_id)
        add_member(db, workspace, manager, "manager")
        manager_context = replace(world[0], actor=ActorRef.user(manager.id), role="manager")
        db.commit()
    manager_world = (manager_context, *world[1:])

    def attempt(actor_world):
        try:
            return submit(session_factory, clock, actor_world, target).operation_id
        except AppError as exc:
            return exc.code

    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(attempt, (world, manager_world)))
    operation_ids = [value for value in outcomes if isinstance(value, uuid.UUID)]
    assert len(operation_ids) == 1
    assert "CONFLICT_STATE" in outcomes
    with session_factory() as db:
        operations = list(
            db.scalars(select(Operation).where(Operation.subject_type == "public_comment"))
        )
        assert len(operations) == 1
        assert operations[0].status == "pending"

    calls = []
    guard = Lock()
    original = MockInstagramProvider.perform_comment_effect

    def counted(provider, *args, **kwargs):
        with guard:
            calls.append(args)
        return original(provider, *args, **kwargs)

    monkeypatch.setattr(MockInstagramProvider, "perform_comment_effect", counted)
    with ThreadPoolExecutor(2) as pool:
        list(
            pool.map(
                lambda _: execute(
                    session_factory, clock, world[3], world[0].workspace_id, operation_ids[0]
                ),
                range(2),
            )
        )
    assert len(calls) == 1
    with session_factory() as db:
        assert db.get(Operation, operation_ids[0]).attempts == 1
        assert db.get(Operation, operation_ids[0]).status == "succeeded"
        assert len(db.scalars(select(SimCommentEffect)).all()) == 1


def test_manual_finish_preserves_newer_source_even_with_cached_orm_target(session_factory, clock):
    from app.integrations.instagram.base import PublicEffectResult
    from app.operations.manual_comments import _finish

    world, _, target = ready(session_factory, clock, "hide", "off")
    submitted = submit(session_factory, clock, world, target)
    with session_factory() as finishing:
        operation = finishing.get(Operation, submitted.operation_id)
        operation.status = "in_progress"
        cached_target = finishing.get(PublicComment, target[0])
        finishing.commit()
        with session_factory() as source_update:
            current = source_update.get(PublicComment, target[0])
            current.version += 1
            current.text = "Newer native source body"
            source_update.commit()
        _finish(finishing, clock, operation, PublicEffectResult("verified-effect", "hidden"), None)
        finishing.commit()
        assert cached_target.version == target[1] + 1
    with session_factory() as db:
        source = db.get(PublicComment, target[0])
        assert source.version == target[1] + 1
        assert source.text == "Newer native source body"
        assert source.state == "visible"
        assert db.get(Operation, submitted.operation_id).status == "succeeded"


def test_manual_and_agent_admission_share_account_first_target_serialization(
    session_factory, clock
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    world, ctx, target = ready(session_factory, clock, "hide")
    start = Barrier(2)

    def manual():
        start.wait()
        try:
            submit(session_factory, clock, world, target)
            return "manual"
        except AppError as exc:
            return "blocked" if exc.code == "CONFLICT_STATE" else exc.code

    def agent():
        start.wait()
        try:
            propose(session_factory, clock, ctx, target, "hide")
            return "agent"
        except AssertionError:
            return "blocked"

    with ThreadPoolExecutor(2) as pool:
        manual_result = pool.submit(manual)
        agent_result = pool.submit(agent)
        outcomes = [manual_result.result(), agent_result.result()]
    assert outcomes.count("blocked") == 1
    with session_factory() as db:
        effects = len(list(db.scalars(select(AgentAction)))) + len(
            list(db.scalars(select(Operation).where(Operation.subject_type == "public_comment")))
        )
        assert effects == 1
        assert list(db.scalars(select(SimCommentEffect))) == []
