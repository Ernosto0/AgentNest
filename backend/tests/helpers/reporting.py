"""A day of persisted records with a known, different count for every report metric (AC-E1).

``build_day`` inserts the rows straight into the tables with explicit timestamps, so the expected
numbers in ``EXPECTED`` are facts about the script below, not outputs of the code under test.
The day is ``2026-03-10`` in ``Europe/Istanbul`` (UTC+3). The report period is the whole local
day and ``now`` is its end, as if the report were generated right after midnight.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.approvals.models import Approval
from app.audit.models import AuditLog
from app.content.models import ContentItem
from app.core.context import WorkspaceContext
from app.identity.models import User, Workspace
from app.inbox.models import Conversation, InboundEvent, Message, ReplyDraft
from app.integrations.instagram.models import SocialAccount
from app.operations.models import Operation
from app.reporting.periods import day_bounds
from tests.factories import create_user, create_workspace, knowledge_ctx

DAY = date(2026, 3, 10)
TIMEZONE = "Europe/Istanbul"

EXPECTED: dict[str, int | float] = {
    "inbound_messages": 15,
    "conversations_with_inbound": 8,
    "new_conversations": 6,
    "replies_sent": 40,
    "replies_sent_auto": 13,
    "replies_sent_approved": 12,
    "replies_sent_by_owner": 14,
    "native_replies": 5,
    "escalations": 7,
    "missed_conversations": 11,
    "median_first_response_minutes": 6.5,
    "attention_now": 9,
    "unanswered_open_now": 3,
    "pending_approvals_now": 4,
    "content_published": 2,
    "content_failed": 1,
    "content_scheduled_next_24h": 10,
    "content_on_hold_now": 16,
    "fact_changes": 17,
    "integration_errors": 18,
}
EXPECTED_BREAKDOWN = {"command.update_fact": 1, "content.publish": 1, "reply.send": 2}
# The answered inbound bursts behind the median, in minutes.
EXPECTED_BURSTS = sorted([5, 10, 20, 2, 30, 1, 5, 8, 10, 5])


def at(day: date, hour: int, minute: int = 0, second: int = 0, tz: str = TIMEZONE) -> datetime:
    """The instant (UTC) at local wall-clock time ``hour:minute:second`` of ``day``."""
    local = datetime.combine(day, time(hour, minute, second), tzinfo=ZoneInfo(tz))
    return local.astimezone(UTC)


@dataclass
class Scenario:
    workspace: Workspace
    account: SocialAccount
    user: User
    ctx: WorkspaceContext
    start: datetime
    end: datetime
    now: datetime


class Builder:
    """Inserts rows for one workspace. Everything is flagged ``simulated`` unless told otherwise."""

    def __init__(
        self,
        session: Session,
        workspace: Workspace,
        user: User,
        *,
        simulated: bool = True,
        account: SocialAccount | None = None,
    ) -> None:
        self.session = session
        self.workspace = workspace
        self.user = user
        self.simulated = simulated
        if account is not None:
            self.account = account
            return
        self.account = SocialAccount(
            workspace_id=workspace.id,
            platform="instagram",
            provider_kind="mock" if simulated else "meta",
            external_account_id=f"ext-{uuid.uuid4().hex[:12]}",
            username="gym",
            status="connected",
            capabilities={},
            granted_scopes=[],
        )
        session.add(self.account)
        session.flush()

    # -- inbox ----------------------------------------------------------------------------

    def conversation(
        self, created_at: datetime, *, attention: str = "none", simulated: bool | None = None
    ) -> Conversation:
        conversation = Conversation(
            workspace_id=self.workspace.id,
            social_account_id=self.account.id,
            customer_external_id=f"cust-{uuid.uuid4().hex[:12]}",
            attention=attention,
            is_simulated=self.simulated if simulated is None else simulated,
            created_at=created_at,
        )
        self.session.add(conversation)
        self.session.flush()
        return conversation

    def message(
        self,
        conversation: Conversation,
        direction: str,
        when: datetime,
        *,
        kind: str | None = None,
        draft: ReplyDraft | None = None,
        deleted: bool = False,
        simulated: bool | None = None,
    ) -> Message:
        sender = kind or ("customer" if direction == "inbound" else "business_app")
        message = Message(
            workspace_id=self.workspace.id,
            conversation_id=conversation.id,
            social_account_id=self.account.id,
            direction=direction,
            sender_kind=sender,
            provider_timestamp=when,
            reply_draft_id=draft.id if draft else None,
            is_deleted=deleted,
            is_simulated=self.simulated if simulated is None else simulated,
        )
        self.session.add(message)
        self.session.flush()
        # Keep the conversation's denormalised timestamps as the app keeps them.
        if direction == "inbound" and not deleted:
            conversation.last_inbound_at = max(filter(None, [conversation.last_inbound_at, when]))
        elif direction == "outbound":
            conversation.last_outbound_at = max(filter(None, [conversation.last_outbound_at, when]))
        conversation.last_message_at = max(filter(None, [conversation.last_message_at, when]))
        return message

    def draft(
        self,
        conversation: Conversation,
        covers: Message,
        *,
        source: str,
        decision: str,
        status: str = "sent",
        created_at: datetime,
    ) -> ReplyDraft:
        draft = ReplyDraft(
            workspace_id=self.workspace.id,
            conversation_id=conversation.id,
            covers_through_message_id=covers.id,
            source=source,
            decision=decision,
            status=status,
            created_by_actor_type="system",
            is_simulated=self.simulated,
            created_at=created_at,
        )
        self.session.add(draft)
        self.session.flush()
        return draft

    def reply(
        self,
        conversation: Conversation,
        covers: Message,
        when: datetime,
        *,
        source: str,
        decision: str,
    ) -> Message:
        """A draft and the outbound message that sent it."""
        draft = self.draft(conversation, covers, source=source, decision=decision, created_at=when)
        return self.message(conversation, "outbound", when, draft=draft)

    # -- other tables ---------------------------------------------------------------------

    def approval(self, action: str, status: str) -> Approval:
        approval = Approval(
            workspace_id=self.workspace.id,
            kind="authorization",
            action=action,
            subject_type="reply_draft",
            subject_id=uuid.uuid4(),
            subject_version=1,
            payload_hash="0" * 64,
            summary={},
            required_permission="reply.approve",
            status=status,
            requested_by_actor_type="system",
            expires_at=datetime(2030, 1, 1, tzinfo=UTC),
            is_simulated=self.simulated,
        )
        self.session.add(approval)
        self.session.flush()
        return approval

    def content(self, status: str, **fields: Any) -> ContentItem:
        item = ContentItem(
            workspace_id=self.workspace.id,
            content_type="feed_image",
            status=status,
            title="post",
            created_by_user_id=self.user.id,
            is_simulated=self.simulated,
            **fields,
        )
        self.session.add(item)
        self.session.flush()
        return item

    def audit(self, action: str, when: datetime, resource_id: uuid.UUID | None = None) -> AuditLog:
        entry = AuditLog(
            workspace_id=self.workspace.id,
            occurred_at=when,
            actor_type="system",
            action=action,
            resource_type="x",
            resource_id=resource_id or uuid.uuid4(),
            is_simulated=self.simulated,
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def operation(self, status: str, completed_at: datetime | None) -> Operation:
        operation = Operation(
            workspace_id=self.workspace.id,
            operation_type="send_reply",
            idempotency_key=f"send_reply:{uuid.uuid4()}",
            subject_type="reply_draft",
            subject_id=uuid.uuid4(),
            social_account_id=self.account.id,
            provider_kind=self.account.provider_kind,
            status=status,
            completed_at=completed_at,
            is_simulated=self.simulated,
        )
        self.session.add(operation)
        self.session.flush()
        return operation

    def inbound_event(self, status: str, received_at: datetime) -> InboundEvent:
        event = InboundEvent(
            workspace_id=self.workspace.id,
            social_account_id=self.account.id,
            provider_kind=self.account.provider_kind,
            dedup_key=f"evt-{uuid.uuid4()}",
            event_type="message",
            status=status,
            correlation_id=uuid.uuid4(),
            is_simulated=self.simulated,
            received_at=received_at,
        )
        self.session.add(event)
        self.session.flush()
        return event


def build_day(
    session: Session,
    *,
    workspace: Workspace | None = None,
    user: User | None = None,
    simulated: bool = True,
) -> Scenario:
    """Insert the whole script for ``DAY`` and return the period to report on."""
    workspace = workspace or create_workspace(session, timezone=TIMEZONE)
    user = user or create_user(session)
    b = Builder(session, workspace, user, simulated=simulated)
    d = DAY
    prev = d - timedelta(days=1)
    start, end = day_bounds(d, TIMEZONE)
    now = end

    def t(hour: int, minute: int = 0, second: int = 0, day: date = d) -> datetime:
        return at(day, hour, minute, second)

    old = t(9, day=d - timedelta(days=5))

    # --- six new conversations (created in the period) ------------------------------------
    n1, n2, n3, n4, n5, n6 = (
        b.conversation(t(h, 0), attention=a)
        for h, a in [
            (9, "none"),
            (10, "none"),
            (12, "needs_approval"),
            (14, "none"),
            (15, "needs_human"),
            (16, "failed"),
        ]
    )
    o1, o2 = b.conversation(old), b.conversation(old)

    # N1: two bursts, answered by an automatic and an approved reply.
    m = b.message(n1, "inbound", t(9, 0))
    b.reply(n1, m, t(9, 5), source="ai", decision="auto")
    b.message(n1, "inbound", t(9, 30))
    m = b.message(n1, "inbound", t(9, 31))
    b.reply(n1, m, t(9, 40), source="ai", decision="approval_required")

    # N2: two owner replies; one escalation draft that was superseded.
    m = b.message(n2, "inbound", t(10, 0))
    b.draft(n2, m, source="ai", decision="human_required", status="superseded", created_at=t(10, 5))
    b.reply(n2, m, t(10, 20), source="owner", decision="approval_required")
    m = b.message(n2, "inbound", t(11, 0))
    b.reply(n2, m, t(11, 2), source="owner", decision="approval_required")

    # N3: two owner replies, then a customer message nobody answered.
    m = b.message(n3, "inbound", t(12, 0))
    b.draft(
        n3, m, source="ai", decision="human_required", status="superseded", created_at=t(12, 10)
    )
    b.reply(n3, m, t(12, 30), source="owner", decision="approval_required")
    b.reply(n3, m, t(12, 45), source="owner", decision="approval_required")
    b.message(n3, "inbound", t(13, 0))

    # N4: an automatic reply and one outbound message without a draft.
    m = b.message(n4, "inbound", t(14, 0))
    b.reply(n4, m, t(14, 1), source="ai", decision="auto")
    b.message(n4, "outbound", t(14, 30))

    # N5: an unanswered message and four escalation drafts (one open, three superseded).
    m5 = b.message(n5, "inbound", t(15, 0))
    b.draft(
        n5, m5, source="ai", decision="human_required", status="needs_human", created_at=t(15, 1)
    )
    for minute in (2, 3, 4):
        b.draft(
            n5,
            m5,
            source="ai",
            decision="human_required",
            status="superseded",
            created_at=t(15, minute),
        )

    # N6: a deleted first message (ignored), then two bursts answered by approved replies.
    m = b.message(n6, "inbound", t(16, 0), deleted=True)
    m = b.message(n6, "inbound", t(16, 5))
    b.draft(n6, m, source="ai", decision="human_required", status="superseded", created_at=t(16, 6))
    b.reply(n6, m, t(16, 10), source="ai", decision="approval_required")
    b.message(n6, "inbound", t(17, 0))
    m = b.message(n6, "inbound", t(17, 5))
    b.reply(n6, m, t(17, 8), source="approved_answer", decision="approval_required")

    # O1: older conversation, a message that is still unanswered.
    b.message(o1, "inbound", t(18, 0))
    # O2: older conversation, answered five times from the Instagram app.
    b.message(o2, "inbound", t(8, 0))
    b.message(o2, "outbound", t(8, 10), kind="business_native")
    b.message(o2, "inbound", t(8, 20))
    for minute in (25, 30, 40, 50):
        b.message(o2, "outbound", t(8, minute), kind="business_native")

    # F1: outbound-only filler (its one inbound message is three days old).
    f1 = b.conversation(old)
    anchor = b.message(f1, "inbound", t(10, 0, day=d - timedelta(days=3)))
    for source, decision, count in [
        ("ai", "auto", 11),
        ("ai", "approval_required", 9),
        ("owner", "approval_required", 10),
    ]:
        for i in range(count):
            b.reply(f1, anchor, t(19, i, 30), source=source, decision=decision)

    # Window ended in the period: 11 conversations with no reply (the first at the very start).
    for i in range(11):
        c = b.conversation(old)
        b.message(c, "inbound", t(0, 0, day=prev) + timedelta(hours=i))
    # ... one that was answered, one whose window ended a second before the period.
    answered = b.conversation(old)
    b.message(answered, "inbound", t(12, 0, day=prev))
    b.message(answered, "outbound", t(13, 0, day=prev), kind="business_native")
    late = b.conversation(old)
    b.message(late, "inbound", t(23, 59, 59, day=d - timedelta(days=2)))

    # Conversations that need attention but have no messages (6 + N3, N5, N6 = 9).
    for state in [
        "needs_human",
        "needs_approval",
        "failed",
        "needs_human",
        "needs_approval",
        "failed",
    ]:
        b.conversation(old, attention=state)

    # --- approvals --------------------------------------------------------------------------
    for action in ["reply.send", "reply.send", "content.publish", "command.update_fact"]:
        b.approval(action, "pending")
    for status in ["approved", "approved", "rejected", "expired"]:
        b.approval("reply.send", status)

    # --- content ----------------------------------------------------------------------------
    b.content("published", published_at=t(11, 0))
    b.content("published", published_at=t(23, 59, 59))
    b.content("published", published_at=t(0, 0, day=d + timedelta(days=1)))  # next local day
    b.content("published", published_at=t(23, 59, 59, day=prev))  # previous local day
    failed = b.content("failed")
    for minute in (10, 20, 30):  # one item failing three times counts once
        b.audit("content.failed", t(13, minute), failed.id)
    b.audit("content.failed", t(23, 59, 59, day=prev), uuid.uuid4())  # outside the period
    b.audit("content.published", t(13, 40), failed.id)  # another action
    for i in range(10):
        b.content("scheduled", scheduled_at=now + timedelta(hours=2 * i))
    b.content("scheduled", scheduled_at=now + timedelta(hours=24))  # exactly 24 h: outside
    b.content("scheduled", scheduled_at=now - timedelta(seconds=1))  # already due
    b.content("draft", scheduled_at=now + timedelta(hours=3))  # not scheduled
    for _ in range(16):
        b.content("on_hold")

    # --- knowledge --------------------------------------------------------------------------
    for action, count in [("fact.updated", 7), ("fact.verified", 6), ("fact.archived", 4)]:
        for i in range(count):
            b.audit(action, t(9 + i, 15))
    for i in range(3):
        b.audit("fact.created", t(9 + i, 45))  # not a change in F.1
    b.audit("fact.updated", t(23, 59, 59, day=prev))
    b.audit("fact.updated", t(0, 0, day=d + timedelta(days=1)))

    # --- integration errors (6 + 7 + 3 + 2 = 18) --------------------------------------------
    for i in range(6):
        b.operation("failed", t(10 + i, 5))
    b.operation("failed", t(0, 0, day=d + timedelta(days=1)))  # outside
    b.operation("succeeded", t(12, 0))
    b.operation("cancelled", t(12, 1))
    for i in range(7):
        b.inbound_event("failed", t(8 + i, 50))
    b.inbound_event("processed", t(12, 0))
    b.inbound_event("failed", t(23, 59, 59, day=prev))
    for i in range(3):
        b.audit("social_account.needs_reauth", t(14 + i, 0))
    for i in range(2):
        b.audit("social_account.degraded", t(18 + i, 0))
    b.audit("social_account.connected", t(20, 0))
    b.audit("social_account.needs_reauth", t(23, 59, 59, day=prev))

    session.flush()
    return Scenario(workspace, b.account, user, knowledge_ctx(workspace), start, end, now)
