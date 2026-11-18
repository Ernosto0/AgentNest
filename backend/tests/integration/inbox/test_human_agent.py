"""Session 09: a person's reply up to 7 days after the customer's last message, with the Human
Agent tag. Boundaries, the capability flag, every automated source, the ledger, the simulator and
the Meta request, the window state in the conversation view, and workspace isolation."""

import json
import uuid
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.canonical import payload_hash
from app.inbox import human_agent
from app.inbox.approval_payload import approval_payload
from app.inbox.expiry import expire_closed_window_drafts
from app.inbox.models import ReplyDraft
from app.integrations.instagram.base import AccountRef, SendResult
from app.integrations.instagram.errors import ProviderInvalidRequest, ProviderWindowClosed
from app.integrations.instagram.meta import MetaInstagramProvider
from app.integrations.instagram.mock import MockInstagramProvider
from app.integrations.instagram.models import SimInboundMessage
from app.integrations.instagram.oauth import SCOPES, compute_capabilities
from app.operations.send import execute_send_reply
from tests.factories import create_workspace
from tests.integration.inbox.conftest import APP_SECRET, InboxEnv

PRICE_Q = "Aylık üyelik ne kadar?"
OWN_TEXT = "Merhaba, size bugün dönüş yapıyoruz."
H = timedelta(hours=1)
MIN = timedelta(minutes=1)
SEC = timedelta(seconds=1)


@pytest.fixture
def gym(inbox: InboxEnv):  # type: ignore[no-untyped-def]
    return inbox.seed_facts()


@pytest.fixture
def ha(inbox: InboxEnv, gym) -> InboxEnv:
    """The account holds the Human Agent capability, and the customer wrote just now."""
    inbox.account.capabilities = {"messaging": True, "human_agent": True}
    inbox.session.commit()
    inbox.deliver_and_process(PRICE_Q)
    return inbox


def call(inbox: InboxEnv, role: str, method: str, path: str, **kwargs):  # type: ignore[no-untyped-def]
    return inbox.env.call(getattr(inbox.env, role), method, path, **kwargs)


def reply(inbox: InboxEnv, text: str = OWN_TEXT, role: str = "owner", **extra):  # type: ignore[no-untyped-def]
    body = {"text": text, "client_request_id": str(uuid.uuid4()), **extra}
    path = f"/conversations/{inbox.conversation().id}/replies"
    return call(inbox, role, "POST", path, json=body)


def draft_of(inbox: InboxEnv, response) -> ReplyDraft:  # type: ignore[no-untyped-def]
    assert response.status_code == 201, response.text
    draft = inbox.session.get(ReplyDraft, uuid.UUID(response.json()["draft"]["id"]))
    assert draft is not None
    return draft


def run_send(inbox: InboxEnv, draft: ReplyDraft, provider: object = None):  # type: ignore[no-untyped-def]
    return execute_send_reply(
        inbox.factory,
        inbox.clock,
        inbox.settings,
        inbox.env.workspace.id,
        draft.id,
        provider=provider,  # type: ignore[arg-type]
    )


class SpyProvider:
    """Counts the sends that really reach the simulator and remembers the tag."""

    def __init__(self, inbox: InboxEnv) -> None:
        self.inner = MockInstagramProvider(inbox.factory, inbox.clock, APP_SECRET)
        self.calls: list[tuple[str, str | None]] = []

    def send_text_message(
        self, account: AccountRef, recipient_id: str, text: str, message_tag: str | None = None
    ) -> SendResult:
        self.calls.append((text, message_tag))
        return self.inner.send_text_message(account, recipient_id, text, message_tag)

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        return getattr(self.inner, name)


# --- boundaries ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("after", "status", "tag"),
    [
        (timedelta(hours=23, minutes=57, seconds=59), 201, None),  # still a normal reply
        (timedelta(hours=23, minutes=58), 201, "HUMAN_AGENT"),  # the 24 h margin is reached
        (timedelta(hours=24, seconds=1), 201, "HUMAN_AGENT"),
        (timedelta(days=3), 201, "HUMAN_AGENT"),
        (timedelta(days=7) - 2 * MIN - SEC, 201, "HUMAN_AGENT"),  # just under 7 days
        (timedelta(days=7) - 2 * MIN, 409, None),  # at the 7-day margin: closed
        (timedelta(days=7) + H, 409, None),
    ],
)
def test_the_tag_is_accepted_between_24_hours_and_7_days_only(
    ha: InboxEnv, after: timedelta, status: int, tag: str | None
) -> None:
    ha.clock.advance(after)
    response = reply(ha)
    assert response.status_code == status, response.text
    if status == 409:
        assert response.json()["code"] == "MESSAGING_WINDOW_CLOSED"
        return
    assert response.json()["draft"]["message_tag"] == tag
    assert draft_of(ha, response).message_tag == tag


