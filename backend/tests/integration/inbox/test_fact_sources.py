"""D-01: every value of a draft shows the fact it came from and when that was verified, from a
server-provided mapping (inbox draft, approvals, the agent's exact action, Telegram)."""

import uuid
from datetime import UTC, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.inbox.models import ReplyDraft
from app.integrations.channels.base import ChannelRecipient
from app.integrations.channels.telegram import TelegramChannel
from app.knowledge import service as knowledge_service
from app.knowledge.sources import fact_sources, unique_sources
from app.notifications.models import Notification, NotificationDelivery
from tests.factories import create_workspace, money
from tests.helpers.gym import MONTHLY
from tests.integration.inbox.conftest import InboxEnv

PRICE_Q = "Aylık üyelik ne kadar?"


@pytest.fixture
def gym(inbox: InboxEnv):  # type: ignore[no-untyped-def]
    return inbox.seed_facts()


def call(inbox: InboxEnv, role: str, method: str, path: str, **kwargs):  # type: ignore[no-untyped-def]
    return inbox.env.call(getattr(inbox.env, role), method, path, **kwargs)


def _record(fact_id: uuid.UUID, version: int, display: str, key: str = MONTHLY) -> dict[str, Any]:
    return {
        "key": key,
        "fact_id": str(fact_id),
        "version": version,
        "span": [0, 1],
        "display": display,
    }


# --- the mapping --------------------------------------------------------------------------------


def test_the_draft_names_each_value_s_fact_and_its_verified_time(inbox: InboxEnv, gym) -> None:
    seeded_at = inbox.clock.now()
    inbox.clock.advance(timedelta(days=3))  # the draft is made well after the fact was verified
    draft = inbox.ask(PRICE_Q)
    body = call(inbox, "staff", "GET", f"/reply-drafts/{draft.id}").json()

    (chip,) = body["rendered_facts"]
    assert chip["key"] == MONTHLY and chip["label"] == "Aylık üyelik"
    assert chip["verified_at"] is not None
    assert chip["verified_at"].replace("Z", "+00:00") == seeded_at.astimezone(UTC).isoformat()
    assert body["facts_used"] == [
        {
            "key": MONTHLY,
            "label": "Aylık üyelik",
            "display": "6.000 ₺ / ay",
            "verified_at": chip["verified_at"],
        }
    ]


def test_the_conversation_view_carries_the_same_mapping(inbox: InboxEnv, gym) -> None:
    inbox.ask(PRICE_Q)
    body = call(inbox, "owner", "GET", f"/conversations/{inbox.conversation().id}").json()
    (used,) = body["open_draft"]["facts_used"]
    assert used["key"] == MONTHLY and used["verified_at"] is not None


def test_a_draft_that_quotes_no_fact_has_an_empty_list(inbox: InboxEnv, gym) -> None:
    inbox.deliver_and_process("merhaba")
    body = call(inbox, "owner", "GET", f"/conversations/{inbox.conversation().id}").json()
    draft = body["open_draft"] or {}
    assert draft.get("facts_used", []) == []


def test_the_date_is_that_of_the_version_the_draft_rendered(inbox: InboxEnv, gym) -> None:
    """A price that changed after the draft was made does not make the draft look freshly
    verified: the date belongs to the rendered version (the history is insert-only)."""
    first = inbox.clock.now()  # when the seed verified the price
    draft = inbox.ask(PRICE_Q)
    inbox.clock.advance(timedelta(days=5))
    fact = gym[MONTHLY]
    knowledge_service.update_fact(
        inbox.session,
        inbox.clock,
        inbox.env.ctx(inbox.env.owner),
        fact.id,
        expected_version=fact.current_version,
        value=money("7000"),
        reason="price list",
    )
    inbox.session.expire_all()
    changed = inbox.session.get(type(fact), fact.id)
    assert changed is not None and changed.current_version == 2
    assert changed.last_verified_at is not None and changed.last_verified_at > first

    body = call(inbox, "owner", "GET", f"/reply-drafts/{draft.id}").json()
    (chip,) = body["rendered_facts"]
    assert chip["version"] == 1  # still the old value, as the text says
    assert chip["verified_at"].replace("Z", "+00:00") == first.astimezone(UTC).isoformat()
    assert "6.000" in body["text"]


def test_a_value_quoted_twice_is_listed_once_but_chipped_twice(inbox: InboxEnv, gym) -> None:
    fact = gym[MONTHLY]
    rendered = [_record(fact.id, 1, "6.000 ₺ / ay"), _record(fact.id, 1, "6.000 ₺ / ay")]
    sources = fact_sources(inbox.session, inbox.env.workspace.id, rendered, "tr")
    assert len(sources) == 2
    assert len(unique_sources(sources)) == 1


def test_the_label_follows_the_language(inbox: InboxEnv, gym) -> None:
    fact = gym[MONTHLY]
    (tr,) = fact_sources(inbox.session, inbox.env.workspace.id, [_record(fact.id, 1, "x")], "tr")
    (en,) = fact_sources(inbox.session, inbox.env.workspace.id, [_record(fact.id, 1, "x")], "en")
    assert tr.label == "Aylık üyelik" and en.label == "Monthly membership"


