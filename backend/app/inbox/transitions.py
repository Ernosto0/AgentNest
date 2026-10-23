"""The only place where reply-draft states change (state-machines.md §4).

Pure: maps ``(current state, event)`` to the next state or raises ``CONFLICT_STATE``. Initial
states come from the policy decision (:func:`initial_status`). ``outcome_unknown`` never goes
back to ``sending`` (a send is never repeated on ambiguity, INV-05).
"""

from app.core.errors import AppError

_TRANSITIONS: dict[tuple[str, str], str] = {
    ("pending_approval", "approve"): "queued",
    ("pending_approval", "reject"): "rejected",
    ("pending_approval", "expire"): "expired",
    ("pending_approval", "supersede"): "superseded",
    ("pending_approval", "edit"): "pending_approval",
    ("pending_approval", "cancel"): "cancelled",  # account disconnected
    ("needs_human", "supersede"): "superseded",
    ("needs_human", "expire"): "expired",
    ("queued", "start_send"): "sending",
    ("queued", "expire"): "expired",
    ("queued", "cancel"): "cancelled",
    ("sending", "succeed"): "sent",
    ("sending", "fail"): "failed",
    ("sending", "unknown"): "outcome_unknown",
    ("sending", "expire"): "expired",  # the provider says the window closed: nothing was sent
    ("sending", "retry"): "queued",  # the provider certainly did not accept it: try again
    ("outcome_unknown", "succeed"): "sent",
    ("outcome_unknown", "fail"): "failed",
}
DRAFT_EVENTS = frozenset(event for _, event in _TRANSITIONS)

_INITIAL = {
    "auto": "queued",  # the approval is granted by policy, recorded separately
    "approval_required": "pending_approval",
    "human_required": "needs_human",
    "blocked": "blocked",
}


def initial_status(decision: str) -> str:
    try:
        return _INITIAL[decision]
    except KeyError:
        raise AppError("CONFLICT_STATE", entity="reply_draft", decision=decision) from None


def apply_draft_event(current: str, event: str) -> str:
    try:
        return _TRANSITIONS[(current, event)]
    except KeyError:
        raise AppError(
            "CONFLICT_STATE", entity="reply_draft", status=current, event=event
        ) from None
