"""Every transition of state-machines.md §2 is allowed, and everything else is refused."""

import itertools

import pytest

from app.core.errors import AppError
from app.knowledge.transitions import (
    CANDIDATE_EVENTS,
    FACT_EVENTS,
    apply_candidate_event,
    apply_fact_event,
)

FACT_ALLOWED = {
    (None, "create_verified"): "verified",
    (None, "create_unverified"): "unverified",
    ("unverified", "verify"): "verified",
    ("unverified", "edit"): "verified",
    ("verified", "edit"): "verified",
    ("unverified", "archive"): "archived",
    ("verified", "archive"): "archived",
    ("archived", "restore"): "unverified",
}
CANDIDATE_ALLOWED = {
    (None, "propose"): "pending",
    (None, "propose_same"): "superseded",
    ("pending", "accept"): "accepted",
    ("pending", "reject"): "rejected",
    ("pending", "supersede"): "superseded",
}


@pytest.mark.parametrize(("pair", "expected"), FACT_ALLOWED.items())
def test_allowed_fact_transitions(pair: tuple[str | None, str], expected: str) -> None:
    assert apply_fact_event(*pair) == expected


def test_every_other_fact_transition_is_a_conflict() -> None:
    states = [None, "unverified", "verified", "archived"]
    for state, event in itertools.product(states, FACT_EVENTS):
        if (state, event) in FACT_ALLOWED:
            continue
        with pytest.raises(AppError) as raised:
            apply_fact_event(state, event)
        assert raised.value.code == "CONFLICT_STATE"


def test_archived_facts_cannot_be_verified_or_edited_directly() -> None:
    for event in ("verify", "edit", "archive"):
        with pytest.raises(AppError):
            apply_fact_event("archived", event)


@pytest.mark.parametrize(("pair", "expected"), CANDIDATE_ALLOWED.items())
def test_allowed_candidate_transitions(pair: tuple[str | None, str], expected: str) -> None:
    assert apply_candidate_event(*pair) == expected


def test_resolved_candidates_are_terminal() -> None:
    states = [None, "pending", "accepted", "rejected", "superseded"]
    for state, event in itertools.product(states, CANDIDATE_EVENTS):
        if (state, event) in CANDIDATE_ALLOWED:
            continue
        with pytest.raises(AppError) as raised:
            apply_candidate_event(state, event)
        assert raised.value.code == "CONFLICT_STATE"


def test_unknown_events_are_conflicts_too() -> None:
    with pytest.raises(AppError):
        apply_fact_event("verified", "explode")