def test_a_fact_of_another_workspace_is_never_read(inbox: InboxEnv, gym) -> None:
    other = create_workspace(inbox.session, name="Other")
    fact = gym[MONTHLY]
    (source,) = fact_sources(inbox.session, other.id, [_record(fact.id, 1, "6.000 ₺")], "tr")
    assert source.label == MONTHLY  # the key: the label of a foreign fact is not looked up
    assert source.verified_at is None


def test_a_version_with_no_recorded_verification_has_no_date(inbox: InboxEnv, gym) -> None:
    fact = gym[MONTHLY]
    (source,) = fact_sources(
        inbox.session, inbox.env.workspace.id, [_record(fact.id, 0, "6.000 ₺")], "tr"
    )
    assert source.verified_at is None  # never guessed


def test_a_person_s_own_text_has_no_fact_sources(inbox: InboxEnv, gym) -> None:
    inbox.deliver_and_process(PRICE_Q)
    conversation = inbox.conversation()
    response = call(
        inbox,
        "owner",
        "POST",
        f"/conversations/{conversation.id}/replies",
        json={"text": "Üyelik 6000 TL", "client_request_id": str(uuid.uuid4())},
    )
    assert response.status_code == 201
    draft = response.json()["draft"]
    assert draft["rendered_facts"] == [] and draft["facts_used"] == []


# --- Telegram -----------------------------------------------------------------------------------


class FakeTelegram:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send_message(self, **kwargs: Any) -> dict[str, Any]:
        self.sent.append(kwargs)
        return {"message_id": 7}


def _deliver_telegram(inbox: InboxEnv, draft: ReplyDraft, locale: str = "en") -> str:
    assert draft.approval_id is not None
    from app.approvals.models import Approval

    approval = inbox.session.get(Approval, draft.approval_id)
    assert approval is not None
    notification = inbox.session.scalars(
        select(Notification).where(
            Notification.subject_id == approval.id,
            Notification.recipient_user_id == inbox.env.owner.user.id,
        )
    ).first()
    assert notification is not None  # the approval announced itself to the owner
    delivery = NotificationDelivery(
        workspace_id=inbox.env.workspace.id,
        notification_id=notification.id,
        recipient_user_id=inbox.env.owner.user.id,
        channel="telegram",
        status="pending",
    )
    inbox.session.add(delivery)
    inbox.session.flush()
    fake = FakeTelegram()
    result = TelegramChannel(client=fake).deliver_notification(  # type: ignore[arg-type]
        inbox.session,
        inbox.clock,
        delivery,
        ChannelRecipient(
            user_id=inbox.env.owner.user.id,
            workspace_id=inbox.env.workspace.id,
            channel="telegram",
            channel_chat_id="123",
            ui_locale=locale,
            timezone="Europe/Istanbul",
        ),
    )
    assert result.success, result.error_message
    (message,) = fake.sent
    assert message["parse_mode"] == "HTML"
    assert len(message["text"]) <= 4096
    return str(message["text"])


def test_the_telegram_approval_names_the_source_and_the_verified_date(inbox: InboxEnv, gym) -> None:
    draft = inbox.ask(PRICE_Q)
    text = _deliver_telegram(inbox, draft)
    assert "Proposed Reply" in text and "6.000" in text
    assert "<b>6.000 ₺ / ay</b> — from: Monthly membership, verified 2026-01-15" in text


def test_the_telegram_approval_is_turkish_for_a_turkish_owner(inbox: InboxEnv, gym) -> None:
    text = _deliver_telegram(inbox, inbox.ask(PRICE_Q), locale="tr")
    assert "Değerlerin kaynağı" in text
    assert "<b>6.000 ₺ / ay</b> — kaynak: Aylık üyelik, doğrulandı 2026-01-15" in text


def test_telegram_source_lines_are_escaped_and_clipped(inbox: InboxEnv, gym) -> None:
    draft = inbox.ask(PRICE_Q)
    fact = gym[MONTHLY]
    fact.label = {"tr": "<b>x</b> & " + "y" * 200, "en": "<b>x</b> & " + "y" * 200}
    inbox.session.flush()
    text = _deliver_telegram(inbox, draft)
    assert "&lt;b&gt;x&lt;/b&gt; &amp; " in text
    assert "<b>x</b>" not in text
    assert "y" * 100 not in text  # clipped to 60 characters


def test_the_telegram_message_stays_inside_the_limit_with_many_values(inbox: InboxEnv, gym) -> None:
    draft = inbox.ask(PRICE_Q)
    fact = gym[MONTHLY]
    draft.validation = {
        **draft.validation,
        "rendered": [{**_record(fact.id, 1, f"{i} ₺"), "key": f"pricing.k{i}"} for i in range(200)],
    }
    inbox.session.flush()
    text = _deliver_telegram(inbox, draft)
    assert text.count("— from:") < 200 and "more" in text
