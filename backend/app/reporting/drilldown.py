"""The list behind a report number (plan H1, AC-E3).

``metric_items`` runs the very row set that produced the metric, over the same period, so the
number of rows equals the value by construction (the median metric lists its answered bursts,
each with its ``measure`` in minutes). Rows are newest first and paged by an opaque keyset cursor
over ``(occurred_at, id)``. Labels are resolved from the records at read time, scoped to the
workspace; they never contain message text (a customer is shown by handle only).
"""

import base64
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from app.approvals.models import Approval
from app.audit.models import AuditLog
from app.content.models import ContentItem
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.core.i18n import catalog_keys, normalize_locale, t
from app.inbox.models import Conversation, ReplyDraft
from app.operations.models import Operation
from app.reporting import links
from app.reporting.definitions import BY_KEY
from app.reporting.metrics import compute_metric
from app.reporting.models import DailyReport
from app.reporting.periods import day_bounds
from app.reporting.service import check_not_future

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_CONVERSATION_KINDS = ("message", "conversation", "reply_draft")


@dataclass(frozen=True)
class Item:
    kind: str
    id: uuid.UUID
    label: str
    occurred_at: datetime | None
    is_simulated: bool
    measure: float | None
    link: links.Link | None


@dataclass(frozen=True)
class Drilldown:
    key: str
    value: int | float | None
    items: list[Item]
    next_cursor: str | None


def _bad_cursor() -> AppError:
    return AppError(
        "VALIDATION_FAILED", errors=[{"field": "cursor", "code": "invalid", "params": {}}]
    )


