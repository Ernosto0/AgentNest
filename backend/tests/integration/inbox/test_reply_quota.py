"""P-11: the monthly AI reply allowance on the drafting job.

What is counted, the 80% / 100% warnings once per period, and what happens at the end of the
grace: the customer's message still arrives and is announced, the model is not called, nothing
stays stuck, and drafting works again as soon as the allowance does.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.inbox.models import Conversation
from app.integrations.llm import FakeLLMProvider
from app.notifications.models import Notification
from app.plans import service
from tests.integration.inbox.conftest import InboxEnv

PRICE_Q = "Aylık üyelik ne kadar?"


@pytest.fixture
def gym(inbox: InboxEnv, provider: FakeLLMProvider):  # type: ignore[no-untyped-def]
    return inbox.seed_facts()


def plan(inbox: InboxEnv, *, quota: int | None = None, used: int | None = None):  # type: ignore[no-untyped-def]
    """The workspace's plan row, optionally with a quota override and a usage already spent."""
    inbox.session.expire_all()
    row = service.get_plan(inbox.session, inbox.clock, inbox.env.workspace.id)
    if quota is not None:
        row.quota_override = quota
        # a period that surrounds the frozen clock, so nothing rolls over by accident
        row.period_start = inbox.clock.now()
        row.anchor_day = row.period_start.day
        row.period_end = service.next_month(row.period_start, row.anchor_day)
    if used is not None:
        row.used = used
    inbox.session.commit()
    return row


def used(inbox: InboxEnv) -> int:
    return plan(inbox).used


def notifications(inbox: InboxEnv, kind: str) -> list[Notification]:
    inbox.session.expire_all()
    return list(inbox.session.scalars(select(Notification).where(Notification.type == kind)))


def model_calls(provider: FakeLLMProvider) -> int:
    return len([c for c in provider.calls if c.task == "draft_reply"])


# --- counting ----------------------------------------------------------------------------------


def test_a_draft_with_text_counts_once(inbox: InboxEnv, gym, provider: FakeLLMProvider) -> None:
    plan(inbox, quota=100, used=0)
    draft = inbox.ask(PRICE_Q)
    assert draft.text and used(inbox) == 1
    # running the job again (a retry, a replay) does not charge again
    inbox.process()
    assert used(inbox) == 1


def test_a_run_that_ends_without_text_is_not_counted(
    inbox: InboxEnv, gym, provider: FakeLLMProvider
) -> None:
    plan(inbox, quota=100, used=0)
    inbox.deliver_and_process(
        None, attachments=[{"type": "image", "payload": {"url": "https://example.test/p.jpg"}}]
    )
    inbox.draft_now()
    draft = inbox.draft()
    assert draft is not None and draft.status == "needs_human" and not draft.text
    assert used(inbox) == 0


def test_two_customers_two_drafts(inbox: InboxEnv, gym) -> None:
    plan(inbox, quota=100, used=0)
    inbox.ask(PRICE_Q, customer="cust-1")
    inbox.ask(PRICE_Q, customer="cust-2")
    assert used(inbox) == 2


# --- the warnings ------------------------------------------------------------------------------


def test_the_warnings_are_sent_once_while_real_drafts_cross_the_thresholds(
    inbox: InboxEnv, gym
) -> None:
    plan(inbox, quota=5, used=0)  # limit 6
    for n in range(1, 4):
        inbox.ask(PRICE_Q, customer=f"c{n}")
    assert notifications(inbox, "quota.warning") == []  # 3 of 5
    inbox.ask(PRICE_Q, customer="c4")  # 4 of 5 is 80%
    assert len(notifications(inbox, "quota.warning")) == 2  # owner and manager
    inbox.ask(PRICE_Q, customer="c5")  # 5 of 5
    assert len(notifications(inbox, "quota.grace")) == 2
    inbox.ask(PRICE_Q, customer="c6")  # still drafted inside the grace
    assert used(inbox) == 6
    assert len(notifications(inbox, "quota.paused")) == 2
    assert len(notifications(inbox, "quota.warning")) == 2
    assert len(notifications(inbox, "quota.grace")) == 2


# --- the pause ---------------------------------------------------------------------------------


def paused_conversation(inbox: InboxEnv, provider: FakeLLMProvider) -> Conversation:
    plan(inbox, quota=10, used=11)  # the grace is used up
    before = model_calls(provider)
    inbox.deliver_and_process(PRICE_Q)
    inbox.draft_now()
    assert model_calls(provider) == before  # the model was not called
    return inbox.conversation()


