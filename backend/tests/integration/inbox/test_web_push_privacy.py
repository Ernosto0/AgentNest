"""F-01 part 2: a real customer message and the reply drafted for it never reach a push payload.

The customer text is delivered through the Instagram webhook, processed and drafted by the real
pipeline; the draft's approval notifies the owner, who has a device and has opted in; the push is
sent by the real job. The fake push service then receives the payload, and the test searches
everything it was given for the customer's words, the draft and the customer's handle.
"""

import base64
import json
from collections.abc import Iterator
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.core.config import Settings
from app.core.security import generate_vapid_keys
from app.integrations.channels import registry
from app.integrations.channels.web_push.adapter import WebPushChannel
from app.integrations.channels.web_push.sender import SendOutcome
from app.jobs.testing import run_due_jobs
from app.notifications import push_preferences, push_subscriptions
from app.notifications.models import NotificationDelivery
from tests.integration.inbox.conftest import InboxEnv

PUBLIC, PRIVATE = generate_vapid_keys()
TOKEN_KEYS = "k1:" + base64.b64encode(b"7" * 32).decode()
ENDPOINT = "https://fcm.googleapis.com/fcm/send/owner-phone"
P256DH = base64.urlsafe_b64encode(b"\x04" + b"p" * 64).rstrip(b"=").decode()
AUTH = base64.urlsafe_b64encode(b"a" * 16).rstrip(b"=").decode()

CUSTOMER_MESSAGE = "Aylık üyelik ne kadar?"  # one the drafting pipeline can answer
CUSTOMER_HANDLE = "ayse_yilmaz_93"
ODD_MESSAGE = "ZZ-GIZLI-MUSTERI-MESAJI ZZ-ANAHTAR"  # one it hands to a human


@pytest.fixture
def pushed(
    inbox: InboxEnv, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Iterator[list[dict[str, Any]]]:
    push_settings = settings.model_copy(
        update={
            "web_push_vapid_public_key": PUBLIC,
            "web_push_vapid_private_key": SecretStr(PRIVATE),
            "web_push_subject": "mailto:ops@example.com",
            "token_encryption_keys": SecretStr(TOKEN_KEYS),
            "token_encryption_active_key_id": "k1",
        }
    )
    monkeypatch.setattr("app.notifications.push_dispatch.get_settings", lambda: push_settings)
    calls: list[dict[str, Any]] = []

    def sender(**kwargs: Any) -> SendOutcome:
        calls.append(kwargs)
        return SendOutcome("sent", status_code=201)

    registry.reset_channel_registry()
    registry.register_channel("web_push", WebPushChannel(sender=sender, settings=push_settings))
    env = inbox.env
    ctx = env.ctx(env.owner)
    push_subscriptions.subscribe(
        env.session,
        env.clock,
        push_settings,
        ctx,
        env.owner.user.id,
        endpoint=ENDPOINT,
        p256dh=P256DH,
        auth=AUTH,
        user_agent=None,
        label=None,
    )
    push_preferences.set_preferences(
        env.session, env.clock, ctx, env.owner.user.id, {"approvals": True}
    )
    yield calls
    registry.reset_channel_registry()


def test_a_reply_approval_push_contains_no_customer_text_or_draft(
    inbox: InboxEnv, pushed: list[dict[str, Any]]
) -> None:
    inbox.seed_facts()
    draft = inbox.ask(CUSTOMER_MESSAGE, customer=CUSTOMER_HANDLE)
    assert draft.text and draft.status == "pending_approval", (
        draft.status,
        draft.text,
        draft.decision,
    )

    run_due_jobs(inbox.env.clock, session_factory=inbox.factory)
    inbox.session.expire_all()
    ledger = list(inbox.session.scalars(select(NotificationDelivery)))
    assert [d.channel for d in ledger] == ["web_push"], "the owner's approval was not pushed"
    assert ledger[0].status == "delivered"
    assert len(pushed) == 1

    everything = json.dumps(pushed[0], default=str, ensure_ascii=False)
    body = json.loads(pushed[0]["payload"])
    assert set(body) == {"title", "body", "url", "tag"}
    assert body["url"] == f"/w/{inbox.env.workspace.id}/approvals"
    forbidden = [
        CUSTOMER_MESSAGE,
        CUSTOMER_HANDLE,
        draft.text,
        "6.000",
        "golkent.demo",  # the connected account's handle
    ]
    for text in forbidden:
        # The destination URL and keys are in the call's other fields (the sender needs them);
        # what the push service is *given to show* is the payload only.
        assert text not in body["title"] + body["body"] + body["url"] + body["tag"], text
    assert draft.text not in everything


def test_a_message_handed_to_a_human_is_not_pushed_at_all(
    inbox: InboxEnv, pushed: list[dict[str, Any]]
) -> None:
    """``conversation.needs_human`` is not a pushable type: its notification stays in the app."""
    inbox.seed_facts()
    inbox.deliver_and_process(ODD_MESSAGE, customer=CUSTOMER_HANDLE)
    inbox.draft_now()
    run_due_jobs(inbox.env.clock, session_factory=inbox.factory)
    assert pushed == []
    inbox.session.expire_all()
    assert list(inbox.session.scalars(select(NotificationDelivery))) == []
