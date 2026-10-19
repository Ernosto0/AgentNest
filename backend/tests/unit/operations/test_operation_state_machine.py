"""State-machines.md §6: the operation ledger's state machine (INV-05)."""

import pytest

from app.core.errors import AppError
from app.operations.models import OPERATION_STATUSES
from app.operations.transitions import OPERATION_EVENTS, apply_operation_event

ALLOWED = [
    ("pending", "start", "in_progress"),
    ("pending", "cancel", "cancelled"),
    ("in_progress", "succeed", "succeeded"),
    ("in_progress", "retry", "retry_wait"),
    ("in_progress", "fail", "failed"),
    ("in_progress", "unknown", "outcome_unknown"),
    ("retry_wait", "start", "in_progress"),
    ("retry_wait", "cancel", "cancelled"),
    ("retry_wait", "fail", "failed"),
    ("outcome_unknown", "succeed", "succeeded"),
    ("outcome_unknown", "fail", "failed"),
]
TERMINAL = ("succeeded", "failed", "cancelled")


@pytest.mark.parametrize(("current", "event", "expected"), ALLOWED)
def test_allowed_transitions(current: str, event: str, expected: str) -> None:
    assert apply_operation_event(current, event, operation_type="send_reply") == expected


def test_everything_else_is_a_conflict() -> None:
    allowed = {(c, e) for c, e, _ in ALLOWED} | {("outcome_unknown", "start")}
    for status in OPERATION_STATUSES:
        for event in OPERATION_EVENTS:
            if (status, event) in allowed:
                continue
            with pytest.raises(AppError) as excinfo:
                apply_operation_event(status, event, operation_type="send_reply")
            assert excinfo.value.code == "CONFLICT_STATE"


@pytest.mark.parametrize("status", TERMINAL)
def test_terminal_states_have_no_way_out(status: str) -> None:
    for event in OPERATION_EVENTS:
        with pytest.raises(AppError):
            apply_operation_event(status, event, operation_type="send_reply")


def test_an_ambiguous_send_is_never_started_again() -> None:
    """INV-05: ``outcome_unknown -> in_progress`` is forbidden for send_reply."""
    with pytest.raises(AppError) as excinfo:
        apply_operation_event("outcome_unknown", "start", operation_type="send_reply")
    assert excinfo.value.params["reason"] == "never_repeat_an_ambiguous_effect"


def test_a_publish_by_container_may_be_repeated_after_an_unknown_outcome() -> None:
    assert (
        apply_operation_event("outcome_unknown", "start", operation_type="publish_content")
        == "in_progress"
    )
