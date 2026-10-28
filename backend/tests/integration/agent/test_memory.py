"""Attributable private memory through runtime, corrections and privacy boundaries."""

import json
import uuid
from dataclasses import replace

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.agent.coordinator import claim, fresh
from app.agent.models import AgentThread
from app.agent.tools.broker import build_default_broker
from app.core.errors import AppError
from app.inbox.models import Message, ReplyDraft
from app.integrations.llm.fake import FakeLLMProvider
from app.memory import service
from app.memory.models import (
    CustomerIdentity,
    CustomerMemory,
    MemorySource,
    MemoryVersion,
    SummaryVersion,
)
from app.retention.cleanup import run_retention
from tests.integration.agent.test_context_grounding import scenario
from tests.integration.agent.test_coordinator import deps, result
from tests.integration.agent.test_dm import deliver, drain, process_inbound, setup


def prepared(db, clock):
    context, workspace, source = scenario(db, clock)
    thread = db.get(AgentThread, context.thread_id)
    identity = service.resolve_identity(db, clock, thread)
    source.text = "I prefer evening schedule. I wear size M."
    source.external_message_id = uuid.uuid4().hex
    db.flush()
    return replace(context, memory_generation=identity.generation), identity, source


def learn(db, clock, context, source, topic="schedule", quote="I prefer evening schedule."):
    return service.write_proposal(
        db,
        clock,
        context,
        service.MemoryProposal(
            topic=topic, kind="preference", source_message_id=source.id, quote=quote
        ),
    )


def owner(context):
    return replace(context.workspace, role="owner")


def test_relevant_private_context_summary_refresh_and_public_denial(db_session, clock):
    ctx, identity, source = prepared(db_session, clock)
    first = learn(db_session, clock, ctx, source)
    learn(db_session, clock, ctx, source, "size", "I wear size M.")
    data = service.private_context(db_session, clock, ctx, "schedule")
    assert [m["topic"] for m in data["memories"]] == ["schedule"]
    assert "size M" not in data["summary"]["body"]
    assert service.private_context(db_session, clock, ctx, "weather")["memories"] == []
    assert (
        service.private_context(db_session, clock, replace(ctx, surface="comment"), "schedule")
        is None
    )
    public = replace(ctx, surface="comment")
    assert all(
        t.name not in {"memory.read", "memory.write"}
        for t in build_default_broker().available(public)
    )
    assert (
        build_default_broker()
        .dispatch(
            db_session,
            clock,
            public,
            name="memory.read",
            version="v1",
            arguments={"relevant_to": "schedule"},
        )
        .error
        == "TOOL_FORBIDDEN"
    )
    old_version = data["summary"]["version"]
    service.change(
        db_session,
        clock,
        owner(ctx),
        ctx.account_id,
        identity.id,
        uuid.UUID(first["memory_id"]),
        service.MemoryChange(expected_version=1, body="Customer prefers morning schedule."),
    )
    changed = service.private_context(db_session, clock, ctx, "schedule")
    assert changed["summary"]["version"] > old_version
    assert "morning" in changed["summary"]["body"] and "evening" not in changed["summary"]["body"]
    assert all(
        not s.body or "evening" not in s.body for s in db_session.scalars(select(SummaryVersion))
    )
    assert all(
        not v.body or "evening" not in v.body for v in db_session.scalars(select(MemoryVersion))
    )


