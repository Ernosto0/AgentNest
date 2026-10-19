"""The only place where operation states change (state-machines.md §6).

Pure. ``outcome_unknown -> in_progress`` exists only for operations that are safe to repeat
(publishing, by container); for ``send_reply`` it is forbidden: an ambiguous send is
reconciled and never repeated (INV-05, ADR-011).
"""

from app.core.errors import AppError

_TRANSITIONS: dict[tuple[str, str], str] = {
    ("pending", "start"): "in_progress",
    ("pending", "cancel"): "cancelled",
    ("in_progress", "succeed"): "succeeded",
    ("in_progress", "retry"): "retry_wait",
    ("in_progress", "fail"): "failed",
    ("in_progress", "unknown"): "outcome_unknown",
    ("retry_wait", "start"): "in_progress",
    ("retry_wait", "cancel"): "cancelled",
    ("retry_wait", "fail"): "failed",
    ("outcome_unknown", "succeed"): "succeeded",
    ("outcome_unknown", "fail"): "failed",
    ("outcome_unknown", "start"): "in_progress",  # publish only (checked below)
}
SAFE_TO_REPEAT = frozenset({"publish_content"})
OPERATION_EVENTS = frozenset(event for _, event in _TRANSITIONS)


def apply_operation_event(current: str, event: str, *, operation_type: str) -> str:
    if current == "outcome_unknown" and event == "start" and operation_type not in SAFE_TO_REPEAT:
        raise AppError(
            "CONFLICT_STATE",
            entity="operation",
            status=current,
            event=event,
            reason="never_repeat_an_ambiguous_effect",
        )
    try:
        return _TRANSITIONS[(current, event)]
    except KeyError:
        raise AppError("CONFLICT_STATE", entity="operation", status=current, event=event) from None
