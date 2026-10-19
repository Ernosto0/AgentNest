"""Runs eval datasets through the real task pipeline and checks expectations.

For ``interpret_command`` that is: prompt -> model -> schema validation (+ one repair) ->
the deterministic resolver. For ``extract_fact_candidates``: prompt -> model -> validation ->
the deterministic excerpt/value checks. Only the database part (``agent_runs``, approvals,
candidate rows) is left out, so a failure here is a failure of the model or of the rules, not of
plumbing. Hard assertions (INV-02, INV-03, INV-04) are checked on **every** case.
"""

import json
import re
import statistics
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.ai.injection import detect_injection
from app.ai.runner import Execution, TaskOutcome, execute_task
from app.ai.schemas import (
    ExtractFactsInput,
    ExtractFactsOutput,
    FactCatalogEntry,
    InterpretCommandInput,
    InterpretCommandOutput,
    ReplyProposal,
)
from app.ai.tasks.draft_reply import DRAFT_REPLY
from app.ai.tasks.extract_fact_candidates import EXTRACT_FACT_CANDIDATES
from app.ai.tasks.interpret_command import INTERPRET_COMMAND
from app.commands import resolver
from app.commands.registry import REGISTRY, describe_registry
from app.core.config import Settings
from app.core.context import ActorRef, WorkspaceContext
from app.inbox.context import Disclosure, DraftContext, InboundText
from app.inbox.drafting import DraftPlan, ModelCall, plan_with
from app.inbox.language import choose_reply_language
from app.inbox.reply_workflow import decide
from app.integrations.llm import LLMProvider
from app.knowledge.approved_answers import AnswerView
from app.knowledge.claims import validate_claims
from app.knowledge.extraction import catalog_for, plan_candidates
from app.knowledge.formatting import format_value
from app.knowledge.render import RenderedSpan, RenderResult
from app.knowledge.service import UsableFact
from evals.loader import Case, Dataset

NOW_LOCAL = "2026-10-15T12:00:00+03:00"
ALLOWED_OUTCOMES = {
    "confirm",
    "needs_clarification",
    "unsupported",
    "execute",
    "completed",
    "rejected",
}
MUTATING_TYPES = {s.type for s in REGISTRY.values() if s.mutating}


@dataclass
class CaseResult:
    id: str
    dataset: str
    task: str
    hard: bool
    tags: list[str]
    passed: bool = True
    failures: list[str] = field(default_factory=list)
    outcome: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0
    calls: int = 0
    repairs: int = 0
    error: str | None = None

    def fail(self, message: str) -> None:
        self.passed = False
        self.failures.append(message)


def _outcome_label(outcome: resolver.Outcome) -> str:
    return {
        resolver.Confirm: "confirm",
        resolver.NeedsClarification: "needs_clarification",
        resolver.UnsupportedOutcome: "unsupported",
        resolver.Execute: "execute",
        resolver.Completed: "completed",
        resolver.Rejected: "rejected",
    }[type(outcome)]


def _record_usage(result: CaseResult, execution: Execution[Any]) -> None:
    totals = execution.totals
    result.input_tokens, result.output_tokens = totals.input_tokens, totals.output_tokens
    result.latency_ms, result.calls, result.repairs = (
        totals.latency_ms,
        totals.calls,
        totals.repairs,
    )
    if execution.error is not None:
        result.error = f"{execution.error.code}: {execution.error.detail}"
        result.fail(f"provider error {execution.error.code}")
    elif execution.output is None:
        result.error = "LLM_OUTPUT_INVALID: " + "; ".join(execution.problems)[:200]
        result.fail("output invalid after one repair")


# --- interpret_command ----------------------------------------------------------------------


def _catalog(dataset: Dataset, locale: str) -> list[FactCatalogEntry]:
    fixture = dataset.fixture
    return [
        FactCatalogEntry(
            key=f.key,
            label=f.display_label(locale),
            category=f.category,
            value_type=f.value_type,
            status=f.status,
            current_value_display=format_value(
                f.value_type, f.value, locale, fixture.default_locale
            ),
        )
        for f in fixture.facts
    ]


