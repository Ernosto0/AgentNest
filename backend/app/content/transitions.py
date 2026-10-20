"""The only place where a content item's status changes (state-machines.md section 5).

``next_status`` is the pure table: ``(current status, event) -> next status`` or
``CONFLICT_STATE``. ``apply`` runs one event as a **conditional update** (``WHERE status =
:expected``), so a concurrent change surfaces as ``CONFLICT_STATE`` instead of a lost update,
and writes the audit entry in the same transaction (INV-12). Nothing else may assign
``ContentItem.status``.

The table is the diagram of section 5 plus the four transitions of plan.md G1: ``draft ->
cancelled``, ``pending_approval -> cancelled``, ``retry_scheduled -> on_hold`` and
``publishing -> on_hold`` (``ACCOUNT_UNAVAILABLE`` only). ``published`` and ``cancelled`` have
no outgoing event: published content is immutable (INV-17).
"""

from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.content.models import ContentItem
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError

SUBJECT_TYPE = "content_item"

# ``(current status, event) -> next status``.
_TRANSITIONS: dict[tuple[str, str], str] = {
    # draft
    ("draft", "edit"): "draft",  # a payload change (version + 1)
    ("draft", "submit"): "pending_approval",  # submitter lacks content.approve
    ("draft", "schedule"): "scheduled",  # submit + self-approve (content.approve)
    ("draft", "cancel"): "cancelled",  # G1
    # pending_approval
    ("pending_approval", "approve"): "scheduled",
    ("pending_approval", "reject"): "rejected",
    ("pending_approval", "withdraw"): "draft",
    ("pending_approval", "expire"): "draft",  # APPROVAL_EXPIRED
    ("pending_approval", "edit"): "draft",
    ("pending_approval", "cancel"): "cancelled",  # G1
    # scheduled
    ("scheduled", "start"): "publishing",  # the publish job claims it (due checks passed)
    ("scheduled", "edit"): "draft",
    ("scheduled", "cancel"): "cancelled",
    ("scheduled", "hold"): "on_hold",  # FACT_CHANGED / ACCOUNT_UNAVAILABLE
    # on_hold
    ("on_hold", "edit"): "draft",
    ("on_hold", "reapprove"): "scheduled",  # G2: version + 1
    ("on_hold", "cancel"): "cancelled",
    # publishing
    ("publishing", "succeed"): "published",
    ("publishing", "retry"): "retry_scheduled",
    ("publishing", "fail"): "failed",
    ("publishing", "hold"): "on_hold",  # G1, ACCOUNT_UNAVAILABLE only
    # retry_scheduled
    ("retry_scheduled", "start"): "publishing",
    ("retry_scheduled", "cancel"): "cancelled",
    ("retry_scheduled", "fail"): "failed",  # deadline passed
    ("retry_scheduled", "hold"): "on_hold",  # G1
    # rejected / failed
    ("rejected", "edit"): "draft",
    ("failed", "edit"): "draft",
}
CONTENT_EVENTS = frozenset(event for _, event in _TRANSITIONS)

# An auth error during an attempt is the only reason to hold an item that is publishing.
PUBLISHING_HOLD_REASON = "ACCOUNT_UNAVAILABLE"

# Statuses from which a payload edit is allowed (they all lead back to ``draft``).
EDITABLE_STATUSES = frozenset(status for (status, event) in _TRANSITIONS if event == "edit")

# Audit action per resulting status (observability.md section 5).
_AUDIT_ACTION = {
    "draft": "content.updated",
    "pending_approval": "content.submitted",
    "scheduled": "content.scheduled",
    "on_hold": "content.on_hold",
    "cancelled": "content.cancelled",
    "rejected": "content.rejected",
    "publishing": "content.publishing",
    "retry_scheduled": "content.retry_scheduled",
    "published": "content.published",
    "failed": "content.failed",
}

# Columns a caller may set in the same conditional update as the status change.
_SETTABLE = frozenset(
    {
        "social_account_id",
        "title",
        "objective",
        "caption",
        "overlay_text_suggestions",
        "visual_notes",
        "media_asset_id",
        "scheduled_at",
        "schedule_input",
        "approval_id",
        "rejection_note",
        "validation",
        "published_at",
        "external_media_id",
        "external_permalink",
        "last_error_code",
        "agent_run_id",
        "is_simulated",
    }
)


def next_status(current: str, event: str, reason: str | None = None) -> str:
    """The status after ``event``, or ``CONFLICT_STATE``."""
    try:
        target = _TRANSITIONS[(current, event)]
    except KeyError:
        raise AppError(
            "CONFLICT_STATE", entity="content_item", status=current, event=event
        ) from None
    if current == "publishing" and event == "hold" and reason != PUBLISHING_HOLD_REASON:
        raise AppError("CONFLICT_STATE", entity="content_item", status=current, event=event)
    return target


def apply(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    item: ContentItem,
    event: str,
    *,
    reason: str | None = None,
    **changes: Any,
) -> ContentItem:
    """Apply ``event`` to ``item`` (conditional update, audited). No commit.

    ``reason`` is the hold reason of ``hold`` / ``withdraw`` / ``expire`` (``FACT_CHANGED``,
    ``ACCOUNT_UNAVAILABLE``, ``APPROVAL_EXPIRED``), the error code of ``fail`` / ``retry``, and
    is recorded in the audit entry of every event. ``changes`` are further columns written in
    the same statement (see ``_SETTABLE``); ``status``, ``version`` and the ownership columns
    are never settable.

    ``edit`` and ``reapprove`` increment ``version`` (a payload change and plan.md G2) and
    clear the reasons of the previous state.
    """
    unknown = set(changes) - _SETTABLE
    if unknown:
        raise ValueError(f"not settable through a transition: {sorted(unknown)}")
    previous = item.status
    new_status = next_status(previous, event, reason)
    session.flush()

    values: dict[str, Any] = {"status": new_status, "updated_at": clock.now(), **changes}
    if event in ("edit", "reapprove"):
        values["version"] = ContentItem.version + 1
        values["hold_reason"] = None
        if event == "edit":
            values.setdefault("rejection_note", None)
            values.setdefault("last_error_code", None)
    if event in ("hold", "withdraw", "expire") and reason is not None:
        values["hold_reason"] = reason
    if event in ("fail", "retry") and reason is not None:
        values.setdefault("last_error_code", reason)

    result = session.execute(
        update(ContentItem)
        .where(
            ContentItem.id == item.id,
            ContentItem.workspace_id == ctx.workspace_id,
            ContentItem.status == previous,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:  # type: ignore[attr-defined]
        raise AppError("CONFLICT_STATE", entity="content_item", status=previous, event=event)
    session.refresh(item)
    audit.record(
        session,
        ctx,
        _AUDIT_ACTION[new_status],
        "content_item",
        item.id,
        {
            "from": previous,
            "event": event,
            "reason": reason,
            "version": item.version,
            "content_type": item.content_type,
        },
        is_simulated=item.is_simulated,
        clock=clock,
    )
    return item
