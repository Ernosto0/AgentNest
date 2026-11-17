"""Retention of voice-note transcripts (F-03): the words go with the message text at 365 days, the
row and its metadata stay, a transcript of a younger message is untouched, the run is idempotent
and it is counted in the audit entry. There is no raw audio to expire: it is never stored."""

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.inbox.models import Message, MessageTranscript
from tests.integration.retention.test_retention import NOW, World, ago, go


@pytest.fixture
def world(db_session: Session) -> World:
    return World(db_session)


def with_transcript(world: World, when: object, text: str) -> tuple[Message, MessageTranscript]:
    conversation = world.builder.conversation(when)  # type: ignore[arg-type]
    message = world.builder.message(conversation, "inbound", when)  # type: ignore[arg-type]
    row = MessageTranscript(
        workspace_id=world.workspace.id,
        message_id=message.id,
        status="succeeded",
        text=text,
        language="tr",
        provider="fake",
        model="fake",
        duration_seconds=6.0,
    )
    world.session.add(row)
    world.session.flush()
    return message, row


def test_the_transcript_text_is_nulled_with_the_message_text_at_365_days(
    db_session: Session, shared_session_factory, settings: Settings, world: World
) -> None:
    _, young = with_transcript(world, ago(365, -1), "genç kayıt")  # one second short of a year
    _, old = with_transcript(world, ago(365, 1), "eski kayıt")
    counts = go(db_session, shared_session_factory, settings)

    assert young.text == "genç kayıt" and young.erased_at is None
    assert old.text is None and old.erased_at == NOW
    # the row and what we know about it stay (INV-17 / ADR-022: only the words go)
    assert (old.status, old.language, old.provider, old.duration_seconds) == (
        "succeeded",
        "tr",
        "fake",
        6.0,
    )
    assert counts.transcripts_nulled == 1


def test_a_second_run_changes_nothing(
    db_session: Session, shared_session_factory, settings: Settings, world: World
) -> None:
    with_transcript(world, ago(400), "eski")
    first = go(db_session, shared_session_factory, settings)
    second = go(db_session, shared_session_factory, settings)
    assert first.transcripts_nulled == 1 and second.transcripts_nulled == 0


def test_the_retention_period_follows_the_message_text_setting(
    db_session: Session, shared_session_factory, settings: Settings, world: World
) -> None:
    _, row = with_transcript(world, ago(40), "kırk günlük")
    shortened = settings.model_copy(update={"retention_message_text_days": 30})
    db_session.commit()
    from app.retention import cleanup

    cleanup.run_retention(shared_session_factory, shortened, NOW)
    db_session.expire_all()
    assert row.text is None