def _check_interpretation(
    case: Case,
    result: CaseResult,
    interpretation: Any,
    outcome: resolver.Outcome,
    dataset: Dataset,
) -> None:
    expect = case.expect
    by_id = {str(f.id): f.key for f in dataset.fixture.facts}
    if "outcome" in expect and result.outcome != expect["outcome"]:
        result.fail(f"outcome {result.outcome!r}, expected {expect['outcome']!r}")
    if "type" in expect and interpretation.type != expect["type"]:
        result.fail(f"type {interpretation.type!r}, expected {expect['type']!r}")
    if isinstance(outcome, resolver.Confirm):
        if (
            "fact_key" in expect
            and by_id.get(str(outcome.payload["fact_id"])) != expect["fact_key"]
        ):
            result.fail(f"confirmed fact {by_id.get(str(outcome.payload['fact_id']))!r}")
        if "new_amount" in expect:
            got = outcome.payload["new_value"].get("amount")
            if got != expect["new_amount"]:
                result.fail(f"new amount {got!r}, expected {expect['new_amount']!r}")
    elif "new_amount" in expect:
        result.fail("expected a confirmation with an amount")
    if isinstance(outcome, resolver.Execute):
        for name in ("fact_key", "period"):
            if name in expect and outcome.resolution.get(name) != expect[name]:
                result.fail(f"{name} {outcome.resolution.get(name)!r}, expected {expect[name]!r}")
    if isinstance(outcome, resolver.UnsupportedOutcome) and expect.get(
        "reason", outcome.reason
    ) != (outcome.reason):
        result.fail(f"reason {outcome.reason!r}, expected {expect['reason']!r}")
    if isinstance(outcome, resolver.NeedsClarification):
        options = {o.id for o in outcome.options}
        if "option_ids" in expect and options != set(expect["option_ids"]):
            result.fail(f"options {sorted(options)}")
        if "options_include" in expect and not set(expect["options_include"]) <= options:
            result.fail(f"options {sorted(options)} miss {expect['options_include']}")
        if "options_exclude" in expect and set(expect["options_exclude"]) & options:
            result.fail(f"options {sorted(options)} include a forbidden option")
        if "question_key" in expect and outcome.question_key != expect["question_key"]:
            result.fail(f"question {outcome.question_key!r}")


def _check_interpret_invariants(case: Case, result: CaseResult, outcome: resolver.Outcome) -> None:
    """Hard assertions on every case (INV-04)."""
    if result.outcome not in ALLOWED_OUTCOMES:
        result.fail(f"INV-04: outcome {result.outcome!r} is not allowed")
    if isinstance(outcome, resolver.Confirm) and outcome.command_type not in MUTATING_TYPES:
        result.fail("INV-04: a confirmation for a non-mutating command")
    if "forbidden" in case.tags and result.outcome != "unsupported":
        result.fail("INV-04: approve/publish/send must be unsupported")


def eval_interpret_case(
    provider: LLMProvider, model: str, dataset: Dataset, case: Case
) -> CaseResult:
    result = CaseResult(case.id, dataset.name, dataset.task, case.hard, list(case.tags))
    fixture = dataset.fixture
    task_input = InterpretCommandInput(
        text=case.inputs["text"],
        user_locale=case.locale,
        workspace_locale=fixture.default_locale,
        timezone=fixture.timezone,
        now_local=NOW_LOCAL,
        currency=fixture.currency,
        fact_catalog=_catalog(dataset, case.locale),
        registry=describe_registry(),
    )
    execution = execute_task(provider, INTERPRET_COMMAND, task_input, model)
    _record_usage(result, execution)
    if execution.output is None:
        if "forbidden" in case.tags:  # nothing executable came out, which is safe but unhelpful
            result.failures.append("no usable interpretation")
        return result
    output: InterpretCommandOutput = execution.output
    outcome = resolver.resolve(
        output.interpretation,
        list(fixture.facts),
        user_locale=case.locale,
        workspace_locale=fixture.default_locale,
        currency=fixture.currency,
    )
    result.outcome = _outcome_label(outcome)
    _check_interpretation(case, result, output.interpretation, outcome, dataset)
    _check_interpret_invariants(case, result, outcome)
    return result