def test_with_the_capability_off_a_reply_after_24_hours_is_refused(inbox: InboxEnv, gym) -> None:
    inbox.deliver_and_process(PRICE_Q)  # the account has no ``human_agent`` capability
    inbox.clock.advance(timedelta(hours=26))
    response = reply(inbox)
    assert response.status_code == 409 and response.json()["code"] == "MESSAGING_WINDOW_CLOSED"
    assert inbox.session.scalars(select(ReplyDraft).where(ReplyDraft.source == "owner")).all() == []


def test_a_real_account_also_needs_the_operators_setting() -> None:
    meta = SimpleNamespace(provider_kind="meta", capabilities={"human_agent": True})
    on = SimpleNamespace(meta_human_agent_enabled=True)
    off = SimpleNamespace(meta_human_agent_enabled=False)
    assert human_agent.available(on, meta) is True  # type: ignore[arg-type]
    assert human_agent.available(off, meta) is False  # type: ignore[arg-type]
    no_capability = SimpleNamespace(provider_kind="meta", capabilities={"messaging": True})
    assert human_agent.available(on, no_capability) is False  # type: ignore[arg-type]
    assert human_agent.available(None, meta) is False  # type: ignore[arg-type]


def test_the_capability_needs_the_messaging_scope_and_the_setting() -> None:
    granted = list(SCOPES)
    assert compute_capabilities(granted, True)["human_agent"] is False
    assert compute_capabilities(granted, True, human_agent_enabled=True)["human_agent"] is True
    without_messaging = [s for s in granted if s != SCOPES[1]]
    flags = compute_capabilities(without_messaging, True, human_agent_enabled=True)
    assert flags["human_agent"] is False and flags["messaging"] is False


# --- the whole path ------------------------------------------------------------------------------


def test_a_persons_reply_after_24_hours_is_sent_once_with_the_tag_through_the_ledger(
    ha: InboxEnv,
) -> None:
    ha.clock.advance(timedelta(days=3))
    draft = draft_of(ha, reply(ha))
    assert (draft.status, draft.source, draft.created_by_actor_type) == ("queued", "owner", "user")
    assert draft.decision_reasons == ["OWNER_REPLY", "HUMAN_AGENT_TAG"]

    approval = ha.approval_of(draft)
    payload = approval_payload(draft, ha.conversation())
    assert payload["message_tag"] == "HUMAN_AGENT"  # the approval covers the tag
    assert approval.payload_hash == payload_hash(payload)
    assert approval.expires_at <= ha.conversation().last_inbound_at + timedelta(days=7)

    ha.process()
    assert ha.refreshed(draft).status == "sent"
    (sent,) = ha.sim_sent()
    assert (sent.text, sent.message_tag) == (OWN_TEXT, "HUMAN_AGENT")
    operation = ha.operation(draft)
    assert operation is not None
    assert (operation.operation_type, operation.status) == ("send_reply", "succeeded")
    assert operation.provider_ref["message_tag"] == "HUMAN_AGENT"
    run_send(ha, draft)  # running the send again changes nothing
    assert len(ha.sim_sent()) == 1


def test_a_reply_inside_the_24_hour_window_carries_no_tag(ha: InboxEnv) -> None:
    ha.clock.advance(timedelta(hours=2))
    draft = draft_of(ha, reply(ha))
    assert draft.message_tag is None
    assert "message_tag" not in approval_payload(draft, ha.conversation())
    ha.process()
    (sent,) = ha.sim_sent()
    assert sent.message_tag is None


