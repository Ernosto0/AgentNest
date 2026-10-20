"""The content state machine (state-machines.md section 5, plus plan.md G1).

The expected table below is written out independently of the implementation, so a transition
that is added, dropped or renamed in ``content.transitions`` turns this red.
"""

import itertools

import pytest

from app.content.models import CONTENT_STATUSES
from app.content.transitions import CONTENT_EVENTS, EDITABLE_STATUSES, next_status
from app.core.errors import AppError

# (from, event) -> to. The first block is the diagram of section 5; the G1 block is the rest.
DIAGRAM = {
    ("draft", "submit"): "pending_approval",
    ("draft", "schedule"): "scheduled",
    ("pending_approval", "approve"): "scheduled",
    ("pending_approval", "reject"): "rejected",
    ("pending_approval", "withdraw"): "draft",
    ("pending_approval", "edit"): "draft",
    ("pending_approval", "expire"): "draft",
    ("scheduled", "start"): "publishing",
    ("scheduled", "edit"): "draft",
    ("scheduled", "cancel"): "cancelled",
    ("scheduled", "hold"): "on_hold",
    ("on_hold", "edit"): "draft",
    ("on_hold", "reapprove"): "scheduled",
    ("on_hold", "cancel"): "cancelled",
    ("publishing", "succeed"): "published",
    ("publishing", "retry"): "retry_scheduled",
    ("publishing", "fail"): "failed",
    ("retry_scheduled", "start"): "publishing",
    ("retry_scheduled", "cancel"): "cancelled",
    ("retry_scheduled", "fail"): "failed",
    ("rejected", "edit"): "draft",
    ("failed", "edit"): "draft",
    ("draft", "edit"): "draft",  # a payload change that keeps the status (version + 1)
}
G1 = {
    ("draft", "cancel"): "cancelled",
    ("pending_approval", "cancel"): "cancelled",
    ("retry_scheduled", "hold"): "on_hold",
}
ALLOWED = {**DIAGRAM, **G1}
PUBLISHING_HOLD = ("publishing", "hold")  # G1, but only for ACCOUNT_UNAVAILABLE


def test_the_statuses_are_the_ten_of_the_state_machine() -> None:
    assert set(CONTENT_STATUSES) == {
        "draft",
        "pending_approval",
        "scheduled",
        "publishing",
        "retry_scheduled",
        "on_hold",
        "published",
        "rejected",
        "failed",
        "cancelled",
    }


@pytest.mark.parametrize(("pair", "target"), sorted(ALLOWED.items()))
def test_every_allowed_transition(pair: tuple[str, str], target: str) -> None:
    assert next_status(*pair) == target


def test_publishing_may_be_held_only_because_the_account_is_unavailable() -> None:
    assert next_status("publishing", "hold", "ACCOUNT_UNAVAILABLE") == "on_hold"
    for reason in (None, "FACT_CHANGED", "APPROVAL_EXPIRED", ""):
        with pytest.raises(AppError) as error:
            next_status("publishing", "hold", reason)
        assert error.value.code == "CONFLICT_STATE"


def test_the_holds_of_scheduled_items_do_not_need_the_publishing_reason() -> None:
    for status in ("scheduled", "retry_scheduled"):
        for reason in (None, "FACT_CHANGED", "ACCOUNT_UNAVAILABLE"):
            assert next_status(status, "hold", reason) == "on_hold"


def test_every_other_combination_is_a_conflict() -> None:
    """Exhaustive: no (status, event) outside the table moves anything."""
    for status, event in itertools.product(CONTENT_STATUSES, sorted(CONTENT_EVENTS)):
        if (status, event) in ALLOWED or (status, event) == PUBLISHING_HOLD:
            continue
        with pytest.raises(AppError) as error:
            next_status(status, event, "ACCOUNT_UNAVAILABLE")
        assert error.value.code == "CONFLICT_STATE", (status, event)


@pytest.mark.invariant("INV-17")
def test_published_content_has_no_way_out() -> None:
    """Published items are immutable: no event, not even an edit, leaves ``published``."""
    for event in sorted(CONTENT_EVENTS):
        with pytest.raises(AppError) as error:
            next_status("published", event, "ACCOUNT_UNAVAILABLE")
        assert error.value.code == "CONFLICT_STATE", event
    assert "published" not in EDITABLE_STATUSES


def test_cancelled_is_terminal() -> None:
    for event in sorted(CONTENT_EVENTS):
        with pytest.raises(AppError):
            next_status("cancelled", event)


def test_the_key_forbidden_paths() -> None:
    forbidden = [
        ("publishing", "cancel"),  # the outcome must be determined first
        ("publishing", "edit"),
        ("retry_scheduled", "edit"),
        ("draft", "start"),  # never published without a schedule and an approval
        ("pending_approval", "start"),
        ("on_hold", "start"),  # a held item is re-approved, not published
        ("draft", "approve"),
        ("rejected", "schedule"),
        ("failed", "retry"),
        ("scheduled", "succeed"),  # only a publish attempt can succeed
        ("draft", "succeed"),
        ("failed", "reapprove"),
    ]
    for pair in forbidden:
        with pytest.raises(AppError) as error:
            next_status(*pair)
        assert error.value.code == "CONFLICT_STATE", pair


def test_the_editable_statuses_are_the_ones_that_return_to_draft() -> None:
    assert {
        "draft",
        "pending_approval",
        "scheduled",
        "on_hold",
        "rejected",
        "failed",
    } == EDITABLE_STATUSES