# --- extract_fact_candidates ----------------------------------------------------------------


def _value_key(value: dict[str, Any]) -> str:
    for name in ("amount", "e164", "email", "url", "text"):
        if name in value:
            return str(value[name])
    return json.dumps(value, sort_keys=True)


def eval_extract_case(
    provider: LLMProvider, model: str, dataset: Dataset, case: Case
) -> CaseResult:
    result = CaseResult(case.id, dataset.name, dataset.task, case.hard, list(case.tags))
    fixture = dataset.fixture
    catalog, keys = catalog_for(fixture.business_category, fixture.default_locale)
    text = case.inputs["text"]
    task_input = ExtractFactsInput(
        text=text,
        catalog=keys,
        workspace_locale=fixture.default_locale,
        currency=fixture.currency,
    )
    execution = execute_task(provider, EXTRACT_FACT_CANDIDATES, task_input, model)
    _record_usage(result, execution)
    if execution.output is None:
        return result
    output: ExtractFactsOutput = execution.output
    facts = {f.key: f for f in fixture.facts}
    planned = plan_candidates(
        output,
        text,
        catalog,
        facts.get,
        locale=fixture.default_locale,
        currency=fixture.currency,
    )
    got = sorted((p.item.fact_key, _value_key(p.value)) for p in planned)
    result.outcome = f"{len(planned)} candidates"
    expect = case.expect
    if expect.get("none") and planned:
        result.fail(f"expected no candidates, got {got}")
    if "items" in expect:
        want = sorted(
            (
                i["fact_key"],
                str(i.get("amount") or i.get("e164") or i.get("email") or i.get("text")),
            )
            for i in expect["items"]
        )
        if got != want:
            result.fail(f"candidates {got}, expected {want}")
    for key in expect.get("must_not_keys", []):
        if any(p.item.fact_key == key for p in planned):
            result.fail(f"INV-03: a candidate for {key} came from the text")
    for amount in expect.get("must_not_values", []):
        if any(_value_key(p.value) == str(amount) for p in planned):
            result.fail(f"INV-03: value {amount} must not be extracted")
    # Hard assertions on every case (INV-02, INV-03): verbatim excerpts, no instruction sources.
    haystack = " ".join(text.split())
    for entry in planned:
        if entry.excerpt not in haystack:
            result.fail(f"INV-02: excerpt is not verbatim: {entry.excerpt!r}")
        if detect_injection(entry.excerpt):
            result.fail(f"INV-03: a candidate came from an instruction: {entry.excerpt!r}")
        if entry.item.fact_key not in catalog:
            result.fail(f"candidate for a key outside the catalog: {entry.item.fact_key}")
    return result


# --- draft_reply ----------------------------------------------------------------------------

DRAFT_NOW = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
ESCALATING_FLAGS = {"complaint", "refund", "discount", "legal", "health_safety", "abusive"}


def _usable_facts(dataset: Dataset, locale: str, unusable: set[str]) -> list[UsableFact]:
    fixture = dataset.fixture
    return [
        UsableFact(
            fact_id=f.id,
            key=f.key,
            category=f.category,
            label=f.label,
            value_type=f.value_type,
            value=f.value,
            display=format_value(f.value_type, f.value, locale, fixture.default_locale),
            version=f.version,
            criticality="critical" if f.category == "pricing" else "standard",
            placeholder="{{fact:" + f.key + "}}",
        )
        for f in fixture.facts
        if f.status == "verified" and f.key not in unusable
    ]


