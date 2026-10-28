"""Scoped APIs and privacy fences on already projected replies/unknown sends."""

import uuid
from dataclasses import replace

import pytest
from sqlalchemy import select

from app.agent.context import assemble
from app.agent.coordinator import claim, run_activation
from app.agent.dm import send
from app.agent.grounding import ReplyValidationArgs
from app.agent.models import AgentThread
from app.agent.tools.broker import BrokerContext, build_default_broker
from app.audit.models import AuditLog
from app.inbox.models import Conversation, Message, ReplyDraft
from app.inbox.views import draft_out
from app.integrations.instagram.models import SimFailureRule, SimSentMessage
from app.integrations.llm.fake import FakeLLMProvider
from app.memory import service
from app.memory.models import CustomerIdentity, MemoryVersion
from app.operations import accounts, conversation_deletion
from app.operations.models import Operation
from app.operations.reconcile import reconcile_send
from app.operations.send import execute_send_reply
from tests.helpers.env import build_env
from tests.integration.agent.test_coordinator import deps, result
from tests.integration.agent.test_delegation import _account
from tests.integration.agent.test_dm import deliver, process_inbound, setup
from tests.integration.agent.test_memory import learn, owner, prepared


def test_memory_routes_roles_pagination_real_foreign_ids_and_redaction(
    db_session, make_client, clock
):
    env = build_env(db_session, make_client, clock)
    social, _ = _account(env)
    conversation = Conversation(
        workspace_id=env.workspace.id,
        social_account_id=social.id,
        customer_external_id=uuid.uuid4().hex,
    )
    db_session.add(conversation)
    db_session.flush()
    thread = AgentThread(
        workspace_id=env.workspace.id,
        social_account_id=social.id,
        surface="dm",
        source_ref=str(conversation.id),
        dm_conversation_id=conversation.id,
    )
    db_session.add(thread)
    db_session.flush()
    identity = service.resolve_identity(db_session, clock, thread)
    ctx = BrokerContext(
        env.ctx(env.owner), social.id, thread.id, "dm", "customer", identity.generation
    )
    source = Message(
        workspace_id=env.workspace.id,
        social_account_id=social.id,
        conversation_id=conversation.id,
        direction="inbound",
        sender_kind="customer",
        external_message_id=uuid.uuid4().hex,
        text="I prefer evening schedule. I wear size M.",
        provider_timestamp=clock.now(),
    )
    db_session.add(source)
    db_session.flush()
    first = learn(db_session, clock, ctx, source)
    learn(db_session, clock, ctx, source, "size", "I wear size M.")
    db_session.commit()
    base = f"/accounts/{social.id}/customers/{identity.id}"
    first_page = env.call(env.staff, "GET", base + "/memory?limit=1").json()
    assert len(first_page["items"]) == 1 and first_page["next_cursor"]
    second = env.call(
        env.owner, "GET", base + "/memory?limit=1&cursor=" + first_page["next_cursor"]
    ).json()
    assert len(second["items"]) == 1 and second["items"][0]["id"] != first_page["items"][0]["id"]
    assert len(env.call(env.owner, "GET", base + "/sources?limit=1").json()["items"]) == 1
    path = base + f"/memory/{first['memory_id']}/correct"
    body = {"expected_version": 1, "body": "I prefer morning schedule."}
    assert env.call(env.staff, "POST", path, json=body).status_code == 403
    assert env.call(env.manager, "POST", path, json=body).status_code == 200
    correction = db_session.scalar(select(AuditLog).where(AuditLog.action == "memory.corrected"))
    assert correction.actor_id == str(env.manager.user.id)
    assert correction.metadata_["memory_id"] == first["memory_id"]
    assert correction.metadata_["memory_version"] == 2
    version = db_session.scalar(
        select(MemoryVersion).where(
            MemoryVersion.memory_id == uuid.UUID(first["memory_id"]), MemoryVersion.version == 2
        )
    )
    assert version.author_user_id == env.manager.user.id
    assert env.call(env.owner, "POST", path, json=body).status_code == 409
    another = CustomerIdentity(
        workspace_id=env.workspace.id,
        social_account_id=social.id,
        provider_subject_hash=uuid.uuid4().hex,
        evidence_kind="provider_dm_participant",
        created_at=clock.now(),
    )
    db_session.add(another)
    db_session.flush()
    assert (
        env.call(
            env.owner,
            "POST",
            f"/accounts/{social.id}/customers/{another.id}/memory/{first['memory_id']}/forget",
        ).status_code
        == 404
    )
    foreign_ctx, foreign_identity, foreign_source = prepared(db_session, clock)
    foreign_memory = learn(db_session, clock, foreign_ctx, foreign_source)
    for foreign_path in (
        f"/accounts/{foreign_ctx.account_id}/customers/{identity.id}/memory",
        f"/accounts/{social.id}/customers/{foreign_identity.id}/memory",
        f"/accounts/{social.id}/customers/{foreign_identity.id}/sources",
    ):
        assert env.call(env.owner, "GET", foreign_path).status_code == 404
    assert (
        env.call(
            env.owner, "POST", base + f"/memory/{foreign_memory['memory_id']}/forget"
        ).status_code
        == 404
    )
    assert (
        env.call(env.manager, "POST", base + f"/memory/{first['memory_id']}/forget").status_code
        == 200
    )
    assert "evening" not in env.call(env.owner, "GET", base + "/memory").text
    assert "morning" not in env.call(env.owner, "GET", base + "/memory").text
    assert all(
        s["removed"] and s["message_id"] is None
        for s in env.call(env.owner, "GET", base + "/sources").json()["items"]
        if s["memory_id"] == first["memory_id"]
    )