def test_a_staff_reply_after_24_hours_waits_for_an_owner_who_approves_the_tag(
    ha: InboxEnv,
) -> None:
    ha.clock.advance(timedelta(days=2))
    draft = draft_of(ha, reply(ha, role="staff"))
    assert draft.status == "pending_approval" and draft.message_tag == "HUMAN_AGENT"
    approval = ha.approval_of(draft)
    assert approval.payload_hash == payload_hash(approval_payload(draft, ha.conversation()))
    assert "HUMAN_AGENT_TAG" in approval.summary["reasons"]
    ha.process()
    assert ha.sim_sent() == []
    assert ha.decide(draft, role="owner").status_code == 200
    ha.process()
    assert ha.refreshed(draft).status == "sent"
    assert [m.message_tag for m in ha.sim_sent()] == ["HUMAN_AGENT"]


def test_a_tagged_draft_edited_by_someone_keeps_a_matching_approval(ha: InboxEnv) -> None:
    ha.clock.advance(timedelta(days=2))
    draft = draft_of(ha, reply(ha, role="staff"))
    version = draft.version
    response = call(
        ha, "staff", "PATCH", f"/reply-drafts/{draft.id}",
        json={"text": "Düzeltilmiş yanıt", "expected_version": version},
    )  # fmt: skip
    assert response.status_code == 200, response.text
    edited = ha.refreshed(draft)
    assert edited.message_tag == "HUMAN_AGENT" and edited.version == version + 1
    assert ha.approval_of(edited).payload_hash == payload_hash(
        approval_payload(edited, ha.conversation())
    )


# --- automated sources are rejected --------------------------------------------------------------


def test_an_assistant_draft_cannot_use_the_tag_at_the_database(ha: InboxEnv) -> None:
    ha.clock.advance(timedelta(days=2))
    draft = ha.make_draft("queued", with_approval=True)  # source ai, system actor
    draft.message_tag = "HUMAN_AGENT"
    with pytest.raises(IntegrityError):
        ha.session.commit()
    ha.session.rollback()


def test_an_assistant_draft_waiting_after_24_hours_is_expired_not_tagged(ha: InboxEnv) -> None:
    draft = ha.make_draft("queued", with_approval=True)
    ha.clock.advance(timedelta(days=2))
    spy = SpyProvider(ha)
    outcome = run_send(ha, draft, spy)
    assert (outcome.kind, outcome.error_code) == ("expired", "MESSAGING_WINDOW_CLOSED")
    assert spy.calls == [] and ha.operation(draft) is None
    assert ha.refreshed(draft).status == "expired"


def test_a_follow_up_or_approved_answer_draft_after_24_hours_is_never_tagged(
    ha: InboxEnv,
) -> None:
    draft = ha.make_draft("queued", with_approval=True)
    draft.source, draft.intent = "approved_answer", "follow_up"
    ha.session.commit()
    ha.clock.advance(timedelta(days=2))
    spy = SpyProvider(ha)
    outcome = run_send(ha, draft, spy)
    assert (outcome.kind, outcome.error_code) == ("expired", "MESSAGING_WINDOW_CLOSED")
    assert spy.calls == [] and ha.sim_sent() == []


def test_the_assistants_draft_chosen_as_a_starting_point_cannot_carry_the_tag(
    ha: InboxEnv,
) -> None:
    ai_draft = ha.make_draft("pending_approval")
    ha.clock.advance(timedelta(days=2))
    response = reply(ha, "Başka bir metin", from_draft_id=str(ai_draft.id))
    assert response.status_code == 409 and response.json()["code"] == "HUMAN_AGENT_NOT_ALLOWED"


def test_the_assistants_text_pasted_unchanged_cannot_carry_the_tag(ha: InboxEnv) -> None:
    ai_draft = ha.make_draft("pending_approval", text="Üyelik 6.000 ₺ / ay.")
    ai_draft.suggestion_text = "Öneri metni"
    ha.session.commit()
    ha.clock.advance(timedelta(days=2))
    for text in ("Üyelik 6.000 ₺ / ay.", "  Öneri metni "):
        response = reply(ha, text)
        assert response.status_code == 409 and response.json()["code"] == "HUMAN_AGENT_NOT_ALLOWED"
    assert reply(ha, "Üyelik bilgisini gönderiyorum.").status_code == 201


