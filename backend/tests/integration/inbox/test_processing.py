"""P4-04: inbound processing. Conversations, messages, ordering, echoes, supersession,
debounced draft jobs, human mode."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from app.inbox import echoes
from app.inbox.models import InboundEvent
from app.integrations.instagram import webhook_format as wf
from app.notifications.models import Notification
from tests.integration.inbox.conftest import InboxEnv


def event(inbox: InboxEnv) -> InboundEvent:
    inbox.session.expire_all()
    return inbox.session.scalars(select(InboundEvent).order_by(InboundEvent.received_at)).first()  # type: ignore[return-value]


# --- a customer message ------------------------------------------------------------------------


def test_a_message_creates_the_conversation_and_the_message(inbox: InboxEnv) -> None:
    sent_at = inbox.clock.now() - timedelta(seconds=3)
    inbox.deliver_and_process("Aylık üyelik ne kadar?", mid="m-1", at=sent_at)

    conversation = inbox.conversation()
    assert conversation.handling_mode == "automatic"
    assert conversation.attention == "none"
    assert conversation.last_inbound_at == sent_at
    assert conversation.last_message_at == sent_at
    assert conversation.last_outbound_at is None
    assert conversation.is_simulated is True

    (message,) = inbox.messages()
    assert (message.direction, message.sender_kind) == ("inbound", "customer")
    assert message.external_message_id == "m-1"
    assert message.text == "Aylık üyelik ne kadar?"
    assert message.provider_timestamp == sent_at
    assert message.is_simulated is True
    assert message.social_account_id == inbox.account.id

    done = event(inbox)
    assert done.status == "processed"
    assert done.processed_at == inbox.clock.now()


def test_receiving_a_message_is_audited_without_its_text(inbox: InboxEnv) -> None:
    inbox.deliver_and_process("gizli içerik", mid="m-1")
    (entry,) = inbox.session.scalars(select(AuditLog).where(AuditLog.action == "message.received"))
    assert entry.workspace_id == inbox.env.workspace.id
    assert entry.is_simulated is True
    assert "gizli" not in str(entry.metadata_)
    assert entry.correlation_id == event(inbox).correlation_id


def test_the_same_customer_continues_one_conversation(inbox: InboxEnv) -> None:
    inbox.deliver_and_process("bir", mid="m-1")
    inbox.deliver_and_process("iki", mid="m-2")
    inbox.deliver_and_process("üç", customer="cust-2", mid="m-3")
    assert [m.text for m in inbox.messages("cust-1")] == ["bir", "iki"]
    assert [m.text for m in inbox.messages("cust-2")] == ["üç"]


def test_processing_an_event_twice_changes_nothing(inbox: InboxEnv) -> None:
    from app.inbox import processing

    inbox.deliver_and_process(mid="m-1")
    processing.process_inbound_event(
        inbox.session, inbox.clock, inbox.env.workspace.id, event(inbox).id, debounce_seconds=8
    )
    assert len(inbox.messages()) == 1
    assert len(inbox.jobs("draft_reply")) == 1


def test_a_message_id_that_is_already_stored_is_not_stored_again(inbox: InboxEnv) -> None:
    """INV-06: unique (account, provider message id), even if a second event row exists."""
    inbox.deliver_and_process(mid="m-1")
    inbox.session.add(
        InboundEvent(
            workspace_id=inbox.env.workspace.id,
            social_account_id=inbox.account.id,
            provider_kind="mock",
            dedup_key="ig:mock-golkent:replayed-by-another-route",
            event_type="message",
            payload=event(inbox).payload,
            status="received",
            correlation_id=event(inbox).correlation_id,
            is_simulated=True,
        )
    )
    inbox.session.commit()
    from app.inbox import processing

    replay = inbox.session.scalars(
        select(InboundEvent).where(InboundEvent.dedup_key.like("%replayed%"))
    ).one()
    processing.process_inbound_event(
        inbox.session, inbox.clock, inbox.env.workspace.id, replay.id, debounce_seconds=8
    )
    assert len(inbox.messages()) == 1
    assert len(inbox.jobs("draft_reply")) == 1  # no second draft for the same message


def test_attachment_only_messages_are_stored(inbox: InboxEnv) -> None:
    inbox.deliver_and_process(
        None, mid="m-1", attachments=[{"type": "image", "url": "https://example.test/a.jpg"}]
    )
    (message,) = inbox.messages()
    assert message.text is None
    assert message.attachments == [
        {"type": "image", "url": "https://example.test/a.jpg", "note": None}
    ]


# --- ordering ------------------------------------------------------------------------------------


def test_out_of_order_delivery_cannot_move_the_conversation_backwards(inbox: InboxEnv) -> None:
    now = inbox.clock.now()
    inbox.deliver_and_process("ikinci", mid="m-2", at=now)
    inbox.deliver_and_process("birinci", mid="m-1", at=now - timedelta(minutes=5))

    conversation = inbox.conversation()
    assert conversation.last_inbound_at == now
    assert conversation.last_message_at == now
    assert [m.text for m in inbox.messages()] == ["birinci", "ikinci"]  # by provider time


# --- debounced draft jobs -----------------------------------------------------------------------


def test_a_message_schedules_the_conversations_draft_job_after_the_debounce(
    inbox: InboxEnv,
) -> None:
    inbox.deliver(mid="m-1")
    inbox.process()  # processes the event; the draft job is not due yet
    (job,) = inbox.jobs("draft_reply")
    conversation = inbox.conversation()
    assert job.run_at == inbox.clock.now() + timedelta(
        seconds=inbox.settings.reply_debounce_seconds
    )
    assert job.payload == {
        "conversation_id": str(conversation.id),
        "message_id": None,  # the job drafts for whichever message is newest when it runs
        "requested": False,
    }
    assert job.dedup_key == f"draft_reply:{conversation.id}"
    assert job.workspace_id == inbox.env.workspace.id


def test_a_burst_leaves_one_job_per_conversation_and_keeps_its_run_at(inbox: InboxEnv) -> None:
    inbox.deliver_and_process("mesaj 1", mid="m-1")
    (first,) = inbox.jobs("draft_reply")
    for number in (2, 3):
        inbox.clock.advance(timedelta(seconds=2))
        inbox.deliver_and_process(f"mesaj {number}", mid=f"m-{number}")
    inbox.deliver_and_process("mesaj 3", mid="m-3")  # redelivered
    (job,) = inbox.jobs("draft_reply")
    assert job.id == first.id
    assert job.run_at == first.run_at  # not extended: a stream of messages cannot postpone it


def test_another_conversation_gets_its_own_job(inbox: InboxEnv) -> None:
    inbox.deliver_and_process("bir", customer="cust-1", mid="m-1")
    inbox.deliver_and_process("iki", customer="cust-2", mid="m-2")
    jobs = inbox.jobs("draft_reply")
    assert len(jobs) == 2 and len({j.dedup_key for j in jobs}) == 2


# --- human mode ----------------------------------------------------------------------------------


def test_human_mode_skips_drafting_and_asks_for_a_person(inbox: InboxEnv) -> None:
    inbox.deliver_and_process(mid="m-1")  # creates the conversation
    conversation = inbox.conversation()
    conversation.handling_mode = "human"
    inbox.session.commit()
    jobs_before = len(inbox.jobs("draft_reply"))

    inbox.deliver_and_process("hâlâ orada mısınız?", mid="m-2")

    assert len(inbox.jobs("draft_reply")) == jobs_before
    assert inbox.conversation().attention == "needs_human"
    notified = list(
        inbox.session.scalars(
            select(Notification).where(Notification.type == "conversation.needs_human")
        )
    )
    # owner and manager hold reply.approve; staff do not
    assert {n.recipient_user_id for n in notified} == {
        inbox.env.owner.user.id,
        inbox.env.manager.user.id,
    }
    assert all(n.params["reasons"] == ["HUMAN_TAKEOVER"] for n in notified)
    assert all(n.is_simulated for n in notified)


# --- supersession --------------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["pending_approval", "needs_human"])
def test_a_new_message_supersedes_a_draft_waiting_for_a_person(
    inbox: InboxEnv, status: str
) -> None:
    inbox.deliver_and_process(mid="m-1")
    draft = inbox.make_draft(status)
    inbox.deliver_and_process("bir şey daha", mid="m-2")

    refreshed = inbox.draft()
    assert refreshed is not None and refreshed.id == draft.id
    assert refreshed.status == "superseded"
    assert refreshed.failure_code == "NEW_INBOUND"
    assert inbox.approval_status(draft) in (None, "cancelled")
    if status == "pending_approval":
        assert inbox.approval_status(draft) == "cancelled"
    assert inbox.conversation().attention == "none"


def test_a_new_message_does_not_touch_a_queued_or_sending_draft(inbox: InboxEnv) -> None:
    inbox.deliver_and_process(mid="m-1")
    draft = inbox.make_draft("queued", with_approval=False)
    inbox.deliver_and_process("bir şey daha", mid="m-2")
    assert inbox.draft().status == "queued"  # type: ignore[union-attr]

    draft.status = "sending"
    inbox.session.commit()
    inbox.deliver_and_process("ve bir şey daha", mid="m-3")
    assert inbox.draft().status == "sending"  # type: ignore[union-attr]


# --- echoes --------------------------------------------------------------------------------------


def echo_payload(inbox: InboxEnv, text: str = "Merhaba, ben yazıyorum", mid: str = "native-1"):  # type: ignore[no-untyped-def]
    return wf.build_echo_payload(
        inbox.account.external_account_id, "cust-1", mid, text, inbox.clock.now()
    )


def test_an_echo_with_an_unknown_id_is_a_reply_typed_in_the_instagram_app(
    inbox: InboxEnv,
) -> None:
    inbox.deliver_and_process(mid="m-1")
    inbox.clock.advance(timedelta(seconds=30))
    assert inbox.post(echo_payload(inbox)).status_code == 200
    inbox.process()

    outbound = [m for m in inbox.messages() if m.direction == "outbound"]
    assert [(m.sender_kind, m.text) for m in outbound] == [
        ("business_native", "Merhaba, ben yazıyorum")
    ]
    conversation = inbox.conversation()
    assert conversation.last_outbound_at == inbox.clock.now()
    assert conversation.attention == "none"


@pytest.mark.parametrize(
    ("status", "expected", "reason"),
    [
        ("pending_approval", "superseded", "OWNER_REPLIED_NATIVELY"),
        ("needs_human", "superseded", "OWNER_REPLIED_NATIVELY"),
        ("queued", "cancelled", "OWNER_REPLIED_NATIVELY"),
    ],
)
def test_a_native_reply_retires_the_open_draft(
    inbox: InboxEnv, status: str, expected: str, reason: str
) -> None:
    inbox.deliver_and_process(mid="m-1")
    draft = inbox.make_draft(status, with_approval=status == "pending_approval")
    inbox.clock.advance(timedelta(seconds=30))
    inbox.post(echo_payload(inbox))
    inbox.process()

    refreshed = inbox.draft()
    assert refreshed is not None
    assert (refreshed.status, refreshed.failure_code) == (expected, reason)
    if status == "pending_approval":
        assert inbox.approval_status(draft) == "cancelled"


def test_a_native_reply_leaves_a_draft_that_is_being_sent_alone(inbox: InboxEnv) -> None:
    inbox.deliver_and_process(mid="m-1")
    inbox.make_draft("queued", with_approval=False).status = "sending"
    inbox.session.commit()
    inbox.post(echo_payload(inbox))
    inbox.process()
    assert inbox.draft().status == "sending"  # type: ignore[union-attr]


def test_the_echo_of_a_message_we_already_know_is_not_a_native_reply(inbox: InboxEnv) -> None:
    inbox.deliver_and_process(mid="m-1")
    inbox.post(echo_payload(inbox, mid="native-1"))
    inbox.process()
    # a second event row for the same provider id (e.g. replayed through another path)
    inbox.post(echo_payload(inbox, text="başka metin", mid="native-1"))
    inbox.process()
    assert len([m for m in inbox.messages() if m.direction == "outbound"]) == 1


def test_an_echo_claimed_by_a_send_is_not_recorded_as_a_native_reply(inbox: InboxEnv) -> None:
    claimed: list[echoes.Echo] = []

    def matcher(session, clock, ctx, echo) -> bool:  # type: ignore[no-untyped-def]
        claimed.append(echo)
        return True

    with echoes.matchers_snapshot():
        echoes.register_matcher(matcher)
        inbox.deliver_and_process(mid="m-1")
        inbox.post(echo_payload(inbox, mid="our-send-1"))
        inbox.process()

    assert [(e.mid, e.customer_id, e.text) for e in claimed] == [
        ("our-send-1", "cust-1", "Merhaba, ben yazıyorum")
    ]
    assert [m for m in inbox.messages() if m.direction == "outbound"] == []
    assert event_status(inbox, "echo") == "processed"


def event_status(inbox: InboxEnv, event_type: str) -> str:
    inbox.session.expire_all()
    return (
        inbox.session.scalars(select(InboundEvent).where(InboundEvent.event_type == event_type))
        .one()
        .status
    )


# --- other events and edge cases -----------------------------------------------------------------


def test_reactions_and_read_receipts_are_marked_processed_without_a_message(
    inbox: InboxEnv,
) -> None:
    inbox.deliver_and_process(mid="m-1")
    account_id = inbox.account.external_account_id
    inbox.post(
        wf.build_payload(
            account_id,
            inbox.clock.now(),
            wf.reaction_item(account_id, "cust-1", "m-1", inbox.clock.now()),
            wf.read_item(account_id, "cust-1", "m-1", inbox.clock.now()),
        )
    )
    inbox.process()
    assert event_status(inbox, "reaction") == "processed"
    assert event_status(inbox, "read") == "processed"
    assert len(inbox.messages()) == 1


def test_an_account_disconnected_after_ingest_ignores_the_event(inbox: InboxEnv) -> None:
    inbox.deliver(mid="m-1")
    inbox.account.status = "disconnected"
    inbox.session.commit()
    inbox.process()
    done = event(inbox)
    assert (done.status, done.ignore_reason) == ("ignored", "ACCOUNT_DISCONNECTED")
    assert inbox.session.scalars(select(InboundEvent)).all()
    from app.inbox.models import Conversation

    assert inbox.session.scalars(select(Conversation)).all() == []


def test_a_failing_event_is_marked_failed_after_the_last_attempt(inbox: InboxEnv) -> None:
    """The dead-job hook records the failure on the event instead of losing it silently."""
    from app.inbox.jobs import _on_event_dead as _on_dead
    from app.inbox.payloads import ProcessInboundEventPayload
    from app.jobs.registry import JobContext

    inbox.deliver(mid="m-1")
    stored = event(inbox)
    job = JobContext(
        job_id=stored.id,
        job_type="process_inbound_event",
        workspace_id=inbox.env.workspace.id,
        correlation_id=stored.correlation_id,
        payload=ProcessInboundEventPayload(event_id=stored.id),
        attempt=3,
        max_attempts=3,
        session_factory=inbox.factory,
        clock=inbox.clock,
        _heartbeat=lambda: None,
    )
    _on_dead(job, "INTERNAL_ERROR")
    failed = event(inbox)
    assert (failed.status, failed.error_code) == ("failed", "INTERNAL_ERROR")
