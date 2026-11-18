import uuid
from datetime import timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.agent.repository import scoped_account
from app.core.canonical import payload_hash
from app.inbox import follow_up
from app.inbox.approval_payload import approval_payload
from app.inbox.models import Conversation, ConversationFollowUp, Message, ReplyDraft
from app.inbox.payloads import FollowUpCheckPayload
from app.inbox.reply_workflow import SEND_MARGIN
from app.jobs.registry import RescheduleJob
from app.operations.send import execute_send_reply
from app.policy.rules_reply import WINDOW_MARGIN
from tests.integration.inbox.conftest import InboxEnv


def configure(inbox: InboxEnv, **changes: object) -> None:
    workspace = inbox.env.workspace
    workspace.settings = {**workspace.settings, **changes}
    inbox.session.commit()


def row(inbox: InboxEnv) -> ConversationFollowUp:
    inbox.session.expire_all()
    return inbox.session.scalars(select(ConversationFollowUp)).one()


def arm(inbox: InboxEnv, *, enabled: bool = True, intent: str = "pricing") -> ReplyDraft:
    configure(inbox, follow_up_enabled=enabled)
    inbox.seed_facts()
    draft = inbox.ask()
    draft.intent = intent
    inbox.session.commit()
    assert inbox.approve_and_send(draft).status == "sent"
    return draft


def check(inbox: InboxEnv, armed: ConversationFollowUp | None = None) -> None:
    armed = armed or row(inbox)
    follow_up.check(
        inbox.session,
        inbox.clock,
        inbox.env.ctx(inbox.env.owner),
        FollowUpCheckPayload(follow_up_id=armed.id, answer_draft_id=armed.answer_draft_id),
    )
    inbox.session.commit()


def draft_follow_up(inbox: InboxEnv) -> ReplyDraft:
    arm(inbox)
    inbox.clock.advance(hours=6)
    check(inbox)
    result = inbox.session.get(ReplyDraft, row(inbox).reply_draft_id)
    assert result is not None
    return result


def send(inbox: InboxEnv, draft: ReplyDraft):  # type: ignore[no-untyped-def]
    return execute_send_reply(
        inbox.factory, inbox.clock, inbox.settings, inbox.env.workspace.id, draft.id
    )


def test_default_off_creates_nothing(inbox: InboxEnv) -> None:
    arm(inbox, enabled=False)
    assert inbox.session.scalars(select(ConversationFollowUp)).all() == []
    assert inbox.jobs("follow_up_check") == []
    inbox.clock.advance(hours=25)
    inbox.process()
    assert inbox.session.scalars(select(ConversationFollowUp)).all() == []


@pytest.mark.parametrize("intent", ["pricing", "booking"])
def test_happy_path_and_duplicate_check(inbox: InboxEnv, intent: str) -> None:
    answer = arm(inbox, intent=intent)
    armed = row(inbox)
    assert armed.status == "scheduled"
    assert armed.due_at == armed.answered_at + timedelta(hours=6)
    jobs = inbox.jobs("follow_up_check")
    assert len(jobs) == 1
    assert jobs[0].run_at == armed.due_at
    inbox.clock.advance(hours=6)
    inbox.process()
    check(inbox)
    armed = row(inbox)
    assert armed.status == "drafted"
    draft = inbox.session.get(ReplyDraft, armed.reply_draft_id)
    assert draft is not None
    assert draft.intent == "follow_up"
    assert draft.status == "pending_approval"
    assert draft.decision == "approval_required"
    assert draft.decision_reasons == ["FOLLOW_UP_REQUIRES_APPROVAL"]
    assert draft.is_simulated
    assert armed.is_simulated
    approval = inbox.approval_of(draft)
    assert approval.kind == "authorization"
    assert approval.payload_hash == payload_hash(approval_payload(draft, inbox.conversation()))
    ctx = inbox.env.ctx(inbox.env.owner)
    follow_up.schedule_after_answer(
        inbox.session, inbox.clock, ctx, inbox.conversation(), answer, sent_at=inbox.clock.now()
    )
    inbox.session.commit()
    assert row(inbox).reply_draft_id == draft.id
    assert len(inbox.jobs("follow_up_check")) == 1


