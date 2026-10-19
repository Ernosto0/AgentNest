"""The reply rules R1 to R17 (workflows.md §C.1), each a small pure function.

A rule returns ``None`` (does not apply) or a :class:`Finding` (an outcome and its reason).
The engine takes the most restrictive outcome. The model's output enters only through
``model_flags``, ``model_needs_human`` and ``model_can_answer``, and every one of those can
only make a decision stricter (INV-04): a rule never reads a model field to *relax* anything.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.policy.classes import ALWAYS_HUMAN_INTENTS, intent_action_class

BLOCKED = "blocked"
HUMAN = "human_required"
APPROVAL = "approval_required"
AUTO = "auto"
# Most restrictive first.
SEVERITY = (BLOCKED, HUMAN, APPROVAL, AUTO)

WINDOW_MARGIN = timedelta(minutes=5)
AUTO_RATE_LIMIT = 3  # automatic replies per conversation per hour

ESCALATING_INTENTS = ("complaint", "refund_request", "discount_request", "sensitive")
ESCALATING_FLAGS = (
    "complaint",
    "refund",
    "discount",
    "legal",
    "health_safety",
    "abusive",
    "personal_data",
)
LLM_REASONS = {
    "LLM_UNAVAILABLE": "LLM_UNAVAILABLE",
    "LLM_BUDGET_EXCEEDED": "LLM_BUDGET_EXCEEDED",
    "LLM_OUTPUT_INVALID": "LLM_OUTPUT_INVALID",
    "LLM_REFUSED": "LLM_REFUSED",
}


@dataclass(frozen=True)
class Finding:
    outcome: str
    reason: str


@dataclass(frozen=True)
class ReplyPolicyInput:
    now: datetime
    # the connection
    account_status: str | None
    account_can_message: bool
    window_end: datetime | None
    # the conversation
    handling_mode: str
    # the pre-checks (code)
    language_supported: bool
    keyword_flags: frozenset[str]
    escalation_keyword: bool
    injection_suspected: bool
    attachment_only: bool
    # the model's proposal (None when no model ran)
    intent: str | None
    model_flags: frozenset[str] = field(default_factory=frozenset)
    model_responded: bool = False
    model_needs_human: bool = False
    model_can_answer: bool = True
    llm_error: str | None = None
    # the pipeline's checks (code)
    required_facts_usable: bool = True
    render_failed: bool = False
    grounding_failed: bool = False
    # the workspace
    automation_mode: str = "approval"
    readiness_level: str = "not_ready"
    auto_replies_last_hour: int = 0


Rule = Callable[[ReplyPolicyInput], list[Finding]]


def _one(finding: Finding | None) -> list[Finding]:
    return [finding] if finding else []


def r1_account(i: ReplyPolicyInput) -> list[Finding]:
    if i.account_status != "connected":
        return [Finding(BLOCKED, "ACCOUNT_NOT_CONNECTED")]
    if not i.account_can_message:
        return [Finding(BLOCKED, "CAPABILITY_MISSING")]
    return []


def r2_window(i: ReplyPolicyInput) -> list[Finding]:
    if i.window_end is None or i.now >= i.window_end - WINDOW_MARGIN:
        return [Finding(BLOCKED, "MESSAGING_WINDOW_CLOSED")]
    return []


def r3_takeover(i: ReplyPolicyInput) -> list[Finding]:
    return _one(Finding(HUMAN, "HUMAN_TAKEOVER") if i.handling_mode == "human" else None)


def r4_language(i: ReplyPolicyInput) -> list[Finding]:
    return _one(None if i.language_supported else Finding(HUMAN, "LANGUAGE_UNSUPPORTED"))


def r5_sensitive(i: ReplyPolicyInput) -> list[Finding]:
    """The union of the model's flags and the keyword flags: no model output removes a reason."""
    findings: list[Finding] = []
    if i.intent in ESCALATING_INTENTS:
        findings.append(Finding(HUMAN, f"INTENT_{i.intent.upper()}"))
    flags = (i.model_flags | i.keyword_flags) & set(ESCALATING_FLAGS)
    findings += [
        Finding(HUMAN, f"FLAG_{flag.upper()}") for flag in ESCALATING_FLAGS if flag in flags
    ]
    return findings


