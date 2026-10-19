"""State-machines.md §4: the reply-draft state machine and the conversation attention rules."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import AppError
from app.inbox.attention import compute_attention, customer_number
from app.inbox.models import DRAFT_STATUSES, OPEN_DRAFT_STATUSES
from app.inbox.transitions import DRAFT_EVENTS, apply_draft_event, initial_status

ALLOWED = [
    ("pending_approval", "approve", "queued"),
    ("pending_approval", "reject", "rejected"),
    ("pending_approval", "expire", "expired"),
    ("pending_approval", "supersede", "superseded"),
    ("pending_approval", "edit", "pending_approval"),
    ("needs_human", "supersede", "superseded"),
    ("needs_human", "expire", "expired"),
    ("queued", "start_send", "sending"),
    ("queued", "expire", "expired"),
    ("queued", "cancel", "cancelled"),
    ("sending", "succeed", "sent"),
    ("sending", "fail", "failed"),
    ("sending", "unknown", "outcome_unknown"),
    ("sending", "retry", "queued"),
    ("sending", "expire", "expired"),
    ("outcome_unknown", "succeed", "sent"),
    ("outcome_unknown", "fail", "failed"),
]
TERMINAL = ["sent", "failed", "rejected", "expired", "superseded", "cancelled", "blocked"]


@pytest.mark.parametrize(("current", "event", "expected"), ALLOWED)
def test_allowed_transitions(current: str, event: str, expected: str) -> None:
    assert apply_draft_event(current, event) == expected


def test_every_other_combination_is_a_conflict() -> None:
    allowed = {(c, e) for c, e, _ in ALLOWED}
    for status in DRAFT_STATUSES:
        for event in DRAFT_EVENTS:
            if (status, event) in allowed:
                continue
            with pytest.raises(AppError) as excinfo:
                apply_draft_event(status, event)
            assert excinfo.value.code == "CONFLICT_STATE"


def test_terminal_states_have_no_way_out() -> None:
    for status in TERMINAL:
        for event in DRAFT_EVENTS:
            with pytest.raises(AppError):
                apply_draft_event(status, event)


def test_an_unknown_send_outcome_never_goes_back_to_sending() -> None:
    """INV-05: an ambiguous send is reconciled, never repeated."""
    with pytest.raises(AppError):
        apply_draft_event("outcome_unknown", "start_send")
    with pytest.raises(AppError):
        apply_draft_event("outcome_unknown", "cancel")


def test_initial_status_follows_the_decision() -> None:
    assert initial_status("auto") == "queued"
    assert initial_status("approval_required") == "pending_approval"
    assert initial_status("human_required") == "needs_human"
    assert initial_status("blocked") == "blocked"
    with pytest.raises(AppError):
        initial_status("whatever")


def test_open_statuses_are_exactly_the_non_terminal_ones() -> None:
    assert set(OPEN_DRAFT_STATUSES) == set(DRAFT_STATUSES) - set(TERMINAL)


# --- attention -------------------------------------------------------------------------------

T0 = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)


def attention(**overrides: object) -> str:
    values: dict[str, object] = {
        "open_draft_status": None,
        "latest_draft_status": None,
        "latest_draft_at": None,
        "handling_mode": "automatic",
        "last_inbound_at": T0,
        "last_outbound_at": None,
    }
    values.update(overrides)
    return compute_attention(**values)  # type: ignore[arg-type]


def test_a_quiet_conversation_needs_nothing() -> None:
    assert attention() == "none"


def test_a_draft_waiting_for_a_person_asks_for_that_person() -> None:
    assert attention(open_draft_status="needs_human") == "needs_human"
    assert attention(open_draft_status="pending_approval") == "needs_approval"
    assert attention(open_draft_status="queued") == "none"


def test_needs_human_wins_over_needs_approval() -> None:
    assert attention(handling_mode="human", open_draft_status="pending_approval") == "needs_human"


def test_human_mode_needs_a_person_only_while_the_last_message_is_unanswered() -> None:
    assert attention(handling_mode="human") == "needs_human"
    assert attention(handling_mode="human", last_outbound_at=T0 + timedelta(minutes=1)) == "none"


def test_a_failed_or_blocked_draft_matters_until_a_later_outbound_message() -> None:
    later = T0 + timedelta(minutes=2)
    assert attention(latest_draft_status="failed", latest_draft_at=later) == "failed"
    assert attention(latest_draft_status="blocked", latest_draft_at=later) == "failed"
    answered = {"last_outbound_at": later + timedelta(minutes=1)}
    assert attention(latest_draft_status="failed", latest_draft_at=later, **answered) == "none"
    assert attention(latest_draft_status="sent", latest_draft_at=later) == "none"


def test_the_customer_number_is_short_and_stable() -> None:
    import uuid

    ident = uuid.UUID("12345678-1234-5678-1234-567812345678")
    assert customer_number(ident) == customer_number(ident)
    assert 0 <= customer_number(ident) < 10000
