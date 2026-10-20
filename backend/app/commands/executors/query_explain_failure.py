"""``query.explain_failure``: why a post failed or was put on hold, in plain language.

The explanation comes from the error catalog (``errors.<CODE>.what`` / ``.next``, observability.md
§4), not from the model and not from a raw provider message. A hold has a reason rather than an
error (``FACT_CHANGED``, ``ACCOUNT_UNAVAILABLE``); those have their own texts. A code with no
text falls back to a generic one, so the owner never sees a bare code (INV-18).
"""

import uuid
from typing import Any

from app.commands.resolver import content_link
from app.commands.results import CommandResult, ExecContext
from app.content import hooks, service
from app.content.models import ContentItem
from app.core.errors import ERROR_CATALOG
from app.core.i18n import format_local_slot, t

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


def execute(ec: ExecContext, resolution: dict[str, Any]) -> CommandResult:
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
        },
        [content_link(item.id)],
    )