def test_correction_forget_and_old_source_replay_fenced(db_session, clock):
    ctx, identity, source = prepared(db_session, clock)
    written = learn(db_session, clock, ctx, source)
    memory_id = uuid.UUID(written["memory_id"])
    service.change(
        db_session,
        clock,
        owner(ctx),
        ctx.account_id,
        identity.id,
        memory_id,
        service.MemoryChange(expected_version=1, body="I prefer morning schedule."),
    )
    with pytest.raises(ValueError, match="generation"):
        learn(db_session, clock, ctx, source)
    current = replace(ctx, memory_generation=identity.generation)
    with pytest.raises(ValueError, match="tombstone"):
        learn(db_session, clock, current, source)
    service.change(db_session, clock, owner(ctx), ctx.account_id, identity.id, memory_id, None)
    assert db_session.get(CustomerMemory, memory_id).body is None
    assert not service.export_customer(db_session, clock, owner(ctx), ctx.account_id, identity.id)[
        "memories"
    ]
    assert all(v.body is None for v in db_session.scalars(select(MemoryVersion)))
    # A newly received source can be learned at the same frozen instant: server source refs,
    # not provider or DB wall-clock timestamps, establish the privacy cutoff.
    new_source = Message(
        workspace_id=source.workspace_id,
        social_account_id=source.social_account_id,
        conversation_id=source.conversation_id,
        direction="inbound",
        sender_kind="customer",
        external_message_id=uuid.uuid4().hex,
        text="I prefer morning schedule.",
        provider_timestamp=source.provider_timestamp,
        created_at=clock.now(),
    )
    db_session.add(new_source)
    db_session.flush()
    learn(
        db_session,
        clock,
        replace(ctx, memory_generation=identity.generation),
        new_source,
        quote=new_source.text,
    )
    assert service.relevant(db_session, clock, identity, "schedule")[0]["body"] == new_source.text


def test_conflicting_customer_statements_version_and_duplicate(db_session, clock):
    ctx, identity, source = prepared(db_session, clock)
    learn(db_session, clock, ctx, source)
    other = Message(
        workspace_id=source.workspace_id,
        social_account_id=source.social_account_id,
        conversation_id=source.conversation_id,
        direction="inbound",
        sender_kind="customer",
        external_message_id=uuid.uuid4().hex,
        text="I prefer morning schedule. I wear size L.",
        provider_timestamp=clock.now(),
    )
    db_session.add(other)
    db_session.flush()
    updated = learn(db_session, clock, ctx, other, quote="I prefer morning schedule.")
    assert updated["version"] == 2
    current = replace(ctx, memory_generation=identity.generation)
    assert learn(db_session, clock, current, other, quote="I prefer morning schedule.")["duplicate"]
    learn(db_session, clock, current, other, "size", "I wear size L.")
    assert len(service.relevant(db_session, clock, identity, "size schedule")) == 2


@pytest.mark.parametrize(
    "quote", ["I am pregnant", "I am gay", "I prefer evening schedule but my password is abc"]
)
def test_sensitive_statements_never_stored(db_session, clock, quote):
    ctx, _, source = prepared(db_session, clock)
    source.text = quote
    db_session.flush()
    with pytest.raises(ValueError):
        learn(db_session, clock, ctx, source, quote=quote)
    assert db_session.scalar(select(func.count()).select_from(CustomerMemory)) == 0


def test_customer_claim_and_open_goal_are_never_business_fact_authority(db_session, clock):
    from app.agent.grounding import ReplyValidationArgs, validate_reply
    from app.knowledge.models import BusinessFact

    ctx, identity, source = prepared(db_session, clock)
    source.text = "I want a consultation service for 700 TL."
    db_session.flush()
    service.write_proposal(
        db_session,
        clock,
        ctx,
        service.MemoryProposal(
            topic="service", kind="open_goal", source_message_id=source.id, quote=source.text
        ),
    )
    stored = service.relevant(db_session, clock, identity, "consultation")
    assert stored[0]["kind"] == "open_goal"
    assert stored[0]["authority"] == "customer_statement_only"
    assert db_session.scalar(select(func.count()).select_from(BusinessFact)) == 0
    checked = validate_reply(
        db_session,
        clock,
        ctx,
        ReplyValidationArgs(template="Our consultation service costs 700 TL.", language="en"),
    )
    assert not checked.valid


