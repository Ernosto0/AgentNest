"""The reply policy engine (workflows.md §C.1, rules R1 to R17): table-driven, plus adversarial
model output. AC-B4 (default), AC-B6 (complaints), AC-B7 (injection) and INV-04 (the model can
only escalate)."""

import itertools
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.policy.classes import (
    DEFAULT_MODE,
    effective_mode,
    fact_action_class,
    intent_action_class,
    required_facts_usable,
)
from app.policy.engine import Decision, evaluate_reply
from app.policy.rules_reply import RULES, SEVERITY, ReplyPolicyInput

NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)


def base(**overrides: object) -> ReplyPolicyInput:
    """A clean pricing question on a ready workspace whose pricing policy is `approval`."""
    values: dict[str, object] = {
        "now": NOW,
        "account_status": "connected",
        "account_can_message": True,
        "window_end": NOW + timedelta(hours=10),
        "handling_mode": "automatic",
        "language_supported": True,
        "keyword_flags": frozenset(),
        "escalation_keyword": False,
        "injection_suspected": False,
        "attachment_only": False,
        "intent": "pricing",
        "model_flags": frozenset(),
        "model_responded": True,
        "model_needs_human": False,
        "model_can_answer": True,
        "llm_error": None,
        "required_facts_usable": True,
        "render_failed": False,
        "grounding_failed": False,
        "automation_mode": "approval",
        "readiness_level": "ready",
        "auto_replies_last_hour": 0,
    }
    values.update(overrides)
    return ReplyPolicyInput(**values)  # type: ignore[arg-type]


def decide(**overrides: object) -> Decision:
    return evaluate_reply(base(**overrides))


# --- the outcomes --------------------------------------------------------------------------------


def test_the_default_policy_requires_approval() -> None:
    """AC-B4: with the default automation policy a clean reply still needs the owner."""
    assert decide() == Decision("approval_required", ("POLICY_REQUIRES_APPROVAL",))


def test_a_clean_reply_under_an_automatic_policy_is_automatic() -> None:
    assert decide(automation_mode="auto") == Decision("auto", ("POLICY_AUTO",))


