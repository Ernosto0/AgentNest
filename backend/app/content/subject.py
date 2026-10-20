"""Registers ``content_item`` as an approval subject (workflows.md sections D and E step 5).

The callback runs in the **same transaction** as the decision, so an item is never queued for
publishing unless its approval is recorded as approved, and a failing callback leaves the
approval pending (409 to the decider). Imported by ``app.handlers.load_handlers`` in the API
and the worker.

- approved: ``pending_approval -> scheduled`` and the ``publish_content`` job is queued at
  ``scheduled_at``;
- rejected: ``pending_approval -> rejected``, with the decider's note;
- expired: ``pending_approval -> draft (APPROVAL_EXPIRED)``. The approvals service already
  notifies the requester (``approval.expired``) after the callback, so nothing is sent here.

An approval whose item moved on (edited, cancelled, a newer version) is stale: the decision is
refused with ``APPROVAL_STALE`` (INV-16). The payload is also recomputed from the item at
decision time and must hash to what the approval was bound to.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals import callbacks
from app.approvals.models import Approval
from app.content import service, transitions
from app.content.models import ContentItem, MediaAsset
from app.content.payload import approval_payload, approval_payload_hash
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError

APPROVAL_EXPIRED = "APPROVAL_EXPIRED"


def bound_payload_hash(session: Session, item: ContentItem) -> str | None:
    """The hash of the payload the item would be submitted with right now, for the account and
    instant it was submitted with; ``None`` if the media or the schedule is gone."""
    if item.media_asset_id is None or item.scheduled_at is None or item.social_account_id is None:
        return None
    sha256 = session.scalar(
        select(MediaAsset.sha256).where(
            MediaAsset.workspace_id == item.workspace_id, MediaAsset.id == item.media_asset_id
        )
    )
    if sha256 is None:
        return None
    return approval_payload_hash(
        approval_payload(
            item,
            version=item.version,
            social_account_id=item.social_account_id,
            media_sha256=sha256,
            scheduled_at=item.scheduled_at,
        )
    )


def on_decided(session: Session, clock: Clock, ctx: WorkspaceContext, approval: Approval) -> None:
    item = session.scalars(
        select(ContentItem)
        .where(
            ContentItem.workspace_id == approval.workspace_id,
            ContentItem.id == approval.subject_id,
        )
        .with_for_update()
    ).one_or_none()
    if item is None:
        raise AppError("NOT_FOUND")
    if item.status != "pending_approval" or item.version != approval.subject_version:
        if approval.status == "expired":
            return  # nothing waits for this approval any more
        # Never schedule an item that is no longer the one that was approved.
        raise AppError("APPROVAL_STALE")

    if approval.status == "approved":
        if bound_payload_hash(session, item) != approval.payload_hash:
            raise AppError("APPROVAL_STALE")
        transitions.apply(session, clock, ctx, item, "approve")
        service.enqueue_publish(session, clock, item)
    elif approval.status == "rejected":
        transitions.apply(
            session, clock, ctx, item, "reject", rejection_note=approval.decision_note
        )
    elif approval.status == "expired":
        # The instant has passed with nobody deciding: back to a draft that has to be rescheduled.
        transitions.apply(
            session,
            clock,
            ctx,
            item,
            "expire",
            reason=APPROVAL_EXPIRED,
            scheduled_at=None,
            schedule_input=None,
        )
    # A cancelled approval is handled by whoever cancelled it.


def subject_version(session: Session, ctx: WorkspaceContext, subject_id: uuid.UUID) -> int | None:
    """The item's version while it still awaits this decision; ``None`` once it moved on, which
    makes any decision on its approval stale."""
    row = session.execute(
        select(ContentItem.version, ContentItem.status).where(
            ContentItem.workspace_id == ctx.workspace_id, ContentItem.id == subject_id
        )
    ).one_or_none()
    if row is None or row.status != "pending_approval":
        return None
    return int(row.version)


def subject_status(session: Session, ctx: WorkspaceContext, subject_id: uuid.UUID) -> str | None:
    return session.scalar(
        select(ContentItem.status).where(
            ContentItem.workspace_id == ctx.workspace_id, ContentItem.id == subject_id
        )
    )


callbacks.register(
    transitions.SUBJECT_TYPE,
    on_decided,
    current_version=subject_version,
    status_of=subject_status,
)
