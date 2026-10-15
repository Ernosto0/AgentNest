"""Candidate relations and fact usability (business-knowledge.md §1, §5; INV-02, INV-19)."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest

from app.knowledge.candidates import FactSnapshot, compute_relation
from app.knowledge.usability import display_state, is_usable, local_today, window_state

PRICE = {"amount": "6000.00", "currency": "TRY", "unit": "month"}
OTHER = {"amount": "5500.00", "currency": "TRY", "unit": "month"}


def _fact(status: str = "verified", value: dict[str, Any] = PRICE) -> FactSnapshot:
    return FactSnapshot(uuid.uuid4(), status, "money", value)


@pytest.mark.parametrize(
    ("fact", "value", "source", "expected"),
    [
        (None, OTHER, "staff_proposal", "new"),
        (None, OTHER, "pasted_text", "new"),
        (_fact("unverified"), PRICE, "pasted_text", "new"),  # accepting it would verify the fact
        (_fact("archived"), OTHER, "staff_proposal", "new"),
        (_fact(), PRICE, "pasted_text", "same"),
        (_fact(), {**PRICE, "amount": "6000"}, "staff_proposal", "same"),
        (_fact(), OTHER, "pasted_text", "discrepancy"),
        (_fact(), OTHER, "instagram_profile", "discrepancy"),
        (_fact(), OTHER, "website", "discrepancy"),
        (_fact(), OTHER, "staff_proposal", "contest"),
    ],
)
def test_relation_table(
    fact: FactSnapshot | None, value: dict[str, Any], source: str, expected: str
) -> None:
    assert compute_relation(fact, value, "money", source) == expected


def test_a_candidate_of_another_value_type_is_new() -> None:
    assert compute_relation(_fact(), {"text": "x"}, "text", "staff_proposal") == "new"


# --- usability ------------------------------------------------------------------------------

TODAY = date(2026, 10, 15)


def _usable(**overrides: Any) -> bool:
    params: dict[str, Any] = {
        "status": "verified",
        "valid_from": None,
        "valid_until": None,
        "today": TODAY,
        "contested": False,
    }
    return is_usable(**{**params, **overrides})


def test_only_verified_uncontested_facts_in_their_window_are_usable() -> None:
    assert _usable()
    assert not _usable(status="unverified")
    assert not _usable(status="archived")
    assert not _usable(contested=True)
    assert not _usable(valid_until=date(2026, 10, 14))
    assert not _usable(valid_from=date(2026, 10, 16))


def test_window_bounds_are_inclusive() -> None:
    assert _usable(valid_from=TODAY, valid_until=TODAY)
    assert window_state(TODAY, date(2026, 10, 14), TODAY) == "expired"
    assert window_state(date(2026, 10, 16), None, TODAY) == "not_started"


def test_display_state_labels() -> None:
    kwargs: dict[str, Any] = {"valid_from": None, "valid_until": None, "today": TODAY}
    assert display_state(status="unverified", contested=False, **kwargs) == "unverified"
    assert display_state(status="verified", contested=True, **kwargs) == "contested"
    assert display_state(status="verified", contested=False, **kwargs) == "verified"
    assert display_state(status="archived", contested=False, **kwargs) == "archived"
    assert (
        display_state(
            status="verified", contested=False, **{**kwargs, "valid_until": date(2026, 1, 1)}
        )
        == "expired"
    )


def test_today_is_the_workspace_local_date_not_the_utc_date() -> None:
    late_utc = datetime(2026, 10, 29, 21, 30, tzinfo=UTC)  # 00:30 on 30 Oct in Istanbul (UTC+3)
    assert local_today(late_utc, "Europe/Istanbul") == date(2026, 10, 30)
    assert local_today(late_utc, "UTC") == date(2026, 10, 29)
    # A promotion valid until 29 Oct is already over in Istanbul but not in UTC:
    assert not _usable(
        valid_until=date(2026, 10, 29), today=local_today(late_utc, "Europe/Istanbul")
    )
    assert _usable(valid_until=date(2026, 10, 29), today=local_today(late_utc, "UTC"))


def test_a_dst_timezone_is_handled_by_the_database_of_zones() -> None:
    before_change = datetime(
        2026, 3, 29, 0, 30, tzinfo=UTC
    )  # Lisbon moves to summer time 01:00 UTC
    assert local_today(before_change, "Europe/Lisbon") == date(2026, 3, 29)
    after_midnight = datetime(2026, 7, 1, 23, 30, tzinfo=UTC)  # UTC+1 in July: already 2 July
    assert local_today(after_midnight, "Europe/Lisbon") == date(2026, 7, 2)