@pytest.mark.parametrize("change", ["hours", "owner", "agent", "controller"])
def test_noneligible_answers_do_not_arm(inbox: InboxEnv, change: str) -> None:
    arm(inbox, enabled=False)
    draft = inbox.session.scalars(select(ReplyDraft)).one()
    configure(inbox, follow_up_enabled=True)
    if change == "hours":
        draft.intent = "hours"
    elif change == "owner":
        draft.source = "owner"
    elif change == "agent":
        draft.origin = "agent"
    else:
        scoped_account(
            inbox.session, inbox.env.workspace.id, inbox.account.id
        ).controller_mode = "agent"
    if change != "agent":
        inbox.session.flush()
    conversation = inbox.session.get(Conversation, draft.conversation_id)
    assert conversation is not None
    follow_up.schedule_after_answer(
        inbox.session,
        inbox.clock,
        inbox.env.ctx(inbox.env.owner),
        conversation,
        draft,
        sent_at=inbox.clock.now(),
    )
    if change == "agent":
        draft.origin = "legacy"
    inbox.session.commit()
    assert inbox.session.scalars(select(ConversationFollowUp)).all() == []


@pytest.mark.parametrize(
    ("offset", "expected"), [(-60, "drafted"), (0, "skipped"), (360, "skipped")]
)
def test_draft_window_boundary(inbox: InboxEnv, offset: int, expected: str) -> None:
    arm(inbox)
    boundary = inbox.conversation().last_inbound_at + timedelta(hours=24) - WINDOW_MARGIN
    inbox.clock.advance(boundary + timedelta(seconds=offset) - inbox.clock.now())
    check(inbox)
    assert row(inbox).status == expected
    if expected == "skipped":
        assert row(inbox).reason_code == "MESSAGING_WINDOW_CLOSED"
        assert row(inbox).reply_draft_id is None


def test_arming_too_late_records_skip_without_job(inbox: InboxEnv) -> None:
    answer = arm(inbox, enabled=False)
    configure(inbox, follow_up_enabled=True)
    inbox.clock.advance(hours=20)
    follow_up.schedule_after_answer(
        inbox.session,
        inbox.clock,
        inbox.env.ctx(inbox.env.owner),
        inbox.conversation(),
        answer,
        sent_at=inbox.clock.now(),
    )
    inbox.session.commit()
    assert row(inbox).reason_code == "MESSAGING_WINDOW_CLOSED"
    assert inbox.jobs("follow_up_check") == []


@pytest.mark.parametrize(("offset", "status"), [(-1, "sent"), (0, "expired"), (61, "expired")])
def test_send_window_boundary(inbox: InboxEnv, offset: int, status: str) -> None:
    draft = draft_follow_up(inbox)
    assert inbox.decide(draft).status_code == 200
    boundary = inbox.conversation().last_inbound_at + timedelta(hours=24) - SEND_MARGIN
    inbox.clock.advance(boundary + timedelta(seconds=offset) - inbox.clock.now())
    outcome = send(inbox, draft)
    assert outcome.kind == status
    assert inbox.refreshed(draft).status == status
    if status == "expired":
        assert inbox.refreshed(draft).failure_code == "MESSAGING_WINDOW_CLOSED"
        assert inbox.operation(draft) is None
        assert len(inbox.sim_sent()) == 1  # original answer only
    else:
        assert len(inbox.sim_sent()) == 2


def test_expired_approval_cannot_send(inbox: InboxEnv) -> None:
    draft = draft_follow_up(inbox)
    inbox.clock.advance(hours=24)
    assert inbox.decide(draft).status_code == 409
    send(inbox, draft)
    assert inbox.operation(draft) is None


