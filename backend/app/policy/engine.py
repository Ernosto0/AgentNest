"""The reply policy engine: every rule is evaluated, the most restrictive outcome wins
(ADR-014). Pure."""

from dataclasses import dataclass

from app.policy.rules_reply import AUTO, RULES, SEVERITY, Finding, ReplyPolicyInput


@dataclass(frozen=True)
class Decision:
    outcome: str  # blocked | human_required | approval_required | auto
    reasons: tuple[str, ...]  # the reasons of the rules that produced that outcome, in rule order


def evaluate_reply(policy_input: ReplyPolicyInput) -> Decision:
    """``blocked`` > ``human_required`` > ``approval_required`` > ``auto``.

    The reasons are those of the winning outcome only (the chips explain *why this level*); a
    decision of ``auto`` carries ``POLICY_AUTO``.
    """
    findings: list[Finding] = []
    for rule in RULES:
        findings.extend(rule(policy_input))
    for outcome in SEVERITY:
        reasons = tuple(dict.fromkeys(f.reason for f in findings if f.outcome == outcome))
        if reasons:
            return Decision(outcome, reasons)
    return Decision(AUTO, ("POLICY_AUTO",))
