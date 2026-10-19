"""P4-09: the inbox API and the human actions: conversations, takeover, manual replies, edits,
cancellation."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.approvals.models import Approval
from app.core.canonical import payload_hash
from app.inbox.approval_payload import approval_payload
from app.inbox.models import ReplyDraft
from app.jobs.models import Job
from tests.factories import create_workspace
from tests.integration.inbox.conftest import InboxEnv

PRICE_Q = "Aylık üyelik ne kadar?"


@pytest.fixture
def gym(inbox: InboxEnv):  # type: ignore[no-untyped-def]
    return inbox.seed_facts()


def call(inbox: InboxEnv, role: str, method: str, path: str, **kwargs):  # type: ignore[no-untyped-def]
    return inbox.env.call(getattr(inbox.env, role), method, path, **kwargs)


def reply(inbox: InboxEnv, conversation_id: object, text: str, role: str = "owner", **extra):  # type: ignore[no-untyped-def]
    body = {"text": text, "client_request_id": str(uuid.uuid4()), **extra}
    return call(inbox, role, "POST", f"/conversations/{conversation_id}/replies", json=body)


# --- listing and reading -------------------------------------------------------------------------


def test_the_inbox_lists_conversations_with_their_attention(inbox: InboxEnv, gym) -> None:
    inbox.ask(PRICE_Q, customer="cust-1", mid="m-1")  # needs approval
    inbox.ask("Bu bir rezalet, şikayetçiyim", customer="cust-2", mid="m-2")  # needs a person
    inbox.deliver_and_process("merhaba", customer="cust-3", mid="m-3")  # not drafted yet

    everything = call(inbox, "staff", "GET", "/conversations").json()["items"]
    assert len(everything) == 3
    by_attention = {c["attention"] for c in everything}
    assert by_attention == {"needs_approval", "needs_human", "none"}

    approval = call(inbox, "owner", "GET", "/conversations?attention=needs_approval").json()
    assert [c["attention"] for c in approval["items"]] == ["needs_approval"]
    human = call(inbox, "owner", "GET", "/conversations?attention=needs_human").json()["items"]
    assert len(human) == 1 and human[0]["is_simulated"] is True


def test_the_list_row_has_what_the_screen_needs(inbox: InboxEnv, gym) -> None:
    inbox.ask(PRICE_Q, mid="m-1")
    (row,) = call(inbox, "owner", "GET", "/conversations").json()["items"]
    assert row["last_message_preview"] == PRICE_Q
    assert row["handling_mode"] == "automatic"
    assert row["customer_handle"] is None and 0 <= row["customer_number"] < 10000
    assert row["window_ends_at"].startswith("2026-01-16T12:00")
    assert set(row) == {
        "id", "customer_handle", "customer_number", "last_message_preview", "last_message_at",
        "attention", "handling_mode", "window_ends_at", "is_simulated",
    }  # fmt: skip


def test_the_conversation_shows_messages_and_the_open_draft_with_its_fact_chips(
    inbox: InboxEnv, gym
) -> None:
    draft = inbox.ask(PRICE_Q)
    conversation = inbox.conversation()
    body = call(inbox, "owner", "GET", f"/conversations/{conversation.id}").json()

    assert [m["text"] for m in body["messages"]] == [PRICE_Q]
    assert body["messages"][0]["direction"] == "inbound"
    open_draft = body["open_draft"]
    assert open_draft["id"] == str(draft.id)
    assert open_draft["text"] == "Merhaba! Aylık üyelik ücretimiz 6.000 ₺ / ay."
    assert open_draft["status"] == "pending_approval"
    assert open_draft["decision_reasons"] == ["POLICY_REQUIRES_APPROVAL"]
    assert open_draft["validation"] == {"passed": True, "issues": []}
    (chip,) = open_draft["rendered_facts"]
    assert chip["key"] == "pricing.membership_monthly" and chip["label"] == "Aylık üyelik"
    assert chip["display"] == "6.000 ₺ / ay" and chip["version"] == 1
    start, end = chip["span"]
    assert open_draft["text"][start:end] == "6.000 ₺ / ay"
    assert open_draft["approval_id"] == str(draft.approval_id)
    assert body["recent_drafts"] == []


def test_a_closed_draft_moves_to_the_recent_list(inbox: InboxEnv, gym) -> None:
    draft = inbox.ask(PRICE_Q)
    inbox.decide(draft, "reject")
    body = call(inbox, "owner", "GET", f"/conversations/{inbox.conversation().id}").json()
    assert body["open_draft"] is None
    assert [d["status"] for d in body["recent_drafts"]] == ["rejected"]


def test_a_draft_can_be_read_on_its_own(inbox: InboxEnv, gym) -> None:
    draft = inbox.ask(PRICE_Q)
    body = call(inbox, "staff", "GET", f"/reply-drafts/{draft.id}").json()
    assert body["id"] == str(draft.id) and body["text"].startswith("Merhaba!")


def test_a_conversation_or_draft_of_another_workspace_is_not_found(inbox: InboxEnv, gym) -> None:
    inbox.deliver_and_process(PRICE_Q)
    other = create_workspace(inbox.session, name="Other")
    path = f"/api/v1/workspaces/{other.id}"
    assert inbox.env.owner.client.get(f"{path}/conversations").status_code == 404
    conversation = inbox.conversation()
    wrong = call(inbox, "owner", "GET", f"/conversations/{uuid.uuid4()}")
    assert wrong.status_code == 404
    assert call(inbox, "owner", "GET", f"/reply-drafts/{uuid.uuid4()}").status_code == 404
    assert call(inbox, "owner", "GET", f"/conversations/{conversation.id}").status_code == 200


# --- takeover, release, suggest ------------------------------------------------------------------


def test_takeover_stops_drafting_and_withdraws_a_draft_waiting_for_approval(
    inbox: InboxEnv, gym
) -> None:
    draft = inbox.ask(PRICE_Q, mid="m-1")
    conversation = inbox.conversation()
    response = call(inbox, "staff", "POST", f"/conversations/{conversation.id}/takeover")
    assert response.status_code == 200 and response.json()["handling_mode"] == "human"
    refreshed = inbox.refreshed(draft)
    assert (refreshed.status, refreshed.failure_code) == ("superseded", "HUMAN_TAKEOVER")
    assert inbox.approval_of(draft).status == "cancelled"
    assert response.json()["attention"] == "needs_human"  # the customer is still unanswered

    inbox.clock.advance(timedelta(seconds=30))
    jobs_before = len(inbox.jobs("draft_reply"))
    inbox.deliver_and_process("bir şey daha", mid="m-2")
    assert len(inbox.jobs("draft_reply")) == jobs_before  # human mode: no new draft


def test_release_returns_to_automatic_and_drafts_the_waiting_question(inbox: InboxEnv, gym) -> None:
    inbox.deliver_and_process(PRICE_Q, mid="m-1")
    inbox.draft_now()
    conversation = inbox.conversation()
    call(inbox, "owner", "POST", f"/conversations/{conversation.id}/takeover")
    inbox.session.expire_all()
    assert inbox.draft() is not None and inbox.draft().status == "superseded"  # type: ignore[union-attr]

    response = call(inbox, "owner", "POST", f"/conversations/{conversation.id}/release")
    assert response.json()["handling_mode"] == "automatic"
    inbox.process()
    draft = inbox.draft()
    assert draft is not None and draft.status == "pending_approval"
    assert draft.text == "Merhaba! Aylık üyelik ücretimiz 6.000 ₺ / ay."


def test_suggest_reply_works_in_human_mode_but_the_result_is_for_a_person(
    inbox: InboxEnv, gym
) -> None:
    inbox.deliver_and_process(PRICE_Q)
    conversation = inbox.conversation()
    call(inbox, "owner", "POST", f"/conversations/{conversation.id}/takeover")
    response = call(inbox, "staff", "POST", f"/conversations/{conversation.id}/suggest-reply")
    assert response.status_code == 202
    inbox.process()
    draft = inbox.draft()
    assert draft is not None
    assert (draft.status, draft.decision_reasons) == ("needs_human", ["HUMAN_TAKEOVER"])
    assert draft.text is None
    assert draft.suggestion_text == "Merhaba! Aylık üyelik ücretimiz 6.000 ₺ / ay."


def test_suggest_reply_replaces_a_draft_that_waits_for_approval(inbox: InboxEnv, gym) -> None:
    first = inbox.ask(PRICE_Q)
    conversation = inbox.conversation()
    assert (
        call(inbox, "owner", "POST", f"/conversations/{conversation.id}/suggest-reply").status_code
        == 202
    )
    assert inbox.refreshed(first).status == "superseded"
    inbox.process()
    assert inbox.draft().status == "pending_approval"  # type: ignore[union-attr]
    assert inbox.draft().id != first.id  # type: ignore[union-attr]


# --- a person's own reply ------------------------------------------------------------------------


def test_the_owner_replies_and_the_reply_is_sent_with_a_recorded_self_approval(
    inbox: InboxEnv, gym
) -> None:
    inbox.deliver_and_process(PRICE_Q)
    conversation = inbox.conversation()
    response = reply(inbox, conversation.id, "Merhaba! Size hemen dönüyoruz.")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["draft"]["source"] == "owner" and body["draft"]["status"] == "queued"
    assert body["warnings"] == []

    draft = inbox.session.get(ReplyDraft, uuid.UUID(body["draft"]["id"]))
    assert draft is not None
    approval = inbox.approval_of(draft)
    assert approval.status == "approved" and approval.decision_channel == "web"
    assert approval.decided_by_user_id == inbox.env.owner.user.id
    assert approval.requested_by_actor_id == str(inbox.env.owner.user.id)
    assert approval.payload_hash == payload_hash(approval_payload(draft, inbox.conversation()))

    inbox.process()  # the send job
    assert inbox.refreshed(draft).status == "sent"
    (sent,) = inbox.sim_sent()
    assert sent.text == "Merhaba! Size hemen dönüyoruz."


def test_a_reply_withdraws_the_draft_it_replaces(inbox: InboxEnv, gym) -> None:
    ai_draft = inbox.ask("Bu bir rezalet, şikayetçiyim")
    conversation = inbox.conversation()
    response = reply(
        inbox, conversation.id, "Özür dileriz, sizi arayacağız.", from_draft_id=str(ai_draft.id)
    )
    assert response.status_code == 201
    old = inbox.refreshed(ai_draft)
    assert (old.status, old.failure_code) == ("superseded", "MANUAL_REPLY")
    assert str(old.superseded_by_id) == response.json()["draft"]["id"]


def test_a_reply_withdraws_a_pending_approval_for_the_same_question(inbox: InboxEnv, gym) -> None:
    draft = inbox.ask(PRICE_Q)
    reply(inbox, inbox.conversation().id, "Kendi cevabım")
    assert inbox.refreshed(draft).status == "superseded"
    assert inbox.approval_of(draft).status == "cancelled"


def test_a_staff_reply_needs_the_approval_of_an_owner(inbox: InboxEnv, gym) -> None:
    inbox.deliver_and_process(PRICE_Q)
    conversation = inbox.conversation()
    response = reply(inbox, conversation.id, "Merhaba, yardımcı olabilirim.", role="staff")
    assert response.status_code == 201
    draft = inbox.session.get(ReplyDraft, uuid.UUID(response.json()["draft"]["id"]))
    assert draft is not None and draft.status == "pending_approval"
    approval = inbox.approval_of(draft)
    assert approval.status == "pending" and approval.required_permission == "reply.approve"
    assert approval.requested_by_actor_id == str(inbox.env.staff.user.id)
    inbox.process()
    assert inbox.sim_sent() == []  # nothing is sent without an owner

    assert inbox.decide(draft, role="staff").status_code == 403
    assert inbox.decide(draft, role="owner").status_code == 200
    inbox.process()
    assert inbox.refreshed(draft).status == "sent"


def test_a_reply_request_is_idempotent_per_author(inbox: InboxEnv, gym) -> None:
    inbox.deliver_and_process(PRICE_Q)
    conversation = inbox.conversation()
    body = {"text": "Merhaba!", "client_request_id": "req-1"}
    path = f"/conversations/{conversation.id}/replies"
    first = call(inbox, "owner", "POST", path, json=body)
    second = call(inbox, "owner", "POST", path, json=body)
    assert first.json()["draft"]["id"] == second.json()["draft"]["id"]
    inbox.process()
    assert len(inbox.sim_sent()) == 1
    other = call(inbox, "manager", "POST", path, json=body)  # the same id from someone else
    assert other.status_code in (201, 409)
    if other.status_code == 201:
        assert other.json()["draft"]["id"] != first.json()["draft"]["id"]


def test_numbers_in_a_reply_are_warnings_not_blocks(inbox: InboxEnv, gym) -> None:
    inbox.deliver_and_process(PRICE_Q)
    conversation = inbox.conversation()
    ok = reply(inbox, conversation.id, "Aylık üyelik 6.000 ₺")  # equals the verified price
    assert ok.status_code == 201
    (issue,) = ok.json()["warnings"]
    assert issue["code"] == "MONEY" and issue["matches_verified"] is True
    assert ok.json()["draft"]["validation"]["passed"] is False

    wrong = reply(inbox, conversation.id, "Aylık üyelik 5.000 ₺")
    assert wrong.status_code == 201  # still allowed: it is the owner's call
    (issue,) = wrong.json()["warnings"]
    assert issue["matches_verified"] is False


@pytest.mark.parametrize("text", ["", "   ", "a" * 1001])
def test_empty_or_oversized_replies_are_rejected(inbox: InboxEnv, gym, text: str) -> None:
    inbox.deliver_and_process(PRICE_Q)
    response = reply(inbox, inbox.conversation().id, text)
    assert response.status_code == 422


def test_a_reply_after_the_window_is_refused(inbox: InboxEnv, gym) -> None:
    inbox.deliver_and_process(PRICE_Q)
    inbox.clock.advance(timedelta(hours=24))
    response = reply(inbox, inbox.conversation().id, "Geç kaldık")
    assert response.status_code == 409 and response.json()["code"] == "MESSAGING_WINDOW_CLOSED"


def test_a_reply_through_a_disconnected_account_is_refused(inbox: InboxEnv, gym) -> None:
    inbox.deliver_and_process(PRICE_Q)
    inbox.account.status = "needs_reauth"
    inbox.session.commit()
    response = reply(inbox, inbox.conversation().id, "Merhaba")
    assert response.status_code == 409 and response.json()["code"] == "ACCOUNT_NOT_CONNECTED"


def test_a_reply_cannot_be_written_while_another_is_being_sent(inbox: InboxEnv, gym) -> None:
    inbox.deliver_and_process(PRICE_Q)
    draft = inbox.make_draft("queued", with_approval=False)
    draft.status = "sending"
    inbox.session.commit()
    response = reply(inbox, inbox.conversation().id, "Bir daha")
    assert response.status_code == 409


# --- editing and cancelling ----------------------------------------------------------------------


def test_editing_a_draft_binds_a_new_approval_to_the_new_text(inbox: InboxEnv, gym) -> None:
    draft = inbox.ask(PRICE_Q)
    old_approval = inbox.approval_of(draft)
    response = call(
        inbox, "owner", "PATCH", f"/reply-drafts/{draft.id}",
        json={"text": "Merhaba! Aylık üyelik ücretimiz 6.000 ₺.", "expected_version": 1},
    )  # fmt: skip
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["draft"]["version"] == 2 and body["draft"]["source"] == "owner"
    assert body["draft"]["status"] == "pending_approval"
    assert body["draft"]["rendered_facts"] == []  # no longer a rendering of a template

    inbox.session.expire_all()
    assert inbox.session.get(Approval, old_approval.id).status == "cancelled"  # type: ignore[union-attr]
    assert old_approval.cancel_reason == "SUBJECT_EDITED"
    fresh = inbox.refreshed(draft)
    new_approval = inbox.approval_of(fresh)
    assert new_approval.id != old_approval.id and new_approval.status == "pending"
    assert new_approval.subject_version == 2
    assert new_approval.payload_hash == payload_hash(approval_payload(fresh, inbox.conversation()))
    # the old hash can no longer approve anything
    stale = call(
        inbox, "owner", "POST", f"/approvals/{old_approval.id}/decision",
        json={"decision": "approve", "payload_hash": old_approval.payload_hash},
    )  # fmt: skip
    assert stale.status_code == 409


def test_editing_with_approve_sends_the_new_text(inbox: InboxEnv, gym) -> None:
    draft = inbox.ask(PRICE_Q)
    response = call(
        inbox, "owner", "PATCH", f"/reply-drafts/{draft.id}",
        json={"text": "Merhaba, kısaca: 6.000 ₺", "expected_version": 1, "approve": True},
    )  # fmt: skip
    assert response.status_code == 200
    assert response.json()["draft"]["status"] == "queued"
    inbox.process()
    (sent,) = inbox.sim_sent()
    assert sent.text == "Merhaba, kısaca: 6.000 ₺"
    assert inbox.refreshed(draft).status == "sent"


def test_a_stale_edit_is_a_version_conflict(inbox: InboxEnv, gym) -> None:
    draft = inbox.ask(PRICE_Q)
    response = call(
        inbox, "owner", "PATCH", f"/reply-drafts/{draft.id}",
        json={"text": "Yeni metin", "expected_version": 7},
    )  # fmt: skip
    assert response.status_code == 409 and response.json()["code"] == "VERSION_CONFLICT"


def test_only_a_draft_waiting_for_approval_can_be_edited(inbox: InboxEnv, gym) -> None:
    draft = inbox.ask(PRICE_Q)
    inbox.approve_and_send(draft)
    response = call(
        inbox, "owner", "PATCH", f"/reply-drafts/{draft.id}",
        json={"text": "Geç", "expected_version": 1},
    )  # fmt: skip
    assert response.status_code == 409


def test_a_queued_reply_can_be_cancelled_before_it_goes_out(inbox: InboxEnv, gym) -> None:
    inbox.deliver_and_process(PRICE_Q)
    body = reply(inbox, inbox.conversation().id, "Merhaba!").json()
    draft_id = body["draft"]["id"]
    cancelled = call(inbox, "owner", "POST", f"/reply-drafts/{draft_id}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["failure_code"] == "OWNER_CANCELLED"
    inbox.process()  # the already queued send job finds nothing to do
    assert inbox.sim_sent() == []
    again = call(inbox, "owner", "POST", f"/reply-drafts/{draft_id}/cancel")
    assert again.status_code == 409


def test_a_draft_waiting_for_approval_cannot_be_cancelled_only_rejected(
    inbox: InboxEnv, gym
) -> None:
    draft = inbox.ask(PRICE_Q)
    assert call(inbox, "owner", "POST", f"/reply-drafts/{draft.id}/cancel").status_code == 409


def test_the_send_job_is_enqueued_once_for_a_reply(inbox: InboxEnv, gym) -> None:
    inbox.deliver_and_process(PRICE_Q)
    reply(inbox, inbox.conversation().id, "Merhaba!")
    sends = list(inbox.session.scalars(select(Job).where(Job.job_type == "send_reply")))
    assert len(sends) == 1