def test_same_handle_is_never_identity_evidence_and_public_context_is_empty(db_session, clock):
    ctx, identity, source = prepared(db_session, clock)
    learn(db_session, clock, ctx, source)
    conversation = db_session.get(Conversation, source.conversation_id)
    conversation.customer_handle = "same_display_name"
    other = Conversation(
        workspace_id=source.workspace_id,
        social_account_id=source.social_account_id,
        customer_external_id=uuid.uuid4().hex,
        customer_handle=conversation.customer_handle,
    )
    db_session.add(other)
    db_session.flush()
    thread = AgentThread(
        workspace_id=source.workspace_id,
        social_account_id=source.social_account_id,
        surface="dm",
        source_ref=str(other.id),
        dm_conversation_id=other.id,
    )
    db_session.add(thread)
    db_session.flush()
    other_identity = service.resolve_identity(db_session, clock, thread)
    assert other_identity.id != identity.id
    thread.surface = "comment"
    thread.dm_conversation_id = None
    thread.customer_identity_id = identity.id
    db_session.flush()
    public = replace(ctx, thread_id=thread.id, surface="comment")
    assert "evening schedule" not in assemble(db_session, clock, public).messages[0].content


@pytest.mark.commits
@pytest.mark.parametrize("privacy", ["correct", "forget", "source"])
def test_projected_old_memory_reply_cannot_send_after_privacy_change(
    session_factory, clock, privacy
):
    world = setup(session_factory, clock)
    deliver(session_factory, clock, world, "I prefer evening schedule.")
    process_inbound(session_factory, clock)
    with session_factory() as db:
        thread_id = db.scalar(select(AgentThread.id))
    captured = claim(deps(session_factory, clock), world[0].workspace_id, thread_id)
    with session_factory() as db:
        source = db.scalar(select(Message).where(Message.direction == "inbound"))
        written = learn(db, clock, captured.context, source)
        send(
            db,
            clock,
            captured.context,
            ReplyValidationArgs(template="Let us discuss your evening schedule.", language="en"),
        )
        draft = db.scalar(select(ReplyDraft))
        draft_id = draft.id
        assert draft.status == "queued"
        identity = db.scalar(select(CustomerIdentity))
        if privacy == "source":
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
                if privacy == "correct"
                else None,
            )
        db.commit()
    assert (
        execute_send_reply(session_factory, clock, world[3], world[0].workspace_id, draft_id).kind
        == "skipped"
    )
    with session_factory() as db:
        assert not db.scalars(select(SimSentMessage)).all()
        assert db.get(ReplyDraft, draft_id).text is None
        assert db.get(ReplyDraft, draft_id).status == "cancelled"


