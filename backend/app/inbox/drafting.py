"""The drafting pipeline (workflows.md §C step 3, parts 2 to 6): from a gathered context to a
:class:`DraftPlan`, with no database writes of its own.

    pre-checks (language, injection, escalation keywords, attachment-only)
      -> the model PROPOSES a reply template (outside any transaction)
      -> code renders the placeholders from usable facts
      -> the claim validator checks everything that is not a placeholder
      -> one regeneration with the validator's feedback, then a human (INV-02)

The plan carries facts, not decisions: the policy engine turns it into a decision
(``inbox.reply_workflow``). Nothing the model says can lower what code has found: the flags of
the model and of the keyword scan are kept apart so that policy can take their union.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.ai.injection import detect_injection
from app.ai.runner import RunnerDeps, TaskOutcome, run_task
from app.ai.schemas import (
    DraftApprovedAnswer,
    DraftFact,
    DraftMessage,
    DraftReplyInput,
    ReplyProposal,
)
from app.ai.tasks.draft_reply import DRAFT_REPLY
from app.inbox.context import DraftContext, model_facts
from app.inbox.escalation import keyword_flags, matches_escalation_keywords
from app.knowledge.approved_answers import AnswerView
from app.knowledge.claims import ClaimIssue, ClaimReport, length_issue, validate_claims
from app.knowledge.render import RenderResult, render
from app.knowledge.service import UsableFact

MAX_REPLY_BYTES = 1000  # Instagram's text limit for a direct message
LLM_ERRORS = ("LLM_BUDGET_EXCEEDED", "LLM_OUTPUT_INVALID", "LLM_REFUSED", "LLM_UNAVAILABLE")
MARK_OPEN, MARK_CLOSE = "⟦", "⟧"


@dataclass(frozen=True)
class DraftPlan:
    language: str | None  # the reply language; None when unsupported
    detected_language: str | None
    intent: str | None
    model_flags: tuple[str, ...]
    keyword_flags: tuple[str, ...]
    injection: bool
    escalation_keyword: bool
    can_answer: bool
    model_needs_human: bool
    attachment_only: bool
    language_unsupported: bool
    llm_error: str | None
    source: str  # ai | approved_answer
    approved_answer_id: uuid.UUID | None
    template: str | None
    text: str | None  # rendered and validated; sendable only if validation passed
    suggestion_text: str | None  # a failed text with its issues marked: never sendable
    validation: dict[str, Any]  # {passed, issues, rendered}
    used_facts: tuple[tuple[uuid.UUID, int], ...]
    render_failed: bool  # a placeholder named a fact that is not usable
    grounding_failed: bool  # the claim validator refused the text, twice
    agent_run_ids: tuple[uuid.UUID, ...] = field(default=())
    usable_keys: frozenset[str] = field(default_factory=frozenset)

    @property
    def has_sendable_text(self) -> bool:
        return self.text is not None and bool(self.validation.get("passed"))


def mark_issues(text: str, issues: tuple[ClaimIssue, ...]) -> str:
    """The text with each issue's span wrapped in ⟦ ⟧ (overlaps merged), for the owner to see."""
    spans = sorted((i.start, i.end) for i in issues if 0 <= i.start < i.end <= len(text))
    merged: list[list[int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    out, cursor = [], 0
    for start, end in merged:
        out += [text[cursor:start], MARK_OPEN, text[start:end], MARK_CLOSE]
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


def disclosure_suffix(context: DraftContext) -> str:
    """The notice appended by code (never by the model) to automatic replies."""
    return f"\n\n{context.disclosure.text}" if context.disclosure.enabled else ""


def _label(fact: UsableFact, language: str) -> str:
    return fact.label.get(language) or fact.label.get("tr") or fact.label.get("en") or fact.key


def _task_input(
    context: DraftContext, facts: list[UsableFact], language: str, feedback: list[str]
) -> DraftReplyInput:
    return DraftReplyInput(
        reply_language=language,
        facts=[
            DraftFact(
                key=f.key,
                label=_label(f, language),
                value_type=f.value_type,
                value_display=f.display,
                placeholder=f.placeholder,
            )
            for f in facts
        ],
        price_disclosure="share" if context.price_disclosure == "share" else "do_not_share",
        approved_answers=[
            DraftApprovedAnswer(
                id=str(a.id),
                intent=a.intent,
                example_questions=list(a.example_questions),
                answer_template=a.answer_template,
                status=a.status,
            )
            for a in context.approved_answers
        ],
        brand_voice=context.brand_voice,
        conversation=[
            DraftMessage(role="customer" if role == "customer" else "business", text=text)
            for role, text in context.history
        ],
        validator_feedback=feedback,
    )


@dataclass
class _Checked:
    rendered: RenderResult
    report: ClaimReport | None
    issues: list[ClaimIssue]

    @property
    def passed(self) -> bool:
        return self.rendered.ok and not self.issues


def _check(template: str, facts: list[UsableFact], language: str, suffix: str) -> _Checked:
    rendered = render(template, facts, language)
    if not rendered.ok:
        return _Checked(rendered, None, [])
    report = validate_claims(rendered.text, rendered, language)
    issues = list(report.issues)
    too_long = length_issue(rendered.text + suffix, max_bytes=MAX_REPLY_BYTES)
    if too_long is not None:
        issues.append(too_long)
    return _Checked(rendered, report, issues)


def _feedback(checked: _Checked) -> list[str]:
    lines: list[str] = []
    for error in checked.rendered.errors:
        lines.append(f"{error.code}: {error.key or ''} is not one of the provided facts")
    for issue in checked.issues:
        if issue.code == "TOO_LONG":
            lines.append(f"TOO_LONG: the reply must be shorter than {MAX_REPLY_BYTES} bytes")
        else:
            lines.append(
                f"{issue.code}: '{issue.text}' is a value that must come from a placeholder"
            )
    return lines


def _validation(checked: _Checked | None, passed: bool) -> dict[str, Any]:
    if checked is None:
        return {"passed": passed, "issues": [], "rendered": []}
    return {
        "passed": passed,
        "issues": [i.to_dict() for i in checked.issues]
        + [{"code": e.code, "span": None, "text": e.key or ""} for e in checked.rendered.errors],
        "rendered": [
            {
                "key": s.key,
                "fact_id": str(s.fact_id),
                "version": s.version,
                "span": [s.start, s.end],
                "display": s.display,
            }
            for s in checked.rendered.spans
        ],
    }


# One model call: the task input in, the runner's outcome out. The job passes the real runner;
# the eval harness passes a database-free one, so both exercise exactly this pipeline.
ModelCall = Callable[[DraftReplyInput], TaskOutcome[ReplyProposal]]


def make_plan(
    deps: RunnerDeps,
    context: DraftContext,
    correlation_id: uuid.UUID | None,
    job_id: uuid.UUID | None = None,
) -> DraftPlan:
    """Run the pipeline. Raises ``RetryableError`` (from the runner) for transient LLM errors so
    that the job retries; every other failure is recorded in the plan."""
    return plan_with(
        context,
        lambda task_input: run_task(
            deps, context.ctx, DRAFT_REPLY, task_input, correlation_id, job_id=job_id
        ),
    )


def plan_with(context: DraftContext, call: ModelCall) -> DraftPlan:
    """The pipeline around an injectable model call."""
    text = context.customer_text
    flags = tuple(sorted(keyword_flags(text)))
    base: dict[str, Any] = {
        "language": context.language.code,
        "detected_language": context.language.detected,
        "keyword_flags": flags,
        "injection": bool(detect_injection(text)),
        "escalation_keyword": matches_escalation_keywords(text, context.escalation_keywords),
        "usable_keys": context.usable_keys,
    }
    empty: dict[str, Any] = {
        "intent": None,
        "model_flags": (),
        "can_answer": False,
        "model_needs_human": False,
        "attachment_only": False,
        "language_unsupported": False,
        "llm_error": None,
        "source": "ai",
        "approved_answer_id": None,
        "template": None,
        "text": None,
        "suggestion_text": None,
        "validation": _validation(None, False),
        "used_facts": (),
        "render_failed": False,
        "grounding_failed": False,
    }
    if context.attachment_only:  # nothing to read: a person looks at the picture
        return DraftPlan(**base, **{**empty, "attachment_only": True})
    language = context.language.code
    if language is None:
        return DraftPlan(**base, **{**empty, "language_unsupported": True})

    facts = model_facts(context)
    suffix = disclosure_suffix(context)
    run_ids: list[uuid.UUID] = []
    feedback: list[str] = []
    for attempt in range(2):
        outcome = call(_task_input(context, facts, language, feedback))
        run_ids.append(outcome.agent_run_id)
        if not outcome.ok or outcome.output is None:
            code = outcome.error_code if outcome.error_code in LLM_ERRORS else "LLM_UNAVAILABLE"
            return DraftPlan(**base, **{**empty, "llm_error": code}, agent_run_ids=tuple(run_ids))
        proposal = outcome.output
        answer = _chosen_answer(context, proposal)
        template = answer.answer_template if answer else proposal.reply_template
        common = {
            "intent": proposal.intent,
            "model_flags": tuple(sorted(proposal.flags)),
            "can_answer": proposal.can_answer,
            "model_needs_human": proposal.needs_human,
            "source": "approved_answer" if answer else "ai",
            "approved_answer_id": answer.id if answer else None,
            "template": template,
        }
        if not template or not proposal.can_answer:
            return DraftPlan(
                **base,
                **{**empty, **common, "template": None},
                agent_run_ids=tuple(run_ids),
            )
        checked = _check(template, facts, language, suffix)
        if checked.passed:
            return DraftPlan(
                **base,
                **{
                    **empty,
                    **common,
                    "text": checked.rendered.text,
                    "validation": _validation(checked, True),
                    "used_facts": checked.rendered.used,
                },
                agent_run_ids=tuple(run_ids),
            )
        if attempt == 0 and answer is None:  # the owner's own wording is never regenerated
            feedback = _feedback(checked)
            continue
        render_failed = not checked.rendered.ok
        return DraftPlan(
            **base,
            **{
                **empty,
                **common,
                "validation": _validation(checked, False),
                "suggestion_text": None
                if render_failed
                else mark_issues(checked.rendered.text, tuple(checked.issues)),
                "render_failed": render_failed,
                "grounding_failed": not render_failed,
            },
            agent_run_ids=tuple(run_ids),
        )
    raise AssertionError("unreachable: the loop returns on its second pass")  # pragma: no cover


def _chosen_answer(context: DraftContext, proposal: ReplyProposal) -> AnswerView | None:
    if proposal.approved_answer_id is None:
        return None
    return next(
        (a for a in context.approved_answers if str(a.id) == proposal.approved_answer_id), None
    )


def failed_plan(context: DraftContext, error_code: str) -> DraftPlan:
    """The plan for a draft job that could not get a proposal at all (retries exhausted): a
    person answers (rule R10)."""
    return DraftPlan(
        language=context.language.code,
        detected_language=context.language.detected,
        intent=None,
        model_flags=(),
        keyword_flags=tuple(sorted(keyword_flags(context.customer_text))),
        injection=bool(detect_injection(context.customer_text)),
        escalation_keyword=matches_escalation_keywords(
            context.customer_text, context.escalation_keywords
        ),
        can_answer=False,
        model_needs_human=False,
        attachment_only=False,
        language_unsupported=False,
        llm_error=error_code,
        source="ai",
        approved_answer_id=None,
        template=None,
        text=None,
        suggestion_text=None,
        validation=_validation(None, False),
        used_facts=(),
        render_failed=False,
        grounding_failed=False,
        usable_keys=context.usable_keys,
    )
