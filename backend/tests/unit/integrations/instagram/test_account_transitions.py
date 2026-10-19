"""State-machines.md §7: the social-account state machine."""

import pytest

from app.core.errors import AppError
from app.integrations.instagram.transitions import apply_account_transition

ALLOWED = [
    (None, "connected"),
    ("connected", "needs_reauth"),
    ("connected", "degraded"),
    ("connected", "disconnected"),
    ("degraded", "connected"),
    ("degraded", "needs_reauth"),
    ("degraded", "disconnected"),
    ("needs_reauth", "connected"),
    ("needs_reauth", "disconnected"),
]
FORBIDDEN = [
    (None, "degraded"),
    (None, "disconnected"),
    ("connected", "connected"),
    ("needs_reauth", "degraded"),
    ("disconnected", "connected"),  # reconnecting creates a new account row
    ("disconnected", "needs_reauth"),
]


@pytest.mark.parametrize(("current", "target"), ALLOWED)
def test_allowed_transitions(current: str | None, target: str) -> None:
    assert apply_account_transition(current, target) == target


@pytest.mark.parametrize(("current", "target"), FORBIDDEN)
def test_forbidden_transitions_are_a_conflict(current: str | None, target: str) -> None:
    with pytest.raises(AppError) as excinfo:
        apply_account_transition(current, target)
    assert excinfo.value.code == "CONFLICT_STATE"
