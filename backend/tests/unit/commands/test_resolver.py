"""Deterministic resolution of interpretations (agent-runtime.md §3, workflows.md §B)."""

import uuid
from typing import Any

import pytest

from app.ai.schemas import (
    Clarify,
    NormalizedBoolean,
    NormalizedMoney,
    NormalizedText,
    QueryActivitySummary,
    QueryFact,
    QueryPendingApprovals,
    Unsupported,
    UpdateBrandVoice,
    UpdateFact,
)
from app.commands import resolver
from app.commands.resolver import (
    Completed,
    Confirm,
    Execute,
    FactSnapshot,
    NeedsClarification,
    Rejected,
    UnsupportedOutcome,
)


def snap(
    key: str,
    label: str,
    value: dict[str, Any],
    vt: str = "money",
    status: str = "verified",
    version: int = 1,
    allowed: tuple[str, ...] = (),
) -> FactSnapshot:
    return FactSnapshot(
        id=uuid.uuid5(uuid.NAMESPACE_URL, key),
        key=key,
        label={"tr": label, "en": label},
        category=key.split(".")[0],
        value_type=vt,
        value=value,
        status=status,
        version=version,
        allowed_values=allowed,
    )


def money(amount: str, unit: str = "month", currency: str = "TRY") -> dict[str, Any]:
    return {"amount": amount, "currency": currency, "unit": unit}


MONTHLY = snap("pricing.membership_monthly", "Aylık üyelik", money("6000.00"), version=3)
QUARTER = snap("pricing.membership_3_months", "3 aylık üyelik", money("16500.00", "package"))
REFORMER = snap("pricing.reformer_8_sessions", "Reformer 8 seans", money("4800.00", "package"))
STUDENT = snap("pricing.student_monthly", "Öğrenci aylık", money("4500.00"), status="unverified")
PHONE = snap("contact.phone", "Telefon", {"e164": "+905550000000"}, "phone")
NAME = snap("identity.business_name", "İşletme adı", {"text": "Gölkent"}, "text")
HOURS = snap("hours.weekly", "Çalışma saatleri", {"mon": [], "exceptions": []}, "weekly_hours")
FLAG = snap("location.online_only", "Sadece çevrimiçi", {"value": False}, "boolean")
PRICE_MODE = snap(
    "policy.price_disclosure",
    "Fiyat paylaşımı",
    {"value": "share"},
    "enum",
    allowed=("share", "do_not_share"),
)
VOICE = snap(
    "brand.voice_guidelines",
    "Marka dili",
    {"tr": "Sıcak ve kısa.", "en": "Warm and short."},
    "localized_text",
)
FACTS = [MONTHLY, QUARTER, REFORMER, STUDENT, PHONE, NAME, HOURS, FLAG, PRICE_MODE, VOICE]


def run(
    interpretation: Any, user_locale: str = "tr", facts: list[FactSnapshot] | None = None
) -> Any:
    return resolver.resolve(
        interpretation,
        facts or FACTS,
        user_locale=user_locale,
        workspace_locale=user_locale,
        currency="TRY",
    )


def update(key: str, raw: str, model: Any = None, reason: str | None = None) -> UpdateFact:
    return UpdateFact(
        type="knowledge.update_fact",
        fact_key=key,
        raw_value_text=raw,
        normalized_value=model,
        reason=reason,
    )


def tl(amount: str) -> NormalizedMoney:
    return NormalizedMoney(kind="money", amount=amount, currency="TRY")


# --- a clean money update becomes a confirmation --------------------------------------------


def test_a_clean_update_becomes_a_confirmation_with_a_bound_payload() -> None:
    out = run(update(MONTHLY.key, "7.000 TL", tl("7000.00")))
    assert isinstance(out, Confirm)
    assert (out.command_type, out.action) == ("knowledge.update_fact", "command.update_fact")
    assert out.fact_id == MONTHLY.id
    assert out.payload == {
        "fact_id": str(MONTHLY.id),
        "from_version": 3,  # the version the owner saw: binds the confirmation
        "new_value": {"amount": "7000.00", "currency": "TRY", "unit": "month"},
        "reason": None,
    }
    assert out.summary["old_formatted"] == "6.000 ₺ / ay"
    assert out.summary["new_formatted"] == "7.000 ₺ / ay"  # the unit is kept
    assert out.summary["label"] == "Aylık üyelik"