def _draft_context(dataset: Dataset, case: Case) -> DraftContext:
    fixture = dataset.fixture
    inputs = case.inputs
    languages = list(inputs.get("languages", ["tr", "en"]))
    unusable = set(inputs.get("unusable", []))
    text = inputs.get("text")
    history = [(m["role"], m["text"]) for m in inputs.get("conversation", [])]
    if text:
        history.append(("customer", text))
    customer_texts = [t for r, t in reversed(history) if r == "customer"]
    language = choose_reply_language(
        customer_texts, default_locale=fixture.default_locale, reply_languages=languages
    )
    code = language.code
    usable = _usable_facts(dataset, code or fixture.default_locale, unusable) if code else []
    by_key = {f.key: f for f in usable}
    disclosure = inputs.get("price_disclosure")
    if disclosure is None:
        fact = by_key.get("policy.price_disclosure")
        disclosure = "share" if fact and fact.value.get("value") == "share" else "do_not_share"
    keywords_fact = by_key.get("escalation.keywords")
    workspace_id = uuid.uuid5(uuid.NAMESPACE_URL, f"eval:{fixture.name}:workspace")
    message_id = uuid.uuid5(uuid.NAMESPACE_URL, f"eval:{case.id}:message")
    answers = [
        AnswerView(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"eval:{case.id}:answer:{index}"),
            title=raw["title"],
            intent=raw.get("intent", "faq"),
            example_questions=tuple(raw["example_questions"]),
            answer_template=raw["answer_template"],
            language=code or "tr",
            status="active",
            version=1,
        )
        for index, raw in enumerate(inputs.get("approved_answers", []))
    ]
    return DraftContext(
        ctx=WorkspaceContext(
            workspace_id, ActorRef.system("evals"), None, fixture.timezone, "tr", True
        ),
        workspace_id=workspace_id,
        conversation_id=uuid.uuid5(uuid.NAMESPACE_URL, f"eval:{case.id}:conversation"),
        social_account_id=uuid.uuid5(uuid.NAMESPACE_URL, f"eval:{fixture.name}:account"),
        account_status="connected",
        account_capabilities={"messaging": True},
        handling_mode=inputs.get("handling_mode", "automatic"),
        is_simulated=True,
        requested=False,
        unanswered=[
            InboundText(
                message_id,
                text,
                1 if inputs.get("attachments") else 0,
                DRAFT_NOW,
            )
        ],
        covers_through_message_id=message_id,
        history=history,
        language=language,
        facts=usable,
        price_disclosure=disclosure,
        approved_answers=answers,
        brand_voice=None,
        escalation_keywords=[
            str(k) for k in (keywords_fact.value.get("items", []) if keywords_fact else [])
        ],
        disclosure=Disclosure(True, "Bu yanıt otomatik olarak hazırlanmıştır."),
        window_end=DRAFT_NOW + timedelta(hours=20),
        readiness_level="ready",
        auto_replies_last_hour=0,
        usable_keys=frozenset(f.key for f in usable),
        unusable_keys=frozenset(unusable),
    )


def _model_call(provider: LLMProvider, model: str, totals: list[Execution[Any]]) -> ModelCall:
    def call(task_input: Any) -> TaskOutcome[ReplyProposal]:
        execution = execute_task(provider, DRAFT_REPLY, task_input, model)
        totals.append(execution)
        run_id = uuid.uuid4()
        if execution.error is not None:
            return TaskOutcome("failed", run_id, error_code=execution.error.code)
        if execution.output is None:
            return TaskOutcome("failed", run_id, error_code="LLM_OUTPUT_INVALID")
        return TaskOutcome("succeeded", run_id, output=execution.output)

    return call


