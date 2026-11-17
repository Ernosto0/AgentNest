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


# --- voice notes (F-03, Feature Phase 2 Session 02) ------------------------------------------


def voice_cases() -> list[Any]:
    (dataset,) = load_datasets("draft_reply", only="draft_reply_voice")
    return list(dataset.cases)


def test_the_voice_dataset_has_turkish_disfluent_and_misspelled_transcripts() -> None:
    cases = voice_cases()
    assert 10 <= len(cases) <= 25
    assert all(c.inputs.get("transcript") and not c.inputs.get("text") for c in cases)
    turkish = [c for c in cases if c.locale == "tr"]
    assert len(turkish) >= 10
    tags = {t for c in cases for t in c.tags}
    assert {"disfluent", "misspelled", "delegation", "injection", "escalation"} <= tags
    assert any("ıı" in c.inputs["transcript"] for c in cases)  # disfluencies as heard
    assert all(c.hard for c in cases)


def test_the_fake_provider_passes_every_voice_case() -> None:
    report = run(FakeLLMProvider())
    voice = [r for r in report.results if r.dataset == "draft_reply_voice"]
    assert len(voice) == len(voice_cases())
    assert [(r.id, r.failures) for r in voice if not r.passed] == []


class AlwaysAnswersWithThePrice(Permissive):
    """A model that never flags or escalates anything and answers every voice note with the
    monthly price (through a real placeholder, so grounding holds)."""

    name = "always-price"

    def generate_structured(self, **kwargs: Any) -> Any:
        context = kwargs["context"]
        proposal = kwargs["output_schema"].model_validate(
            {
                "intent": "pricing",
                "flags": [],
                "can_answer": True,
                "needs_human": False,
                "approved_answer_id": None,
                "reply_template": "Aylık üyelik ücretimiz {{fact:pricing.membership_monthly}}.",
                "used_fact_keys": ["pricing.membership_monthly"],
                "language": context.reply_language,
            }
        )
        return LLMResult(
            raw_text=proposal.model_dump_json(),
            usage=LLMUsage(),
            latency_ms=0,
            provider=self.name,
            model=kwargs["model"],
            is_fake=True,
        )


def test_a_model_that_answers_everything_cannot_make_a_voice_reply_automatic() -> None:
    """The voice cases ask for automatic classes (delegation). Whatever the model proposes, no
    voice-note reply is automatic and no transcript invariant is violated."""
    (dataset,) = load_datasets("draft_reply", only="draft_reply_voice")
    report = run_task_evals(
        "draft_reply", [dataset], AlwaysAnswersWithThePrice(), "fake", Settings(_env_file=None)
    )
    assert len(report.results) == len(dataset.cases)
    assert [r.id for r in report.results if r.outcome == "auto"] == []
    invariant_failures = [
        (r.id, f) for r in report.results for f in r.failures if f.startswith("INV-")
    ]
    assert invariant_failures == []
    delegated = {c.id for c in dataset.cases if "delegation" in c.tags}
    answered = [r for r in report.results if r.id in delegated and r.outcome != "human_required"]
    assert answered and all(r.outcome == "approval_required" for r in answered)
