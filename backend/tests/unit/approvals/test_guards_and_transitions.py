"""Pure approval guards and the state machine (state-machines.md §1, ADR-014)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.approvals.guards import ApprovalFacts, decision_blocker, may_decide
from app.approvals.transitions import APPROVAL_EVENTS, apply_approval_event
from app.core.context import ActorRef
from app.core.errors import AppError

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
HASH = "a" * 64
REQUESTER = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"


def facts(**overrides: object) -> ApprovalFacts:
    values: dict[str, object] = {
        "kind": "confirmation",
        "status": "pending",
        "required_permission": "knowledge.verify",
        "requested_by_actor_type": "user",
        "requested_by_actor_id": REQUESTER,
        "payload_hash": HASH,
        "subject_version": 1,
        "expires_at": NOW + timedelta(minutes=30),
    }
    values.update(overrides)
    return ApprovalFacts(**values)  # type: ignore[arg-type]


def blocker(
    approval: ApprovalFacts | None = None,
    *,
    actor: ActorRef | None = None,
    role: str | None = "owner",
    now: datetime = NOW,
    supplied_hash: str = HASH,
    subject_version: int | None = 1,
) -> str | None:
    return decision_blocker(
        approval or facts(),
        actor=actor or ActorRef("user", OTHER),
        role=role,
        now=now,
        supplied_hash=supplied_hash,
        subject_version=subject_version,
    )


def test_the_happy_path_has_no_blocker() -> None:
    assert blocker() is None


def test_a_wrong_hash_is_stale() -> None:
    assert blocker(supplied_hash="b" * 64) == "APPROVAL_STALE"


def test_a_changed_subject_version_is_stale_even_with_the_right_hash() -> None:
    assert blocker(subject_version=2) == "APPROVAL_STALE"
    assert blocker(subject_version=None) == "APPROVAL_STALE"  # the subject is gone


def test_an_already_decided_approval_cannot_be_decided_again() -> None:
    for status in ("approved", "rejected", "cancelled"):
        assert blocker(facts(status=status)) == "APPROVAL_ALREADY_DECIDED"


def test_an_approval_that_already_expired_still_reads_as_expired() -> None:
    assert blocker(facts(status="expired")) == "APPROVAL_EXPIRED"


def test_expiry_is_inclusive_at_the_deadline() -> None:
    approval = facts()
    assert blocker(approval, now=approval.expires_at - timedelta(seconds=1)) is None
    assert blocker(approval, now=approval.expires_at) == "APPROVAL_EXPIRED"
    assert blocker(approval, now=approval.expires_at + timedelta(days=1)) == "APPROVAL_EXPIRED"


def test_permission_is_checked_before_anything_is_revealed() -> None:
    # A staff member who is not the requester learns nothing about state, expiry or hash.
    staff = ActorRef("user", OTHER)
    assert blocker(facts(status="approved"), actor=staff, role="staff") == "FORBIDDEN"
    assert blocker(actor=staff, role="staff", now=NOW + timedelta(days=1)) == "FORBIDDEN"
    assert blocker(actor=staff, role="staff", supplied_hash="b" * 64) == "FORBIDDEN"


def test_the_requester_may_decide_their_own_confirmation_without_the_permission() -> None:
    staff_requester = ActorRef("user", REQUESTER)
    assert blocker(actor=staff_requester, role="staff") is None


def test_the_requester_exception_does_not_apply_to_authorizations() -> None:
    approval = facts(kind="authorization")
    assert blocker(approval, actor=ActorRef("user", REQUESTER), role="staff") == "FORBIDDEN"
    assert blocker(approval, actor=ActorRef("user", OTHER), role="manager") is None


def test_the_requester_exception_does_not_cover_other_people() -> None:
    assert blocker(actor=ActorRef("user", OTHER), role="staff") == "FORBIDDEN"


def test_only_a_human_can_decide() -> None:
    for actor in (ActorRef.system("job"), ActorRef("agent", "run-1"), ActorRef("provider", "x")):
        assert not may_decide(facts(), actor, "owner")
        assert blocker(actor=actor, role="owner") == "FORBIDDEN"


def test_a_user_without_a_role_cannot_decide() -> None:
    assert blocker(role=None) == "FORBIDDEN"


# --- state machine -------------------------------------------------------------------------


def test_request_creates_a_pending_approval() -> None:
    assert apply_approval_event(None, "request") == "pending"


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ("approve", "approved"),
        ("reject", "rejected"),
        ("expire", "expired"),
        ("cancel", "cancelled"),
    ],
)
def test_pending_approvals_move_to_a_terminal_state(event: str, expected: str) -> None:
    assert apply_approval_event("pending", event) == expected


@pytest.mark.parametrize("status", ["approved", "rejected", "expired", "cancelled"])
@pytest.mark.parametrize("event", sorted(APPROVAL_EVENTS - {"request"}))
def test_terminal_states_have_no_outgoing_transitions(status: str, event: str) -> None:
    with pytest.raises(AppError) as info:
        apply_approval_event(status, event)
    assert info.value.code == "CONFLICT_STATE"


def test_a_second_request_for_an_existing_approval_is_refused() -> None:
    with pytest.raises(AppError):
        apply_approval_event("pending", "request")