def test_editing_an_assistant_draft_never_extends_its_window(ha: InboxEnv) -> None:
    ai_draft = ha.make_draft("pending_approval")
    ha.clock.advance(timedelta(hours=25))
    response = call(
        ha, "owner", "PATCH", f"/reply-drafts/{ai_draft.id}",
        json={"text": "Düzenledim", "expected_version": ai_draft.version, "approve": True},
    )  # fmt: skip
    assert response.status_code == 409 and response.json()["code"] == "MESSAGING_WINDOW_CLOSED"
    assert ha.refreshed(ai_draft).message_tag is None and ha.sim_sent() == []


# --- send-time checks ----------------------------------------------------------------------------


def test_turning_the_capability_off_before_the_send_cancels_it(ha: InboxEnv) -> None:
    ha.clock.advance(timedelta(days=2))
    draft = draft_of(ha, reply(ha))
    ha.account.capabilities = {"messaging": True, "human_agent": False}
    ha.session.commit()
    spy = SpyProvider(ha)
    outcome = run_send(ha, draft, spy)
    assert (outcome.kind, outcome.error_code) == ("failed", "HUMAN_AGENT_DISABLED")
    refreshed = ha.refreshed(draft)
    assert (refreshed.status, refreshed.failure_code) == ("cancelled", "HUMAN_AGENT_DISABLED")
    assert spy.calls == [] and ha.operation(draft) is None


def test_the_send_is_refused_in_the_last_minute_of_the_seven_days(ha: InboxEnv) -> None:
    ha.clock.advance(timedelta(days=6, hours=23))
    draft = draft_of(ha, reply(ha))
    ha.clock.advance(timedelta(hours=1) - 30 * SEC)  # 30 seconds before the 7 days end
    spy = SpyProvider(ha)
    outcome = run_send(ha, draft, spy)
    assert (outcome.kind, outcome.error_code) == ("expired", "MESSAGING_WINDOW_CLOSED")
    assert spy.calls == [] and ha.refreshed(draft).status == "expired"


def test_a_tagged_draft_whose_standard_window_reopened_is_sent_without_the_tag(
    ha: InboxEnv,
) -> None:
    ha.clock.advance(timedelta(days=2))
    draft = draft_of(ha, reply(ha))
    now = ha.clock.now()
    conversation = ha.conversation()
    conversation.last_inbound_at = now  # the customer wrote again (the simulator knows it too)
    ha.session.add(
        SimInboundMessage(
            workspace_id=ha.env.workspace.id,
            social_account_id=ha.account.id,
            sender_id="cust-1",
            mid="mid-again",
            received_at=now,
        )
    )
    ha.session.commit()
    spy = SpyProvider(ha)
    assert run_send(ha, draft, spy).kind == "sent"
    assert spy.calls == [(OWN_TEXT, None)]


def test_the_expiry_sweep_waits_for_the_seven_days_of_a_tagged_reply(ha: InboxEnv) -> None:
    ha.clock.advance(timedelta(days=2))
    tagged = draft_of(ha, reply(ha))
    assert expire_closed_window_drafts(ha.factory, ha.clock) == 0
    assert ha.refreshed(tagged).status == "queued"
    ha.clock.advance(timedelta(days=5, hours=1))
    assert expire_closed_window_drafts(ha.factory, ha.clock) == 1
    assert ha.refreshed(tagged).status == "expired"


def test_the_expiry_sweep_still_retires_an_assistant_draft_after_24_hours(ha: InboxEnv) -> None:
    plain = ha.make_draft("queued", with_approval=True)
    ha.clock.advance(timedelta(days=2))
    assert expire_closed_window_drafts(ha.factory, ha.clock) == 1
    assert ha.refreshed(plain).status == "expired"


# --- the providers -------------------------------------------------------------------------------


def test_the_simulator_allows_seven_days_with_the_tag_and_no_more(ha: InboxEnv) -> None:
    provider = MockInstagramProvider(ha.factory, ha.clock, APP_SECRET)
    account = AccountRef(ha.account.id, ha.env.workspace.id, ha.account.external_account_id)
    ha.clock.advance(timedelta(days=3))
    with pytest.raises(ProviderWindowClosed):
        provider.send_text_message(account, "cust-1", "no tag")
    with pytest.raises(ProviderInvalidRequest):
        provider.send_text_message(account, "cust-1", "x", message_tag="ACCOUNT_UPDATE")
    provider.send_text_message(account, "cust-1", "tagged", message_tag="HUMAN_AGENT")
    ha.clock.advance(timedelta(days=4))
    with pytest.raises(ProviderWindowClosed):
        provider.send_text_message(account, "cust-1", "too late", message_tag="HUMAN_AGENT")
    assert [m.message_tag for m in ha.sim_sent()] == ["HUMAN_AGENT"]


