"""The only place where command states change (state-machines.md §3).

Pure: ``(current state, event) -> next state`` or ``CONFLICT_STATE``. The Phase 3 registry has
no ``content.create_draft``, so the ``interpreting -> executing`` shortcut does not exist yet.
"""

from app.core.errors import AppError

_TRANSITIONS: dict[tuple[str | None, str], str] = {
    (None, "submit"): "interpreting",
    ("interpreting", "complete"): "completed",  # read-only command executed, or nothing to do
    ("interpreting", "ask_confirmation"): "awaiting_confirmation",
    ("interpreting", "clarify"): "needs_clarification",
    ("interpreting", "unsupported"): "unsupported",
    ("interpreting", "fail"): "failed",
    ("needs_clarification", "answer"): "interpreting",
    ("needs_clarification", "cancel"): "cancelled",
    ("needs_clarification", "expire"): "expired",
    ("awaiting_confirmation", "approved"): "executing",
    ("awaiting_confirmation", "cancel"): "cancelled",
    ("awaiting_confirmation", "expire"): "expired",
    ("executing", "complete"): "completed",
    ("executing", "fail"): "failed",
}
COMMAND_EVENTS = frozenset(event for _, event in _TRANSITIONS)
TERMINAL = frozenset({"completed", "unsupported", "failed", "cancelled", "expired"})


def apply_command_event(current: str | None, event: str) -> str:
    try:
        return _TRANSITIONS[(current, event)]
    except KeyError:
        raise AppError("CONFLICT_STATE", entity="command", status=current, event=event) from None
