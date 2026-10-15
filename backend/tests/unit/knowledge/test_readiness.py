"""Readiness levels (AC-A5, workflows.md §A step 7)."""

from datetime import UTC, datetime
from typing import Any

from app.knowledge.readiness import Readiness, compute_readiness
from app.knowledge.templates import load_template

REVIEWED = datetime(2026, 10, 15, tzinfo=UTC)

DRAFT_FACTS: dict[str, dict[str, Any]] = {
    "identity.business_name": {"text": "Gölkent"},
    "contact.phone": {"e164": "+905550000000"},
    "location.address": {"lines": ["x"], "city": "Burdur"},
    "hours.weekly": {"mon": []},
}
READY_FACTS: dict[str, dict[str, Any]] = {
    **DRAFT_FACTS,
    "booking.instructions": {"tr": "Arayın"},
    "policy.price_disclosure": {"value": "share"},
    "pricing.membership_monthly": {"amount": "6000.00", "currency": "TRY"},
    "service.fitness": {"tr": "Fitness"},
}


def _compute(
    usable: dict[str, dict[str, Any]],
    *,
    category: str = "gym",
    account: bool = True,
    reviewed: datetime | None = REVIEWED,
) -> Readiness:
    return compute_readiness(
        load_template(category), usable, account_connected=account, automation_reviewed_at=reviewed
    )


def _status(report: Readiness) -> dict[str, bool]:
    return {r.code: r.satisfied for r in report.requirements}


def test_everything_present_and_an_account_connected_is_ready() -> None:
    report = _compute(READY_FACTS)
    assert report.level == "ready"
    assert all(_status(report).values())


def test_without_a_connected_account_the_level_is_ready_for_drafts() -> None:
    report = _compute(READY_FACTS, account=False)
    assert report.level == "ready_for_drafts"
    account = next(r for r in report.requirements if r.code == "account_connected")
    assert (account.satisfied, account.status) == (False, "not_connected")


def test_unreviewed_automation_blocks_ready() -> None:
    report = _compute(READY_FACTS, reviewed=None)
    assert report.level == "ready_for_drafts"
    assert not _status(report)["automation_reviewed"]


def test_a_missing_draft_requirement_is_not_ready_and_listed() -> None:
    facts = {k: v for k, v in READY_FACTS.items() if k != "hours.weekly"}
    report = _compute(facts)
    assert report.level == "not_ready"
    hours = next(r for r in report.requirements if r.code == "hours")
    assert hours.missing_keys == ("hours.weekly",)
    assert (hours.link.target, hours.link.category) == ("knowledge", "hours")


def test_missing_ready_requirement_downgrades_to_ready_for_drafts() -> None:
    facts = {k: v for k, v in READY_FACTS.items() if k != "booking.instructions"}
    assert _compute(facts).level == "ready_for_drafts"


def test_any_one_contact_channel_is_enough_and_online_only_replaces_the_address() -> None:
    facts = {k: v for k, v in DRAFT_FACTS.items() if k not in ("contact.phone", "location.address")}
    assert _compute(facts).level == "not_ready"
    facts["contact.email"] = {"email": "a@b.co"}
    facts["location.online_only"] = {"value": True}
    assert _compute(facts).level == "ready_for_drafts"
    facts["location.online_only"] = {"value": False}
    assert _compute(facts).level == "not_ready"


def test_price_policy_depends_on_the_disclosure_choice() -> None:
    no_price = {k: v for k, v in READY_FACTS.items() if k != "pricing.membership_monthly"}
    report = _compute(no_price)
    assert report.level == "ready_for_drafts"
    policy = next(r for r in report.requirements if r.code == "price_policy")
    assert policy.missing_keys == ("pricing.membership_monthly",)

    hidden = {**no_price, "policy.price_disclosure": {"value": "do_not_share"}}
    assert not _status(_compute(hidden))["price_policy"]  # needs the answer text
    hidden["policy.price_answer_text"] = {"tr": "Arayın"}
    assert _compute(hidden).level == "ready"

    undecided = {k: v for k, v in READY_FACTS.items() if k != "policy.price_disclosure"}
    assert not _status(_compute(undecided))["price_policy"]


def test_pilates_requires_the_reformer_package_price_not_the_monthly_membership() -> None:
    facts = {k: v for k, v in READY_FACTS.items() if k != "pricing.membership_monthly"}
    assert _compute(facts, category="pilates_studio").level == "ready_for_drafts"
    facts["pricing.reformer_8_sessions"] = {"amount": "4800.00", "currency": "TRY"}
    assert _compute(facts, category="pilates_studio").level == "ready"


def test_at_least_one_service_is_required() -> None:
    facts = {k: v for k, v in READY_FACTS.items() if k != "service.fitness"}
    report = _compute(facts)
    assert report.level == "ready_for_drafts"
    assert not _status(report)["services"]