def test_the_meta_request_carries_the_documented_tag_fields_only_when_tagged(
    ha: InboxEnv,
) -> None:
    seen: list[dict[str, object]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"recipient_id": "cust-1", "message_id": "meta-mid-1"})

    provider = MetaInstagramProvider(
        ha.clock, APP_SECRET, "v25.0", transport=httpx.MockTransport(handle)
    )
    account = AccountRef(uuid.uuid4(), uuid.uuid4(), "biz-1", lambda: "synthetic-token")
    provider.send_text_message(account, "cust-1", "plain")
    provider.send_text_message(account, "cust-1", "tagged", message_tag="HUMAN_AGENT")
    assert seen[0] == {"recipient": {"id": "cust-1"}, "message": {"text": "plain"}}
    assert seen[1] == {
        "recipient": {"id": "cust-1"},
        "message": {"text": "tagged"},
        "messaging_type": "MESSAGE_TAG",
        "tag": "HUMAN_AGENT",
    }
    with pytest.raises(ProviderInvalidRequest):
        provider.send_text_message(account, "cust-1", "x", message_tag="ACCOUNT_UPDATE")
    assert len(seen) == 2  # an unsupported tag never reaches the network


# --- the window state in the conversation view ---------------------------------------------------


@pytest.mark.parametrize(
    ("after", "state", "has_until"),
    [
        (timedelta(hours=2), "open", False),
        (timedelta(hours=23, minutes=57), "open", False),
        (timedelta(hours=23, minutes=58), "human_agent_only", True),
        (timedelta(days=3), "human_agent_only", True),
        (timedelta(days=7) - 2 * MIN, "closed", False),
        (timedelta(days=9), "closed", False),
    ],
)
def test_the_conversation_shows_the_window_state(
    ha: InboxEnv, after: timedelta, state: str, has_until: bool
) -> None:
    last = ha.conversation().last_inbound_at
    ha.clock.advance(after)
    body = call(ha, "owner", "GET", f"/conversations/{ha.conversation().id}").json()
    conversation = body["conversation"]
    assert conversation["window_state"] == state
    assert (conversation["human_agent_until"] is not None) is has_until
    if has_until:
        expected = (last + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M")
        assert conversation["human_agent_until"].startswith(expected)
    (row,) = call(ha, "staff", "GET", "/conversations").json()["items"]
    assert row["window_state"] == state


def test_without_the_capability_the_view_goes_from_open_to_closed(inbox: InboxEnv, gym) -> None:
    inbox.deliver_and_process(PRICE_Q)
    inbox.clock.advance(timedelta(days=2))
    body = call(inbox, "owner", "GET", f"/conversations/{inbox.conversation().id}").json()
    assert body["conversation"]["window_state"] == "closed"
    assert body["conversation"]["human_agent_until"] is None


def test_a_tagged_draft_shows_its_tag_in_the_draft_view(ha: InboxEnv) -> None:
    ha.clock.advance(timedelta(days=2))
    draft = draft_of(ha, reply(ha, role="staff"))
    body = call(ha, "owner", "GET", f"/reply-drafts/{draft.id}").json()
    assert body["message_tag"] == "HUMAN_AGENT"


# --- isolation -----------------------------------------------------------------------------------


def test_another_workspace_cannot_reply_to_or_read_the_conversation(ha: InboxEnv) -> None:
    ha.clock.advance(timedelta(days=2))
    conversation_id = ha.conversation().id
    other = create_workspace(ha.session, name="Other")
    base = f"/api/v1/workspaces/{other.id}"
    client = ha.env.owner.client
    assert client.get(f"{base}/conversations/{conversation_id}").status_code == 404
    body = {"text": OWN_TEXT, "client_request_id": str(uuid.uuid4())}
    sent = client.post(
        f"{base}/conversations/{conversation_id}/replies",
        json=body,
        headers=ha.env.owner.headers,
    )
    assert sent.status_code == 404
    assert ha.session.scalars(select(ReplyDraft).where(ReplyDraft.source == "owner")).all() == []