@pytest.mark.parametrize(
    ("raw", "amount"),
    [
        ("7000", "7000.00"),
        ("7.000 TL", "7000.00"),
        ("7 bin TL", "7000.00"),
        ("7.500,50 ₺", "7500.50"),
    ],
)
def test_turkish_notations_are_read_by_the_locale_aware_parser(raw: str, amount: str) -> None:
    out = run(update(MONTHLY.key, raw, tl(amount)))
    assert isinstance(out, Confirm) and out.payload["new_value"]["amount"] == amount


def test_the_model_is_not_needed_to_read_the_value() -> None:
    out = run(update(MONTHLY.key, "7.000 TL", None))
    assert isinstance(out, Confirm) and out.payload["new_value"]["amount"] == "7000.00"


def test_a_stated_reason_is_kept_and_trimmed() -> None:
    out = run(update(MONTHLY.key, "7000", None, reason="  zam  "))
    assert isinstance(out, Confirm) and out.payload["reason"] == "zam"


# --- re-parse and disagreement --------------------------------------------------------------


def test_a_foreign_notation_is_a_question_not_a_guess() -> None:
    # "7.000" in an English workspace is 7000 or 7.00 (AC-C6 style clarification).
    en_fact = snap(
        "pricing.membership_monthly", "Monthly membership", money("89.00", "month", "EUR")
    )
    out = resolver.resolve(
        update(en_fact.key, "7.000", tl("7000.00")),
        [en_fact],
        user_locale="en",
        workspace_locale="en",
        currency="EUR",
    )
    assert isinstance(out, NeedsClarification) and out.kind == "value"
    assert [o.label for o in out.options] == ["€7,000", "€7"]
    assert out.question_key == "command.clarify.which_value"
    assert out.pending["fact_key"] == en_fact.key


def test_when_code_and_model_disagree_the_owner_decides() -> None:
    out = run(update(MONTHLY.key, "7.000 TL", tl("7.00")))  # the model read 7.00
    assert isinstance(out, NeedsClarification) and out.kind == "value"
    assert [o.label for o in out.options] == ["7.000 ₺", "7 ₺"]
    assert out.options[0].value == {
        "amount": "7000.00",
        "currency": "TRY",
    }  # the code's reading first


def test_a_different_currency_from_the_model_is_a_disagreement_too() -> None:
    out = run(
        update(MONTHLY.key, "7000", NormalizedMoney(kind="money", amount="7000.00", currency="USD"))
    )
    assert isinstance(out, NeedsClarification)


def test_an_unreadable_model_amount_is_a_disagreement_not_a_crash() -> None:
    out = run(
        update(MONTHLY.key, "7000", NormalizedMoney(kind="money", amount="seven", currency="TRY"))
    )
    assert isinstance(
        out, Confirm
    )  # the code's own reading stands when the model gave nothing usable


def test_the_clarified_value_is_used_without_asking_again() -> None:
    first = run(update(MONTHLY.key, "7.000 TL", tl("7.00")))
    clarification = {
        "kind": first.kind,
        "options": [{"id": o.id, "label": o.label, "value": o.value} for o in first.options],
        "pending": first.pending,
    }
    chosen = resolver.resolve_choice(
        clarification, "1", FACTS, user_locale="tr", workspace_locale="tr", currency="TRY"
    )
    assert isinstance(chosen, Confirm) and chosen.payload["new_value"]["amount"] == "7.00"


@pytest.mark.parametrize("raw", ["çok pahalı", "", "   ", "7.0000 TL", "abc 7 def 8"])
def test_an_unreadable_amount_is_rejected_with_a_message(raw: str) -> None:
    out = run(update(MONTHLY.key, raw, None))
    assert isinstance(out, Rejected) and out.error_code == "VALIDATION_FAILED"
    assert out.result.message_key == "command.value_unreadable"


# --- catalog validation ---------------------------------------------------------------------


def test_an_unknown_key_offers_the_closest_facts() -> None:
    out = run(update("pricing.membership_monthy", "7000", None))  # a typo from the model
    assert isinstance(out, NeedsClarification) and out.kind == "fact"
    assert out.options[0].id == "pricing.membership_monthly"
    assert 1 <= len(out.options) <= 3
    assert out.pending == {"intent": "knowledge.update_fact", "raw_value_text": "7000"}


def test_a_nonsense_key_with_no_similar_fact_is_unsupported() -> None:
    out = run(update("zzzz.qqqq", "7000", None), facts=[MONTHLY])
    assert isinstance(out, UnsupportedOutcome)


