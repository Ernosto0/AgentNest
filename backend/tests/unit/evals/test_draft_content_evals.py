"""The draft_content eval datasets and the harness around the generation pipeline (P5-09)."""

from typing import Any

import pytest
from pydantic import BaseModel

from app.content import generation
from app.core.config import Settings
from app.integrations.llm import FakeLLMProvider
from app.integrations.llm.base import LLMMessage, LLMResult, LLMUsage
from evals.loader import TASKS, load_datasets
from evals.runner import EVALUATORS, run_task_evals


def run(provider: Any) -> Any:
    return run_task_evals(
        "draft_content",
        load_datasets("draft_content"),
        provider,
        "fake",
        Settings(_env_file=None),
    )


def test_the_task_is_registered_in_the_harness() -> None:
    assert "draft_content" in TASKS and "draft_content" in EVALUATORS


def test_the_datasets_cover_both_languages_and_the_required_themes() -> None:
    cases = [c for d in load_datasets("draft_content") for c in d.cases]
    assert len(cases) >= 15
    assert {"tr", "en"} <= {c.locale for c in cases}
    assert sum(1 for c in cases if c.locale == "en") >= 5
    tags = {t for c in cases for t in c.tags}
    assert {"price", "promotion", "discount", "story", "do_not_share", "grounding"} <= tags
    assert len({c.id for c in cases}) == len(cases)
    assert sum(1 for c in cases if c.hard) >= 10
    types = {c.inputs.get("content_type", "feed_image") for c in cases}
    assert types == {"feed_image", "story_image"}


def test_the_fake_provider_passes_every_case_without_a_hard_failure() -> None:
    report = run(FakeLLMProvider())
    failures = [(r.id, r.failures) for r in report.results if not r.passed]
    assert failures == []
    assert report.hard_failures == []
    assert report.metrics()["accuracy"] == 1.0
    outcomes = {r.outcome for r in report.results}
    assert outcomes == {"clean", "flagged"}  # the unbacked ones really are flagged


class Scripted:
    """A model that answers every case with the same proposal."""

    name = "scripted"
    is_fake = True

    def __init__(self, **fields: Any) -> None:
        self.fields = fields

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
        is_story = context.content_type == "story_image"  # type: ignore[attr-defined]
        base: dict[str, Any] = {
            "title": "Başlık",
            "caption_template": None if is_story else "Merhaba!",
            "overlay_text_suggestions": ["Merhaba"] if is_story else [],
            "visual_notes": "",
            "hashtags": [],
            "used_fact_keys": [],
            "commercial_claims": [],
        }
        proposal = output_schema.model_validate({**base, **self.fields})
        return LLMResult(
            raw_text=proposal.model_dump_json(),
            usage=LLMUsage(),
            latency_ms=0,
            provider=self.name,
            model=model,
            is_fake=True,
        )


def invariant_failures(report: Any) -> list[tuple[str, str]]:
    return [(r.id, f) for r in report.results for f in r.failures if f.startswith("INV-")]


def test_a_model_that_types_the_verified_price_is_caught_by_the_independent_check() -> None:
    """The price is the real one, so the matcher grounds it and the draft passes the stored
    report; the eval still reports it, because the model should have used the placeholder."""
    report = run(Scripted(caption_template="Aylık üyelik 6.000 ₺ / ay, hepinizi bekleriz!"))
    caught = [(i, f) for i, f in invariant_failures(report) if "ungrounded" in f]
    assert caught  # the feed cases that passed with a typed value
    assert report.hard_failures != []


def test_a_model_that_invents_a_price_never_passes() -> None:
    report = run(Scripted(caption_template="Aylık üyelik sadece 1.000 ₺!"))
    assert invariant_failures(report) == []  # the pipeline flagged every one of them
    feed = [r for r in report.results if r.id != "" and r.outcome is not None]
    assert {r.outcome for r in feed if "story" not in r.tags} == {"flagged"}


def test_a_claim_no_fact_backs_is_flagged_and_never_passes() -> None:
    report = run(
        Scripted(
            commercial_claims=[{"claim": "ücretsiz kahve", "fact_key": None}],
        )
    )
    assert invariant_failures(report) == []
    assert {r.outcome for r in report.results} == {"flagged"}


def test_a_regression_that_stops_flagging_claims_is_a_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generation, "_unbacked", lambda claims, keys: [])
    report = run(Scripted(commercial_claims=[{"claim": "ücretsiz kahve", "fact_key": None}]))
    messages = [f for _, f in invariant_failures(report)]
    assert any("was not flagged" in m for m in messages)
    assert report.hard_failures != []


def test_a_story_with_a_caption_is_refused_before_it_is_ever_stored() -> None:
    """The post-validator sends it back once; a model that insists produces no draft."""
    report = run(Scripted(caption_template="Bir açıklama"))
    stories = [r for r in report.results if "story" in r.tags]
    assert stories and all(r.outcome is None and not r.passed for r in stories)
    assert invariant_failures(report) == []


def test_a_placeholder_the_model_invents_fails_the_render_not_the_text() -> None:
    report = run(Scripted(caption_template="Fiyat {{fact:pricing.invented}}", used_fact_keys=[]))
    feed = [r for r in report.results if "story" not in r.tags]
    assert all(r.outcome in (None, "render_failed") for r in feed)
    assert invariant_failures(report) == []