CASES: list[tuple[str, dict[str, object], str, str]] = [
    # (name, overrides, outcome, reason)
    (
        "R1 account not connected",
        {"account_status": "needs_reauth"},
        "blocked",
        "ACCOUNT_NOT_CONNECTED",
    ),
    (
        "R1 account disconnected",
        {"account_status": "disconnected"},
        "blocked",
        "ACCOUNT_NOT_CONNECTED",
    ),
    ("R1 no account", {"account_status": None}, "blocked", "ACCOUNT_NOT_CONNECTED"),
    (
        "R1 messaging capability missing",
        {"account_can_message": False},
        "blocked",
        "CAPABILITY_MISSING",
    ),
    (
        "R2 window closed",
        {"window_end": NOW - timedelta(minutes=1)},
        "blocked",
        "MESSAGING_WINDOW_CLOSED",
    ),
    (
        "R2 inside the safety margin",
        {"window_end": NOW + timedelta(minutes=5)},
        "blocked",
        "MESSAGING_WINDOW_CLOSED",
    ),
    ("R2 unknown window", {"window_end": None}, "blocked", "MESSAGING_WINDOW_CLOSED"),
    ("R3 human takeover", {"handling_mode": "human"}, "human_required", "HUMAN_TAKEOVER"),
    (
        "R4 unsupported language",
        {"language_supported": False},
        "human_required",
        "LANGUAGE_UNSUPPORTED",
    ),
    ("R5 complaint intent", {"intent": "complaint"}, "human_required", "INTENT_COMPLAINT"),
    ("R5 refund intent", {"intent": "refund_request"}, "human_required", "INTENT_REFUND_REQUEST"),
    (
        "R5 discount intent",
        {"intent": "discount_request"},
        "human_required",
        "INTENT_DISCOUNT_REQUEST",
    ),
    ("R5 sensitive intent", {"intent": "sensitive"}, "human_required", "INTENT_SENSITIVE"),
    (
        "R5 model flag complaint",
        {"model_flags": frozenset({"complaint"})},
        "human_required",
        "FLAG_COMPLAINT",
    ),
    (
        "R5 model flag refund",
        {"model_flags": frozenset({"refund"})},
        "human_required",
        "FLAG_REFUND",
    ),
    (
        "R5 model flag discount",
        {"model_flags": frozenset({"discount"})},
        "human_required",
        "FLAG_DISCOUNT",
    ),
    ("R5 model flag legal", {"model_flags": frozenset({"legal"})}, "human_required", "FLAG_LEGAL"),
    (
        "R5 model flag health",
        {"model_flags": frozenset({"health_safety"})},
        "human_required",
        "FLAG_HEALTH_SAFETY",
    ),
    (
        "R5 model flag abusive",
        {"model_flags": frozenset({"abusive"})},
        "human_required",
        "FLAG_ABUSIVE",
    ),
    (
        "R5 model flag personal data",
        {"model_flags": frozenset({"personal_data"})},
        "human_required",
        "FLAG_PERSONAL_DATA",
    ),
    (
        "R5 keyword flag refund",
        {"keyword_flags": frozenset({"refund"})},
        "human_required",
        "FLAG_REFUND",
    ),
    (
        "R5 keyword flag legal",
        {"keyword_flags": frozenset({"legal"})},
        "human_required",
        "FLAG_LEGAL",
    ),
    ("R6 workspace keyword", {"escalation_keyword": True}, "human_required", "ESCALATION_KEYWORD"),
    (
        "R7 model asks for a person",
        {"model_needs_human": True},
        "human_required",
        "MODEL_REQUESTED_HUMAN",
    ),
    (
        "R7 model cannot answer",
        {"model_can_answer": False},
        "human_required",
        "MODEL_REQUESTED_HUMAN",
    ),
    (
        "R8 needed fact not usable",
        {"required_facts_usable": False},
        "human_required",
        "FACT_NOT_USABLE",
    ),
    (
        "R8 a placeholder could not be rendered",
        {"render_failed": True},
        "human_required",
        "FACT_NOT_USABLE",
    ),
    ("R9 grounding failed", {"grounding_failed": True}, "human_required", "GROUNDING_FAILED"),
    ("R10 llm unavailable", {"llm_error": "LLM_UNAVAILABLE"}, "human_required", "LLM_UNAVAILABLE"),
    (
        "R10 llm budget",
        {"llm_error": "LLM_BUDGET_EXCEEDED"},
        "human_required",
        "LLM_BUDGET_EXCEEDED",
    ),
    (
        "R10 llm output invalid",
        {"llm_error": "LLM_OUTPUT_INVALID"},
        "human_required",
        "LLM_OUTPUT_INVALID",
    ),
    ("R10 llm refused", {"llm_error": "LLM_REFUSED"}, "human_required", "LLM_REFUSED"),
    ("R10 unknown llm error", {"llm_error": "SOMETHING_ELSE"}, "human_required", "LLM_UNAVAILABLE"),
    ("R11 attachment only", {"attachment_only": True}, "human_required", "ATTACHMENT_ONLY"),
    (
        "R12 injection heuristics",
        {"injection_suspected": True},
        "approval_required",
        "INJECTION_SUSPECTED",
    ),
    (
        "R12 model flag",
        {"model_flags": frozenset({"injection_suspected"})},
        "approval_required",
        "INJECTION_SUSPECTED",
    ),
    ("R13 automation off", {"automation_mode": "off"}, "human_required", "AUTOMATION_OFF"),
    (
        "R14 policy approval",
        {"automation_mode": "approval"},
        "approval_required",
        "POLICY_REQUIRES_APPROVAL",
    ),
    (
        "R15 auto but not ready",
        {"automation_mode": "auto", "readiness_level": "ready_for_drafts"},
        "approval_required",
        "READINESS_NOT_READY",
    ),
    (
        "R15 auto and not ready at all",
        {"automation_mode": "auto", "readiness_level": "not_ready"},
        "approval_required",
        "READINESS_NOT_READY",
    ),
    (
        "R16 rate guard",
        {"automation_mode": "auto", "auto_replies_last_hour": 3},
        "approval_required",
        "AUTO_RATE_GUARD",
    ),
    ("R17 unsupported intent", {"intent": "other"}, "human_required", "INTENT_UNSUPPORTED"),
]


