"""The only place where fact and candidate states change (state-machines.md §2, §intro).

Both functions are pure: they map ``(current state, event)`` to the next state or raise
``CONFLICT_STATE``. Services call them before touching a row, so a transition that is not in
the tables cannot happen by accident.

Fact states: ``unverified``, ``verified``, ``archived``. "Usable" is computed, not a state.
Candidate states: ``pending`` -> ``accepted | rejected | superseded`` (terminal).
"""

from app.core.errors import AppError

# (current status or None for "does not exist yet", event) -> next status
_FACT_TRANSITIONS: dict[tuple[str | None, str], str] = {
    (None, "create_verified"): "verified",  # created by a verifier
    (None, "create_unverified"): "unverified",  # seed / template default
    ("unverified", "verify"): "verified",
    ("unverified", "edit"): "verified",  # an edit by a verifier verifies
    ("verified", "edit"): "verified",  # new version, still verified
    ("unverified", "archive"): "archived",
    ("verified", "archive"): "archived",
    ("archived", "restore"): "unverified",
}
FACT_EVENTS = frozenset(event for _, event in _FACT_TRANSITIONS)

_CANDIDATE_TRANSITIONS: dict[tuple[str | None, str], str] = {
    (None, "propose"): "pending",
    (None, "propose_same"): "superseded",  # equal to the current value: nothing to decide
    ("pending", "accept"): "accepted",
    ("pending", "reject"): "rejected",
    ("pending", "supersede"): "superseded",
}
CANDIDATE_EVENTS = frozenset(event for _, event in _CANDIDATE_TRANSITIONS)


def apply_fact_event(current: str | None, event: str) -> str:
    """Next fact status for ``event``; ``CONFLICT_STATE`` when the transition is not allowed."""
    try:
        return _FACT_TRANSITIONS[(current, event)]
    except KeyError:
        raise AppError("CONFLICT_STATE", entity="fact", status=current, event=event) from None


def apply_candidate_event(current: str | None, event: str) -> str:
    try:
        return _CANDIDATE_TRANSITIONS[(current, event)]
    except KeyError:
        raise AppError(
            "CONFLICT_STATE", entity="fact_candidate", status=current, event=event
        ) from None
