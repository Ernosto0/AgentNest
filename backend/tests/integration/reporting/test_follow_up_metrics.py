from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.inbox.models import ConversationFollowUp
from app.integrations.instagram.models import SocialAccount
from app.reporting import missed_customers
from tests.factories import knowledge_ctx, workspace_with_members
from tests.helpers.reporting import Builder, at


def seed_follow_up(builder: Builder, when, *, replied: bool = True):  # type: ignore[no-untyped-def]
    conversation = builder.conversation(when - timedelta(hours=7))
    inbound = builder.message(conversation, "inbound", when - timedelta(hours=7))
    answer = builder.draft(
        conversation,
        inbound,
        source="ai",
        decision="approval_required",
        created_at=when - timedelta(hours=6),
    )
    follow_up = builder.draft(
        conversation,
        inbound,
        source="approved_answer",
        decision="approval_required",
        created_at=when,
    )
    follow_up.intent = "follow_up"
    sent = builder.message(conversation, "outbound", when, draft=follow_up)
    builder.session.add(
        ConversationFollowUp(
            workspace_id=builder.workspace.id,
            conversation_id=conversation.id,
            answer_draft_id=answer.id,
            covers_through_message_id=inbound.id,
            answered_at=when - timedelta(hours=6),
            due_at=when,
            status="drafted",
            reply_draft_id=follow_up.id,
            drafted_at=when,
            is_simulated=builder.simulated,
        )
    )
    if replied:
        builder.message(conversation, "inbound", when + timedelta(hours=24))
        builder.message(conversation, "inbound", when + timedelta(minutes=1))
    return sent


def test_real_follow_up_counts_lists_and_local_week(db_session: Session) -> None:
    workspace, users = workspace_with_members(db_session)
    workspace.timezone = "Europe/Istanbul"
    owner = users["owner"]
    real = Builder(db_session, workspace, owner, simulated=False)
    monday = date(2026, 3, 9)
    # Sunday UTC is Monday locally: it must belong to this week (INV-19).
    current = seed_follow_up(real, at(monday, 0, 1))
    seed_follow_up(real, at(monday - timedelta(days=7), 12), replied=False)
    mock = SocialAccount(
        workspace_id=workspace.id,
        provider_kind="mock",
        external_account_id="historical-mock",
        status="disconnected",
    )
    db_session.add(mock)
    db_session.flush()
    seed_follow_up(Builder(db_session, workspace, owner, account=mock), at(monday, 12))
    # Even malformed false flags cannot make mock-account history real.
    seed_follow_up(
        Builder(db_session, workspace, owner, simulated=False, account=mock), at(monday, 13)
    )
    # A real foreign workspace must never appear in A's count or drilldown.
    foreign, foreign_users = workspace_with_members(db_session, name="Foreign report")
    seed_follow_up(
        Builder(db_session, foreign, foreign_users["owner"], simulated=False), at(monday, 12)
    )
    db_session.commit()
    clock = FrozenClock(at(monday + timedelta(days=2), 12))
    ctx = knowledge_ctx(workspace, owner, "owner")
    report = missed_customers.build_report(db_session, clock, ctx, monday)
    assert report.is_partial
    assert report.value("follow_ups_sent") == 1
    assert report.value("follow_up_replies") == 1
    sent_metric = next(m for m in report.metrics if m.key == "follow_ups_sent")
    reply_metric = next(m for m in report.metrics if m.key == "follow_up_replies")
    assert sent_metric.previous_value == 1
    assert reply_metric.previous_value == 0
    for key in ("follow_ups_sent", "follow_up_replies"):
        items = missed_customers.metric_items(db_session, clock, ctx, monday, key, locale="en")
        assert items.value == len(items.items) == 1
        assert items.items[0].id == current.id
