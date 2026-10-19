"""The draft_reply eval datasets and the harness around the drafting pipeline."""

from typing import Any

from pydantic import BaseModel

from app.core.config import Settings
from app.integrations.llm import FakeLLMProvider
from app.integrations.llm.base import LLMMessage, LLMResult, LLMUsage
from evals.loader import load_datasets
from evals.runner import run_task_evals


def run(provider: Any) -> Any:
    return run_task_evals(
        "draft_reply", load_datasets("draft_reply"), provider, "fake", Settings(_env_file=None)
    )


def test_the_datasets_cover_both_languages_and_the_required_themes() -> None:
    datasets = load_datasets("draft_reply")
    cases = [c for d in datasets for c in d.cases]
    assert len(cases) >= 40
    assert {"tr", "en"} <= {c.locale for c in cases}
    tags = {t for c in cases for t in c.tags}
    assert {"escalation", "injection", "grounding", "language"} <= tags
    assert len({c.id for c in cases}) == len(cases)
    assert sum(1 for c in cases if c.hard) >= 25


def test_the_fake_provider_passes_every_case_without_a_hard_failure() -> None:
    report = run(FakeLLMProvider())
    failures = [(r.id, r.failures) for r in report.results if not r.passed]
    assert failures == []
    assert report.hard_failures == []
    assert report.metrics()["accuracy"] == 1.0


class Permissive:
    """A model that is wrong in the dangerous direction: it flags nothing, never asks for a
    person, and always answers with a price it makes up."""

    name = "permissive"
    is_fake = True

    def generate_structured(
        self,
        *,
        task: str,
        model: str,
        system: str,
        messages: list[LLMMessage],
        output_schema: type[BaseModel],
        max_output_tokens: int,
        timeout_s: float,
        context: object | None = None,
    ) -> LLMResult:
        language = context.reply_language  # type: ignore[attr-defined]
        proposal = output_schema.model_validate(
            {
                "intent": "pricing",
                "flags": [],
                "can_answer": True,
                "needs_human": False,
                "approved_answer_id": None,
                "reply_template": "Aylık üyelik 1.000 ₺, %50 indirim!",
                "used_fact_keys": [],
                "language": language,
            }
        )
        return LLMResult(
            raw_text=proposal.model_dump_json(),
            usage=LLMUsage(),
            latency_ms=0,
            provider=self.name,
            model=model,
            is_fake=True,
        )


def test_a_model_that_invents_values_never_gets_one_through() -> None:
    """Whatever the model says, escalation cases still escalate and nothing ungrounded is
    sendable: the deterministic layers hold (no invariant violation), and the harness reports
    that the model is nevertheless wrong about the ordinary cases."""
    report = run(Permissive())
    invariant_failures = [
        (r.id, f) for r in report.results for f in r.failures if f.startswith("INV-")
    ]
    assert invariant_failures == []
    assert report.metrics()["accuracy"] < 0.5  # the cases that expect an answer fail loudly
    sendable = [r for r in report.results if r.outcome in ("approval_required", "auto")]
    assert sendable == []  # every invented price was refused by the validator
