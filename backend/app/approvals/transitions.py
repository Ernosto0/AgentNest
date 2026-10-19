"""The only place where approval states change (state-machines.md §1).

Pure: maps ``(current state, event)`` to the next state or raises ``CONFLICT_STATE``. Terminal
states (approved, rejected, expired, cancelled) have no outgoing transitions; an approval that
was approved may be *consumed* by one operation, but that is not a state change.
"""

from app.core.errors import AppError

_TRANSITIONS: dict[tuple[str | None, str], str] = {
    (None, "request"): "pending",
    ("pending", "approve"): "approved",
    ("pending", "reject"): "rejected",
    ("pending", "expire"): "expired",
    ("pending", "cancel"): "cancelled",
}
APPROVAL_EVENTS = frozenset(event for _, event in _TRANSITIONS)


def apply_approval_event(current: str | None, event: str) -> str:
    try:
        return _TRANSITIONS[(current, event)]
    except KeyError:
        raise AppError("CONFLICT_STATE", entity="approval", status=current, event=event) from None