def test_unique_conversation_and_deletion(inbox: InboxEnv) -> None:
    arm(inbox)
    existing = row(inbox)
    duplicate = ConversationFollowUp(
        workspace_id=existing.workspace_id,
        conversation_id=existing.conversation_id,
        answer_draft_id=existing.answer_draft_id,
        covers_through_message_id=existing.covers_through_message_id,
        answered_at=existing.answered_at,
        due_at=existing.due_at,
        status="scheduled",
    )

    def insert_duplicate() -> None:
        inbox.session.add(duplicate)
        inbox.session.flush()

    with pytest.raises(IntegrityError), inbox.session.begin_nested():
        insert_duplicate()
    inbox.session.execute(delete(Conversation).where(Conversation.id == existing.conversation_id))
    inbox.session.commit()
    assert inbox.session.scalar(select(ConversationFollowUp.id)) is None


@pytest.mark.parametrize("stage", ["scheduled", "pending_approval", "queued"])
def test_customer_reply_cancels(inbox: InboxEnv, stage: str) -> None:
    draft = None
    if stage == "scheduled":
        arm(inbox)
    else:
        draft = draft_follow_up(inbox)
        if stage == "queued":
            assert inbox.decide(draft).status_code == 200
    inbox.deliver("Thanks", mid="customer-returned")
    from app.inbox import processing
    from app.inbox.models import InboundEvent

    event = inbox.session.scalars(
        select(InboundEvent).where(InboundEvent.status == "received")
    ).one()
    processing.process_inbound_event(
        inbox.session, inbox.clock, inbox.env.workspace.id, event.id, debounce_seconds=8
    )
    if stage == "scheduled":
        assert row(inbox).status == "cancelled"
        assert row(inbox).reason_code == "CUSTOMER_REPLIED"
        inbox.clock.advance(hours=6)
        check(inbox)
        assert row(inbox).reply_draft_id is None
    else:
        assert draft is not None
        assert inbox.refreshed(draft).status == (
            "superseded" if stage == "pending_approval" else "cancelled"
        )
        assert row(inbox).status == "drafted"
        assert send(inbox, draft).kind != "sent"


@pytest.mark.parametrize(
    "code", ["FOLLOW_UP_OFF", "HUMAN_TAKEOVER", "CONTROLLER_CHANGED", "CUSTOMER_REPLIED"]
)
def test_send_time_rejections(inbox: InboxEnv, code: str) -> None:
    draft = draft_follow_up(inbox)
    assert inbox.decide(draft).status_code == 200
    if code == "FOLLOW_UP_OFF":
        configure(inbox, follow_up_enabled=False)
    elif code == "HUMAN_TAKEOVER":
        inbox.conversation().handling_mode = "human"
    elif code == "CONTROLLER_CHANGED":
        scoped_account(
            inbox.session, inbox.env.workspace.id, inbox.account.id
        ).controller_mode = "agent"
    else:
        conversation = inbox.conversation()
        inbox.clock.advance(seconds=1)
        inbox.session.add(
            Message(
                workspace_id=conversation.workspace_id,
                conversation_id=conversation.id,
                social_account_id=conversation.social_account_id,
                direction="inbound",
                sender_kind="customer",
                provider_timestamp=inbox.clock.now(),
                text="Another question",
                is_simulated=True,
            )
        )
    inbox.session.commit()
    send(inbox, draft)
    assert inbox.refreshed(draft).status == "cancelled"
    assert inbox.refreshed(draft).failure_code == code
    assert inbox.operation(draft) is None


