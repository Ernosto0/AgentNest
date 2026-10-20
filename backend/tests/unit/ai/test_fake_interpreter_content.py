"""The fake interpreter's content phrases (tr and en): the demo commands of Phase 5."""

import pytest

from app.ai.schemas import (
    ContentCancelScheduled,
    ContentCatalogEntry,
    ContentCreateDraft,
    ContentRef,
    InterpretCommandInput,
    InterpretCommandOutput,
    QueryContentStatus,
    QueryExplainFailure,
    Unsupported,
)
from app.ai.tasks.interpret_command import fake_interpret_command, post_validate

# 2026-01-15 is a Thursday; tomorrow is the 16th.
NOW_LOCAL = "2026-01-15T15:00:00+03:00"
CATALOG = [
    ContentCatalogEntry(
        ref_id="C1",
        title="Deneme dersi duyurusu",
        content_type="story_image",
        status="scheduled",
        local_schedule="2026-01-16T19:00",
    ),
    ContentCatalogEntry(
        ref_id="C2",
        title="Haftalık program",
        content_type="feed_image",
        status="failed",
        local_schedule="2026-01-14T10:00",
    ),
]


def interpret(text: str, locale: str = "tr") -> object:
    task_input = InterpretCommandInput(
        text=text,
        user_locale=locale,
        workspace_locale=locale,
        timezone="Europe/Istanbul",
        now_local=NOW_LOCAL,
        currency="TRY",
        fact_catalog=[],
        registry=[],
        content_catalog=CATALOG,
    )
    output = fake_interpret_command(task_input)
    assert isinstance(output, InterpretCommandOutput)
    assert post_validate(task_input, output) == []  # what the runner would accept
    return output.interpretation


@pytest.mark.parametrize(
    ("text", "locale", "kind", "objective"),
    [
        ("Deneme dersi için bir story hazırla", "tr", "story_image", "Deneme dersi"),
        ("Yaz kampanyası için bir post hazırla", "tr", "feed_image", "Yaz kampanyası"),
        ("Yeni sezon için bir hikaye oluştur", "tr", "story_image", "Yeni sezon"),
        ("Prepare a story about the trial class", "en", "story_image", "the trial class"),
        ("Write a post for summer memberships", "en", "feed_image", "summer memberships"),
    ],
)
def test_prepare_a_draft(text: str, locale: str, kind: str, objective: str) -> None:
    result = interpret(text, locale)
    assert isinstance(result, ContentCreateDraft), result
    assert (result.content_type, result.objective, result.notes) == (kind, objective, None)


@pytest.mark.parametrize(
    ("text", "locale", "date", "kind"),
    [
        ("yarınki postu iptal et", "tr", "2026-01-16", "feed_image"),
        ("Yarınki story'yi iptal et", "tr", "2026-01-16", "story_image"),
        ("cuma günkü paylaşımı iptal et", "tr", "2026-01-16", None),
        ("cancel tomorrow's post", "en", "2026-01-16", "feed_image"),
        ("Cancel the story on Friday", "en", "2026-01-16", "story_image"),
    ],
)
def test_cancel_a_scheduled_post_by_date_and_type(
    text: str, locale: str, date: str, kind: str | None
) -> None:
    result = interpret(text, locale)
    assert isinstance(result, ContentCancelScheduled), result
    assert result.content_ref.local_date == date and result.content_ref.content_type == kind
    assert result.content_ref.alias is None


def test_cancel_by_alias_and_by_the_owners_own_words() -> None:
    by_alias = interpret("C1 postunu iptal et")
    assert isinstance(by_alias, ContentCancelScheduled) and by_alias.content_ref.alias == "C1"
    unknown = interpret("C7 postunu iptal et")  # an alias nobody was shown is not passed on
    assert isinstance(unknown, ContentCancelScheduled) and unknown.content_ref.alias is None
    by_words = interpret("deneme dersi postunu iptal et")
    assert isinstance(by_words, ContentCancelScheduled)
    assert by_words.content_ref.description == "deneme dersi"


@pytest.mark.parametrize(
    ("text", "locale"),
    [
        ("son hata neydi?", "tr"),
        ("Son hata ne", "tr"),
        ("what was the last error", "en"),
        ("what went wrong", "en"),
        ("neden başarısız oldu", "tr"),
    ],
)
def test_explain_the_latest_failure(text: str, locale: str) -> None:
    result = interpret(text, locale)
    assert isinstance(result, QueryExplainFailure), result
    assert result.content_ref == "latest_failure"


def test_explain_the_failure_of_a_named_post() -> None:
    result = interpret("why did tomorrow's post fail", "en")
    assert isinstance(result, QueryExplainFailure)
    assert isinstance(result.content_ref, ContentRef)
    assert result.content_ref.local_date == "2026-01-16"
    by_alias = interpret("C2 neden başarısız oldu")
    assert isinstance(by_alias, QueryExplainFailure)
    assert isinstance(by_alias.content_ref, ContentRef) and by_alias.content_ref.alias == "C2"


@pytest.mark.parametrize(
    ("text", "locale"),
    [
        ("yarınki postun durumu ne", "tr"),
        ("what is the status of tomorrow's post", "en"),
    ],
)
def test_content_status(text: str, locale: str) -> None:
    result = interpret(text, locale)
    assert isinstance(result, QueryContentStatus), result
    assert result.content_ref.local_date == "2026-01-16"


@pytest.mark.parametrize(
    "text",
    [
        "story'yi hemen yayınla",
        "Publish the story now",
        "bu postu paylaş",
        "story hazırla ve yayınla",
        "prepare a story and publish it",
        "yarınki postu onayla",
    ],
)
def test_publishing_and_approving_stay_unsupported(text: str) -> None:
    assert isinstance(interpret(text), Unsupported), text


def test_a_price_correction_is_not_a_failure_question() -> None:
    result = interpret("Fiyatta hata var, aylık üyelik 7000 TL olsun")
    assert not isinstance(result, QueryExplainFailure)


@pytest.mark.parametrize(
    "bad",
    [
        ContentRef(alias="3", description=None, local_date=None, content_type=None),
        ContentRef(alias=None, description=None, local_date="yarın", content_type=None),
        ContentRef(alias=None, description="x" * 300, local_date=None, content_type=None),
    ],
)
def test_a_malformed_reference_is_sent_back_for_repair(bad: ContentRef) -> None:
    task_input = InterpretCommandInput(
        text="x",
        user_locale="tr",
        workspace_locale="tr",
        timezone="Europe/Istanbul",
        now_local=NOW_LOCAL,
        currency="TRY",
        fact_catalog=[],
        registry=[],
    )
    output = InterpretCommandOutput(
        interpretation=ContentCancelScheduled(type="content.cancel_scheduled", content_ref=bad)
    )
    assert post_validate(task_input, output)
