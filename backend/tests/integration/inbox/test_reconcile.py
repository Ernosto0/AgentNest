"""P4-08: an ambiguous send is reconciled and never repeated.

AC-G5 (both branches), INV-05, INV-06; echo matching; stuck operations."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from app.inbox import echoes
from app.inbox.echoes import Echo
from app.inbox.models import ReplyDraft
from app.integrations.instagram import webhook_format as wf
from app.integrations.instagram.base import AccountRef, SendResult
from app.integrations.instagram.mock import MockInstagramProvider
from app.jobs.models import Job
from app.notifications.models import Notification
from app.operations.jobs import reconcile_stuck_operations
from app.operations.models import Operation
from app.operations.payloads import ReconcileStuckPayload
from app.operations.resolution import text_sha256
from app.operations.send import execute_send_reply
from tests.integration.inbox.conftest import APP_SECRET, InboxEnv

PRICE_Q = "Aylık üyelik ne kadar?"
TEXT = "Merhaba! Aylık üyelik ücretimiz 6.000 ₺ / ay."


@pytest.fixture
def gym(inbox: InboxEnv):  # type: ignore[no-untyped-def]
    return inbox.seed_facts()


def unknown_send(inbox: InboxEnv) -> ReplyDraft:
    """Approve a reply whose send times out *after* Instagram accepted it."""
    draft = inbox.ask(PRICE_Q)
    inbox.fail("send", "timeout_after_success")
    assert inbox.decide(draft).status_code == 200
    inbox.process()
    return draft


def outbound(inbox: InboxEnv) -> list[tuple[str, str | None]]:
    return [(m.sender_kind, m.text) for m in inbox.messages() if m.direction == "outbound"]


# --- the unknown outcome -------------------------------------------------------------------------


def test_a_timeout_after_success_is_an_unknown_outcome_not_a_failure(inbox: InboxEnv, gym) -> None:
    draft = unknown_send(inbox)
    refreshed = inbox.refreshed(draft)
    operation = inbox.operation(draft)
    assert refreshed.status == "outcome_unknown"
    assert operation is not None and operation.status == "outcome_unknown"
    assert operation.last_error_code == "OUTCOME_UNKNOWN"
    assert len(inbox.sim_sent()) == 1  # the message really went out
    assert outbound(inbox) == []  # but we do not record it until it is confirmed
    reconcile = inbox.jobs("reconcile_send")
    assert [(j.run_at, j.payload["round"]) for j in reconcile] == [
        (inbox.clock.now() + timedelta(minutes=2), 1)
    ]
    assert [j.job_type for j in inbox.jobs("demo_emit_echo")] == ["demo_emit_echo"]
    inbox.session.expire_all()
    assert inbox.conversation().attention == "none"  # nothing for the owner to do yet


def test_an_unexpected_error_after_the_call_is_treated_as_unknown_and_never_retried(
    inbox: InboxEnv, gym
) -> None:
    draft = inbox.ask(PRICE_Q)
    inbox.decide(draft)

    class Exploding:
        calls = 0

        def send_text_message(
            self, account: AccountRef, recipient_id: str, text: str
        ) -> SendResult:
            Exploding.calls += 1
            raise RuntimeError("the connection broke somewhere")

    outcome = execute_send_reply(
        inbox.factory,
        inbox.clock,
        inbox.settings,
        inbox.env.workspace.id,
        draft.id,
        provider=Exploding(),  # type: ignore[arg-type]
    )
    assert outcome.kind == "unknown"
    assert inbox.refreshed(draft).status == "outcome_unknown"
    # running the send again does not call the provider
    assert (
        execute_send_reply(
            inbox.factory,
            inbox.clock,
            inbox.settings,
            inbox.env.workspace.id,
            draft.id,
            provider=Exploding(),  # type: ignore[arg-type]
        ).kind
        == "skipped"
    )
    assert Exploding.calls == 1


# --- AC-G5, first branch: the echo arrives -------------------------------------------------------


def test_ac_g5_the_echo_confirms_the_send(inbox: InboxEnv, gym) -> None:
    draft = unknown_send(inbox)
    inbox.clock.advance(timedelta(seconds=6))
    inbox.process()  # the simulated Instagram delivers the echo webhook

    refreshed = inbox.refreshed(draft)
    assert refreshed.status == "sent"
    operation = inbox.operation(draft)
    assert operation is not None and operation.status == "succeeded"
    assert operation.result["resolved_by"] == "echo"
    (stored,) = inbox.sim_sent()  # never resent
    assert operation.result["message_id"] == stored.message_id
    assert outbound(inbox) == [("business_app", TEXT)]  # ours, not "typed in the app"
    assert inbox.conversation().attention == "none"
    entries = {
        e.action
        for e in inbox.session.scalars(select(AuditLog).where(AuditLog.resource_id == draft.id))
    }
    assert "reply.sent" in entries and "reply.outcome_unconfirmed" not in entries


def test_the_reconciliation_that_comes_after_the_echo_does_nothing(inbox: InboxEnv, gym) -> None:
    draft = unknown_send(inbox)
    inbox.clock.advance(timedelta(seconds=6))
    inbox.process()
    inbox.clock.advance(timedelta(minutes=3))
    inbox.process()  # the reconcile job finds the operation already resolved
    assert inbox.refreshed(draft).status == "sent"
    assert len(inbox.sim_sent()) == 1 and len(outbound(inbox)) == 1


# --- the lookup ----------------------------------------------------------------------------------


def test_without_an_echo_the_conversation_lookup_finds_the_message(inbox: InboxEnv, gym) -> None:
    inbox.fail("echo", "transient")  # Instagram never echoes this one
    draft = unknown_send(inbox)
    inbox.clock.advance(timedelta(seconds=6))
    inbox.process()
    assert inbox.refreshed(draft).status == "outcome_unknown"  # no echo came

    inbox.clock.advance(timedelta(minutes=2))
    inbox.process()  # reconcile_send, round 1
    refreshed = inbox.refreshed(draft)
    assert refreshed.status == "sent"
    operation = inbox.operation(draft)
    assert operation is not None and operation.result["resolved_by"] == "lookup"
    assert len(inbox.sim_sent()) == 1
    assert outbound(inbox) == [("business_app", TEXT)]


# --- AC-G5, second branch: nothing confirms it ----------------------------------------------------


def test_ac_g5_without_an_echo_or_a_lookup_it_is_reported_unconfirmed_and_never_resent(
    inbox: InboxEnv, gym
) -> None:
    inbox.fail("echo", "transient")
    inbox.fail("lookup", "transient", remaining=None)  # the lookup is unavailable throughout
    draft = unknown_send(inbox)

    for _ in range(5):  # rounds at +2, +4, +6, +8 and +10 minutes
        inbox.clock.advance(timedelta(minutes=2))
        inbox.process()
        if inbox.refreshed(draft).status != "outcome_unknown":
            break

    refreshed = inbox.refreshed(draft)
    assert (refreshed.status, refreshed.failure_code) == ("failed", "OUTCOME_UNCONFIRMED")
    operation = inbox.operation(draft)
    assert operation is not None and operation.status == "failed"
    assert operation.last_error_code == "OUTCOME_UNCONFIRMED"
    assert len(inbox.sim_sent()) == 1  # still exactly one message, never repeated
    assert inbox.conversation().attention == "failed"
    inbox.session.expire_all()
    notified = inbox.session.scalars(
        select(Notification).where(Notification.type == "reply.failed")
    ).all()
    assert {n.recipient_user_id for n in notified} == {
        inbox.env.owner.user.id,
        inbox.env.manager.user.id,
    }
    assert notified[0].params["code"] == "OUTCOME_UNCONFIRMED"
    actions = {e.action for e in inbox.session.scalars(select(AuditLog))}
    assert "reply.outcome_unconfirmed" in actions


def test_the_reconciliation_is_checked_every_two_minutes_for_ten(inbox: InboxEnv, gym) -> None:
    inbox.fail("echo", "transient")
    inbox.fail("lookup", "transient", remaining=None)
    unknown_send(inbox)
    rounds = []
    for _ in range(6):
        inbox.clock.advance(timedelta(minutes=2))
        inbox.process()
        rounds = sorted(j.payload["round"] for j in inbox.jobs("reconcile_send"))
    assert rounds == [1, 2, 3, 4, 5]  # then the window is over


def test_a_late_echo_after_giving_up_is_not_taken_for_a_reply_typed_in_the_app(
    inbox: InboxEnv, gym
) -> None:
    inbox.fail("echo", "transient")
    inbox.fail("lookup", "transient", remaining=None)
    draft = unknown_send(inbox)
    for _ in range(5):
        inbox.clock.advance(timedelta(minutes=2))
        inbox.process()
    assert inbox.refreshed(draft).status == "failed"
    (stored,) = inbox.sim_sent()

    late = wf.build_echo_payload(
        inbox.account.external_account_id, "cust-1", stored.message_id, TEXT, stored.sent_at
    )
    assert inbox.post(late).status_code == 200
    inbox.process()
    assert outbound(inbox) == [("business_app", TEXT)]  # recorded as ours
    assert inbox.refreshed(draft).status == "failed"  # the terminal state is not rewritten
    actions = [e.action for e in inbox.session.scalars(select(AuditLog))]
    assert "reply.late_confirmation" in actions


# --- echo matching -------------------------------------------------------------------------------


def operation_in_flight(inbox: InboxEnv, status: str, text: str = TEXT) -> Operation:
    draft = inbox.ask(PRICE_Q)
    inbox.decide(draft)
    fresh = inbox.refreshed(draft)
    now = inbox.clock.now()
    operation = Operation(
        workspace_id=inbox.env.workspace.id,
        operation_type="send_reply",
        idempotency_key=f"send_reply:{draft.id}",
        subject_type="reply_draft",
        subject_id=draft.id,
        social_account_id=inbox.account.id,
        provider_kind="mock",
        status=status,
        attempts=1,
        started_at=now,
        provider_ref={"recipient_id": "cust-1", "text_sha256": text_sha256(text)},
        is_simulated=True,
    )
    inbox.session.add(operation)
    fresh.status = "sending" if status == "in_progress" else "outcome_unknown"
    inbox.session.commit()
    return operation


def echo_of(
    inbox: InboxEnv, text: str, mid: str = "e-1", *, after: timedelta = timedelta(0)
) -> Echo:
    return Echo(inbox.account.id, "cust-1", mid, text, inbox.clock.now() + after)


def test_an_echo_of_a_send_in_flight_is_claimed_and_its_id_remembered(inbox: InboxEnv, gym) -> None:
    operation = operation_in_flight(inbox, "in_progress")
    assert echoes.claimed_by_a_send(
        inbox.session, inbox.clock, inbox.env.ctx(inbox.env.owner), echo_of(inbox, TEXT)
    )
    inbox.session.flush()
    inbox.session.refresh(operation)
    assert operation.provider_ref["echo_mid"] == "e-1"
    assert operation.status == "in_progress"  # the send's own outcome is still to be recorded


def test_an_echo_with_other_text_is_not_ours(inbox: InboxEnv, gym) -> None:
    operation_in_flight(inbox, "in_progress")
    ctx = inbox.env.ctx(inbox.env.owner)
    assert not echoes.claimed_by_a_send(inbox.session, inbox.clock, ctx, echo_of(inbox, "Merhaba!"))


def test_an_echo_for_another_customer_is_not_ours(inbox: InboxEnv, gym) -> None:
    operation_in_flight(inbox, "outcome_unknown")
    other = Echo(inbox.account.id, "cust-2", "e-9", TEXT, inbox.clock.now())
    assert not echoes.claimed_by_a_send(
        inbox.session, inbox.clock, inbox.env.ctx(inbox.env.owner), other
    )


def test_an_echo_outside_the_reconciliation_window_is_not_ours(inbox: InboxEnv, gym) -> None:
    operation_in_flight(inbox, "outcome_unknown")
    ctx = inbox.env.ctx(inbox.env.owner)
    late = echo_of(inbox, TEXT, after=timedelta(minutes=30))
    assert not echoes.claimed_by_a_send(inbox.session, inbox.clock, ctx, late)


def test_a_reply_typed_in_the_app_after_a_send_is_still_recognised_as_native(
    inbox: InboxEnv, gym
) -> None:
    draft = inbox.ask(PRICE_Q)
    inbox.approve_and_send(draft)
    inbox.clock.advance(timedelta(minutes=1))
    native = wf.build_echo_payload(
        inbox.account.external_account_id, "cust-1", "typed-in-app", "Size dönüş yapacağım",
        inbox.clock.now(),
    )  # fmt: skip
    inbox.post(native)
    inbox.process()
    assert ("business_native", "Size dönüş yapacağım") in outbound(inbox)


def test_the_echo_a_successful_send_causes_is_not_taken_for_a_native_reply(
    inbox: InboxEnv, gym
) -> None:
    draft = inbox.ask(PRICE_Q)
    inbox.approve_and_send(draft)
    inbox.clock.advance(timedelta(seconds=2))
    inbox.process()  # demo_emit_echo delivers the echo of the message we sent
    assert outbound(inbox) == [("business_app", TEXT)]
    assert inbox.refreshed(draft).status == "sent"


# --- stuck operations ----------------------------------------------------------------------------


def stuck_job(inbox: InboxEnv):  # type: ignore[no-untyped-def]
    from app.jobs.registry import JobContext

    return JobContext(
        job_id=uuid.uuid4(),
        job_type="reconcile_stuck_operations",
        workspace_id=None,
        correlation_id=None,
        payload=ReconcileStuckPayload(),
        attempt=1,
        max_attempts=1,
        session_factory=inbox.factory,
        clock=inbox.clock,
        _heartbeat=lambda: None,
    )


def test_a_send_stuck_in_progress_becomes_unknown_and_is_reconciled_not_resent(
    inbox: InboxEnv, gym
) -> None:
    operation = operation_in_flight(inbox, "in_progress")
    draft = inbox.session.get(ReplyDraft, operation.subject_id)
    inbox.clock.advance(timedelta(minutes=14))
    reconcile_stuck_operations(stuck_job(inbox))
    inbox.session.expire_all()
    assert inbox.session.get(Operation, operation.id).status == "in_progress"  # type: ignore[union-attr]

    inbox.clock.advance(timedelta(minutes=2))
    reconcile_stuck_operations(stuck_job(inbox))
    inbox.session.expire_all()
    refreshed_op = inbox.session.get(Operation, operation.id)
    assert refreshed_op is not None and refreshed_op.status == "outcome_unknown"
    assert inbox.refreshed(draft).status == "outcome_unknown"  # type: ignore[arg-type]
    rounds = [j.payload["round"] for j in inbox.jobs("reconcile_send")]
    assert rounds == [1]
    assert inbox.sim_sent() == []  # nothing was sent to find this out


def test_a_stuck_operation_that_is_found_in_the_lookup_is_closed_as_sent(
    inbox: InboxEnv, gym
) -> None:
    operation = operation_in_flight(inbox, "in_progress")
    draft = inbox.session.get(ReplyDraft, operation.subject_id)
    MockInstagramProvider(inbox.factory, inbox.clock, APP_SECRET).send_text_message(
        AccountRef(inbox.account.id, inbox.env.workspace.id, inbox.account.external_account_id),
        "cust-1",
        TEXT,
    )  # the worker died after Instagram accepted it
    inbox.clock.advance(timedelta(minutes=16))
    reconcile_stuck_operations(stuck_job(inbox))
    inbox.clock.advance(timedelta(minutes=3))
    inbox.process()
    assert inbox.refreshed(draft).status == "sent"  # type: ignore[arg-type]
    assert len(inbox.sim_sent()) == 1


def test_reconciliation_jobs_have_distinct_keys_per_round(inbox: InboxEnv, gym) -> None:
    inbox.fail("echo", "transient")
    inbox.fail("lookup", "transient", remaining=None)
    unknown_send(inbox)
    inbox.clock.advance(timedelta(minutes=2))
    inbox.process()
    keys = {
        j.dedup_key
        for j in inbox.session.scalars(select(Job).where(Job.job_type == "reconcile_send"))
    }
    assert len(keys) == 2 and all(k.startswith("reconcile_send:") for k in keys)
