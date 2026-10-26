"""Scoped, uncommitted persistence operations for the account agent."""

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.agent.jobs import AgentWakePayload
from app.agent.models import AccountAgent, AgentAction, AgentEvent, AgentThread
from app.audit.service import record
from app.core.clock import Clock
from app.jobs.queue import enqueue


class AgentScopeError(ValueError):
    """An account or thread reference does not belong to the requested scope."""


def scoped_account(
    session: Session, workspace_id: uuid.UUID, account_id: uuid.UUID, *, lock: bool = False
) -> AccountAgent:
    query = select(AccountAgent).where(
        AccountAgent.workspace_id == workspace_id,
        AccountAgent.social_account_id == account_id,
    )
    if lock:
        query = query.with_for_update()
    account = session.scalar(query)
    if account is None:
        raise AgentScopeError("account agent not found")
    return account


def scoped_thread(
    session: Session,
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    thread_id: uuid.UUID,
    *,
    lock: bool = False,
) -> AgentThread:
    query = select(AgentThread).where(
        AgentThread.id == thread_id,
        AgentThread.workspace_id == workspace_id,
        AgentThread.social_account_id == account_id,
    )
    if lock:
        query = query.with_for_update()
    thread = session.scalar(query)
    if thread is None:
        raise AgentScopeError("agent thread not found")
    return thread


def add_event_and_wake(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    thread_id: uuid.UUID,
    kind: str,
    source_kind: str,
    source_key: str,
    source_id: str | None,
    source_version: int,
    clock: Clock,
) -> AgentEvent:
    """Deduplicate, allocate a monotonic cursor and enqueue in one caller transaction.

    The caller first stores the authoritative domain record. This operation never commits.
    A duplicate source returns the original event without a second logical wake.
    """
    # Account-first locking also serializes a duplicated source routed to two threads.
    account = scoped_account(session, workspace_id, account_id, lock=True)
    thread = scoped_thread(session, workspace_id, account_id, thread_id, lock=True)
    existing = session.scalar(
        select(AgentEvent).where(
            AgentEvent.workspace_id == workspace_id,
            AgentEvent.social_account_id == account_id,
            AgentEvent.source_kind == source_kind,
            AgentEvent.source_key == source_key,
        )
    )
    if existing is not None:
        if existing.thread_id != thread_id:
            raise AgentScopeError("source identity already belongs to another thread")
        return existing
    if account.controller_mode != "agent" or account.state != "active":
        raise AgentScopeError("account agent is inactive")
    if thread.controller_epoch != account.controller_epoch or thread.handling_mode != "agent":
        raise AgentScopeError("thread controller is stale")
    now = clock.now()
    thread.event_cursor += 1
    thread.thread_version += 1
    thread.last_activity_at = now
    event = AgentEvent(
        workspace_id=workspace_id,
        social_account_id=account_id,
        thread_id=thread_id,
        cursor=thread.event_cursor,
        kind=kind,
        source_kind=source_kind,
        source_key=source_key,
        source_id=source_id,
        source_version=source_version,
        created_at=now,
    )
    session.add(event)
    session.flush()
    enqueue(
        session,
        "agent_wake",
        AgentWakePayload(thread_id=thread_id),
        workspace_id=workspace_id,
        correlation_id=event.id,
        dedup_key=f"agent_wake:{thread_id}",
        clock=clock,
    )
    record(
        session,
        None,
        "agent.event_recorded",
        "agent_event",
        event.id,
        {"thread_id": thread_id, "cursor": event.cursor, "kind": kind},
        workspace_id=workspace_id,
        clock=clock,
    )
    return event


def stable_intent_key(
    *,
    account_id: uuid.UUID,
    thread_id: uuid.UUID,
    goal_key: str,
    source_key: str,
    action_type: str,
    target_ref: str,
    semantic_slot: str,
) -> str:
    """Server-built identity excludes model call IDs, text, and retry count."""
    parts = (
        str(account_id),
        str(thread_id),
        goal_key,
        source_key,
        action_type,
        target_ref,
        semantic_slot,
    )
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def admit_action(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    account_id: uuid.UUID,
    thread_id: uuid.UUID,
    session_id: uuid.UUID,
    source_event_id: uuid.UUID,
    action_type: str,
    target_ref: str,
    semantic_slot: str,
    payload_hash: str,
    clock: Clock,
) -> AgentAction:
    """Return the sole action for an event obligation, even when a model rewords it."""
    thread = scoped_thread(session, workspace_id, account_id, thread_id, lock=True)
    event = session.scalar(
        select(AgentEvent).where(
            AgentEvent.id == source_event_id,
            AgentEvent.workspace_id == workspace_id,
            AgentEvent.thread_id == thread.id,
        )
    )
    if event is None:
        raise AgentScopeError("source event not found in thread")
    from app.agent.models import AgentSession

    goal = session.scalar(
        select(AgentSession).where(
            AgentSession.id == session_id,
            AgentSession.workspace_id == workspace_id,
            AgentSession.thread_id == thread_id,
        )
    )
    if goal is None:
        raise AgentScopeError("agent session not found in thread")
    key = stable_intent_key(
        account_id=account_id,
        thread_id=thread_id,
        goal_key=goal.goal_key,
        source_key=f"{event.source_kind}:{event.source_key}",
        action_type=action_type,
        target_ref=target_ref,
        semantic_slot=semantic_slot,
    )
    candidate_id = uuid.uuid4()
    session.execute(
        pg_insert(AgentAction)
        .values(
            id=candidate_id,
            workspace_id=workspace_id,
            social_account_id=account_id,
            thread_id=thread_id,
            session_id=session_id,
            intent_key=key,
            action_type=action_type,
            payload_hash=payload_hash,
            target_ref=target_ref,
            initiating_event_id=source_event_id,
            initiating_cursor=event.cursor,
            status="proposed",
            created_at=clock.now(),
            updated_at=clock.now(),
        )
        .on_conflict_do_nothing(constraint="uq_agent_actions_workspace_id_thread_id_intent_key")
    )
    action = session.scalar(
        select(AgentAction).where(
            AgentAction.workspace_id == workspace_id,
            AgentAction.thread_id == thread_id,
            AgentAction.intent_key == key,
        )
    )
    if action is None:
        raise RuntimeError("action insert could not be resolved")
    if action.id == candidate_id:
        record(
            session,
            None,
            "agent.action_proposed",
            "agent_action",
            action.id,
            {"thread_id": thread_id, "action_type": action_type},
            workspace_id=workspace_id,
            clock=clock,
        )
    return action
