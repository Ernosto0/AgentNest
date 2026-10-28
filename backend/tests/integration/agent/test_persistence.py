"""Committed agent-state invariants and tenant/account isolation (P7.5-02)."""

import threading
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.agent.models import AccountAgent, AgentAction, AgentEvent, AgentSession, AgentThread
from app.agent.repository import AgentScopeError, add_event_and_wake, admit_action
from app.agent.transitions import StaleAgentState, transition_session
from app.core.clock import FrozenClock
from app.identity.models import Workspace
from app.inbox.models import Conversation
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job

pytestmark = pytest.mark.commits


def _account(factory: sessionmaker[Session], *, suffix: str) -> tuple[uuid.UUID, uuid.UUID]:
    with factory() as session:
        workspace = Workspace(
            name="Test",
            slug=f"agent-{suffix}-{uuid.uuid4().hex[:6]}",
            business_category="services",
            market="global",
            default_locale="en",
            timezone="UTC",
            currency="USD",
        )
        session.add(workspace)
        session.flush()
        account = SocialAccount(
            workspace_id=workspace.id,
            provider_kind="mock",
            external_account_id=f"{suffix}-{uuid.uuid4().hex}",
        )
        session.add(account)
        session.flush()
        account_agent = session.scalar(
            select(AccountAgent).where(
                AccountAgent.workspace_id == workspace.id,
                AccountAgent.social_account_id == account.id,
            )
        )
        assert account_agent is not None
        assert (
            account_agent.controller_mode,
            account_agent.state,
            account_agent.controller_epoch,
        ) == (
            "legacy",
            "inactive",
            0,
        )
        session.commit()
        return workspace.id, account.id


def _thread(
    factory: sessionmaker[Session],
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    *,
    source: str = "customer",
) -> uuid.UUID:
    with factory() as session:
        account = session.scalar(
            select(AccountAgent).where(
                AccountAgent.workspace_id == workspace_id,
                AccountAgent.social_account_id == account_id,
            )
        )
        assert account is not None
        account.controller_mode = "agent"
        account.state = "active"
        account.controller_epoch = 1
        conversation = Conversation(
            workspace_id=workspace_id,
            social_account_id=account_id,
            customer_external_id=source,
        )
        session.add(conversation)
        session.flush()
        thread = AgentThread(
            workspace_id=workspace_id,
            social_account_id=account_id,
            surface="dm",
            source_ref=str(conversation.id),
            dm_conversation_id=conversation.id,
            controller_epoch=1,
        )
        session.add(thread)
        session.commit()
        return thread.id


def _event(
    factory: sessionmaker[Session],
    clock: FrozenClock,
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    thread_id: uuid.UUID,
    key: str,
) -> AgentEvent:
    with factory() as session:
        event = add_event_and_wake(
            session,
            workspace_id=workspace_id,
            account_id=account_id,
            thread_id=thread_id,
            kind="customer_message",
            source_kind="inbound_event",
            source_key=key,
            source_id=None,
            source_version=1,
            clock=clock,
        )
        session.commit()
        return event