def test_correction_preserves_sent_business_outcome_and_inbox_text(db_session, clock):
    ctx, identity, source = prepared(db_session, clock)
    written = learn(db_session, clock, ctx, source)
    draft = ReplyDraft(
        workspace_id=source.workspace_id,
        conversation_id=source.conversation_id,
        covers_through_message_id=source.id,
        source="ai",
        status="sent",
        created_by_actor_type="agent",
        decision="auto",
        text="Thank you for contacting us.",
        validation={"agent_proposal": {"template": "old private cached proposal"}},
        created_at=clock.now(),
    )
    db_session.add(draft)
    db_session.flush()
    sent_message = Message(
        workspace_id=source.workspace_id,
        social_account_id=source.social_account_id,
        conversation_id=source.conversation_id,
        direction="outbound",
        sender_kind="business_app",
        reply_draft_id=draft.id,
        text=draft.text,
        provider_timestamp=clock.now(),
    )
    db_session.add(sent_message)
    db_session.flush()
    service.change(
        db_session,
        clock,
        owner(ctx),
        ctx.account_id,
        identity.id,
        uuid.UUID(written["memory_id"]),
        service.MemoryChange(expected_version=1, body="I prefer morning schedule."),
    )
    db_session.refresh(draft)
    assert draft.text == "Thank you for contacting us."
    assert "agent_proposal" not in draft.validation
    assert (
        draft_out(
            db_session, owner(ctx), draft, db_session.get(Conversation, source.conversation_id)
        ).text
        == draft.text
    )
    assert sent_message.text == "Thank you for contacting us."
    sent_id = sent_message.id
    service.change(
        db_session,
        clock,
        owner(ctx),
        ctx.account_id,
        identity.id,
        uuid.UUID(written["memory_id"]),
        None,
    )
    db_session.refresh(draft)
    db_session.refresh(sent_message)
    assert draft.status == "sent" and draft.text == "Thank you for contacting us."
    assert sent_message.id == sent_id and sent_message.text == draft.text
    assert (
        draft_out(
            db_session, owner(ctx), draft, db_session.get(Conversation, source.conversation_id)
        ).text
        == draft.text
    )
    assert len(db_session.scalars(select(Message)).all()) == 2


@pytest.mark.commits
def test_disconnect_erases_memory_immediately_with_unknown_send_and_hides_cache(
    session_factory, clock
):
    world = setup(session_factory, clock)
    deliver(session_factory, clock, world, "I prefer evening schedule.")
    process_inbound(session_factory, clock)
    with session_factory() as db:
        thread_id = db.scalar(select(AgentThread.id))
    captured = claim(deps(session_factory, clock), world[0].workspace_id, thread_id)
    with session_factory() as db:
        source = db.scalar(select(Message).where(Message.direction == "inbound"))
        learn(db, clock, captured.context, source)
        service.private_context(db, clock, captured.context, "schedule")
        send(
            db,
            clock,
            captured.context,
            ReplyValidationArgs(template="Let us discuss your evening schedule.", language="en"),
        )
        draft = db.scalar(select(ReplyDraft))
        operation = Operation(
            workspace_id=world[0].workspace_id,
            social_account_id=world[1],
            operation_type="send_reply",
            idempotency_key=f"send_reply:{draft.id}",
            subject_type="reply_draft",
            subject_id=draft.id,
            provider_kind="mock",
            status="outcome_unknown",
            attempts=1,
            max_attempts=6,
            is_simulated=True,
        )
        db.add(operation)
        db.flush()
        draft.status, draft.operation_id = "outcome_unknown", operation.id
        identity_id = db.scalar(select(CustomerIdentity.id))
        db.commit()
    with session_factory() as db:
        accounts.disconnect(db, clock, world[0], world[1], delete_conversation_data=True)
    with session_factory() as db:
        assert db.scalar(select(Operation)).status == "outcome_unknown"
        assert conversation_deletion.pending(db, world[0].workspace_id, account_id=world[1])
        exported = service.export_customer(db, clock, world[0], world[1], identity_id)
        assert exported["memories"] == exported["summaries"] == exported["sources"] == []
        retained = db.scalar(select(ReplyDraft))
        assert retained.text
        assert retained.template is None and "agent_proposal" not in retained.validation
        conversation = db.get(Conversation, retained.conversation_id)
        assert draft_out(db, world[0], retained, conversation).text is None
        assert all(m.text is None and not m.attachments for m in db.scalars(select(Message)))