def test_forged_source_scope_and_identity_never_merge(db_session, clock):
    ctx, identity, source = prepared(db_session, clock)
    other_ctx, other_identity, foreign = prepared(db_session, clock)
    assert identity.id != other_identity.id
    memory_id = uuid.UUID(learn(db_session, clock, ctx, source)["memory_id"])
    with pytest.raises(ValueError, match="source"):
        learn(db_session, clock, ctx, foreign)
    broker = build_default_broker()
    assert not broker.dispatch(
        db_session,
        clock,
        ctx,
        name="memory.write",
        version="v1",
        arguments={
            "topic": "schedule",
            "kind": "verified_business_fact",
            "source_message_id": str(source.id),
            "quote": "I prefer evening schedule.",
        },
    ).ok
    with pytest.raises(IntegrityError), db_session.begin_nested():  # noqa: PT012
        db_session.add(
            MemorySource(
                workspace_id=identity.workspace_id,
                social_account_id=identity.social_account_id,
                customer_identity_id=other_identity.id,
                memory_id=memory_id,
                source_key="forged",
                memory_version=1,
                message_id=foreign.id,
                observed_at=clock.now(),
            )
        )
        db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():  # noqa: PT012
        db_session.add(
            MemorySource(
                workspace_id=identity.workspace_id,
                social_account_id=identity.social_account_id,
                customer_identity_id=identity.id,
                memory_id=memory_id,
                source_key="foreign-source",
                memory_version=1,
                message_id=foreign.id,
                observed_at=clock.now(),
            )
        )
        db_session.flush()
    # A foreign linked identity in a thread is rejected by a real composite FK.
    with pytest.raises(IntegrityError), db_session.begin_nested():  # noqa: PT012
        thread = db_session.get(AgentThread, ctx.thread_id)
        thread.customer_identity_id = other_identity.id
        db_session.flush()


def test_source_removal_clears_history_summaries_and_replay(db_session, clock):
    ctx, identity, source = prepared(db_session, clock)
    learn(db_session, clock, ctx, source)
    service.private_context(db_session, clock, ctx, "schedule")
    source.is_deleted = True
    service.erase_source(db_session, clock, source)
    assert all(m.body is None for m in db_session.scalars(select(CustomerMemory)))
    assert all(s.body is None for s in db_session.scalars(select(SummaryVersion)))
    assert all(s.query_hash == "" for s in db_session.scalars(select(SummaryVersion)))
    assert all(s.removed and s.message_id is None for s in db_session.scalars(select(MemorySource)))
    assert not service.export_customer(db_session, clock, owner(ctx), ctx.account_id, identity.id)[
        "memories"
    ]
    external_id = source.external_message_id
    conversation_id = source.conversation_id
    db_session.delete(source)
    db_session.flush()
    replay = Message(
        workspace_id=ctx.workspace.workspace_id,
        social_account_id=ctx.account_id,
        conversation_id=conversation_id,
        direction="inbound",
        sender_kind="customer",
        external_message_id=external_id,
        text="I prefer evening schedule.",
        provider_timestamp=clock.now(),
    )
    db_session.add(replay)
    db_session.flush()
    with pytest.raises(ValueError, match="tombstone"):
        learn(db_session, clock, replace(ctx, memory_generation=identity.generation), replay)


def test_memory_export_erase_owner_only_and_scope(db_session, clock):
    ctx, identity, source = prepared(db_session, clock)
    learn(db_session, clock, ctx, source)
    service.private_context(db_session, clock, ctx, "schedule")
    assert service.export_customer(db_session, clock, owner(ctx), ctx.account_id, identity.id)[
        "sources"
    ]
    for role in ("staff", "manager"):
        with pytest.raises(AppError) as err:
            service.export_customer(
                db_session, clock, replace(ctx.workspace, role=role), ctx.account_id, identity.id
            )
        assert err.value.code == "FORBIDDEN"
        with pytest.raises(AppError):
            service.erase_customer(
                db_session, clock, replace(ctx.workspace, role=role), ctx.account_id, identity.id
            )
    service.erase_customer(db_session, clock, owner(ctx), ctx.account_id, identity.id)
    data = service.export_customer(db_session, clock, owner(ctx), ctx.account_id, identity.id)
    assert data["memories"] == data["sources"] == data["summaries"] == []