def test_new_accounts_start_legacy_and_cross_account_dm_fk_is_rejected(
    session_factory: sessionmaker[Session],
) -> None:
    workspace_id, account_a = _account(session_factory, suffix="a")
    with session_factory() as session:
        account_b = SocialAccount(
            workspace_id=workspace_id,
            provider_kind="mock",
            external_account_id=f"b-{uuid.uuid4().hex}",
            status="disconnected",
        )
        session.add(account_b)
        session.flush()
        conversation = Conversation(
            workspace_id=workspace_id, social_account_id=account_a, customer_external_id="one"
        )
        session.add(conversation)
        session.flush()
        session.add(
            AgentThread(
                workspace_id=workspace_id,
                social_account_id=account_b.id,
                surface="dm",
                source_ref=str(conversation.id),
                dm_conversation_id=conversation.id,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()


def test_event_and_wake_are_atomic_and_replay_keeps_cursor(
    session_factory: sessionmaker[Session],
    clock: FrozenClock,
) -> None:
    workspace_id, account_id = _account(session_factory, suffix="event")
    thread_id = _thread(session_factory, workspace_id, account_id)
    first = _event(session_factory, clock, workspace_id, account_id, thread_id, "k1")
    second = _event(session_factory, clock, workspace_id, account_id, thread_id, "k1")
    assert first.id == second.id and second.cursor == 1
    with session_factory() as session:
        assert (
            session.scalar(select(AgentThread.event_cursor).where(AgentThread.id == thread_id)) == 1
        )
        assert (
            session.scalar(select(Job).where(Job.dedup_key == f"agent_wake:{thread_id}:1"))
            is not None
        )
        assert len(session.scalars(select(AgentEvent)).all()) == 1

    with session_factory() as session:
        add_event_and_wake(
            session,
            workspace_id=workspace_id,
            account_id=account_id,
            thread_id=thread_id,
            kind="customer_message",
            source_kind="inbound_event",
            source_key="rolled-back",
            source_id=None,
            source_version=1,
            clock=clock,
        )
        session.rollback()
    with session_factory() as session:
        assert (
            session.scalar(select(AgentThread.event_cursor).where(AgentThread.id == thread_id)) == 1
        )
        assert (
            session.scalar(select(AgentEvent).where(AgentEvent.source_key == "rolled-back")) is None
        )


def test_racing_duplicate_events_admit_one_cursor(
    session_factory: sessionmaker[Session],
    clock: FrozenClock,
) -> None:
    workspace_id, account_id = _account(session_factory, suffix="race")
    thread_id = _thread(session_factory, workspace_id, account_id)
    gate = threading.Barrier(2)
    ids: list[uuid.UUID] = []
    errors: list[Exception] = []

    def write() -> None:
        try:
            gate.wait()
            ids.append(
                _event(session_factory, clock, workspace_id, account_id, thread_id, "same").id
            )
        except Exception as exc:
            errors.append(exc)

    workers = [threading.Thread(target=write) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert not errors
    assert len(set(ids)) == 1
    with session_factory() as session:
        assert (
            session.scalar(select(AgentThread.event_cursor).where(AgentThread.id == thread_id)) == 1
        )


def test_stable_intent_blocks_rewording_and_cas_rejects_stale(
    session_factory: sessionmaker[Session],
    clock: FrozenClock,
) -> None:
    workspace_id, account_id = _account(session_factory, suffix="intent")
    thread_id = _thread(session_factory, workspace_id, account_id)
    event = _event(session_factory, clock, workspace_id, account_id, thread_id, "request")
    with session_factory() as session:
        goal = AgentSession(
            workspace_id=workspace_id,
            thread_id=thread_id,
            initiating_event_cursor=event.cursor,
            goal_key="goal-1",
        )
        session.add(goal)
        session.commit()
        goal_id = goal.id
    with session_factory() as session:
        kwargs = {
            "workspace_id": workspace_id,
            "account_id": account_id,
            "thread_id": thread_id,
            "session_id": goal_id,
            "source_event_id": event.id,
            "action_type": "dm.send",
            "target_ref": "recipient",
            "semantic_slot": "reply:1",
            "clock": clock,
        }
        first = admit_action(session, payload_hash="a" * 64, **kwargs)
        second = admit_action(session, payload_hash="b" * 64, **kwargs)
        assert first.id == second.id and second.payload_hash == "a" * 64
        assert (
            transition_session(
                session,
                workspace_id=workspace_id,
                session_id=goal_id,
                expected_status="queued",
                expected_version=1,
                next_status="running",
                clock=clock,
            )
            == 2
        )
        with pytest.raises(StaleAgentState):
            transition_session(
                session,
                workspace_id=workspace_id,
                session_id=goal_id,
                expected_status="queued",
                expected_version=1,
                next_status="running",
                clock=clock,
            )
        session.commit()
    with session_factory() as session:
        assert session.scalar(select(AgentAction.payload_hash)) == "a" * 64
        assert session.scalar(select(AgentSession.model_steps)) == 0


def test_one_active_goal_per_thread_and_scoped_references(
    session_factory: sessionmaker[Session],
    clock: FrozenClock,
) -> None:
    workspace_id, account_id = _account(session_factory, suffix="active")
    thread_id = _thread(session_factory, workspace_id, account_id)
    foreign_ws, foreign_account = _account(session_factory, suffix="foreign")
    foreign_thread = _thread(session_factory, foreign_ws, foreign_account)
    with session_factory() as session:
        session.add(
            AgentSession(
                workspace_id=workspace_id,
                thread_id=thread_id,
                initiating_event_cursor=0,
                goal_key="one",
            )
        )
        session.flush()
        with pytest.raises(AgentScopeError):
            add_event_and_wake(
                session,
                workspace_id=workspace_id,
                account_id=account_id,
                thread_id=foreign_thread,
                kind="bad",
                source_kind="test",
                source_key="bad",
                source_id=None,
                source_version=1,
                clock=clock,
            )
        session.add(
            AgentSession(
                workspace_id=workspace_id,
                thread_id=thread_id,
                initiating_event_cursor=0,
                goal_key="two",
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()


def test_action_rejects_other_accounts_operation_and_content_origin(
    session_factory: sessionmaker[Session],
    clock: FrozenClock,
) -> None:
    workspace_id, account_id = _account(session_factory, suffix="action-account")
    thread_id = _thread(session_factory, workspace_id, account_id)
    event = _event(session_factory, clock, workspace_id, account_id, thread_id, "source")
    with session_factory() as session:
        other = SocialAccount(
            workspace_id=workspace_id,
            provider_kind="mock",
            external_account_id=f"other-{uuid.uuid4().hex}",
            status="disconnected",
        )
        session.add(other)
        goal = AgentSession(
            workspace_id=workspace_id,
            thread_id=thread_id,
            initiating_event_cursor=1,
            goal_key="goal",
        )
        session.add(goal)
        session.flush()
        action = admit_action(
            session,
            workspace_id=workspace_id,
            account_id=account_id,
            thread_id=thread_id,
            session_id=goal.id,
            source_event_id=event.id,
            action_type="content.publish",
            target_ref="item",
            semantic_slot="publish:1",
            payload_hash="c" * 64,
            clock=clock,
        )
        other_id, action_id = other.id, action.id
        session.commit()

    operation_id = uuid.uuid4()
    with session_factory() as session:
        session.execute(
            text(
                "INSERT INTO operations "
                "(id,workspace_id,social_account_id,operation_type,idempotency_key,"
                "subject_type,subject_id,provider_kind) "
                "VALUES (:id,:w,:a,'send_reply',:key,'reply_draft',:subject,'mock')"
            ),
            {
                "id": operation_id,
                "w": workspace_id,
                "a": other_id,
                "key": f"other-{operation_id}",
                "subject": uuid.uuid4(),
            },
        )
        session.commit()
    with session_factory() as session, pytest.raises(IntegrityError):
        session.execute(
            text("UPDATE agent_actions SET operation_id=:op WHERE id=:action"),
            {"op": operation_id, "action": action_id},
        )

    with session_factory() as session, pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO content_items "
                "(id,workspace_id,social_account_id,origin,agent_action_id,"
                "content_type,status,title) "
                "VALUES (:id,:w,:a,'agent',:action,'feed_image','draft','foreign')"
            ),
            {"id": uuid.uuid4(), "w": workspace_id, "a": other_id, "action": action_id},
        )
