"""The metric registry, ``definitions_version = "1"`` (workflows.md section F.1).

Every metric is defined once, as a **row set**: a SQL ``SELECT`` over persisted records. The
metric's value is computed from that row set (a count, or the median for
``median_first_response_minutes``) and the drill-down list behind each number runs the very same
row set, so the number and the list agree by construction (plan H1, AC-E3).

Every row set returns the same seven columns, in this order:

``subject_type``  what a row is (``message``, ``conversation``, ``reply_draft``, ``approval``,
                  ``content_item``, ``operation``, ``inbound_event``, ``audit_log``)
``subject_id``    the id of that record
``occurred_at``   when it happened (UTC)
``is_simulated``  whether the record is simulated (INV-09)
``link_id``       the record a link should open (the conversation for a message, the content
                  item for its audit entries, ...), or the record itself
``measure``       a number for the median metric (minutes), otherwise NULL
``group_key``     a breakdown label (the approval action), otherwise NULL

Reports read other modules' **models** only (never their services) and never involve the language
model (INV-08). Every query filters by ``workspace_id`` (INV-01).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import (
    Numeric,
    Select,
    Text,
    and_,
    cast,
    exists,
    func,
    literal,
    null,
    or_,
    select,
    tuple_,
    union_all,
)
from sqlalchemy.orm import Session, aliased

from app.agent.models import AgentAction
from app.approvals.models import Approval
from app.audit.models import AuditLog
from app.content.models import ContentItem
from app.core.context import WorkspaceContext
from app.inbox.models import Conversation, InboundEvent, Message, ReplyDraft
from app.integrations.instagram.models import SocialAccount
from app.operations.models import Operation
from app.owner_requests.models import OwnerQuestion

DEFINITIONS_VERSION = "2"

# The 24 h customer-service window of Instagram messaging. Kept equal to
# ``app.inbox.context.MESSAGING_WINDOW`` by a test, so reporting need not import the inbox logic.
MESSAGING_WINDOW = timedelta(hours=24)

Kind = Literal["period", "snapshot"]
ValueKind = Literal["count", "median"]
RowsFn = Callable[[Session, WorkspaceContext, datetime, datetime, datetime], Select[Any]]

# H4: the sections of the summary text.
SECTIONS = ("messages", "approvals", "content", "knowledge", "problems")

ATTENTION_STATES = ("needs_human", "needs_approval", "failed")
FACT_CHANGE_ACTIONS = ("fact.updated", "fact.verified", "fact.archived")
ACCOUNT_PROBLEM_ACTIONS = ("social_account.needs_reauth", "social_account.degraded")


@dataclass(frozen=True)
class Definition:
    key: str
    kind: Kind
    section: str
    inbox: bool  # H2: visible to staff (``reports.view_inbox_metrics``)
    value: ValueKind
    rows: RowsFn
    grouped: bool = False  # the row set carries ``group_key`` and the metric a breakdown


def _row(
    subject_type: str,
    subject_id: Any,
    occurred_at: Any,
    is_simulated: Any,
    link_id: Any,
    *,
    measure: Any = None,
    group_key: Any = None,
) -> tuple[Any, ...]:
    """The seven columns of a row set, labelled."""
    return (
        literal(subject_type, Text).label("subject_type"),
        subject_id.label("subject_id"),
        occurred_at.label("occurred_at"),
        is_simulated.label("is_simulated"),
        link_id.label("link_id"),
        (cast(null(), Numeric) if measure is None else measure).label("measure"),
        (cast(null(), Text) if group_key is None else group_key).label("group_key"),
    )


# --- messages ---------------------------------------------------------------------------------


def _inbound_filter(ctx: WorkspaceContext, start: datetime, end: datetime) -> tuple[Any, ...]:
    return (
        Message.workspace_id == ctx.workspace_id,
        Message.direction == "inbound",
        Message.is_deleted.is_(False),
        Message.provider_timestamp >= start,
        Message.provider_timestamp < end,
    )


def _message_rows(*conditions: Any) -> Select[Any]:
    return select(
        *_row(
            "message",
            Message.id,
            Message.provider_timestamp,
            Message.is_simulated,
            Message.conversation_id,
        )
    ).where(*conditions)


def inbound_messages(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return _message_rows(*_inbound_filter(ctx, start, end))


def conversations_with_inbound(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return (
        select(
            *_row(
                "conversation",
                Message.conversation_id,
                func.min(Message.provider_timestamp),
                func.bool_or(Message.is_simulated),
                Message.conversation_id,
            )
        )
        .where(*_inbound_filter(ctx, start, end))
        .group_by(Message.conversation_id)
    )


def new_conversations(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return select(
        *_row(
            "conversation",
            Conversation.id,
            Conversation.created_at,
            Conversation.is_simulated,
            Conversation.id,
        )
    ).where(
        Conversation.workspace_id == ctx.workspace_id,
        Conversation.created_at >= start,
        Conversation.created_at < end,
    )


def _replies_filter(ctx: WorkspaceContext, start: datetime, end: datetime) -> tuple[Any, ...]:
    return (
        Message.workspace_id == ctx.workspace_id,
        Message.direction == "outbound",
        Message.sender_kind == "business_app",
        Message.provider_timestamp >= start,
        Message.provider_timestamp < end,
    )


def replies_sent(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return _message_rows(*_replies_filter(ctx, start, end))


def _replies_by_draft(
    ctx: WorkspaceContext, start: datetime, end: datetime, *draft_conditions: Any
) -> Select[Any]:
    return (
        _message_rows(*_replies_filter(ctx, start, end), *draft_conditions)
        .join(
            ReplyDraft,
            and_(
                ReplyDraft.workspace_id == Message.workspace_id,
                ReplyDraft.id == Message.reply_draft_id,
            ),
        )
        .where(ReplyDraft.workspace_id == ctx.workspace_id)
    )


def replies_sent_auto(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return _replies_by_draft(ctx, start, end, ReplyDraft.decision == "auto")


def replies_sent_approved(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return _replies_by_draft(
        ctx,
        start,
        end,
        ReplyDraft.source.in_(("ai", "approved_answer")),
        ReplyDraft.decision == "approval_required",
    )


def replies_sent_by_owner(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return _replies_by_draft(ctx, start, end, ReplyDraft.source == "owner")


def native_replies(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return _message_rows(
        Message.workspace_id == ctx.workspace_id,
        Message.sender_kind == "business_native",
        Message.provider_timestamp >= start,
        Message.provider_timestamp < end,
    )


def escalations(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return select(
        *_row(
            "reply_draft",
            ReplyDraft.id,
            ReplyDraft.created_at,
            ReplyDraft.is_simulated,
            ReplyDraft.conversation_id,
        )
    ).where(
        ReplyDraft.workspace_id == ctx.workspace_id,
        ReplyDraft.decision == "human_required",
        ReplyDraft.created_at >= start,
        ReplyDraft.created_at < end,
    )


def missed_conversations(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    """Conversations whose 24 h window ended in the period with no outbound message after the
    last inbound one (a reply written in the Instagram app counts: it is an outbound message)."""
    window_end = Conversation.last_inbound_at + MESSAGING_WINDOW
    answered = exists().where(
        Message.workspace_id == Conversation.workspace_id,
        Message.conversation_id == Conversation.id,
        Message.direction == "outbound",
        Message.provider_timestamp > Conversation.last_inbound_at,
    )
    return select(
        *_row(
            "conversation", Conversation.id, window_end, Conversation.is_simulated, Conversation.id
        )
    ).where(
        Conversation.workspace_id == ctx.workspace_id,
        Conversation.last_inbound_at.is_not(None),
        window_end >= start,
        window_end < end,
        ~answered,
    )


def median_first_response_minutes(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    """The answered inbound bursts of the period; ``measure`` is each one's response time.

    A **burst** is a run of customer messages with no outbound message between them. It starts at
    an inbound message whose predecessor in the conversation (messages ordered by
    ``(provider_timestamp, id)``; deleted inbound messages ignored) is an outbound message or
    absent. The burst is **in the period** when that first message is. It is **answered** when
    the next outbound message of the conversation falls inside the period too. The response time
    is the minutes from the first unanswered message to that outbound message.
    """
    first = aliased(Message, name="burst")
    before = aliased(Message, name="before")
    after = aliased(Message, name="after")

    previous_direction = (
        select(before.direction)
        .where(
            before.workspace_id == first.workspace_id,
            before.conversation_id == first.conversation_id,
            tuple_(before.provider_timestamp, before.id)
            < tuple_(first.provider_timestamp, first.id),
            ~and_(before.direction == "inbound", before.is_deleted.is_(True)),
        )
        .order_by(before.provider_timestamp.desc(), before.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    reply_at = (
        select(func.min(after.provider_timestamp))
        .where(
            after.workspace_id == first.workspace_id,
            after.conversation_id == first.conversation_id,
            after.direction == "outbound",
            tuple_(after.provider_timestamp, after.id) > tuple_(first.provider_timestamp, first.id),
        )
        .scalar_subquery()
    )
    bursts = (
        select(
            first.id.label("id"),
            first.conversation_id.label("conversation_id"),
            first.provider_timestamp.label("started_at"),
            first.is_simulated.label("is_simulated"),
            reply_at.label("replied_at"),
        )
        .where(
            first.workspace_id == ctx.workspace_id,
            first.direction == "inbound",
            first.is_deleted.is_(False),
            first.provider_timestamp >= start,
            first.provider_timestamp < end,
            or_(previous_direction.is_(None), previous_direction == "outbound"),
        )
        .subquery("bursts")
    )
    minutes = func.extract("epoch", bursts.c.replied_at - bursts.c.started_at) / 60
    return select(
        *_row(
            "message",
            bursts.c.id,
            bursts.c.started_at,
            bursts.c.is_simulated,
            bursts.c.conversation_id,
            measure=cast(minutes, Numeric),
        )
    ).where(bursts.c.replied_at.is_not(None), bursts.c.replied_at < end)


def attention_now(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return select(
        *_row(
            "conversation",
            Conversation.id,
            func.coalesce(Conversation.last_message_at, Conversation.created_at),
            Conversation.is_simulated,
            Conversation.id,
        )
    ).where(
        Conversation.workspace_id == ctx.workspace_id,
        Conversation.attention.in_(ATTENTION_STATES),
    )


def unanswered_open_now(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    """The latest message is the customer's and the 24 h window is still open (the same test as
    ``app.inbox.attention``: the last inbound message is newer than the last outbound one)."""
    return select(
        *_row(
            "conversation",
            Conversation.id,
            Conversation.last_inbound_at,
            Conversation.is_simulated,
            Conversation.id,
        )
    ).where(
        Conversation.workspace_id == ctx.workspace_id,
        Conversation.last_inbound_at.is_not(None),
        or_(
            Conversation.last_outbound_at.is_(None),
            Conversation.last_inbound_at > Conversation.last_outbound_at,
        ),
        Conversation.last_inbound_at + MESSAGING_WINDOW > now,
    )


# --- approvals --------------------------------------------------------------------------------


def pending_approvals_now(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return select(
        *_row(
            "approval",
            Approval.id,
            Approval.created_at,
            Approval.is_simulated,
            Approval.id,
            group_key=Approval.action,
        )
    ).where(Approval.workspace_id == ctx.workspace_id, Approval.status == "pending")


# --- content ----------------------------------------------------------------------------------


def _content_rows(occurred_at: Any, *conditions: Any) -> Select[Any]:
    return select(
        *_row("content_item", ContentItem.id, occurred_at, ContentItem.is_simulated, ContentItem.id)
    ).where(*conditions)


def content_published(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return _content_rows(
        ContentItem.published_at,
        ContentItem.workspace_id == ctx.workspace_id,
        ContentItem.published_at >= start,
        ContentItem.published_at < end,
    )


def content_failed(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    """Distinct content items with a ``content.failed`` audit entry in the period."""
    return (
        select(
            *_row(
                "content_item",
                AuditLog.resource_id,
                func.min(AuditLog.occurred_at),
                func.bool_or(AuditLog.is_simulated),
                AuditLog.resource_id,
            )
        )
        .where(
            AuditLog.workspace_id == ctx.workspace_id,
            AuditLog.action == "content.failed",
            AuditLog.occurred_at >= start,
            AuditLog.occurred_at < end,
        )
        .group_by(AuditLog.resource_id)
    )


def content_scheduled_next_24h(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return _content_rows(
        ContentItem.scheduled_at,
        ContentItem.workspace_id == ctx.workspace_id,
        ContentItem.status == "scheduled",
        ContentItem.scheduled_at >= now,
        ContentItem.scheduled_at < now + timedelta(hours=24),
    )


def content_on_hold_now(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return _content_rows(
        ContentItem.updated_at,
        ContentItem.workspace_id == ctx.workspace_id,
        ContentItem.status == "on_hold",
    )


# --- knowledge and problems -------------------------------------------------------------------


def _audit_rows(
    ctx: WorkspaceContext, start: datetime, end: datetime, *actions: str
) -> Select[Any]:
    return select(
        *_row(
            "audit_log",
            AuditLog.id,
            AuditLog.occurred_at,
            AuditLog.is_simulated,
            AuditLog.resource_id,
        )
    ).where(
        AuditLog.workspace_id == ctx.workspace_id,
        AuditLog.action.in_(actions),
        AuditLog.occurred_at >= start,
        AuditLog.occurred_at < end,
    )


def fact_changes(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return _audit_rows(ctx, start, end, *FACT_CHANGE_ACTIONS)


def integration_errors(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    """Operations that failed, inbound events that failed, and accounts that became
    ``needs_reauth`` or ``degraded``, all within the period."""
    failed_operations = select(
        *_row(
            "operation", Operation.id, Operation.completed_at, Operation.is_simulated, Operation.id
        )
    ).where(
        Operation.workspace_id == ctx.workspace_id,
        Operation.status == "failed",
        Operation.completed_at >= start,
        Operation.completed_at < end,
    )
    failed_at = func.coalesce(InboundEvent.processed_at, InboundEvent.received_at)
    failed_events = select(
        *_row(
            "inbound_event", InboundEvent.id, failed_at, InboundEvent.is_simulated, InboundEvent.id
        )
    ).where(
        InboundEvent.workspace_id == ctx.workspace_id,
        InboundEvent.status == "failed",
        failed_at >= start,
        failed_at < end,
    )
    account_problems = _audit_rows(ctx, start, end, *ACCOUNT_PROBLEM_ACTIONS)
    combined = union_all(failed_operations, failed_events, account_problems).subquery("errors")
    return select(*combined.c)


# New metric keys carry their own version; existing definitions and saved generations stay intact.
def _agent_effects(ctx: WorkspaceContext, start: datetime, end: datetime) -> Select[Any]:
    return (
        select(
            *_row(
                "operation",
                Operation.id,
                Operation.completed_at,
                Operation.is_simulated,
                Operation.id,
            )
        )
        .join(
            AgentAction,
            and_(
                AgentAction.workspace_id == Operation.workspace_id,
                AgentAction.operation_id == Operation.id,
            ),
        )
        .where(
            Operation.workspace_id == ctx.workspace_id,
            AgentAction.workspace_id == ctx.workspace_id,
            Operation.status == "succeeded",
            Operation.completed_at >= start,
            Operation.completed_at < end,
        )
    )


def agent_automatic_v1(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return _agent_effects(ctx, start, end).where(
        func.jsonb_typeof(AgentAction.policy_grant) == "object"
    )


def agent_approved_v1(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return _agent_effects(ctx, start, end).where(
        AgentAction.approval_id.is_not(None),
        or_(
            AgentAction.policy_grant.is_(None),
            func.jsonb_typeof(AgentAction.policy_grant) == "null",
        ),
    )


def agent_owner_questions_v1(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return (
        select(
            *_row(
                "owner_question",
                OwnerQuestion.id,
                OwnerQuestion.created_at,
                (SocialAccount.provider_kind == "mock"),
                OwnerQuestion.id,
            )
        )
        .join(
            SocialAccount,
            and_(
                SocialAccount.workspace_id == OwnerQuestion.workspace_id,
                SocialAccount.id == OwnerQuestion.social_account_id,
            ),
        )
        .where(
            OwnerQuestion.workspace_id == ctx.workspace_id,
            OwnerQuestion.created_at >= start,
            OwnerQuestion.created_at < end,
        )
    )


def agent_unknown_now_v1(
    session: Session, ctx: WorkspaceContext, start: datetime, end: datetime, now: datetime
) -> Select[Any]:
    return (
        select(
            *_row(
                "operation",
                Operation.id,
                Operation.created_at,
                Operation.is_simulated,
                Operation.id,
            )
        )
        .join(
            AgentAction,
            and_(
                AgentAction.workspace_id == Operation.workspace_id,
                AgentAction.operation_id == Operation.id,
            ),
        )
        .where(
            Operation.workspace_id == ctx.workspace_id,
            AgentAction.workspace_id == ctx.workspace_id,
            Operation.status == "outcome_unknown",
        )
    )


# --- the registry -----------------------------------------------------------------------------


def _d(
    key: str,
    kind: Kind,
    section: str,
    rows: RowsFn,
    *,
    inbox: bool = False,
    value: ValueKind = "count",
    grouped: bool = False,
) -> Definition:
    return Definition(key, kind, section, inbox, value, rows, grouped)


DEFINITIONS: tuple[Definition, ...] = (
    _d("inbound_messages", "period", "messages", inbound_messages, inbox=True),
    _d("conversations_with_inbound", "period", "messages", conversations_with_inbound, inbox=True),
    _d("new_conversations", "period", "messages", new_conversations, inbox=True),
    _d("replies_sent", "period", "messages", replies_sent, inbox=True),
    _d("replies_sent_auto", "period", "messages", replies_sent_auto, inbox=True),
    _d("replies_sent_approved", "period", "messages", replies_sent_approved, inbox=True),
    _d("replies_sent_by_owner", "period", "messages", replies_sent_by_owner, inbox=True),
    _d("native_replies", "period", "messages", native_replies, inbox=True),
    _d("escalations", "period", "messages", escalations, inbox=True),
    _d("missed_conversations", "period", "messages", missed_conversations, inbox=True),
    _d(
        "median_first_response_minutes",
        "period",
        "messages",
        median_first_response_minutes,
        inbox=True,
        value="median",
    ),
    _d("attention_now", "snapshot", "messages", attention_now, inbox=True),
    _d("unanswered_open_now", "snapshot", "messages", unanswered_open_now, inbox=True),
    _d("pending_approvals_now", "snapshot", "approvals", pending_approvals_now, grouped=True),
    _d("content_published", "period", "content", content_published),
    _d("content_failed", "period", "content", content_failed),
    _d("content_scheduled_next_24h", "snapshot", "content", content_scheduled_next_24h),
    _d("content_on_hold_now", "snapshot", "content", content_on_hold_now),
    _d("fact_changes", "period", "knowledge", fact_changes),
    _d("integration_errors", "period", "problems", integration_errors),
    _d("agent_automatic_v1", "period", "messages", agent_automatic_v1),
    _d("agent_approved_v1", "period", "messages", agent_approved_v1),
    _d("agent_owner_questions_v1", "period", "messages", agent_owner_questions_v1),
    _d("agent_unknown_now_v1", "snapshot", "messages", agent_unknown_now_v1),
)

BY_KEY: dict[str, Definition] = {d.key: d for d in DEFINITIONS}
KEYS: tuple[str, ...] = tuple(d.key for d in DEFINITIONS)
INBOX_KEYS: frozenset[str] = frozenset(d.key for d in DEFINITIONS if d.inbox)