@pytest.mark.parametrize(
    ("name", "overrides", "outcome", "reason"), CASES, ids=[c[0] for c in CASES]
)
def test_each_rule_fires_with_its_outcome_and_reason(
    name: str, overrides: dict[str, object], outcome: str, reason: str
) -> None:
    decision = decide(**overrides)
    assert decision.outcome == outcome
    assert reason in decision.reasons


def test_every_documented_rule_is_exercised_above() -> None:
    assert len(RULES) == 17
    exercised = {name.split()[0] for name, *_ in CASES}
    assert exercised == {f"R{n}" for n in range(1, 18)}


def test_the_rate_guard_allows_two_automatic_replies_an_hour() -> None:
    assert decide(automation_mode="auto", auto_replies_last_hour=2).outcome == "auto"
    assert decide(automation_mode="auto", auto_replies_last_hour=3).outcome == "approval_required"


def test_the_window_margin_is_five_minutes() -> None:
    assert decide(window_end=NOW + timedelta(minutes=5, seconds=1)).outcome == "approval_required"
    assert decide(window_end=NOW + timedelta(minutes=5)).outcome == "blocked"


# --- aggregation ---------------------------------------------------------------------------------


def test_the_most_restrictive_outcome_wins_and_only_its_reasons_are_shown() -> None:
    decision = decide(
        window_end=NOW - timedelta(hours=1),  # blocked
        intent="complaint",  # human_required
        injection_suspected=True,  # approval_required
    )
    assert decision == Decision("blocked", ("MESSAGING_WINDOW_CLOSED",))


def test_all_reasons_of_the_winning_outcome_are_kept() -> None:
    decision = decide(
        intent="refund_request",
        keyword_flags=frozenset({"refund", "complaint"}),
        escalation_keyword=True,
    )
    assert decision.outcome == "human_required"
    assert set(decision.reasons) >= {
        "INTENT_REFUND_REQUEST",
        "FLAG_COMPLAINT",
        "FLAG_REFUND",
        "ESCALATION_KEYWORD",
    }
    assert len(decision.reasons) == len(set(decision.reasons))


def test_the_severity_order_is_blocked_human_approval_auto() -> None:
    assert SEVERITY == ("blocked", "human_required", "approval_required", "auto")


# --- adversarial model output (INV-04) -------------------------------------------------


def test_ac_b6_a_complaint_stays_human_even_when_the_model_says_it_is_fine() -> None:
    """The model labels it pricing and claims needs_human=false; the keywords still escalate."""
    decision = decide(
        intent="pricing",
        model_flags=frozenset(),
        model_needs_human=False,
        model_can_answer=True,
        keyword_flags=frozenset({"complaint", "refund"}),
        automation_mode="auto",
    )
    assert decision.outcome == "human_required"
    assert {"FLAG_REFUND", "FLAG_COMPLAINT"} <= set(decision.reasons)


def test_a_model_that_hides_the_intent_cannot_make_an_escalation_automatic() -> None:
    assert (
        decide(
            intent="greeting", keyword_flags=frozenset({"legal"}), automation_mode="auto"
        ).outcome
        == "human_required"
    )


def test_injection_is_never_automatic() -> None:
    decision = decide(automation_mode="auto", injection_suspected=True)
    assert decision == Decision("approval_required", ("INJECTION_SUSPECTED",))


MODEL_FIELDS = {
    "model_flags": [frozenset(), frozenset({"complaint"}), frozenset({"injection_suspected"})],
    "model_needs_human": [False, True],
    "model_can_answer": [True, False],
}


