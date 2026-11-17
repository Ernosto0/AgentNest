"""Retention of image descriptions (F-03, Session 03): what a model wrote about a customer's picture
goes with the message text at 365 days, the row and its metadata stay, a description of a younger
message is untouched, the run is idempotent and it is counted in the audit entry. There is no raw
image to expire: it is never stored."""

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.inbox.models import Message, MessageImageDescription
from tests.integration.retention.test_retention import NOW, World, ago, go


@pytest.fixture
def world(db_session: Session) -> World:
    return World(db_session)


def with_description(
    world: World, when: object, description: str
) -> tuple[Message, MessageImageDescription]:
    conversation = world.builder.conversation(when)  # type: ignore[arg-type]
    message = world.builder.message(conversation, "inbound", when)  # type: ignore[arg-type]
    row = MessageImageDescription(
        workspace_id=world.workspace.id,
        message_id=message.id,
        status="succeeded",
        looks_like="price_screenshot",
        description=description,
        visible_text="Aylık üyelik 1.500 TL",
        provider="fake",
        model="fake",
        media_type="image/png",
        image_bytes=1234,
    )
    world.session.add(row)
    world.session.flush()
    return message, row


def test_the_description_and_visible_text_are_nulled_with_the_message_text_at_365_days(
    db_session: Session, shared_session_factory, settings: Settings, world: World
) -> None:
    _, young = with_description(world, ago(365, -1), "genç kayıt")  # one second short of a year
    _, old = with_description(world, ago(365, 1), "eski kayıt")
    counts = go(db_session, shared_session_factory, settings)

    assert young.description == "genç kayıt" and young.visible_text and young.erased_at is None
    assert old.description is None and old.visible_text is None and old.erased_at == NOW
    # the row and what we know about it stay (INV-17 / ADR-022: only the words go)
    assert (old.status, old.looks_like, old.provider, old.image_bytes) == (
        "succeeded",
        "price_screenshot",
        "fake",
        1234,
    )
    assert counts.image_descriptions_nulled == 1
    assert counts.as_dict()["image_descriptions_nulled"] == 1


def test_a_second_run_changes_nothing(
    db_session: Session, shared_session_factory, settings: Settings, world: World
) -> None:
    with_description(world, ago(400), "eski")
    first = go(db_session, shared_session_factory, settings)
    second = go(db_session, shared_session_factory, settings)
    assert first.image_descriptions_nulled == 1 and second.image_descriptions_nulled == 0


def test_the_retention_period_follows_the_message_text_setting(
    db_session: Session, shared_session_factory, settings: Settings, world: World
) -> None:
    _, row = with_description(world, ago(40), "kırk günlük")
    shortened = settings.model_copy(update={"retention_message_text_days": 30})
    db_session.commit()
    from app.retention import cleanup

    cleanup.run_retention(shared_session_factory, shortened, NOW)
    db_session.expire_all()
    assert row.description is None and row.visible_text is None


def test_an_already_erased_row_is_not_counted_again(
    db_session: Session, shared_session_factory, settings: Settings, world: World
) -> None:
    _, row = with_description(world, ago(400), "eski")
    row.description = row.visible_text = None
    row.erased_at = ago(10)
    counts = go(db_session, shared_session_factory, settings)
    assert counts.image_descriptions_nulled == 0 and row.erased_at == ago(10)
