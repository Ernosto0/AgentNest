"""Signed inbound -> durable agent -> existing mock send ledger, with real commits."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.agent.control import ControllerChange, change_controller
from app.agent.coordinator import claim, fresh
from app.agent.delegation import apply
from app.agent.dm import send
from app.agent.grounding import ReplyValidationArgs
from app.agent.jobs import AgentRecoverPayload, agent_recover
from app.agent.models import AccountAgent, AgentAction, AgentSession, AgentThread
from app.agent.tools.broker import BrokerContext
from app.approvals import service as approvals
from app.approvals.models import Approval
from app.core.config import Settings
from app.core.errors import RetryableError
from app.inbox.ingest import ingest_webhook
from app.inbox.models import Message, ReplyDraft
from app.inbox.service import release, takeover
from app.integrations.instagram import webhook_format as wf
from app.integrations.instagram.models import (
    SimFailureRule,
    SimInboundMessage,
    SimSentMessage,
    SocialAccount,
)
from app.integrations.llm.fake import FakeLLMProvider
from app.jobs.models import Job
from app.jobs.queue import claim_one
from app.jobs.registry import JobContext
from app.jobs.worker import execute_job
from app.operations.send import execute_send_reply
from tests.factories import knowledge_ctx, workspace_with_members
from tests.integration.agent.test_coordinator import deps, result
from tests.integration.agent.test_delegation import _change, _policy

pytestmark = pytest.mark.commits


def setup(factory, clock, mode="automatic", daily_limit=None):
    settings = Settings(
        _env_file=None,
        llm_provider="fake",
        instagram_enabled_providers="mock",
        media_storage_backend="local",
    )
    with factory() as db:
        workspace, users = workspace_with_members(db, default_locale="en")
        workspace.reply_languages = ["en", "tr"]
        ctx = knowledge_ctx(workspace, users["owner"], "owner")
        social = SocialAccount(
            workspace_id=workspace.id,
            provider_kind="mock",
            external_account_id=uuid.uuid4().hex,
            capabilities={"messaging": True},
            status="connected",
        )
        db.add(social)
        db.flush()
        account = db.scalar(select(AccountAgent).where(AccountAgent.social_account_id == social.id))
        policy = _policy(dm=mode)
        policy.actions["dm.send"].max_per_day = daily_limit
        apply(db, clock, ctx, social.id, _change(policy, account.config_version, None))
        change_controller(
            db,
            clock,
            ctx,
            social.id,
            ControllerChange(
                expected_config_version=account.config_version, client_request_id=uuid.uuid4()
            ),
        )
        db.commit()
        return ctx, social.id, social.external_account_id, settings


def deliver(
    factory,
    clock,
    world,
    text="Hello, what services do you offer?",
    mid=None,
    echo=False,
    customer="customer-one",
):
    ctx, account_id, external, settings = world
    mid = mid or uuid.uuid4().hex
    payload = wf.build_message_payload(external, customer, mid, text, clock.now())
    if echo:
        payload = wf.build_echo_payload(external, "customer-one", mid, text, clock.now())
    raw = wf.serialize(payload)
    with factory() as db:
        if (
            not echo
            and db.scalar(select(SimInboundMessage.id).where(SimInboundMessage.mid == mid)) is None
        ):
            db.add(
                SimInboundMessage(
                    workspace_id=ctx.workspace_id,
                    social_account_id=account_id,
                    sender_id=customer,
                    mid=mid,
                    received_at=clock.now(),
                )
            )
            db.commit()
        return ingest_webhook(
            db,
            clock,
            settings,
            "mock",
            raw,
            {
                wf.SIGNATURE_HEADER: wf.sign(
                    raw, settings.mock_instagram_app_secret.get_secret_value()
                )
            },
        )


def drain(factory, clock, max_jobs=30):
    for _ in range(max_jobs):
        job = claim_one(factory, clock, f"worker-{uuid.uuid4().hex}", 120)
        if job is None:
            return
        assert execute_job(factory, clock, job, lease_seconds=120) == "succeeded"
    pytest.fail("job loop did not settle")


def process_inbound(factory, clock):
    for _ in range(10):
        job = claim_one(factory, clock, "inbound-only", 120)
        assert job is not None
        assert execute_job(factory, clock, job, lease_seconds=120) == "succeeded"
        if job.job_type == "process_inbound_event":
            return
    pytest.fail("inbound job missing")


def reply(fake, template="Hello! How can I help?", **kw):
    args = ReplyValidationArgs(template=template, language="en", **kw)
    fake.queue_step(
        result("tool", tool_name="dm.send", tool_arguments=args.model_dump(mode="json"))
    )


def test_signed_multi_turn_agent_sends_and_observes_verified_ledger(
    session_factory, clock, monkeypatch
):
    world = setup(session_factory, clock)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    for question, answer in [
        ("Hello, what do you offer?", "Hello! What would you like help with?"),
        ("I need a recommendation, can you help?", "What are your preferences?"),
        (
            "I prefer something simple, what do you suggest?",
            "We can discuss a simple option together.",
        ),
        ("Thanks, can we continue?", "Yes! What else would you like to discuss?"),
    ]:
        deliver(session_factory, clock, world, question)
        reply(fake, answer)
        fake.queue_step(result())
        drain(session_factory, clock)
        assert fake.step_calls[-1].observations[0].result["status"] == "succeeded"
        clock.advance(timedelta(seconds=2))
    with session_factory() as db:
        assert len(db.scalars(select(SimSentMessage)).all()) == 4
        assert all(
            row.origin == "agent" and row.status == "sent" for row in db.scalars(select(ReplyDraft))
        )
        assert not db.scalars(select(Approval).where(Approval.status == "pending")).all()


@pytest.mark.parametrize("mode", ["ask", "off"])
def test_ask_uses_original_human_decision_and_off_never_sends(
    session_factory, clock, monkeypatch, mode
):
    world = setup(session_factory, clock, mode)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    deliver(session_factory, clock, world)
    reply(fake)
    if mode == "off":
        fake.queue_step(result())
    drain(session_factory, clock)
    with session_factory() as db:
        assert not db.scalars(select(SimSentMessage)).all()
        action = db.scalar(select(AgentAction))
        if mode == "off":
            assert action.status == "cancelled"
            return
        approval = db.get(Approval, action.approval_id)
        assert approval.subject_type == "agent_action" and approval.status == "pending"
        original_id = approval.id
        approvals.decide(
            db, clock, world[0], approval.id, decision="approve", payload_hash=approval.payload_hash
        )
        db.commit()
    fake.queue_step(result())
    # Force an approval wake ahead of the queued send, as concurrent workers can.
    with session_factory() as db:
        wake_job = db.scalar(
            select(Job).where(Job.job_type == "agent_wake", Job.status == "queued")
        )
        assert wake_job is not None
        wake_job.priority = 1
        db.commit()
    early = claim_one(session_factory, clock, "approval-before-send", 120)
    assert early.job_type == "agent_wake"
    assert execute_job(session_factory, clock, early, lease_seconds=120) == "succeeded"
    assert len(fake.step_calls) == 1
    with session_factory() as db:
        assert db.scalar(select(AgentSession)).status == "waiting_operation"
        assert not db.scalars(select(SimSentMessage)).all()
    drain(session_factory, clock)
    with session_factory() as db:
        draft = db.scalar(select(ReplyDraft))
        approval = db.get(Approval, original_id)
        assert draft.status == "sent" and draft.approval_id == original_id
        assert str(approval.decided_by_user_id) == world[0].actor.id
        assert fake.step_calls[-1].observations[0].result["status"] == "succeeded"


def test_duplicate_webhook_and_takeover_release_aba_fence_old_result(
    session_factory, clock, monkeypatch
):
    world = setup(session_factory, clock)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    assert deliver(session_factory, clock, world, mid="same").received == 1
    assert deliver(session_factory, clock, world, mid="same").duplicates == 1
    # Process just inbound, then claim a model step before a human takes/releases control.
    process_inbound(session_factory, clock)
    with session_factory() as db:
        thread = db.scalar(select(AgentThread))
        tid, conversation_id = thread.id, thread.dm_conversation_id
    captured = claim(deps(session_factory, clock), world[0].workspace_id, tid)
    assert captured is not None
    with session_factory() as db:
        takeover(db, clock, world[0], conversation_id)
        release(db, clock, world[0], conversation_id)
    with session_factory() as db:
        assert fresh(db, deps(session_factory, clock), captured) is None
        db.commit()
        assert len(db.scalars(select(Message).where(Message.direction == "inbound")).all()) == 1


def test_timeout_after_success_reserves_slot_across_new_inbound_and_reword(
    session_factory, clock, monkeypatch
):
    world = setup(session_factory, clock)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    with session_factory() as db:
        db.add(
            SimFailureRule(
                workspace_id=world[0].workspace_id,
                social_account_id=world[1],
                operation="send",
                mode="timeout_after_success",
                remaining=1,
            )
        )
        db.commit()
    deliver(session_factory, clock, world)
    reply(fake)
    drain(session_factory, clock)
    with session_factory() as db:
        action = db.scalar(select(AgentAction))
        thread = db.scalar(select(AgentThread))
        context = BrokerContext(world[0], world[1], thread.id, "dm", "customer")
        first = action.id
    deliver(session_factory, clock, world, "Hello again, please answer me")
    # Run inbound only; uncertain operation blocks another differently worded proposal.
    process_inbound(session_factory, clock)
    with session_factory() as db:
        again = send(
            db, clock, context, ReplyValidationArgs(template="Different greeting!", language="en")
        )
        db.commit()
        assert again["action_id"] == str(first) and again["status"] == "outcome_unknown"
        assert len(db.scalars(select(SimSentMessage)).all()) == 1
        assert len(db.scalars(select(AgentAction)).all()) == 1


def test_epoch_adoption_resume_does_not_strand_existing_thread(session_factory, clock, monkeypatch):
    world = setup(session_factory, clock)
    deliver(session_factory, clock, world)
    process_inbound(session_factory, clock)
    with session_factory() as db:
        account = db.scalar(select(AccountAgent))
        from app.agent.control import adopt_threads

        account.state = "paused"
        account.controller_epoch += 1
        adopt_threads(db, clock, account)
        db.commit()
    clock.advance(timedelta(days=2))
    with session_factory() as db:
        account = db.scalar(select(AccountAgent))
        account.state = "active"
        account.controller_epoch += 1
        adopt_threads(db, clock, account)
        db.commit()
        thread = db.scalar(select(AgentThread))
        tid = thread.id
    assert claim(deps(session_factory, clock), world[0].workspace_id, tid) is not None


def project_until_send_job(factory, clock):
    for _ in range(15):
        job = claim_one(factory, clock, "before-dispatch", 120)
        assert job is not None
        if job.job_type == "send_reply":
            return job
        assert execute_job(factory, clock, job, lease_seconds=120) == "succeeded"
    pytest.fail("send job missing")


def test_crash_after_result_commit_before_wake_is_recovered_without_second_effect(
    session_factory, clock, monkeypatch
):
    world = setup(session_factory, clock)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    deliver(session_factory, clock, world)
    reply(fake)
    job = project_until_send_job(session_factory, clock)
    with session_factory() as db:
        draft_id = db.scalar(select(ReplyDraft.id))
    import app.operations.send as send_module

    original = send_module._wake_agent
    monkeypatch.setattr(
        send_module,
        "_wake_agent",
        lambda *a: (_ for _ in ()).throw(RuntimeError("worker crashed after T5")),
    )
    with pytest.raises(RuntimeError, match="after T5"):
        execute_send_reply(session_factory, clock, world[3], world[0].workspace_id, draft_id)
    monkeypatch.setattr(send_module, "_wake_agent", original)
    with session_factory() as db:
        assert db.scalar(select(ReplyDraft)).status == "sent"
        assert db.scalar(select(AgentAction)).operation_id is None
        assert len(db.scalars(select(SimSentMessage)).all()) == 1
    fake.queue_step(result())
    agent_recover(
        JobContext(
            uuid.uuid4(),
            "agent_recover",
            None,
            None,
            AgentRecoverPayload(),
            1,
            3,
            session_factory,
            clock,
            lambda: None,
        )
    )
    drain(session_factory, clock)
    with session_factory() as db:
        assert db.scalar(select(AgentSession)).status == "completed"
        assert len(db.scalars(select(SimSentMessage)).all()) == 1
    assert fake.step_calls[-1].observations[0].result["status"] == "succeeded"
    assert job.job_type == "send_reply"


def test_account_contention_releases_executor_without_deadlock_or_effect(
    session_factory, clock, monkeypatch
):
    world = setup(session_factory, clock)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    deliver(session_factory, clock, world)
    reply(fake)
    project_until_send_job(session_factory, clock)
    with session_factory() as db:
        draft_id = db.scalar(select(ReplyDraft.id))
        db.scalar(
            select(AccountAgent).where(AccountAgent.social_account_id == world[1]).with_for_update()
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                execute_send_reply,
                session_factory,
                clock,
                world[3],
                world[0].workspace_id,
                draft_id,
            )
            with pytest.raises(RetryableError, match="CONFLICT_STATE"):
                future.result(timeout=5)
        assert not db.scalars(select(SimSentMessage)).all()
        db.commit()
    assert (
        execute_send_reply(session_factory, clock, world[3], world[0].workspace_id, draft_id).kind
        == "sent"
    )
    with session_factory() as db:
        assert len(db.scalars(select(SimSentMessage)).all()) == 1


def test_legacy_job_queued_before_cutover_never_calls_legacy_model(
    session_factory, clock, monkeypatch
):
    world = setup(session_factory, clock)
    with session_factory() as db:
        account = db.scalar(select(AccountAgent))
        change_controller(
            db,
            clock,
            world[0],
            world[1],
            ControllerChange(
                expected_config_version=account.config_version,
                client_request_id=uuid.uuid4(),
                mode="legacy",
            ),
        )
        db.commit()
    deliver(session_factory, clock, world)
    process_inbound(session_factory, clock)
    with session_factory() as db:
        account = db.scalar(select(AccountAgent))
        change_controller(
            db,
            clock,
            world[0],
            world[1],
            ControllerChange(
                expected_config_version=account.config_version, client_request_id=uuid.uuid4()
            ),
        )
        db.commit()
    monkeypatch.setattr(
        "app.inbox.jobs.make_plan", lambda *a, **k: pytest.fail("stale legacy job ran model")
    )
    clock.advance(timedelta(minutes=1))
    drain(session_factory, clock)
    with session_factory() as db:
        assert not db.scalars(select(ReplyDraft)).all()


def test_new_inbound_before_dispatch_cancels_old_exact_reply(session_factory, clock, monkeypatch):
    world = setup(session_factory, clock)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    deliver(session_factory, clock, world)
    reply(fake)
    project_until_send_job(session_factory, clock)
    with session_factory() as db:
        old_id = db.scalar(select(ReplyDraft.id))
    clock.advance(timedelta(seconds=1))
    deliver(session_factory, clock, world, "Wait, I have a different question")
    process_inbound(session_factory, clock)
    assert (
        execute_send_reply(session_factory, clock, world[3], world[0].workspace_id, old_id).kind
        == "failed"
    )
    with session_factory() as db:
        assert not db.scalars(select(SimSentMessage)).all()
        assert db.get(ReplyDraft, old_id).status == "cancelled"


def test_cutover_racing_claimed_send_never_dispatches_displaced_controller(
    session_factory, clock, monkeypatch
):
    world = setup(session_factory, clock)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    deliver(session_factory, clock, world)
    reply(fake)
    project_until_send_job(session_factory, clock)
    with session_factory() as db:
        draft_id = db.scalar(select(ReplyDraft.id))
        account = db.scalar(select(AccountAgent))
        change_controller(
            db,
            clock,
            world[0],
            world[1],
            ControllerChange(
                expected_config_version=account.config_version,
                client_request_id=uuid.uuid4(),
                mode="legacy",
            ),
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                execute_send_reply,
                session_factory,
                clock,
                world[3],
                world[0].workspace_id,
                draft_id,
            )
            with pytest.raises(RetryableError):
                future.result(timeout=5)
        db.commit()
    assert (
        execute_send_reply(session_factory, clock, world[3], world[0].workspace_id, draft_id).kind
        == "failed"
    )
    with session_factory() as db:
        assert not db.scalars(select(SimSentMessage)).all()


def test_disconnect_erase_unlinks_agent_thread_and_fences_slow_step(session_factory, clock):
    from app.operations.accounts import disconnect

    world = setup(session_factory, clock)
    deliver(session_factory, clock, world)
    process_inbound(session_factory, clock)
    with session_factory() as db:
        thread_id = db.scalar(select(AgentThread.id))
    captured = claim(deps(session_factory, clock), world[0].workspace_id, thread_id)
    with session_factory() as db:
        disconnect(db, clock, world[0], world[1], delete_conversation_data=True)
    with session_factory() as db:
        assert fresh(db, deps(session_factory, clock), captured) is None
        db.commit()
        assert db.get(AgentThread, thread_id).dm_conversation_id is None
        assert not db.scalars(select(Message)).all()


def test_two_human_approvals_cannot_bypass_delegation_daily_limit(
    session_factory, clock, monkeypatch
):
    from app.core.errors import AppError

    world = setup(session_factory, clock, mode="ask", daily_limit=1)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    for customer in ("first-customer", "second-customer"):
        deliver(session_factory, clock, world, customer=customer)
        reply(fake)
        drain(session_factory, clock)
    with session_factory() as db:
        pending = db.scalars(
            select(Approval).where(Approval.status == "pending").order_by(Approval.id)
        ).all()
        assert len(pending) == 2
        approvals.decide(
            db,
            clock,
            world[0],
            pending[0].id,
            decision="approve",
            payload_hash=pending[0].payload_hash,
        )
        db.commit()
    with session_factory() as db:
        with pytest.raises(AppError, match="APPROVAL_STALE"):
            approvals.decide(
                db,
                clock,
                world[0],
                pending[1].id,
                decision="approve",
                payload_hash=pending[1].payload_hash,
            )
        db.rollback()
    fake.queue_step(result())
    drain(session_factory, clock)
    with session_factory() as db:
        assert len(db.scalars(select(SimSentMessage)).all()) == 1


def test_release_routes_latest_customer_message_accumulated_during_human_control(
    session_factory, clock, monkeypatch
):
    world = setup(session_factory, clock)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    deliver(session_factory, clock, world)
    process_inbound(session_factory, clock)
    with session_factory() as db:
        thread = db.scalar(select(AgentThread))
        conversation_id = thread.dm_conversation_id
        takeover(db, clock, world[0], conversation_id)
    clock.advance(timedelta(seconds=1))
    deliver(session_factory, clock, world, "Hello, I have a new question while you are here")
    from app.inbox.models import InboundEvent
    from app.inbox.processing import process_inbound_event

    with session_factory() as db:
        inbound = db.scalar(select(InboundEvent).where(InboundEvent.status == "received"))
        process_inbound_event(db, clock, world[0].workspace_id, inbound.id, debounce_seconds=0)
        release(db, clock, world[0], conversation_id)
    reply(fake, "Hello! What is your new question?")
    fake.queue_step(result())
    drain(session_factory, clock)
    with session_factory() as db:
        assert db.scalar(select(AgentThread)).event_cursor == 2
        assert len(db.scalars(select(SimSentMessage)).all()) == 1
        newest = db.scalars(
            select(Message)
            .where(Message.direction == "inbound")
            .order_by(Message.provider_timestamp.desc())
        ).first()
        assert db.scalar(select(ReplyDraft)).covers_through_message_id == newest.id


def test_release_after_native_answer_does_not_reanswer_old_customer_event(
    session_factory, clock, monkeypatch
):
    from app.inbox.models import InboundEvent
    from app.inbox.processing import process_inbound_event

    world = setup(session_factory, clock)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    deliver(session_factory, clock, world)
    process_inbound(session_factory, clock)
    deliver(session_factory, clock, world, "The owner has answered", echo=True)
    with session_factory() as db:
        inbound = db.scalar(select(InboundEvent).where(InboundEvent.status == "received"))
        process_inbound_event(db, clock, world[0].workspace_id, inbound.id, debounce_seconds=0)
        conversation_id = db.scalar(select(AgentThread.dm_conversation_id))
        release(db, clock, world[0], conversation_id)
    drain(session_factory, clock)
    assert not fake.step_calls
    with session_factory() as db:
        assert not db.scalars(select(SimSentMessage)).all()


def test_same_timestamp_burst_uses_cursor_source_not_uuid_order(
    session_factory, clock, monkeypatch
):
    from app.inbox.models import InboundEvent
    from app.inbox.processing import process_inbound_event

    world = setup(session_factory, clock)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    ids = iter(
        [
            uuid.UUID("11111111-1111-4111-8111-111111111111"),
            uuid.UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
            uuid.UUID("22222222-2222-4222-8222-222222222222"),
            uuid.UUID("00000000-0000-4000-8000-000000000001"),
        ]
    )
    monkeypatch.setattr("app.inbox.processing.new_id", lambda: next(ids))
    for mid, question in (
        ("burst-first", "Hello, what services do you offer?"),
        ("burst-latest", "Wait, which option do you recommend?"),
    ):
        deliver(session_factory, clock, world, question, mid=mid)
        with session_factory() as db:
            inbound = db.scalar(select(InboundEvent).where(InboundEvent.status == "received"))
            process_inbound_event(db, clock, world[0].workspace_id, inbound.id, debounce_seconds=0)
    reply(fake, "What are your preferences?")
    fake.queue_step(result())
    drain(session_factory, clock)
    with session_factory() as db:
        assert len(db.scalars(select(SimSentMessage)).all()) == 1
        assert db.scalar(select(ReplyDraft)).covers_through_message_id == uuid.UUID(
            "00000000-0000-4000-8000-000000000001"
        )
        assert db.scalar(select(AgentThread)).event_cursor == 2
    body = fake.step_calls[0].messages[0].content
    assert "what services" in body and "which option" in body


def test_release_resumes_new_human_inbound_after_native_answer_with_equal_timestamp(
    session_factory, clock, monkeypatch
):
    from app.inbox.models import InboundEvent
    from app.inbox.processing import process_inbound_event

    world = setup(session_factory, clock)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))
    deliver(session_factory, clock, world)
    process_inbound(session_factory, clock)
    # Every provider timestamp is equal; actual committed arrival order disambiguates.
    for text, echo in (("The owner has answered", True), ("Hello, I have another question", False)):
        deliver(session_factory, clock, world, text, echo=echo)
        with session_factory() as db:
            inbound = db.scalar(select(InboundEvent).where(InboundEvent.status == "received"))
            process_inbound_event(db, clock, world[0].workspace_id, inbound.id, debounce_seconds=0)
    with session_factory() as db:
        conversation_id = db.scalar(select(AgentThread.dm_conversation_id))
        release(db, clock, world[0], conversation_id)
    reply(fake, "Hello! What is your other question?")
    fake.queue_step(result())
    drain(session_factory, clock)
    with session_factory() as db:
        assert len(db.scalars(select(SimSentMessage)).all()) == 1
        assert db.scalar(select(AgentThread)).event_cursor == 2