def _encode(sort_at: datetime, row_id: uuid.UUID) -> str:
    raw = json.dumps({"t": sort_at.isoformat(), "i": str(row_id)}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        at = datetime.fromisoformat(data["t"])
        if at.tzinfo is None:
            raise ValueError("naive")
        return at, uuid.UUID(data["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise _bad_cursor() from exc


def _period(
    session: Session, ctx: WorkspaceContext, local_date: date, now: datetime
) -> tuple[datetime, datetime]:
    """The period of the number being explained: live up to ``now`` for today, the stored
    report's own period for a past day that has one, else the whole day."""
    today = check_not_future(ctx, local_date, now)
    start, day_end = day_bounds(local_date, ctx.timezone)
    if local_date == today:
        return start, min(now, day_end)
    row = session.scalar(
        select(DailyReport).where(
            DailyReport.workspace_id == ctx.workspace_id, DailyReport.local_date == local_date
        )
    )
    return (row.period_start, row.period_end) if row is not None else (start, day_end)


def _pairs(session: Session, statement: Any) -> dict[Any, Any]:
    """``{first column: second column}`` of a two-column select."""
    return {row[0]: row[1] for row in session.execute(statement)}


def _text(key: str, locale: str, fallback: str) -> str:
    return t(key if key in catalog_keys(locale) else fallback, locale)


def _describe(session: Session, ctx: WorkspaceContext, rows: list[Any], locale: str) -> list[Item]:
    ws = ctx.workspace_id
    by_kind: dict[str, set[uuid.UUID]] = defaultdict(set)
    for row in rows:
        if row.subject_type in _CONVERSATION_KINDS:
            by_kind["conversation"].add(row.link_id)
        elif row.subject_type in ("audit_log", "operation"):
            by_kind[row.subject_type].add(row.subject_id)
        else:
            by_kind[row.subject_type].add(row.link_id)

    handles: dict[uuid.UUID, str | None] = {}
    if by_kind["conversation"]:
        handles = _pairs(
            session,
            select(Conversation.id, Conversation.customer_handle).where(
                Conversation.workspace_id == ws, Conversation.id.in_(by_kind["conversation"])
            ),
        )
    titles: dict[uuid.UUID, str] = {}
    if by_kind["content_item"]:
        titles = _pairs(
            session,
            select(ContentItem.id, ContentItem.title).where(
                ContentItem.workspace_id == ws, ContentItem.id.in_(by_kind["content_item"])
            ),
        )
    approval_actions: dict[uuid.UUID, str] = {}
    if by_kind["approval"]:
        approval_actions = _pairs(
            session,
            select(Approval.id, Approval.action).where(
                Approval.workspace_id == ws, Approval.id.in_(by_kind["approval"])
            ),
        )
    operations: dict[uuid.UUID, Operation] = {}
    if by_kind["operation"]:
        operations = {
            op.id: op
            for op in session.scalars(
                select(Operation).where(
                    Operation.workspace_id == ws, Operation.id.in_(by_kind["operation"])
                )
            )
        }
    draft_ids = {op.subject_id for op in operations.values() if op.subject_type == "reply_draft"}
    draft_conversations: dict[uuid.UUID, uuid.UUID] = {}
    if draft_ids:
        draft_conversations = _pairs(
            session,
            select(ReplyDraft.id, ReplyDraft.conversation_id).where(
                ReplyDraft.workspace_id == ws, ReplyDraft.id.in_(draft_ids)
            ),
        )
    audits: dict[uuid.UUID, AuditLog] = {}
    if by_kind["audit_log"]:
        audits = {
            a.id: a
            for a in session.scalars(
                select(AuditLog).where(
                    AuditLog.workspace_id == ws, AuditLog.id.in_(by_kind["audit_log"])
                )
            )
        }

    items: list[Item] = []
    for row in rows:
        kind: str = row.subject_type
        label: str
        link: links.Link | None = None
        if kind in _CONVERSATION_KINDS:
            handle = handles.get(row.link_id)
            label = handle or t("report.item.customer", locale)
            link = links.conversation_link(ws, row.link_id)
        elif kind == "content_item":
            label = titles.get(row.link_id) or t("report.item.content", locale)
            link = links.content_link(ws, row.link_id)
        elif kind == "approval":
            action = approval_actions.get(row.link_id, "")
            label = _text(f"report.item.approval.{action}", locale, "report.item.approval.other")
            link = links.approval_link(ws, row.link_id)
        elif kind == "operation":
            op = operations.get(row.subject_id)
            op_type = op.operation_type if op else ""
            label = _text(f"report.item.operation.{op_type}", locale, "report.item.operation.other")
            route = None
            if op is not None and op.subject_type == "content_item":
                route = links.content_link(ws, op.subject_id)["route"]
            elif op is not None and op.subject_type == "reply_draft":
                conversation_id = draft_conversations.get(op.subject_id)
                if conversation_id is not None:
                    route = links.conversation_link(ws, conversation_id)["route"]
            link = links.operation_link(ws, row.subject_id, route)
        elif kind == "inbound_event":
            label = t("report.item.inbound_event", locale)
        else:  # audit_log: fact changes and account problems
            audit = audits.get(row.subject_id)
            action = audit.action if audit else ""
            label = _text(f"report.item.audit.{action}", locale, "report.item.audit.other")
            if action.startswith("fact."):
                link = links.knowledge_link(ws)
            elif action.startswith("social_account."):
                link = links.more_link(ws)
        items.append(
            Item(
                kind=kind,
                id=row.subject_id,
                label=label,
                occurred_at=row.occurred_at,
                is_simulated=bool(row.is_simulated),
                measure=None if row.measure is None else round(float(row.measure), 1),
                link=link,
            )
        )
    return items


def metric_items(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    local_date: date,
    key: str,
    *,
    locale: str | None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Drilldown:
    """One page of the rows behind ``key`` for ``local_date``, with the metric's value.

    For a past day the snapshot metrics (``*_now``) list the records as they are now; the stored
    value is as of the generation (workflows.md section F).
    """
    definition = BY_KEY.get(key)
    if definition is None:
        raise AppError("NOT_FOUND")
    now = clock.now()
    start, end = _period(session, ctx, local_date, now)
    language = normalize_locale(locale)
    value = compute_metric(session, ctx, definition, start, end, now).value

    rows = definition.rows(session, ctx, start, end, now).subquery("rows")
    sort_at = func.coalesce(rows.c.occurred_at, _EPOCH).label("sort_at")
    statement = select(rows, sort_at)
    if cursor is not None:
        at, row_id = _decode(cursor)
        statement = statement.where(tuple_(sort_at, rows.c.subject_id) < tuple_(at, row_id))
    page_size = min(max(limit, 1), MAX_LIMIT)
    fetched = list(
        session.execute(
            statement.order_by(sort_at.desc(), rows.c.subject_id.desc()).limit(page_size + 1)
        ).all()
    )
    page = fetched[:page_size]
    next_cursor = (
        _encode(page[-1].sort_at, page[-1].subject_id) if len(fetched) > page_size else None
    )
    return Drilldown(key, value, _describe(session, ctx, page, language), next_cursor)
