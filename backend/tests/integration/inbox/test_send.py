"""P4-08: sending an approved reply through the operations ledger.

AC-B5, AC-B9 (one message), the provider error mapping of workflows.md §G.1, and INV-05/06:
a draft causes at most one message, and an ambiguous send is never repeated."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from app.core.canonical import payload_hash
from app.core.errors import RetryableError
from app.inbox.approval_payload import approval_payload
from app.inbox.models import Message, ReplyDraft
from app.integrations.instagram.base import AccountRef, SendResult
from app.integrations.instagram.mock import MockInstagramProvider
from app.jobs.models import Job
from app.notifications.models import Notification
from app.operations.send import execute_send_reply
from tests.integration.inbox.conftest import APP_SECRET, InboxEnv

PRICE_Q = "Aylık üyelik ne kadar?"


@pytest.fixture
def gym(inbox: InboxEnv):  # type: ignore[no-untyped-def]
    return inbox.seed_facts()


def pending(inbox: InboxEnv, text: str = PRICE_Q, **kwargs: object) -> ReplyDraft:
    return inbox.ask(text, **kwargs)  # type: ignore[arg-type]


def run_send(inbox: InboxEnv, draft: ReplyDraft, provider: object = None):  # type: ignore[no-untyped-def]
    return execute_send_reply(
        inbox.factory,
        inbox.clock,
        inbox.settings,
        inbox.env.workspace.id,
        draft.id,
        provider=provider,  # type: ignore[arg-type]
    )


class CountingProvider:
    """Wraps the mock and counts the sends that really reach it."""

    def __init__(self, inbox: InboxEnv) -> None:
        self.inner = MockInstagramProvider(inbox.factory, inbox.clock, APP_SECRET)
        self.calls: list[tuple[str, str]] = []

    def send_text_message(self, account: AccountRef, recipient_id: str, text: str) -> SendResult:
        self.calls.append((recipient_id, text))
        return self.inner.send_text_message(account, recipient_id, text)

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        return getattr(self.inner, name)


# --- AC-B5 ---------------------------------------------------------------------------------------


def test_ac_b5_an_approved_reply_is_sent_once_and_recorded_everywhere(inbox: InboxEnv, gym) -> None:
    draft = pending(inbox)
    sent = inbox.approve_and_send(draft)

    assert sent.status == "sent"
    operation = inbox.operation(draft)
    assert operation is not None
    assert operation.status == "succeeded"
    assert operation.idempotency_key == f"send_reply:{draft.id}"
    assert operation.operation_type == "send_reply" and operation.attempts == 1
    assert operation.provider_ref["recipient_id"] == "cust-1"
    assert "6.000" not in str(operation.provider_ref)  # a hash, never the text
    assert operation.is_simulated is True and operation.completed_at == inbox.clock.now()

    (stored,) = inbox.sim_sent()  # the simulator saw exactly one message
    assert stored.text == "Merhaba! Aylık üyelik ücretimiz 6.000 ₺ / ay."
    assert stored.recipient_id == "cust-1"
    assert operation.result == {"message_id": stored.message_id}

    outbound = [m for m in inbox.messages() if m.direction == "outbound"]
    assert [(m.sender_kind, m.external_message_id, m.reply_draft_id) for m in outbound] == [
        ("business_app", stored.message_id, draft.id)
    ]
    assert outbound[0].is_simulated is True and outbound[0].text == stored.text
    conversation = inbox.conversation()
    assert conversation.last_outbound_at == inbox.clock.now()
    assert conversation.attention == "none"
    assert inbox.approval_of(draft).operation_id == operation.id  # the approval is consumed

    actions = {
        e.action
        for e in inbox.session.scalars(select(AuditLog).where(AuditLog.is_simulated.is_(True)))
    }
    assert {"approval.approved", "reply.sent", "reply_draft.sent"} <= actions
    sent_entry = inbox.session.scalars(
        select(AuditLog).where(AuditLog.action == "reply.sent")
    ).one()
    assert sent_entry.metadata_["operation_id"] == str(operation.id)
    assert "6.000" not in str(sent_entry.metadata_)


def test_ac_b9_running_the_send_again_sends_nothing_more(inbox: InboxEnv, gym) -> None:
    draft = pending(inbox)
    inbox.approve_and_send(draft)
    assert inbox.decide(draft).status_code == 409  # the second decision
    spy = CountingProvider(inbox)
    for _ in range(3):  # a retried or duplicated job
        outcome = run_send(inbox, draft, spy)
        assert (outcome.kind, outcome.detail) == ("sent", "already_sent")
    assert spy.calls == []
    assert len(inbox.sim_sent()) == 1  # INV-06


def test_a_send_job_for_a_draft_that_is_not_queued_does_nothing(inbox: InboxEnv, gym) -> None:
    draft = pending(inbox)  # pending approval, never approved
    spy = CountingProvider(inbox)
    outcome = run_send(inbox, draft, spy)
    assert outcome.kind == "skipped" and spy.calls == []
    assert inbox.operation(draft) is None  # no ledger row without an approved send


def test_a_send_that_is_already_in_flight_is_not_started_twice(inbox: InboxEnv, gym) -> None:
    draft = pending(inbox)
    assert inbox.decide(draft).status_code == 200
    inbox.refreshed(draft).status = "sending"  # another worker holds it
    inbox.session.commit()
    spy = CountingProvider(inbox)
    assert run_send(inbox, draft, spy).kind == "skipped"
    assert spy.calls == []


# --- INV-15: the ledger row is committed before the provider is called ---------------------------


@pytest.mark.commits
def test_inv15_the_operation_is_committed_in_progress_before_the_provider_is_called(
    session_factory,
    clock,
    settings,  # type: ignore[no-untyped-def]
) -> None:
    from sqlalchemy.orm import Session

    from app.approvals import service as approvals
    from app.core.clock import FrozenClock
    from app.inbox.models import Conversation
    from app.integrations.instagram.models import SimInboundMessage, SocialAccount
    from app.knowledge.models import BusinessFact  # noqa: F401
    from tests.factories import create_user, create_workspace

    with session_factory() as s:
        workspace = create_workspace(s, name="Real commits")
        create_user(s)
        account = SocialAccount(
            workspace_id=workspace.id,
            provider_kind="mock",
            external_account_id="mock-x",
            status="connected",
            capabilities={"messaging": True},
        )
        s.add(account)
        s.flush()
        conversation = Conversation(
            workspace_id=workspace.id,
            social_account_id=account.id,
            customer_external_id="cust-1",
            last_inbound_at=clock.now(),
            is_simulated=True,
        )
        s.add(conversation)
        s.flush()
        inbound = Message(
            workspace_id=workspace.id,
            conversation_id=conversation.id,
            social_account_id=account.id,
            direction="inbound",
            sender_kind="customer",
            external_message_id="in-1",
            text="fiyat?",
            provider_timestamp=clock.now(),
            is_simulated=True,
        )
        s.add(inbound)
        s.add(
            SimInboundMessage(
                workspace_id=workspace.id,
                social_account_id=account.id,
                sender_id="cust-1",
                mid="in-1",
                received_at=clock.now(),
            )
        )
        s.flush()
        draft = ReplyDraft(
            workspace_id=workspace.id,
            conversation_id=conversation.id,
            covers_through_message_id=inbound.id,
            source="ai",
            text="Merhaba",
            decision="auto",
            decision_reasons=["POLICY_AUTO"],
            status="queued",
            created_by_actor_type="system",
            is_simulated=True,
            created_at=clock.now(),
        )
        s.add(draft)
        s.flush()
        from app.approvals.grants import record_policy_grant
        from app.inbox.system import system_context

        ctx = system_context(s, workspace.id)
        assert ctx is not None
        approval = record_policy_grant(
            s,
            clock,
            ctx,
            action="reply.send",
            subject_type="reply_draft",
            subject_id=draft.id,
            subject_version=1,
            payload=approval_payload(draft, conversation),
            summary={},
            required_permission="reply.approve",
            expires_at=clock.now() + timedelta(hours=23),
            execute_before=clock.now() + timedelta(hours=23, minutes=55),
            is_simulated=True,
        )
        draft.approval_id = approval.id
        s.commit()
        workspace_id, draft_id = workspace.id, draft.id
    assert approvals and isinstance(clock, FrozenClock) and Session

    seen: dict[str, str] = {}

    class Spy(CountingProvider):
        def __init__(self) -> None:
            self.inner = MockInstagramProvider(session_factory, clock, APP_SECRET)
            self.calls = []

        def send_text_message(self, account, recipient_id, text):  # type: ignore[no-untyped-def]
            with session_factory() as other:  # another connection: sees only committed rows
                from app.operations.models import Operation

                op = other.scalars(select(Operation)).one()
                seen["operation"] = op.status
                seen["draft"] = other.get(ReplyDraft, draft_id).status  # type: ignore[union-attr]
            return super().send_text_message(account, recipient_id, text)

    outcome = execute_send_reply(
        session_factory,
        clock,
        settings,
        workspace_id,
        draft_id,
        provider=Spy(),  # type: ignore[arg-type]
    )
    assert outcome.kind == "sent"
    assert seen == {"operation": "in_progress", "draft": "sending"}


# --- provider errors: workflows.md §G.1 ----------------------------------------------------------


def test_a_transient_error_is_retried_and_the_message_still_goes_out_once(
    inbox: InboxEnv, gym
) -> None:
    draft = pending(inbox)
    inbox.fail("send", "transient", remaining=2)
    assert inbox.decide(draft).status_code == 200
    inbox.process()  # attempt 1 fails
    operation = inbox.operation(draft)
    assert operation is not None and operation.status == "retry_wait"
    assert operation.attempts == 1 and operation.last_error_code == "PROVIDER_UNAVAILABLE"
    assert inbox.refreshed(draft).status == "queued"  # waiting for the retry
    assert inbox.sim_sent() == []

    for _ in range(4):  # the backoff is 1 then 5 minutes, with jitter: wait until it is due
        inbox.clock.advance(timedelta(minutes=6))
        inbox.process()
        if inbox.refreshed(draft).status == "sent":
            break
    assert inbox.refreshed(draft).status == "sent"
    final = inbox.operation(draft)
    assert final is not None and final.status == "succeeded" and final.attempts == 3
    assert len(inbox.sim_sent()) == 1
    assert inbox.account.consecutive_failures == 0  # any success resets the counter


def test_a_transient_error_counts_against_the_account(inbox: InboxEnv, gym) -> None:
    draft = pending(inbox)
    inbox.fail("send", "transient", remaining=2)
    inbox.decide(draft)
    inbox.process()
    inbox.session.expire_all()
    assert inbox.account.consecutive_failures == 1


def test_the_retries_stop_after_the_last_attempt(inbox: InboxEnv, gym) -> None:
    draft = pending(inbox)
    inbox.fail("send", "transient", remaining=None)
    inbox.decide(draft)
    for _ in range(8):
        inbox.process()
        inbox.clock.advance(timedelta(minutes=31))
    refreshed = inbox.refreshed(draft)
    assert (refreshed.status, refreshed.failure_code) == ("failed", "PROVIDER_UNAVAILABLE")
    operation = inbox.operation(draft)
    assert operation is not None and operation.status == "failed" and operation.attempts == 6
    assert inbox.sim_sent() == []
    inbox.session.expire_all()
    assert inbox.conversation().attention == "failed"
    assert inbox.session.scalars(
        select(Notification).where(Notification.type == "reply.failed")
    ).all()


def test_a_rate_limit_asks_for_the_providers_retry_after(inbox: InboxEnv, gym) -> None:
    draft = pending(inbox)
    inbox.fail("send", "rate_limited", retry_after=900)
    inbox.decide(draft)
    outcome = run_send(inbox, draft)
    assert outcome.kind == "retry" and outcome.retry_after_seconds == 900
    assert inbox.account.consecutive_failures == 0  # not a health failure
    operation = inbox.operation(draft)
    assert operation is not None and operation.last_error_code == "PROVIDER_RATE_LIMITED"


def test_a_rejected_token_waits_for_the_owner_and_asks_for_a_reconnection(
    inbox: InboxEnv, gym
) -> None:
    draft = pending(inbox)
    inbox.fail("send", "auth_revoked")
    inbox.decide(draft)
    outcome = run_send(inbox, draft)
    assert (outcome.kind, outcome.error_code) == ("waiting", "ACCOUNT_NEEDS_REAUTH")
    inbox.session.expire_all()
    assert inbox.account.status == "needs_reauth"
    assert inbox.refreshed(draft).status == "queued"  # still sendable if the window allows
    notice = inbox.session.scalars(
        select(Notification).where(Notification.type == "account.needs_reauth")
    ).all()
    assert [n.recipient_user_id for n in notice] == [inbox.env.owner.user.id]
    assert notice[0].severity == "critical"
    assert inbox.sim_sent() == []


def test_a_missing_permission_fails_the_send_and_the_capability(inbox: InboxEnv, gym) -> None:
    draft = pending(inbox)
    inbox.fail("send", "permission_missing")
    inbox.decide(draft)
    outcome = run_send(inbox, draft)
    assert (outcome.kind, outcome.error_code) == ("failed", "CAPABILITY_MISSING")
    inbox.session.expire_all()
    assert inbox.account.capabilities["messaging"] is False
    refreshed = inbox.refreshed(draft)
    assert (refreshed.status, refreshed.failure_code) == ("failed", "CAPABILITY_MISSING")


def test_the_provider_closing_the_window_expires_the_draft(inbox: InboxEnv, gym) -> None:
    draft = pending(inbox)
    inbox.fail("send", "window_closed")
    inbox.decide(draft)
    outcome = run_send(inbox, draft)
    assert (outcome.kind, outcome.error_code) == ("expired", "MESSAGING_WINDOW_CLOSED")
    refreshed = inbox.refreshed(draft)
    assert (refreshed.status, refreshed.failure_code) == ("expired", "MESSAGING_WINDOW_CLOSED")
    operation = inbox.operation(draft)
    assert operation is not None and operation.status == "failed"


def test_a_request_the_provider_rejects_fails_and_tells_the_owner(inbox: InboxEnv, gym) -> None:
    draft = pending(inbox)
    inbox.fail("send", "invalid_media")
    inbox.decide(draft)
    outcome = run_send(inbox, draft)
    assert (outcome.kind, outcome.error_code) == ("failed", "PROVIDER_REJECTED")
    assert inbox.refreshed(draft).status == "failed"
    inbox.session.expire_all()
    assert inbox.session.scalars(
        select(Notification).where(Notification.type == "reply.failed")
    ).all()


# --- the checks made just before sending ---------------------------------------------------------


def test_nothing_is_sent_once_the_window_is_nearly_closed(inbox: InboxEnv, gym) -> None:
    draft = pending(inbox)
    assert inbox.decide(draft).status_code == 200
    inbox.clock.advance(timedelta(hours=23, minutes=59, seconds=30))  # inside the last minute
    spy = CountingProvider(inbox)
    outcome = run_send(inbox, draft, spy)
    assert (outcome.kind, outcome.error_code) == ("expired", "MESSAGING_WINDOW_CLOSED")
    assert spy.calls == [] and inbox.refreshed(draft).status == "expired"


def test_a_draft_whose_text_changed_after_approval_is_never_sent(inbox: InboxEnv, gym) -> None:
    """INV-16: the approval covers exactly the approved text."""
    draft = pending(inbox)
    assert inbox.decide(draft).status_code == 200
    fresh = inbox.refreshed(draft)
    fresh.text = "Aylık üyelik ücretimiz 1 ₺!"  # someone changed it after approval
    inbox.session.commit()
    spy = CountingProvider(inbox)
    outcome = run_send(inbox, draft, spy)
    assert (outcome.kind, outcome.error_code) == ("failed", "APPROVAL_STALE")
    assert spy.calls == []
    refreshed = inbox.refreshed(draft)
    assert (refreshed.status, refreshed.failure_code) == ("cancelled", "APPROVAL_STALE")


def test_a_new_draft_version_invalidates_the_old_approval(inbox: InboxEnv, gym) -> None:
    draft = pending(inbox)
    assert inbox.decide(draft).status_code == 200
    fresh = inbox.refreshed(draft)
    fresh.version = 2
    inbox.session.commit()
    spy = CountingProvider(inbox)
    assert run_send(inbox, draft, spy).error_code == "APPROVAL_STALE"
    assert spy.calls == []


def test_an_approval_can_authorise_one_operation_only(inbox: InboxEnv, gym) -> None:
    draft = pending(inbox)
    inbox.approve_and_send(draft)
    approval = inbox.approval_of(draft)
    assert approval.operation_id == inbox.operation(draft).id  # type: ignore[union-attr]
    from app.approvals import service as approvals

    with pytest.raises(Exception) as raised:
        approvals.assert_executable(
            inbox.session,
            inbox.clock,
            inbox.env.ctx(inbox.env.owner),
            approval.id,
            1,
            operation_id=uuid.uuid4(),
        )
    assert "CONFLICT_STATE" in str(raised.value)


def test_a_disconnected_account_keeps_the_draft_queued_and_asks_for_a_retry(
    inbox: InboxEnv, gym
) -> None:
    draft = pending(inbox)
    inbox.decide(draft)
    inbox.account.status = "needs_reauth"
    inbox.session.commit()
    outcome = run_send(inbox, draft)
    assert (outcome.kind, outcome.error_code) == ("waiting", "ACCOUNT_NOT_CONNECTED")
    assert inbox.refreshed(draft).status == "queued"
    assert inbox.operation(draft) is None  # nothing started, so nothing in the ledger


def test_the_job_retries_while_the_account_is_unavailable(inbox: InboxEnv, gym) -> None:
    from app.inbox.payloads import SendReplyPayload
    from app.jobs.registry import JobContext
    from app.operations.jobs import send_reply

    draft = pending(inbox)
    inbox.decide(draft)
    inbox.account.status = "needs_reauth"
    inbox.session.commit()
    job = JobContext(
        job_id=uuid.uuid4(),
        job_type="send_reply",
        workspace_id=inbox.env.workspace.id,
        correlation_id=None,
        payload=SendReplyPayload(reply_draft_id=draft.id),
        attempt=1,
        max_attempts=6,
        session_factory=inbox.factory,
        clock=inbox.clock,
        _heartbeat=lambda: None,
    )
    with pytest.raises(RetryableError):
        send_reply(job)


def test_a_crash_after_the_effect_is_repaired_without_sending_again(inbox: InboxEnv, gym) -> None:
    """The operation succeeded but the draft was not closed: the next run only repairs it."""
    draft = pending(inbox)
    assert inbox.decide(draft).status_code == 200
    spy = CountingProvider(inbox)
    run_send(inbox, draft, spy)
    assert len(spy.calls) == 1
    fresh = inbox.refreshed(draft)
    fresh.status = "queued"  # as if T5 had not committed the draft
    inbox.session.commit()
    messages_before = len([m for m in inbox.messages() if m.direction == "outbound"])
    outcome = run_send(inbox, draft, spy)
    assert (outcome.kind, outcome.detail) == ("sent", "repaired")
    assert len(spy.calls) == 1 and len(inbox.sim_sent()) == 1
    assert inbox.refreshed(draft).status == "sent"
    assert len([m for m in inbox.messages() if m.direction == "outbound"]) == messages_before


def test_the_approval_hash_is_the_hash_of_what_is_sent(inbox: InboxEnv, gym) -> None:
    draft = pending(inbox)
    approval = inbox.approval_of(draft)
    inbox.approve_and_send(draft)
    (stored,) = inbox.sim_sent()
    sent = inbox.refreshed(draft)
    assert sent.text == stored.text
    assert approval.payload_hash == payload_hash({**approval_payload(sent, inbox.conversation())})


def test_every_row_a_simulated_send_produces_is_marked_simulated(inbox: InboxEnv, gym) -> None:
    """AC-X2 (partial): the mock's output is labelled as simulated everywhere."""
    draft = pending(inbox)
    inbox.approve_and_send(draft)
    inbox.session.expire_all()
    assert inbox.refreshed(draft).is_simulated
    assert inbox.operation(draft).is_simulated  # type: ignore[union-attr]
    assert all(m.is_simulated for m in inbox.session.scalars(select(Message)))
    assert inbox.conversation().is_simulated
    assert inbox.approval_of(draft).is_simulated
    sends = list(inbox.session.scalars(select(Job).where(Job.job_type == "send_reply")))
    assert [j.status for j in sends] == ["succeeded"]