@pytest.mark.parametrize("mode", ["auto", "approval", "off"])
@pytest.mark.parametrize("intent", ["pricing", "hours", "greeting", "faq"])
def test_the_model_can_only_make_a_decision_stricter(mode: str, intent: str) -> None:
    """Whatever the model's flags and signals, the outcome is never less strict than with the
    most permissive proposal for the same code-derived facts."""
    permissive = evaluate_reply(base(intent=intent, automation_mode=mode))
    for flags, needs_human, can_answer in itertools.product(*MODEL_FIELDS.values()):
        varied = evaluate_reply(
            base(
                intent=intent,
                automation_mode=mode,
                model_flags=flags,
                model_needs_human=needs_human,
                model_can_answer=can_answer,
            )
        )
        assert SEVERITY.index(varied.outcome) <= SEVERITY.index(permissive.outcome)


def test_no_model_signal_removes_a_reason_found_by_code() -> None:
    code_found = base(keyword_flags=frozenset({"legal"}), escalation_keyword=True)
    for flags, needs_human, can_answer in itertools.product(*MODEL_FIELDS.values()):
        varied = evaluate_reply(
            replace(
                code_found,
                model_flags=flags,
                model_needs_human=needs_human,
                model_can_answer=can_answer,
            )
        )
        assert {"FLAG_LEGAL", "ESCALATION_KEYWORD"} <= set(varied.reasons)


def test_without_a_model_proposal_there_is_no_intent_unsupported_noise() -> None:
    decision = decide(intent=None, model_responded=False, attachment_only=True)
    assert decision == Decision("human_required", ("ATTACHMENT_ONLY",))
    decision = decide(intent=None, model_responded=False, language_supported=False)
    assert decision == Decision("human_required", ("LANGUAGE_UNSUPPORTED",))


# --- action classes and the effective mode -------------------------------------------------------


@pytest.mark.parametrize(
    ("intent", "action_class"),
    [
        ("pricing", "reply.pricing"),
        ("hours", "reply.hours"),
        ("location_contact", "reply.location_contact"),
        ("services", "reply.services"),
        ("booking", "reply.booking"),
        ("promotions", "reply.promotions"),
        ("faq", "reply.general_faq"),
        ("greeting", "reply.general_faq"),
        ("complaint", None),
        ("refund_request", None),
        ("discount_request", None),
        ("sensitive", None),
        ("other", None),
        (None, None),
    ],
)
def test_intents_map_to_action_classes(intent: str | None, action_class: str | None) -> None:
    assert intent_action_class(intent) == action_class


def test_facts_map_to_action_classes_by_what_they_say() -> None:
    assert fact_action_class("pricing.membership_monthly") == "reply.pricing"
    assert fact_action_class("contact.phone") == "reply.location_contact"
    assert fact_action_class("hours.weekly") == "reply.hours"
    assert fact_action_class("identity.business_name") is None


def test_a_price_question_labelled_faq_still_needs_the_pricing_policy() -> None:
    """The intent is the model's label; the facts the reply quotes are what it says."""
    modes = {"reply.general_faq": "auto", "reply.pricing": "approval"}
    assert effective_mode(modes, "faq", []) == ("auto", "reply.general_faq")
    assert effective_mode(modes, "faq", ["pricing.membership_monthly"]) == (
        "approval",
        "reply.pricing",
    )
    assert effective_mode({**modes, "reply.pricing": "off"}, "faq", ["pricing.x"]) == (
        "off",
        "reply.pricing",
    )
    assert effective_mode(modes, "pricing", []) == ("approval", "reply.pricing")


def test_the_intents_own_class_wins_a_tie() -> None:
    modes = {"reply.hours": "approval", "reply.pricing": "approval"}
    assert effective_mode(modes, "hours", ["pricing.x"]).action_class == "reply.hours"
    assert effective_mode(modes, "faq", ["pricing.x", "hours.weekly"]).action_class == (
        "reply.general_faq"
    )


def test_the_effective_mode_defaults_to_approval() -> None:
    assert effective_mode({}, "pricing", []).mode == DEFAULT_MODE
    assert effective_mode({}, None, []) == (DEFAULT_MODE, None)


