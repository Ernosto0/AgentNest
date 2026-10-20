"""Notification kinds of the content module (plan.md G14). Producers arrive with the publish
executor and the impact handlers; here the kinds, severities and recipients are defined."""

import pytest
from sqlalchemy import select

from app.content import notifications
from app.notifications.models import Notification
from tests.helpers.content import make_item
from tests.helpers.env import Env


def received(env: Env, kind: str) -> dict[str, Notification]:
    rows = env.session.scalars(select(Notification).where(Notification.type == kind)).all()
    return {str(n.recipient_user_id): n for n in rows}


def test_the_three_kinds_and_their_severities() -> None:
    assert notifications.KINDS == ("content.on_hold", "content.published", "content.failed")
    assert notifications.SEVERITY == {
        "content.on_hold": "attention",
        "content.published": "info",
        "content.failed": "attention",
    }


def test_on_hold_reaches_every_approver_including_the_person_who_caused_it(env: Env) -> None:
    item = make_item(env, status="on_hold", hold_reason="FACT_CHANGED", owner=env.staff)
    # The fact changer is the acting user: they are told too (unlike knowledge.fact_changed).
    created = notifications.notify(
        env.session,
        env.clock,
        env.ctx(env.owner),
        item,
        notifications.ON_HOLD,
        reason="FACT_CHANGED",
    )
    got = received(env, "content.on_hold")
    assert str(env.owner.user.id) in got and str(env.manager.user.id) in got
    assert str(env.staff.user.id) in got  # the author
    assert created == 3
    note = got[str(env.owner.user.id)]
    assert note.severity == "attention"
    assert (note.subject_type, note.subject_id) == ("content_item", item.id)
    assert note.params["reason"] == "FACT_CHANGED" and note.params["title"] == item.title
    assert "caption" not in note.params


def test_published_is_info_and_failed_is_attention(env: Env) -> None:
    item = make_item(env, status="published")
    notifications.notify(env.session, env.clock, env.ctx(env.owner), item, notifications.PUBLISHED)
    notifications.notify(
        env.session,
        env.clock,
        env.ctx(env.owner),
        item,
        notifications.FAILED,
        reason="MEDIA_REJECTED",
    )
    assert {n.severity for n in received(env, "content.published").values()} == {"info"}
    assert {n.severity for n in received(env, "content.failed").values()} == {"attention"}


def test_the_same_event_is_notified_once_until_read(env: Env) -> None:
    item = make_item(env, status="on_hold", hold_reason="ACCOUNT_UNAVAILABLE")
    ctx = env.ctx(env.owner)
    first = notifications.notify(env.session, env.clock, ctx, item, notifications.ON_HOLD)
    again = notifications.notify(env.session, env.clock, ctx, item, notifications.ON_HOLD)
    assert first > 0 and again == 0


def test_a_simulated_item_gives_simulated_notifications(env: Env) -> None:
    item = make_item(env, status="on_hold", is_simulated=True)
    notifications.notify(env.session, env.clock, env.ctx(env.owner), item, notifications.ON_HOLD)
    assert all(n.is_simulated for n in received(env, "content.on_hold").values())


def test_an_unknown_kind_is_refused(env: Env) -> None:
    item = make_item(env)
    with pytest.raises(ValueError):
        notifications.notify(env.session, env.clock, env.ctx(env.owner), item, "content.nope")