def test_choosing_a_fact_resumes_with_the_stored_value() -> None:
    out = run(
        Clarify(
            type="clarify",
            intent="knowledge.update_fact",
            candidate_fact_keys=[MONTHLY.key, QUARTER.key, REFORMER.key],
            raw_value_text="7000",
        )
    )
    assert isinstance(out, NeedsClarification) and out.kind == "fact"
    assert [o.id for o in out.options] == [MONTHLY.key, QUARTER.key, REFORMER.key]
    assert out.options[0].label == "Aylık üyelik · 6.000 ₺ / ay"
    clarification = {
        "kind": out.kind,
        "options": [{"id": o.id, "label": o.label, "value": o.value} for o in out.options],
        "pending": out.pending,
    }
    chosen = resolver.resolve_choice(
        clarification, QUARTER.key, FACTS, user_locale="tr", workspace_locale="tr", currency="TRY"
    )
    assert isinstance(chosen, Confirm)
    assert chosen.payload["fact_id"] == str(QUARTER.id)
    assert chosen.payload["new_value"] == {
        "amount": "7000.00",
        "currency": "TRY",
        "unit": "package",
    }


def test_an_option_that_was_not_offered_cannot_be_chosen() -> None:
    clarification = {
        "kind": "fact",
        "options": [{"id": MONTHLY.key, "label": "x", "value": None}],
        "pending": {"intent": "knowledge.update_fact", "raw_value_text": "7000"},
    }
    for bad in (QUARTER.key, "", "0", "pricing.unknown"):
        assert (
            resolver.resolve_choice(
                clarification, bad, FACTS, user_locale="tr", workspace_locale="tr", currency="TRY"
            )
            is None
        )


def test_model_candidates_are_checked_against_the_catalog() -> None:
    out = run(
        Clarify(
            type="clarify",
            intent="knowledge.update_fact",
            candidate_fact_keys=["made.up", MONTHLY.key, QUARTER.key, MONTHLY.key],
            raw_value_text="7000",
        )
    )
    assert isinstance(out, NeedsClarification)
    assert [o.id for o in out.options] == [MONTHLY.key, QUARTER.key]  # invented + duplicate dropped


def test_a_single_valid_candidate_needs_no_question() -> None:
    out = run(
        Clarify(
            type="clarify",
            intent="knowledge.update_fact",
            candidate_fact_keys=["made.up", MONTHLY.key],
            raw_value_text="7000",
        )
    )
    assert isinstance(out, Confirm) and out.fact_id == MONTHLY.id


def test_no_valid_candidate_is_unsupported() -> None:
    out = run(
        Clarify(
            type="clarify",
            intent="query.fact",
            candidate_fact_keys=["made.up"],
            raw_value_text=None,
        )
    )
    assert isinstance(out, UnsupportedOutcome)


def test_an_update_clarification_without_a_value_cannot_continue() -> None:
    clarification = {
        "kind": "fact",
        "options": [{"id": MONTHLY.key, "label": "x"}],
        "pending": {"intent": "knowledge.update_fact", "raw_value_text": None},
    }
    out = resolver.resolve_choice(
        clarification, MONTHLY.key, FACTS, user_locale="tr", workspace_locale="tr", currency="TRY"
    )
    assert isinstance(out, UnsupportedOutcome)


# --- unchanged values -----------------------------------------------------------------------


def test_the_same_value_is_already_done() -> None:
    out = run(update(MONTHLY.key, "6.000 TL", tl("6000.00")))
    assert isinstance(out, Completed)
    assert out.result.message_key == "command.fact_unchanged"
    assert out.result.params == {"label": "Aylık üyelik", "display": "6.000 ₺ / ay"}


def test_re_entering_an_unverified_value_still_asks_because_it_verifies_the_fact() -> None:
    out = run(update(STUDENT.key, "4.500 TL", None))
    assert isinstance(out, Confirm)


# --- other value types ----------------------------------------------------------------------


def test_a_phone_number_is_normalised() -> None:
    out = run(
        update(PHONE.key, "0555 111 22 33", NormalizedText(kind="text", text="0555 111 22 33"))
    )
    assert isinstance(out, Confirm) and out.payload["new_value"]["e164"] == "+905551112233"


def test_a_bad_phone_number_is_rejected() -> None:
    assert isinstance(run(update(PHONE.key, "12345", None)), Rejected)


