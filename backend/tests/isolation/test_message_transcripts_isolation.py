"""Isolation and Row-Level Security for message_transcripts (INV-01, F-03 Session 01).

Proves: forced RLS and the tenant policy exist; under the runtime role no row is visible without
a tenant context; one workspace cannot read, change, delete or insert into another workspace's
transcripts; a transcript cannot point at another workspace's message (composite FK); the status,
reason and uniqueness constraints hold. There is no endpoint for transcripts of their own: they are
read through the conversation and reply-draft routes (whose foreign-ID 404s the isolation suite
already covers) and through three read helpers, which the last test calls with a foreign workspace.
"""

import contextlib
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.db import clear_tenant_context, set_tenant_context
from app.identity.models import User, Workspace
from app.inbox.models import Message, MessageTranscript
from tests.factories import add_member, create_user, create_workspace
from tests.helpers.reporting import Builder
from tests.helpers.roles import ensure_runtime_roles

WHEN = datetime(2026, 11, 16, 10, 0, tzinfo=UTC)


@contextlib.contextmanager
def as_role(session: Session, role: str) -> Iterator[None]:
    ensure_runtime_roles(session)
    session.execute(text(f"SET LOCAL ROLE {role}"))
    session.execute(text("SET LOCAL search_path = public, pg_temp"))
    try:
        yield
    finally:
        session.execute(text("RESET ROLE"))


def world(session: Session, name: str) -> tuple[Workspace, User, Message]:
    workspace = create_workspace(session, name=name)
    user = create_user(session)
    add_member(session, workspace, user, "owner")
    builder = Builder(session, workspace, user)
    message = builder.message(builder.conversation(WHEN), "inbound", WHEN)
    session.flush()
    return workspace, user, message


def transcript(workspace: Workspace, message: Message, **values: object) -> MessageTranscript:
    return MessageTranscript(
        id=uuid.uuid4(), workspace_id=workspace.id, message_id=message.id, **values
    )


@pytest.mark.invariant("INV-01")
def test_the_table_has_forced_rls_and_the_tenant_policy(db_session: Session) -> None:
    row = db_session.execute(
        text(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = 'message_transcripts' AND relnamespace = 'public'::regnamespace"
        )
    ).one()
    assert tuple(row) == (True, True)
    policies = (
        db_session.execute(
            text(
                "SELECT polname FROM pg_policy "
                "WHERE polrelid = 'public.message_transcripts'::regclass"
            )
        )
        .scalars()
        .all()
    )
    assert policies == ["tenant_isolation_policy"]


@pytest.mark.invariant("INV-01")
def test_workspaces_see_only_their_own_transcripts(db_session: Session) -> None:
    ws_a, _, message_a = world(db_session, "Transcript A")
    ws_b, _, message_b = world(db_session, "Transcript B")
    set_tenant_context(db_session, ws_a.id)
    row_a = transcript(ws_a, message_a, status="succeeded", provider="fake", model="fake")
    row_a.text = "Merhaba"
    db_session.add(row_a)
    db_session.flush()
    set_tenant_context(db_session, ws_b.id)
    row_b = transcript(ws_b, message_b)
    db_session.add(row_b)
    db_session.commit()
    a_id, b_id = row_a.id, row_b.id
    db_session.expunge_all()

    clear_tenant_context(db_session)
    with as_role(db_session, "pivoris_app"):
        assert db_session.scalars(select(MessageTranscript)).all() == []  # fail closed

    set_tenant_context(db_session, ws_a.id)
    with as_role(db_session, "pivoris_app"):
        assert [r.id for r in db_session.scalars(select(MessageTranscript))] == [a_id]
        assert (
            db_session.execute(
                update(MessageTranscript).where(MessageTranscript.id == b_id).values(text="x")
            ).rowcount
            == 0
        )
        assert (
            db_session.execute(
                delete(MessageTranscript).where(MessageTranscript.id == b_id)
            ).rowcount
            == 0
        )

    set_tenant_context(db_session, ws_b.id)
    with as_role(db_session, "pivoris_app"):
        (only,) = db_session.scalars(select(MessageTranscript)).all()
        assert only.id == b_id and only.text is None and only.status == "pending"