@pytest.mark.commits
@pytest.mark.parametrize("disconnect", [False, True])
def test_erasure_unknown_send_reconciles_without_resurrecting_message_body(
    session_factory, clock, disconnect
):
    world = setup(session_factory, clock)
    deliver(session_factory, clock, world, "I prefer evening schedule.")
    process_inbound(session_factory, clock)
    with session_factory() as db:
        thread_id = db.scalar(select(AgentThread.id))
    captured = claim(deps(session_factory, clock), world[0].workspace_id, thread_id)
    with session_factory() as db:
        source = db.scalar(select(Message).where(Message.direction == "inbound"))
        learn(db, clock, captured.context, source)
        send(
            db,
            clock,
            captured.context,
            ReplyValidationArgs(template="Let us discuss your evening schedule.", language="en"),
        )
        draft_id = db.scalar(select(ReplyDraft.id))
        identity_id = db.scalar(select(CustomerIdentity.id))
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
    execute_send_reply(session_factory, clock, world[3], world[0].workspace_id, draft_id)
    with session_factory() as db:
        operation = db.scalar(select(Operation))
        operation_id = operation.id
        assert operation.status == "outcome_unknown"
        assert len(db.scalars(select(SimSentMessage)).all()) == 1
        if disconnect:
            accounts.disconnect(db, clock, world[0], world[1], delete_conversation_data=True)
        else:
            service.erase_customer(db, clock, world[0], world[1], identity_id)
            db.commit()
    assert (
        reconcile_send(session_factory, clock, world[3], world[0].workspace_id, operation_id)
        == "sent"
    )
    with session_factory() as db:
        draft = db.get(ReplyDraft, draft_id)
        assert draft.status == "sent" and draft.text is None
        messages = db.scalars(select(Message).where(Message.direction == "outbound")).all()
        assert len(messages) == 1 and messages[0].text is None
        assert db.get(Operation, operation_id).status == "succeeded"
        assert len(db.scalars(select(SimSentMessage)).all()) == 1
        assert (
            draft_out(db, world[0], draft, db.get(Conversation, draft.conversation_id)).text is None
        )


@pytest.mark.commits
@pytest.mark.parametrize("forget", [False, True])
def test_actual_model_return_after_privacy_change_is_discarded(
    session_factory, clock, monkeypatch, forget
):
    world = setup(session_factory, clock)
    deliver(session_factory, clock, world, "I prefer evening schedule.")
    process_inbound(session_factory, clock)
    with session_factory() as db:
        source = db.scalar(select(Message).where(Message.direction == "inbound"))
        source_id = source.id
        thread = db.scalar(select(AgentThread))
        thread_id = thread.id
        identity = service.resolve_identity(db, clock, thread)
        identity_id = identity.id
        context = BrokerContext(
            world[0], world[1], thread.id, "dm", "customer", identity.generation
        )
        memory_id = uuid.UUID(learn(db, clock, context, source)["memory_id"])
        db.commit()
    fake = FakeLLMProvider()
    calls = []

    def generate(request):
        calls.append(request)
        # This callback stands in for a slow model: the caller has released its DB
        # transaction, and a different request commits a privacy change before return.
        with session_factory() as db:
            if forget:
                service.erase_customer(db, clock, world[0], world[1], identity_id)
            else:
                service.change(
                    db,
                    clock,
                    world[0],
                    world[1],
                    identity_id,
                    memory_id,
                    service.MemoryChange(expected_version=1, body="I prefer morning schedule."),
                )
            db.commit()
        return result(
            "tool",
            tool_name="memory.write",
            tool_arguments={
                "topic": "schedule",
                "kind": "preference",
                "source_message_id": str(source_id),
                "quote": "I prefer evening schedule.",
            },
        )

    monkeypatch.setattr(fake, "generate_step", generate)
    run_activation(
        deps(session_factory, clock, fake), world[0].workspace_id, thread_id, build_default_broker()
    )
    with session_factory() as db:
        data = service.export_customer(db, clock, world[0], world[1], identity_id)
        assert "evening" not in str(data)
        assert (
            (data["memories"] == [])
            if forget
            else (data["memories"][0]["body"] == "I prefer morning schedule.")
        )
        assert len(calls) == 1
