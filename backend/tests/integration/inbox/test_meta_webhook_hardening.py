"""Story/unsend/native-app behavior through signed ingestion and real processing."""

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.core.config import get_settings
from app.inbox import echoes, processing
from app.inbox.ingest import ingest_webhook
from app.inbox.models import InboundEvent, Message
from app.integrations.instagram import webhook_format as wf
from app.integrations.instagram.models import SocialAccount
from tests.factories import create_workspace
from tests.integration.inbox.conftest import InboxEnv


def test_story_reply_is_ingested_and_preserves_story_metadata(inbox: InboxEnv) -> None:
    payload = inbox.message_payload("story question", mid="story-reply")
    payload["entry"][0]["messaging"][0]["message"]["reply_to"] = {
        "story": {"id": "story-1", "url": "https://example.test/story.jpg"}
    }
    assert inbox.post(payload).status_code == 200
    inbox.process()
    (message,) = inbox.messages()
    assert message.attachments == [
        {"type": "story_reply", "url": "https://example.test/story.jpg", "note": "story-1"}
    ]
    assert len(inbox.jobs("draft_reply")) == 1


def test_delete_is_deduped_separately_scoped_and_creates_no_draft(inbox: InboxEnv) -> None:
    inbox.deliver_and_process("existing", mid="shared-mid")
    (original,) = inbox.messages()
    other_ws = create_workspace(inbox.session, name="other")
    other = SocialAccount(
        workspace_id=other_ws.id,
        provider_kind="mock",
        external_account_id="other-biz",
        status="connected",
    )
    inbox.session.add(other)
    inbox.session.flush()
    # Another account/workspace's message has the same provider mid.
    from app.inbox.models import Conversation

    conversation = Conversation(
        workspace_id=other_ws.id, social_account_id=other.id, customer_external_id="other"
    )
    inbox.session.add(conversation)
    inbox.session.flush()
    foreign = Message(
        workspace_id=other_ws.id,
        social_account_id=other.id,
        conversation_id=conversation.id,
        direction="inbound",
        sender_kind="customer",
        external_message_id="shared-mid",
        text="other",
        provider_timestamp=inbox.clock.now(),
        is_simulated=True,
    )
    inbox.session.add(foreign)
    inbox.session.commit()
    before = len(inbox.jobs("draft_reply"))
    payload = inbox.message_payload(None, mid="shared-mid")
    payload["entry"][0]["messaging"][0]["message"]["is_deleted"] = True
    assert inbox.post(payload).status_code == 200
    assert inbox.post(payload).status_code == 200
    events = list(
        inbox.session.scalars(select(InboundEvent).where(InboundEvent.event_type == "delete"))
    )
    assert len(events) == 1
    # A forged workspace job cannot apply the deletion.
    processing.process_inbound_event(
        inbox.session, inbox.clock, other_ws.id, events[0].id, debounce_seconds=8
    )
    inbox.session.refresh(original)
    assert not original.is_deleted
    inbox.process()
    inbox.session.refresh(original)
    inbox.session.refresh(foreign)
    assert original.is_deleted and not foreign.is_deleted
    assert len(inbox.messages()) == 1 and len(inbox.jobs("draft_reply")) == before


def test_unknown_delete_does_not_create_a_message_or_draft(inbox: InboxEnv) -> None:
    payload = inbox.message_payload(None, mid="gone")
    payload["entry"][0]["messaging"][0]["message"]["is_deleted"] = True
    inbox.post(payload)
    inbox.process()
    assert list(inbox.session.scalars(select(Message))) == []
    assert inbox.jobs("draft_reply") == []


@pytest.mark.parametrize("app_id", ["instagram-native", "other-app"])
def test_other_app_echo_bypasses_text_matching_and_supersedes_draft(
    inbox: InboxEnv, monkeypatch: pytest.MonkeyPatch, app_id: str
) -> None:
    inbox.seed_facts()
    draft = inbox.ask()
    assert draft.text
    inbox.account.provider_kind = "meta"
    inbox.session.commit()
    cfg = get_settings().model_copy(
        update={
            "meta_app_id": "our-app",
            "instagram_enabled_providers": "meta",
            "meta_app_secret": SecretStr("synthetic-webhook-secret"),
        }
    )
    monkeypatch.setattr(echoes, "get_settings", lambda: cfg)
    calls = []
    with echoes.matchers_snapshot(clear=True):
        echoes.register_matcher(lambda *args: calls.append(True) or True)
        payload = wf.build_echo_payload(
            inbox.account.external_account_id,
            "cust-1",
            "native-mid",
            draft.text,
            inbox.clock.now(),
            app_id=app_id,
        )
        body = wf.serialize(payload)
        result = ingest_webhook(
            inbox.session,
            inbox.clock,
            cfg,
            "meta",
            body,
            {wf.SIGNATURE_HEADER: wf.sign(body, cfg.meta_app_secret.get_secret_value())},
        )
        assert result.received == 1
        inbox.process()
    assert calls == []
    assert inbox.refreshed(draft).status == "superseded"
    native = [m for m in inbox.messages() if m.external_message_id == "native-mid"]
    assert (
        len(native) == 1
        and native[0].sender_kind == "business_native"
        and not native[0].is_simulated
    )


@pytest.mark.parametrize("app_id", ["our-app", None])
def test_own_or_missing_app_id_still_uses_operation_matchers(
    inbox: InboxEnv, monkeypatch: pytest.MonkeyPatch, app_id: str | None
) -> None:
    cfg = get_settings().model_copy(update={"meta_app_id": "our-app"})
    monkeypatch.setattr(echoes, "get_settings", lambda: cfg)
    calls = []
    with echoes.matchers_snapshot(clear=True):
        echoes.register_matcher(lambda *args: calls.append(True) or True)
        assert echoes.claimed_by_a_send(
            inbox.session,
            inbox.clock,
            inbox.env.ctx(inbox.env.owner),
            echoes.Echo(
                inbox.account.id, "cust-1", "mid", "same text", inbox.clock.now(), app_id, "meta"
            ),
        )
    assert calls == [True]
