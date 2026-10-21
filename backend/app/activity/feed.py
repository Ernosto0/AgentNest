"""The Activity feed query (plan H7): the audit log of one workspace, newest first.

Every query carries the ``workspace_id`` filter (INV-01); system-level rows have no workspace and
never appear. Paging is an opaque keyset cursor over ``(occurred_at, id)``, so entries with the
same timestamp are neither skipped nor repeated. ``date`` is a local day in the workspace
timezone (INV-19).
"""

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.activity.groups import GROUPS, actions_in
from app.audit.models import AuditLog
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.reporting.periods import day_bounds

DEFAULT_LIMIT = 30
MAX_LIMIT = 100


@dataclass(frozen=True)
class FeedPage:
    rows: list[AuditLog]
    next_cursor: str | None


def _bad_cursor() -> AppError:
    return AppError(
        "VALIDATION_FAILED", errors=[{"field": "cursor", "code": "invalid", "params": {}}]
    )


def encode_cursor(occurred_at: datetime, row_id: uuid.UUID) -> str:
    raw = json.dumps({"t": occurred_at.isoformat(), "i": str(row_id)}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        at = datetime.fromisoformat(data["t"])
        if at.tzinfo is None:
            raise ValueError("naive")
        return at, uuid.UUID(data["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise _bad_cursor() from exc


def list_feed(
    session: Session,
    ctx: WorkspaceContext,
    *,
    group: str | None = None,
    local_date: date | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> FeedPage:
    statement = select(AuditLog).where(AuditLog.workspace_id == ctx.workspace_id)
    if group == "system":
        # Everything no other group claims, including actions this version does not know.
        others = [a for a, g in GROUPS.items() if g != "system"]
        statement = statement.where(AuditLog.action.not_in(others))
    elif group is not None:
        statement = statement.where(AuditLog.action.in_(actions_in(group)))
    if local_date is not None:
        start, end = day_bounds(local_date, ctx.timezone)
        statement = statement.where(AuditLog.occurred_at >= start, AuditLog.occurred_at < end)
    if cursor is not None:
        at, row_id = decode_cursor(cursor)
        statement = statement.where(tuple_(AuditLog.occurred_at, AuditLog.id) < tuple_(at, row_id))
    page_size = min(max(limit, 1), MAX_LIMIT)
    fetched = list(
        session.scalars(
            statement.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc()).limit(page_size + 1)
        )
    )
    rows = fetched[:page_size]
    next_cursor = (
        encode_cursor(rows[-1].occurred_at, rows[-1].id) if len(fetched) > page_size else None
    )
    return FeedPage(rows, next_cursor)