def r6_keyword(i: ReplyPolicyInput) -> list[Finding]:
    return _one(Finding(HUMAN, "ESCALATION_KEYWORD") if i.escalation_keyword else None)


def r7_model(i: ReplyPolicyInput) -> list[Finding]:
    if i.model_responded and (i.model_needs_human or not i.model_can_answer):
        return [Finding(HUMAN, "MODEL_REQUESTED_HUMAN")]
    return []


def r8_facts(i: ReplyPolicyInput) -> list[Finding]:
    if not i.required_facts_usable or i.render_failed:
        return [Finding(HUMAN, "FACT_NOT_USABLE")]
    return []


def r9_grounding(i: ReplyPolicyInput) -> list[Finding]:
    return _one(Finding(HUMAN, "GROUNDING_FAILED") if i.grounding_failed else None)


def r10_llm(i: ReplyPolicyInput) -> list[Finding]:
    if i.llm_error is None:
        return []
    return [Finding(HUMAN, LLM_REASONS.get(i.llm_error, "LLM_UNAVAILABLE"))]


def r11_attachment(i: ReplyPolicyInput) -> list[Finding]:
    return _one(Finding(HUMAN, "ATTACHMENT_ONLY") if i.attachment_only else None)


def r12_injection(i: ReplyPolicyInput) -> list[Finding]:
    if i.injection_suspected or "injection_suspected" in i.model_flags:
        return [Finding(APPROVAL, "INJECTION_SUSPECTED")]
    return []


def _has_class(i: ReplyPolicyInput) -> bool:
    return intent_action_class(i.intent) is not None


def r13_automation_off(i: ReplyPolicyInput) -> list[Finding]:
    return _one(
        Finding(HUMAN, "AUTOMATION_OFF") if _has_class(i) and i.automation_mode == "off" else None
    )


def r14_policy_approval(i: ReplyPolicyInput) -> list[Finding]:
    if _has_class(i) and i.automation_mode == "approval":
        return [Finding(APPROVAL, "POLICY_REQUIRES_APPROVAL")]
    return []


def r15_readiness(i: ReplyPolicyInput) -> list[Finding]:
    if _has_class(i) and i.automation_mode == "auto" and i.readiness_level != "ready":
        return [Finding(APPROVAL, "READINESS_NOT_READY")]
    return []


def r16_rate_guard(i: ReplyPolicyInput) -> list[Finding]:
    if (
        _has_class(i)
        and i.automation_mode == "auto"
        and i.auto_replies_last_hour >= AUTO_RATE_LIMIT
    ):
        return [Finding(APPROVAL, "AUTO_RATE_GUARD")]
    return []


def r17_unsupported_intent(i: ReplyPolicyInput) -> list[Finding]:
    """An intent with no action class that is not one of the always-human ones (``other``, or no
    intent at all because no model ran and nothing else already explains it)."""
    if _has_class(i) or i.intent in ALWAYS_HUMAN_INTENTS:
        return []
    if i.intent is None and not i.model_responded:
        return []  # the pre-checks (R4, R10, R11) already say why there was no proposal
    return [Finding(HUMAN, "INTENT_UNSUPPORTED")]


RULES: tuple[Rule, ...] = (
    r1_account,
    r2_window,
    r3_takeover,
    r4_language,
    r5_sensitive,
    r6_keyword,
    r7_model,
    r8_facts,
    r9_grounding,
    r10_llm,
    r11_attachment,
    r12_injection,
    r13_automation_off,
    r14_policy_approval,
    r15_readiness,
    r16_rate_guard,
    r17_unsupported_intent,
)