def test_a_paused_workspace_still_receives_and_announces_the_message(
    inbox: InboxEnv, gym, provider: FakeLLMProvider
) -> None:
    conversation = paused_conversation(inbox, provider)
    # the message is in the inbox
    (message,) = [m for m in inbox.messages() if m.direction == "inbound"]
    assert message.text == PRICE_Q
    # a person is asked to answer: a needs-human draft that says why, and the usual notification
    draft = inbox.draft()
    assert draft is not None and (draft.status, draft.decision) == ("needs_human", "human_required")
    assert draft.decision_reasons == ["REPLY_QUOTA_PAUSED"] and not draft.text
    assert conversation.attention == "needs_human"
    waiting = notifications(inbox, "conversation.needs_human")
    assert {n.recipient_user_id for n in waiting} == {
        inbox.env.owner.user.id,
        inbox.env.manager.user.id,
    }
    assert all(n.params["reasons"] == ["REPLY_QUOTA_PAUSED"] for n in waiting)
    # and the owner is told once why drafting stopped
    assert len(notifications(inbox, "quota.paused")) == 2
    # nothing is stuck and nothing was counted
    assert [j.status for j in inbox.jobs("draft_reply")] == ["succeeded"]
    assert used(inbox) == 11


def automate(inbox: InboxEnv, *classes: str) -> None:
    items = [{"action_class": c, "mode": "auto"} for c in classes]
    response = inbox.env.call(inbox.env.owner, "PUT", "/automation-policies", json={"items": items})
    assert response.status_code == 200, response.text
    reviewed = inbox.env.call(inbox.env.owner, "POST", "/automation-policies/review")
    assert reviewed.status_code == 200, reviewed.text


def test_an_automatic_reply_is_counted_and_sent_while_there_is_allowance(
    inbox: InboxEnv, gym
) -> None:
    automate(inbox, "reply.pricing")
    plan(inbox, quota=100, used=0)
    draft = inbox.ask(PRICE_Q)
    assert inbox.refreshed(draft).status == "sent" and used(inbox) == 1


def test_a_paused_workspace_sends_nothing_by_itself(
    inbox: InboxEnv, gym, provider: FakeLLMProvider
) -> None:
    automate(inbox, "reply.pricing")
    paused_conversation(inbox, provider)
    assert inbox.sim_sent() == []
    draft = inbox.draft()
    assert draft is not None and draft.status == "needs_human"


def test_the_next_message_of_a_paused_workspace_waits_for_a_person_too(
    inbox: InboxEnv, gym, provider: FakeLLMProvider
) -> None:
    paused_conversation(inbox, provider)
    inbox.deliver_and_process("Salı günü açık mısınız?")
    inbox.draft_now()
    assert model_calls(provider) == 0
    draft = inbox.draft()
    assert draft is not None and draft.status == "needs_human"
    assert draft.decision_reasons == ["REPLY_QUOTA_PAUSED"]
    assert len([m for m in inbox.messages() if m.direction == "inbound"]) == 2
    assert len(notifications(inbox, "quota.paused")) == 2  # told once, not per message
    assert all(j.status == "succeeded" for j in inbox.jobs("draft_reply"))


def test_drafting_resumes_when_the_plan_changes(
    inbox: InboxEnv, gym, provider: FakeLLMProvider
) -> None:
    conversation = paused_conversation(inbox, provider)
    plan(inbox, quota=100)  # the operator moved the workspace to a bigger quota
    response = inbox.env.call(
        inbox.env.owner, "POST", f"/conversations/{conversation.id}/suggest-reply"
    )
    assert response.status_code == 202, response.text
    inbox.process()
    draft = inbox.draft()
    assert draft is not None and draft.text and draft.status == "pending_approval"
    assert used(inbox) == 12  # counted like any other draft
    assert model_calls(provider) == 1


def test_drafting_resumes_in_the_next_period(
    inbox: InboxEnv, gym, provider: FakeLLMProvider
) -> None:
    conversation = paused_conversation(inbox, provider)
    row = plan(inbox)
    row.period_end = inbox.clock.now() - timedelta(minutes=1)  # the period has just ended
    row.period_start = row.period_end - timedelta(days=30)
    inbox.session.commit()
    response = inbox.env.call(
        inbox.env.owner, "POST", f"/conversations/{conversation.id}/suggest-reply"
    )
    assert response.status_code == 202, response.text
    inbox.process()
    draft = inbox.draft()
    assert draft is not None and draft.text
    assert used(inbox) == 1  # a new period, a fresh count


def test_the_conversation_can_be_answered_by_hand_while_paused(
    inbox: InboxEnv, gym, provider: FakeLLMProvider
) -> None:
    conversation = paused_conversation(inbox, provider)
    response = inbox.env.call(
        inbox.env.owner,
        "POST",
        f"/conversations/{conversation.id}/replies",
        json={"text": "Merhaba, aylık üyelik ücretimiz 6.000 ₺.", "client_request_id": "manual-1"},
    )
    assert response.status_code == 201, response.text
    assert used(inbox) == 11  # a manual reply is not an AI draft
    assert model_calls(provider) == 0