@pytest.mark.parametrize(
    ("intent", "keys", "disclosure", "answer", "expected"),
    [
        ("pricing", ["pricing.membership_monthly"], "share", False, True),
        ("pricing", ["hours.weekly"], "share", False, False),
        ("pricing", [], "share", True, True),  # an approved answer carries its own content
        ("pricing", ["pricing.membership_monthly"], "do_not_share", False, False),
        ("pricing", ["policy.price_answer_text"], "do_not_share", False, True),
        ("hours", ["hours.weekly"], "share", False, True),
        ("hours", ["contact.phone"], "share", False, False),
        ("location_contact", ["contact.phone"], "share", False, True),
        ("location_contact", ["location.address"], "share", False, True),
        ("location_contact", ["hours.weekly"], "share", False, False),
        ("services", ["service.fitness"], "share", False, True),
        ("services", [], "share", False, False),
        ("booking", ["booking.instructions"], "share", False, True),
        ("booking", [], "share", False, False),
        ("promotions", ["promotion.trial_session"], "share", False, True),
        ("promotions", ["pricing.membership_monthly"], "share", False, False),
        ("faq", ["faq.parking"], "share", False, True),
        ("faq", [], "share", True, True),
        ("faq", [], "share", False, False),
        ("greeting", [], "share", False, True),
        ("complaint", [], "share", False, True),
        (None, [], "share", False, True),
    ],
)
def test_required_facts(
    intent: str | None, keys: list[str], disclosure: str, answer: bool, expected: bool
) -> None:
    assert (
        required_facts_usable(
            intent, keys, price_disclosure=disclosure, approved_answer_used=answer
        )
        is expected
    )


@pytest.mark.parametrize(
    ("intent", "usable", "unusable", "can_answer", "expected"),
    [
        # the information exists but is not usable, and the model could not answer: that is why
        ("pricing", ["pricing.membership_monthly"], ["pricing.student_monthly"], False, False),
        ("pricing", ["pricing.membership_monthly"], ["pricing.student_monthly"], True, True),
        ("hours", ["hours.weekly"], ["hours.holiday"], False, False),
        # nothing relevant is unusable: the model simply had nothing to say (R7 covers it)
        ("pricing", ["pricing.membership_monthly"], ["hours.weekly"], False, True),
        ("pricing", ["pricing.membership_monthly"], [], False, True),
    ],
)
def test_an_unusable_fact_of_the_asked_kind_is_the_reason_when_the_model_cannot_answer(
    intent: str, usable: list[str], unusable: list[str], can_answer: bool, expected: bool
) -> None:
    assert (
        required_facts_usable(
            intent,
            usable,
            price_disclosure="share",
            approved_answer_used=False,
            model_can_answer=can_answer,
            unusable_keys=unusable,
        )
        is expected
    )


@pytest.mark.parametrize(
    ("mode", "outcome", "primary"),
    [
        ("approval", "approval_required", "POLICY_REQUIRES_APPROVAL"),
        ("off", "human_required", "AUTOMATION_OFF"),
    ],
)
def test_a_stricter_fact_class_adds_a_contains_reason(
    mode: str, outcome: str, primary: str
) -> None:
    decision = decide(intent="faq", automation_mode=mode, automation_mode_class="reply.pricing")
    assert decision == Decision(outcome, (primary, "CONTAINS_PRICING"))


@pytest.mark.parametrize("source", [None, "reply.general_faq"])
def test_no_contains_reason_when_the_intents_own_class_decides(source: str | None) -> None:
    decision = decide(intent="faq", automation_mode="approval", automation_mode_class=source)
    assert decision == Decision("approval_required", ("POLICY_REQUIRES_APPROVAL",))


def test_contains_reason_names_the_class_without_its_prefix() -> None:
    decision = decide(
        intent="faq", automation_mode="approval", automation_mode_class="reply.location_contact"
    )
    assert "CONTAINS_LOCATION_CONTACT" in decision.reasons
