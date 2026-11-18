"""The draft_reply eval datasets and the harness around the drafting pipeline."""

from typing import Any

import pytest
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


# --- ru, de and ar (F-11, Feature Phase 5 Session 11) ----------------------------------------

NEW_LANGUAGES = {"ru": "draft_reply_ru", "de": "draft_reply_de", "ar": "draft_reply_ar"}


def language_cases(code: str) -> list[Any]:
    (dataset,) = load_datasets("draft_reply", only=NEW_LANGUAGES[code])
    return list(dataset.cases)


@pytest.mark.parametrize("code", NEW_LANGUAGES)
def test_each_new_language_has_a_full_eval_set(code: str) -> None:
    cases = language_cases(code)
    assert 15 <= len(cases) <= 20
    assert all(c.locale == code for c in cases)
    assert all(code in c.inputs["languages"] or c.id.endswith("goes_to_a_person") for c in cases)
    tags = {t for c in cases for t in c.tags}
    assert {"language", "pricing", "booking", "escalation", "injection", "grounding"} <= tags
    assert sum(1 for c in cases if "injection" in c.tags) >= 3
    assert sum(1 for c in cases if c.hard) >= 12
    intents = {c.expect.get("intent") for c in cases}
    assert {"pricing", "hours", "booking"} <= intents  # prices, hours and booking are covered
    # Some cases must prove the language was detected, others that a person takes over.
    assert any(c.expect.get("language") == code for c in cases)
    assert any(c.expect.get("language") == "none" for c in cases)


@pytest.mark.parametrize("code", NEW_LANGUAGES)
def test_the_fake_provider_passes_every_case_of_the_language(code: str) -> None:
    (dataset,) = load_datasets("draft_reply", only=NEW_LANGUAGES[code])
    report = run_task_evals(
        "draft_reply", [dataset], FakeLLMProvider(), "fake", Settings(_env_file=None)
    )
    assert len(report.results) == len(dataset.cases)
    assert [(r.id, r.failures) for r in report.results if not r.passed] == []
    assert report.hard_failures == []


@pytest.mark.parametrize("code", NEW_LANGUAGES)
def test_a_model_that_invents_values_never_gets_one_through_in_the_language(code: str) -> None:
    (dataset,) = load_datasets("draft_reply", only=NEW_LANGUAGES[code])
    report = run_task_evals(
        "draft_reply", [dataset], Permissive(), "fake", Settings(_env_file=None)
    )
    invariant_failures = [
        (r.id, f) for r in report.results for f in r.failures if f.startswith("INV-")
    ]
    assert invariant_failures == []
    assert [r.id for r in report.results if r.outcome in ("approval_required", "auto")] == []


@pytest.mark.parametrize("code", NEW_LANGUAGES)
def test_an_always_answering_model_never_makes_an_injection_case_automatic(code: str) -> None:
    (dataset,) = load_datasets("draft_reply", only=NEW_LANGUAGES[code])
    report = run_task_evals(
        "draft_reply", [dataset], AlwaysAnswersWithThePrice(), "fake", Settings(_env_file=None)
    )
    injected = {c.id for c in dataset.cases if "injection" in c.tags}
    assert injected
    assert [r.id for r in report.results if r.id in injected and r.outcome == "auto"] == []
    escalations = {c.id for c in dataset.cases if "escalation" in c.tags}
    assert [r.id for r in report.results if r.id in escalations and r.outcome == "auto"] == []


def test_the_pipeline_labels_a_non_turkish_reply_with_the_english_label_first() -> None:
    from types import SimpleNamespace

    from app.inbox.drafting import _label

    fact: Any = SimpleNamespace(label={"tr": "Aylık üyelik", "en": "Monthly membership"}, key="k")
    assert _label(fact, "tr") == "Aylık üyelik"
    assert _label(fact, "en") == "Monthly membership"
    for code in ("ru", "de", "ar"):
        assert _label(fact, code) == "Monthly membership"
    turkish_only: Any = SimpleNamespace(label={"tr": "Aylık üyelik"}, key="k")
    assert _label(turkish_only, "ru") == "Aylık üyelik"
    assert _label(SimpleNamespace(label={}, key="pricing.x"), "de") == "pricing.x"
