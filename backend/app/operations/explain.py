"""What an operation's outcome means for the owner, in plain language (H6, observability.md §4).

The text comes from the error catalog (``errors.<CODE>.what`` / ``.next``), not from the model and
not from a raw provider message. A message that is about *sending a reply* may have a text of its
own (``operation.send_reply.<CODE>.what``): the shared catalog texts talk about posts. A code with
no text falls back to a generic one, so the owner never sees a bare code (INV-18). Provider
payloads and error details never appear here.
"""

from dataclasses import dataclass

from app.core.errors import ERROR_CATALOG
from app.core.i18n import catalog_keys, t
from app.operations.models import Operation

UNKNOWN_KEY = "operation.unknown"
# Statuses that need an explanation; the others (succeeded, pending, ...) have nothing to explain.
EXPLAINED_STATUSES = ("failed", "outcome_unknown", "retry_wait")


@dataclass(frozen=True)
class Explanation:
    code: str | None
    what: str
    next: str
    retryable: bool | None


def failure_code(operation: Operation) -> str | None:
    """The code that says what went wrong, or ``None`` when nothing did."""
    if operation.status not in EXPLAINED_STATUSES:
        return None
    if operation.last_error_code:
        return operation.last_error_code
    return "OUTCOME_UNKNOWN" if operation.status == "outcome_unknown" else None


def _prefix(operation_type: str, code: str | None, locale: str) -> str:
    keys = catalog_keys(locale)
    if code is not None:
        own = f"operation.{operation_type}.{code}"
        if f"{own}.what" in keys:
            return own
        if code in ERROR_CATALOG and f"errors.{code}.what" in keys:
            return f"errors.{code}"
    return UNKNOWN_KEY


def explain(operation: Operation, locale: str | None) -> Explanation | None:
    """What happened and what to do next, or ``None`` for an operation that is not in trouble."""
    if operation.status not in EXPLAINED_STATUSES:
        return None
    code = failure_code(operation)
    prefix = _prefix(operation.operation_type, code, locale or "tr")
    spec = ERROR_CATALOG.get(code) if code else None
    return Explanation(
        code=code,
        what=t(f"{prefix}.what", locale),
        next=t(f"{prefix}.next", locale),
        retryable=spec.retryable if spec is not None else None,
    )