def test_text_boolean_and_enum_values() -> None:
    text = run(update(NAME.key, "Yeni Ad", None))
    assert isinstance(text, Confirm) and text.payload["new_value"] == {"text": "Yeni Ad"}
    yes = run(update(FLAG.key, "evet", None))
    assert isinstance(yes, Confirm) and yes.payload["new_value"] == {"value": True}
    modelled = run(update(FLAG.key, "x", NormalizedBoolean(kind="boolean", value=True)))
    assert isinstance(modelled, Confirm) and modelled.payload["new_value"] == {"value": True}
    assert isinstance(run(update(FLAG.key, "belki", None)), Rejected)
    enum = run(update(PRICE_MODE.key, "do not share", None))
    assert isinstance(enum, Confirm) and enum.payload["new_value"] == {"value": "do_not_share"}
    assert isinstance(run(update(PRICE_MODE.key, "sometimes", None)), Rejected)


def test_hours_are_edited_in_the_app_not_by_command() -> None:
    assert isinstance(run(update(HOURS.key, "9-17", None)), UnsupportedOutcome)


# --- queries and pass-through ---------------------------------------------------------------


def test_a_fact_question_executes_read_only() -> None:
    out = run(QueryFact(type="query.fact", fact_key=MONTHLY.key))
    assert isinstance(out, Execute) and out.command_type == "query.fact"
    assert out.resolution == {"fact_key": MONTHLY.key, "fact_id": str(MONTHLY.id)}


def test_a_question_about_an_unknown_fact_offers_close_ones() -> None:
    out = run(QueryFact(type="query.fact", fact_key="pricing.membership_montly"))
    assert isinstance(out, NeedsClarification)
    chosen = resolver.resolve_choice(
        {
            "kind": out.kind,
            "options": [{"id": o.id, "label": o.label} for o in out.options],
            "pending": out.pending,
        },
        out.options[0].id,
        FACTS,
        user_locale="tr",
        workspace_locale="tr",
        currency="TRY",
    )
    assert isinstance(chosen, Execute) and chosen.command_type == "query.fact"


def test_other_read_only_commands() -> None:
    assert run(QueryPendingApprovals(type="query.pending_approvals")) == Execute(
        "query.pending_approvals", {}
    )
    assert run(QueryActivitySummary(type="query.activity_summary", period="yesterday")) == Execute(
        "query.activity_summary", {"period": "yesterday"}
    )


@pytest.mark.parametrize(
    "reason",
    ["publish", "send_message", "approve", "manage_account", "settings", "members", "other"],
)
def test_unsupported_passes_through_with_its_reason(reason: str) -> None:
    out = run(Unsupported(type="unsupported", reason=reason))  # type: ignore[arg-type]
    assert out == UnsupportedOutcome(reason)


def test_no_interpretation_resolves_to_anything_that_approves_publishes_or_sends() -> None:
    """INV-04: the only outcomes are questions, reads, confirmations and 'unsupported'."""
    outcomes = {
        type(run(i)).__name__
        for i in (
            Unsupported(type="unsupported", reason="approve"),
            Unsupported(type="unsupported", reason="publish"),
            Unsupported(type="unsupported", reason="send_message"),
        )
    }
    assert outcomes == {"UnsupportedOutcome"}


# --- brand voice ----------------------------------------------------------------------------


def test_brand_voice_proposal_becomes_a_confirmation_in_the_workspace_language() -> None:
    out = run(
        UpdateBrandVoice(
            type="knowledge.update_brand_voice",
            instruction="daha samimi",
            proposed_guidelines="Sıcak ve kısa. Daha samimi ol.",
        )
    )
    assert isinstance(out, Confirm) and out.action == "command.update_brand_voice"
    assert out.payload["new_value"] == {
        "tr": "Sıcak ve kısa. Daha samimi ol.",
        "en": "Warm and short.",
    }
    assert out.summary["old_formatted"] == "Sıcak ve kısa."
    assert out.payload["reason"] == "daha samimi"


def test_brand_voice_edge_cases() -> None:
    same = run(
        UpdateBrandVoice(
            type="knowledge.update_brand_voice",
            instruction="x",
            proposed_guidelines="Sıcak ve kısa.",
        )
    )
    assert isinstance(same, Completed)
    empty = run(
        UpdateBrandVoice(
            type="knowledge.update_brand_voice", instruction="x", proposed_guidelines=" "
        )
    )
    assert isinstance(empty, Rejected)
    too_long = run(
        UpdateBrandVoice(
            type="knowledge.update_brand_voice", instruction="x", proposed_guidelines="a" * 2001
        )
    )
    assert isinstance(too_long, Rejected)
    missing = run(
        UpdateBrandVoice(
            type="knowledge.update_brand_voice", instruction="x", proposed_guidelines="y"
        ),
        facts=[MONTHLY],
    )
    assert isinstance(missing, Rejected) and missing.error_code == "NOT_FOUND"