@pytest.mark.parametrize(
    "code",
    [
        "FOLLOW_UP_OFF",
        "HUMAN_TAKEOVER",
        "CONTROLLER_CHANGED",
        "ACCOUNT_NOT_CONNECTED",
        "OPEN_DRAFT_EXISTS",
        "FACT_NOT_USABLE",
        "GROUNDING_FAILED",
        "SOMEONE_ELSE_REPLIED",
    ],
)
def test_due_time_refusals(inbox: InboxEnv, code: str) -> None:
    arm(inbox)
    inbox.clock.advance(hours=6)
    if code == "FOLLOW_UP_OFF":
        configure(inbox, follow_up_enabled=False)
    elif code == "HUMAN_TAKEOVER":
        inbox.conversation().handling_mode = "human"
    elif code == "CONTROLLER_CHANGED":
        scoped_account(
            inbox.session, inbox.env.workspace.id, inbox.account.id
        ).cutover_generation += 1
    elif code == "ACCOUNT_NOT_CONNECTED":
        inbox.account.status = "disconnected"
    elif code == "OPEN_DRAFT_EXISTS":
        inbox.make_draft()
    elif code == "SOMEONE_ELSE_REPLIED":
        inbox.conversation().last_outbound_at = inbox.clock.now()
    else:
        configure(
            inbox,
            follow_up_text={
                "tr": "{{fact:booking.missing}}" if code == "FACT_NOT_USABLE" else "500 TL",
                "en": "",
            },
        )
    inbox.session.commit()
    check(inbox)
    assert row(inbox).reason_code == code
    assert row(inbox).status == ("cancelled" if code == "FOLLOW_UP_OFF" else "skipped")
    assert row(inbox).reply_draft_id is None


def test_hours_raised_reschedules(inbox: InboxEnv) -> None:
    arm(inbox)
    configure(inbox, follow_up_hours=8)
    inbox.clock.advance(hours=6)
    with pytest.raises(RescheduleJob) as exc:
        check(inbox)
    assert exc.value.run_at == row(inbox).answered_at + timedelta(hours=8)


def test_cancelled_row_rearms_for_next_answer(inbox: InboxEnv) -> None:
    arm(inbox)
    original_id = row(inbox).id
    inbox.clock.advance(seconds=1)
    inbox.deliver_and_process(mid="second-question")
    assert row(inbox).status == "cancelled"
    inbox.draft_now()
    next_answer = inbox.draft()
    assert next_answer is not None
    assert inbox.approve_and_send(next_answer).status == "sent"
    assert row(inbox).id == original_id
    assert row(inbox).answer_draft_id == next_answer.id
    assert row(inbox).status == "scheduled"
    inbox.clock.advance(hours=6)
    inbox.process()
    assert row(inbox).status == "drafted"


@pytest.mark.parametrize("status", ["verified", "unverified", "archived"])
def test_custom_fact_and_impact(inbox: InboxEnv, status: str) -> None:
    from app.knowledge import impact
    from app.knowledge.models import BusinessFact, FactReference

    arm(inbox)
    fact = inbox.session.scalars(
        select(BusinessFact).where(BusinessFact.key == "booking.instructions")
    ).one()
    if status != "verified":
        fact.status = status
    inbox.session.commit()
    configure(inbox, follow_up_text={"tr": "{{fact:booking.instructions}}", "en": ""})
    inbox.clock.advance(hours=6)
    check(inbox)
    if status != "verified":
        assert row(inbox).reason_code == "FACT_NOT_USABLE"
        return
    draft_id = row(inbox).reply_draft_id
    reference = inbox.session.scalars(
        select(FactReference).where(FactReference.referrer_id == draft_id)
    ).one()
    assert reference.fact_id == fact.id
    assert inbox.session.get(ReplyDraft, draft_id).validation["rendered"]
    old_version = fact.current_version
    fact.current_version += 1
    inbox.session.flush()
    impact.apply_change(
        inbox.session,
        inbox.clock,
        inbox.env.ctx(inbox.env.owner),
        fact,
        "value_changed",
        old_version,
    )
    inbox.session.commit()
    assert inbox.session.get(ReplyDraft, draft_id).status == "superseded"


def test_foreign_and_stale_jobs_are_noops(inbox: InboxEnv) -> None:
    arm(inbox)
    armed = row(inbox)
    inbox.clock.advance(hours=6)
    ctx = inbox.env.ctx(inbox.env.owner)
    for payload in [
        FollowUpCheckPayload(follow_up_id=uuid.uuid4(), answer_draft_id=armed.answer_draft_id),
        FollowUpCheckPayload(follow_up_id=armed.id, answer_draft_id=uuid.uuid4()),
    ]:
        follow_up.check(inbox.session, inbox.clock, ctx, payload)
    assert row(inbox).status == "scheduled"
