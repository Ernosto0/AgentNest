"""``query.explain_failure``: why a post failed or was put on hold, or why a reply did not go
out, in plain language.

The explanation comes from the error catalog (``errors.<CODE>.what`` / ``.next``, observability.md
§4), not from the model and not from a raw provider message. A hold has a reason rather than an
error (``FACT_CHANGED``, ``ACCOUNT_UNAVAILABLE``); those have their own texts. A code with no
text falls back to a generic one, so the owner never sees a bare code (INV-18). The answer says
what happened, when (the local time in the user's language, INV-19) and the next step, and links
to the post or the conversation.

``latest_failure`` may resolve to a reply operation instead of a post (H6): the resolution then
carries an ``operation_id`` (a ``send_reply`` operation that ended ``failed``, an unconfirmed
send among them).
"""

import uuid
from typing import Any

from sqlalchemy import select

from app.commands.resolver import content_link
from app.commands.results import CommandResult, ExecContext
from app.content import hooks, service
from app.content.models import ContentItem
from app.core.errors import ERROR_CATALOG, AppError
from app.core.i18n import format_local_slot, t
from app.inbox.models import ReplyDraft
from app.operations import explain
from app.operations.models import Operation

HOLD_REASONS = ("FACT_CHANGED", "ACCOUNT_UNAVAILABLE")
UNKNOWN = "UNKNOWN"


def failure_code(item: ContentItem) -> str | None:
    """Why the item is in trouble, or ``None`` when it is not (a normal state)."""
    if item.status == "on_hold":
        return item.hold_reason or UNKNOWN
    if item.status in ("failed", "retry_scheduled"):
        return item.last_error_code or UNKNOWN
    return None


def text_prefix(item: ContentItem, code: str) -> str:
    if item.status == "on_hold" and code in HOLD_REASONS:
        return f"content.hold.{code}"
    if item.status != "on_hold" and code in ERROR_CATALOG:
        return f"errors.{code}"
    return "content.failure.unknown"


def _reply_failure(ec: ExecContext, operation_id: uuid.UUID) -> CommandResult:
    """A reply that did not go out: from the operation (workspace-scoped), never a provider text."""
    operation = ec.session.scalar(
        select(Operation).where(
            Operation.workspace_id == ec.ctx.workspace_id, Operation.id == operation_id
        )
    )
    if operation is None:
        raise AppError("NOT_FOUND")
    explanation = explain.explain(operation, ec.user_locale)
    if explanation is None:  # it recovered meanwhile (a late echo, a reconcile)
        return CommandResult("command.no_failure", {}, [{"target": "inbox"}])
    happened = operation.completed_at or operation.updated_at
    links: list[dict[str, Any]] = [{"target": "inbox"}]
    if operation.subject_type == "reply_draft":
        conversation_id = ec.session.scalar(
            select(ReplyDraft.conversation_id).where(
                ReplyDraft.workspace_id == ec.ctx.workspace_id,
                ReplyDraft.id == operation.subject_id,
            )
        )
        if conversation_id is not None:
            links = [{"target": "inbox", "id": str(conversation_id)}]
    return CommandResult(
        "command.reply_failure",
        {
            "status": operation.status,
            "error_code": explanation.code,
            "what": explanation.what,
            "next": explanation.next,
            "retryable": explanation.retryable,
            "when": format_local_slot(happened, ec.ctx.timezone, ec.user_locale),
            "is_simulated": operation.is_simulated,
        },
        links,
    )


def execute(ec: ExecContext, resolution: dict[str, Any]) -> CommandResult:
    if "operation_id" in resolution:
        return _reply_failure(ec, uuid.UUID(resolution["operation_id"]))
    item = service.get_item(ec.session, ec.ctx, uuid.UUID(resolution["content_id"]))
    code = failure_code(item)
    if code is None:  # a reference to a post that is not in trouble
        return CommandResult(
            "command.no_failure_for_item",
            {"title": item.title, "status": item.status},
            [content_link(item.id)],
        )
    prefix = text_prefix(item, code)
    spec = ERROR_CATALOG.get(code)
    operation = hooks.get().operation_summary(ec.session, ec.ctx, item)
    retry_at = None
    if item.status == "retry_scheduled" and operation and operation.next_attempt_at:
        retry_at = format_local_slot(operation.next_attempt_at, ec.ctx.timezone, ec.user_locale)
    return CommandResult(
        "command.content_failure",
        {
            "title": item.title,
            "status": item.status,
            "error_code": code,
            "what": t(f"{prefix}.what", ec.user_locale),
            "next": t(f"{prefix}.next", ec.user_locale),
            "retryable": spec.retryable if spec is not None else None,
            "is_simulated": item.is_simulated,
            "retry_at": retry_at,
            "when": format_local_slot(item.updated_at, ec.ctx.timezone, ec.user_locale),
        },
        [content_link(item.id)],
    )