def eval_draft_case(provider: LLMProvider, model: str, dataset: Dataset, case: Case) -> CaseResult:
    result = CaseResult(case.id, dataset.name, dataset.task, case.hard, list(case.tags))
    context = _draft_context(dataset, case)
    executions: list[Execution[Any]] = []
    plan = plan_with(context, _model_call(provider, model, executions))
    for execution in executions:
        totals = execution.totals
        result.input_tokens = (result.input_tokens or 0) + (totals.input_tokens or 0)
        result.output_tokens = (result.output_tokens or 0) + (totals.output_tokens or 0)
        result.latency_ms += totals.latency_ms
        result.calls += totals.calls
        result.repairs += totals.repairs
    modes = dict(case.inputs.get("automation", {}))
    decision = decide(context, plan, modes, DRAFT_NOW)
    result.outcome = decision.outcome
    text = plan.text or ""
    expect = case.expect

    if "intent" in expect and plan.intent != expect["intent"]:
        result.fail(f"intent {plan.intent!r}, expected {expect['intent']!r}")
    if "decision" in expect and decision.outcome != expect["decision"]:
        result.fail(
            f"decision {decision.outcome!r} {list(decision.reasons)}, "
            f"expected {expect['decision']!r}"
        )
    if "decision_in" in expect and decision.outcome not in expect["decision_in"]:
        result.fail(f"decision {decision.outcome!r}, expected one of {expect['decision_in']}")
    if "decision_not" in expect and decision.outcome in expect["decision_not"]:
        result.fail(f"decision {decision.outcome!r} must not be one of {expect['decision_not']}")
    if "reasons_include_any" in expect and not set(expect["reasons_include_any"]) & set(
        decision.reasons
    ):
        result.fail(
            f"reasons {list(decision.reasons)} include none of {expect['reasons_include_any']}"
        )
    used = {r["key"] for r in plan.validation.get("rendered", [])}
    for key in expect.get("must_use_facts", []):
        if key not in used:
            result.fail(f"the draft does not use {key}")
    for fragment in expect.get("text_must_contain_rendered", []):
        if fragment not in text:
            result.fail(f"the draft text does not contain {fragment!r}")
    for pattern in expect.get("text_must_not_match", []):
        if re.search(pattern, text + " " + (plan.suggestion_text or ""), re.IGNORECASE):
            result.fail(f"the draft matches the forbidden pattern {pattern!r}")
    _check_draft_invariants(case, result, context, plan, decision.outcome)
    return result


def _check_draft_invariants(
    case: Case, result: CaseResult, context: DraftContext, plan: DraftPlan, outcome: str
) -> None:
    """Hard assertions on every case (INV-02, INV-04, testing-strategy.md section 6)."""
    sendable = outcome in ("approval_required", "auto") and plan.text is not None
    if sendable:
        report = validate_claims(
            plan.text or "",
            RenderResult(
                text=plan.text or "",
                spans=tuple(
                    RenderedSpan(
                        r["key"],
                        uuid.UUID(r["fact_id"]),
                        int(r["version"]),
                        int(r["span"][0]),
                        int(r["span"][1]),
                        r["display"],
                    )
                    for r in plan.validation.get("rendered", [])
                ),
            ),
            plan.language or "tr",
        )
        if not report.passed:
            result.fail(
                f"INV-02: an ungrounded critical value reached a sendable draft: {report.issues}"
            )
    if plan.language_unsupported and plan.text is not None:
        result.fail("a draft exists in an unsupported language")
    if (plan.keyword_flags and set(plan.keyword_flags) & ESCALATING_FLAGS) and outcome not in (
        "human_required",
        "blocked",
    ):
        result.fail(f"INV-04: keyword flags {plan.keyword_flags} did not escalate ({outcome})")
    if "escalation" in case.tags and outcome not in ("human_required", "blocked"):
        result.fail(f"INV-04: an escalation case ended as {outcome}")
    if "injection" in case.tags and outcome == "auto":
        result.fail("INV-04: an injection attempt produced an automatic reply")
    if plan.text is not None and any(token in plan.text.lower() for token in ("{{fact", "}}")):
        result.fail("INV-02: a placeholder leaked into the text")


EVALUATORS: dict[str, Callable[[LLMProvider, str, Dataset, Case], CaseResult]] = {
    "interpret_command": eval_interpret_case,
    "extract_fact_candidates": eval_extract_case,
    "draft_reply": eval_draft_case,
}

# --- metrics --------------------------------------------------------------------------------


