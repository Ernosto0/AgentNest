"""Notification kinds of the content module (plan.md G14, observability.md).

The kinds are defined here and tested in P5-04; their producers arrive with the publish
executor (``content.published``, ``content.failed``, ``content.on_hold`` for an unavailable
account) and the impact handlers (``content.on_hold`` for a changed fact).

Recipients are everyone who may approve content (``content.approve``), **including** the person
who caused the event (a fact changer is told that their change held a post), plus the author
of the item. A notification is created once per recipient and event until it is read.
"""

import uuid

from sqlalchemy.orm import Session

from app.content.models import ContentItem
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.notifications import service as notifications

ON_HOLD = "content.on_hold"
PUBLISHED = "content.published"
FAILED = "content.failed"

SEVERITY = {ON_HOLD: "attention", PUBLISHED: "info", FAILED: "attention"}
KINDS = tuple(SEVERITY)


def notify(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    item: ContentItem,
    kind: str,
    *,
    reason: str | None = None,
) -> int:
    """Notify the approvers and the author of ``item`` about ``kind``. Returns how many were
    created. In the caller's transaction; no commit.

    ``reason`` is the hold reason (``FACT_CHANGED``, ``ACCOUNT_UNAVAILABLE``) or the error
    code of a failure. The params carry ids and codes, never the caption.
    """
    if kind not in SEVERITY:
        raise ValueError(f"unknown content notification kind: {kind}")
    params = {
        "content_id": str(item.id),
        "content_type": item.content_type,
        "title": item.title,
        "version": item.version,
        "reason": reason,
    }
    dedup_key = f"{kind}:{item.id}:v{item.version}"
    created = notifications.notify_permission_holders(
        session,
        clock,
        ctx,
        permission="content.approve",
        type=kind,
        severity=SEVERITY[kind],
        params=params,
        subject_type="content_item",
        subject_id=item.id,
        dedup_key=dedup_key,
        is_simulated=item.is_simulated,
    )
    approver_ids = {n.recipient_user_id for n in created}
    author: uuid.UUID = item.created_by_user_id
    if author not in approver_ids and (
        notifications.notify(
            session,
            clock,
            ctx,
            recipient_user_id=author,
            type=kind,
            severity=SEVERITY[kind],
            params=params,
            subject_type="content_item",
            subject_id=item.id,
            dedup_key=dedup_key,
            is_simulated=item.is_simulated,
        )
        is not None
    ):
        return len(created) + 1
    return len(created)