@pytest.mark.invariant("INV-01")
def test_a_workspace_cannot_write_a_transcript_into_another(db_session: Session) -> None:
    ws_a, _, message_a = world(db_session, "Transcript W A")
    ws_b, _, message_b = world(db_session, "Transcript W B")
    set_tenant_context(db_session, ws_a.id)
    with as_role(db_session, "pivoris_app"):
        with pytest.raises(DBAPIError), db_session.begin_nested():
            db_session.execute(
                insert(MessageTranscript).values(
                    id=uuid.uuid4(), workspace_id=ws_b.id, message_id=message_b.id
                )
            )
        set_tenant_context(db_session, ws_b.id)
        assert db_session.scalars(select(MessageTranscript)).all() == []
    assert message_a.id != message_b.id


@pytest.mark.invariant("INV-01")
def test_a_transcript_cannot_point_at_another_workspaces_message(db_session: Session) -> None:
    ws_a, _, _ = world(db_session, "Transcript FK A")
    _, _, message_b = world(db_session, "Transcript FK B")
    db_session.add(transcript(ws_a, message_b))
    with pytest.raises(IntegrityError):
        db_session.flush()  # composite FK (workspace_id, message_id) -> messages
    db_session.rollback()


def test_the_constraints_hold(db_session: Session) -> None:
    ws, _, message = world(db_session, "Transcript Checks")
    db_session.add(transcript(ws, message))
    db_session.flush()

    def fresh_message() -> uuid.UUID:
        sibling = Message(
            workspace_id=ws.id,
            conversation_id=message.conversation_id,
            social_account_id=message.social_account_id,
            direction="inbound",
            sender_kind="customer",
            provider_timestamp=WHEN,
        )
        db_session.add(sibling)
        db_session.flush()
        return sibling.id

    def insert_bad(**values: object) -> None:
        db_session.add(
            MessageTranscript(id=uuid.uuid4(), workspace_id=ws.id, **values)  # type: ignore[arg-type]
        )
        db_session.flush()

    for bad in (
        {"message_id": message.id},  # one transcript per message
        {"status": "done"},
        {"status": "failed"},  # a failure needs a reason
        {"status": "succeeded"},  # a success needs its provider and model
        {"status": "pending", "reason_code": "VOICE_EXPIRED"},  # a reason only on a failure
        {"source": "typed"},
        {"attachment_index": -1},
    ):
        values = {"message_id": fresh_message(), **bad}
        with pytest.raises(IntegrityError), db_session.begin_nested():
            insert_bad(**values)


@pytest.mark.invariant("INV-01")
def test_the_read_paths_of_the_reply_flow_never_return_another_workspaces_transcript(
    db_session: Session,
) -> None:
    """F-03 Session 02: the drafting context, the inbox views and the agent guard all take the
    workspace from the caller and filter on it, so a foreign message id finds nothing."""
    from app.core.context import ActorRef, WorkspaceContext
    from app.inbox import views
    from app.inbox.context import transcripts_for
    from app.policy.transcripts import recent_transcript_present

    ws_a, _, _ = world(db_session, "Transcript Read A")
    ws_b, _, message_b = world(db_session, "Transcript Read B")
    row_b = transcript(ws_b, message_b, status="succeeded", provider="fake", model="fake")
    row_b.text = "Gizli aylık üyelik sorusu"
    db_session.add(row_b)
    db_session.flush()

    assert transcripts_for(db_session, ws_b.id, [message_b.id])[message_b.id].words
    assert transcripts_for(db_session, ws_a.id, [message_b.id]) == {}
    ctx_a = WorkspaceContext(ws_a.id, ActorRef.system("test"), None, "UTC", "tr", False)
    assert views.transcripts_by_message(db_session, ctx_a, [message_b.id]) == {}
    assert not recent_transcript_present(db_session, ws_a.id, message_b.conversation_id)
    assert recent_transcript_present(db_session, ws_b.id, message_b.conversation_id)