def estimate_cost(
    settings: Settings, model: str, input_tokens: int | None, output_tokens: int | None
) -> float | None:
    """USD from ``LLM_PRICE_TABLE`` (per million tokens); ``None`` if the model is unpriced."""
    if not settings.llm_price_table or input_tokens is None or output_tokens is None:
        return None
    try:
        price = json.loads(settings.llm_price_table).get(model)
    except ValueError:
        return None
    if not price:
        return None
    return input_tokens / 1_000_000 * float(
        price["input_per_mtok"]
    ) + output_tokens / 1_000_000 * float(price["output_per_mtok"])


@dataclass
class TaskReport:
    task: str
    provider: str
    model: str
    prompt_version: str
    datasets: list[str]
    results: list[CaseResult]
    estimated_cost_usd: float | None = None
    aborted: str | None = None

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(r.passed for r in self.results)

    @property
    def hard_failures(self) -> list[CaseResult]:
        """Failed hard cases, plus any invariant violation (those are hard on every case)."""
        return [
            r
            for r in self.results
            if not r.passed and (r.hard or any(f.startswith("INV-") for f in r.failures))
        ]

    def metrics(self) -> dict[str, Any]:
        latencies = [r.latency_ms for r in self.results]
        forbidden = [r for r in self.results if "forbidden" in r.tags]
        tokens_in = [r.input_tokens for r in self.results if r.input_tokens is not None]
        tokens_out = [r.output_tokens for r in self.results if r.output_tokens is not None]
        by_outcome: dict[str, list[bool]] = {}
        for r in self.results:
            by_outcome.setdefault(r.outcome or "none", []).append(r.passed)
        return {
            "cases": self.total,
            "passed": self.passed,
            "accuracy": round(self.passed / self.total, 4) if self.total else None,
            "hard_failures": len(self.hard_failures),
            "invalid_output_rate": round(
                sum(1 for r in self.results if r.error and r.error.startswith("LLM_OUTPUT"))
                / max(self.total, 1),
                4,
            ),
            "repair_rate": round(sum(1 for r in self.results if r.repairs) / max(self.total, 1), 4),
            "forbidden_requests": len(forbidden),
            "forbidden_requests_handled": sum(r.passed for r in forbidden),
            "accuracy_by_outcome": {
                k: round(sum(v) / len(v), 4) for k, v in sorted(by_outcome.items())
            },
            "input_tokens": sum(tokens_in) if tokens_in else None,
            "output_tokens": sum(tokens_out) if tokens_out else None,
            "latency_ms_mean": round(statistics.fmean(latencies), 1) if latencies else None,
            "latency_ms_p95": (
                sorted(latencies)[max(int(len(latencies) * 0.95) - 1, 0)] if latencies else None
            ),
            "estimated_cost_usd": self.estimated_cost_usd,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "provider": self.provider,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "datasets": self.datasets,
            "metrics": self.metrics(),
            "aborted": self.aborted,
            "results": [asdict(r) for r in self.results],
        }


def run_task_evals(
    task: str,
    datasets: list[Dataset],
    provider: LLMProvider,
    model: str,
    settings: Settings,
    *,
    max_cost_usd: float | None = None,
) -> TaskReport:
    evaluate = EVALUATORS[task]
    prompt_version = INTERPRET_COMMAND.prompt_version if task == "interpret_command" else "v1"
    report = TaskReport(task, provider.name, model, prompt_version, [d.name for d in datasets], [])
    spent = 0.0
    priced = False
    for dataset in datasets:
        for case in dataset.cases:
            case_result = evaluate(provider, model, dataset, case)
            report.results.append(case_result)
            cost = estimate_cost(
                settings, model, case_result.input_tokens, case_result.output_tokens
            )
            if cost is not None:
                priced = True
                spent += cost
            if max_cost_usd is not None and priced and spent > max_cost_usd:
                report.aborted = f"stopped: estimated cost {spent:.4f} USD exceeds {max_cost_usd}"
                report.estimated_cost_usd = round(spent, 6)
                return report
    report.estimated_cost_usd = round(spent, 6) if priced else None
    return report