@pytest.mark.commits
def test_real_loop_returning_customer_after_new_goal_worker_restart(
    session_factory, clock, monkeypatch
):
    world = setup(session_factory, clock)
    deliver(session_factory, clock, world, "I prefer evening schedule. I wear size M.")
    process_inbound(session_factory, clock)
    with session_factory() as db:
        source = db.scalar(select(Message).where(Message.direction == "inbound"))
        source_id = source.id
    first = FakeLLMProvider()
    first.queue_step(
        result(
            "tool",
            tool_name="memory.write",
            tool_arguments={
                "topic": "schedule",
                "kind": "preference",
                "source_message_id": str(source_id),
                "quote": "I prefer evening schedule.",
            },
        )
    )
    first.queue_step(
        result(
            "tool",
            tool_name="memory.write",
            tool_arguments={
                "topic": "size",
                "kind": "preference",
                "source_message_id": str(source_id),
                "quote": "I wear size M.",
            },
        )
    )
    first.queue_step(result())
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, first))
    drain(session_factory, clock)
    clock.advance(seconds=5)
    deliver(session_factory, clock, world, "Can we discuss my schedule?")
    restarted = FakeLLMProvider()
    restarted.queue_step(result())
    monkeypatch.setattr(
        "app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, restarted)
    )
    drain(session_factory, clock)
    body = restarted.step_calls[0].messages[0].content
    memory_section = json.loads(
        body.split("<untrusted_agent_context>")[1].split("</untrusted_agent_context>")[0]
    )["customer_memory"]
    assert [m["topic"] for m in memory_section["memories"]] == ["schedule"]
    assert (
        "evening" in memory_section["summary"]["body"]
        and "size M" not in memory_section["summary"]["body"]
    )
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(CustomerIdentity)) == 1


@pytest.mark.commits
@pytest.mark.parametrize("change_kind", ["correct", "forget", "erase", "source"])
def test_model_inflight_generation_fenced(session_factory, clock, change_kind):
    world = setup(session_factory, clock)
    deliver(session_factory, clock, world, "I prefer evening schedule.")
    process_inbound(session_factory, clock)
    with session_factory() as db:
        thread = db.scalar(select(AgentThread))
        thread_id = thread.id
        source = db.scalar(select(Message).where(Message.direction == "inbound"))
        source_id = source.id
    runner = deps(session_factory, clock)
    captured = claim(runner, world[0].workspace_id, thread_id)
    with session_factory() as db:
        source = db.get(Message, source_id)
        written = learn(db, clock, captured.context, source)
        identity = db.scalar(select(CustomerIdentity))
        if change_kind == "erase":
            service.erase_customer(db, clock, world[0], world[1], identity.id)
        elif change_kind == "source":
            source.is_deleted = True
            service.erase_source(db, clock, source)
        else:
            service.change(
                db,
                clock,
                world[0],
                world[1],
                identity.id,
                uuid.UUID(written["memory_id"]),
                service.MemoryChange(expected_version=1, body="I prefer morning schedule.")
                if change_kind == "correct"
                else None,
            )
        db.commit()
    with session_factory() as db:
        assert fresh(db, runner, captured) is None
        with pytest.raises(ValueError):
            learn(db, clock, captured.context, db.get(Message, source_id))
        db.commit()


def test_retention_sweep_removes_memory_versions_sources_and_draft_validation(
    db_session, shared_session_factory, clock, settings
):
    ctx, identity, source = prepared(db_session, clock)
    learn(db_session, clock, ctx, source)
    service.private_context(db_session, clock, ctx, "schedule")
    draft = ReplyDraft(
        workspace_id=source.workspace_id,
        conversation_id=source.conversation_id,
        covers_through_message_id=source.id,
        source="ai",
        status="sent",
        created_by_actor_type="agent",
        decision="auto",
        text="private response",
        validation={"agent_proposal": {"template": "personal proposal"}},
        created_at=clock.now(),
    )
    db_session.add(draft)
    db_session.commit()
    clock.advance(days=366)
    counts = run_retention(shared_session_factory, settings, clock.now(), batch_size=2)
    db_session.expire_all()
    assert counts.memories_nulled == 1
    assert db_session.get(CustomerMemory, db_session.scalar(select(CustomerMemory.id))).body is None
    assert db_session.get(ReplyDraft, draft.id).validation == {}
    assert all(v.body is None for v in db_session.scalars(select(MemoryVersion)))
    assert all(v.body is None for v in db_session.scalars(select(SummaryVersion)))
    assert (
        run_retention(shared_session_factory, settings, clock.now(), batch_size=2).memories_nulled
        == 0
    )
