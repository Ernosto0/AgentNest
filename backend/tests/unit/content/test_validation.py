"""AC-D3 and the other submit rules of plan.md G17 (pure: ``content.validation``)."""

from typing import Any

import pytest

from app.content import validation as v
from app.core.i18n import catalog_keys, t


def facts(**overrides: Any) -> v.SubmitFacts:
    """A feed post that passes every rule, with ``overrides``."""
    values: dict[str, Any] = {
        "content_type": "feed_image",
        "caption": "Cuma günü görüşürüz",
        "overlay_text_suggestions": [],
        "media": v.MediaFacts("ready", 1080, 1350),
        "claim_issues": [],
        "schedule_error": None,
        "account": v.AccountFacts(True, {"publish_feed_image": True, "publish_story_image": True}),
        "quota_exceeded": False,
    }
    return v.SubmitFacts(**{**values, **overrides})


def codes(issues: tuple[v.Issue, ...]) -> list[str]:
    return [i.code for i in issues]


def story(**overrides: Any) -> v.SubmitFacts:
    values: dict[str, Any] = {
        "content_type": "story_image",
        "caption": None,
        "overlay_text_suggestions": ["Deneme dersi bizden"],
        "media": v.MediaFacts("ready", 1080, 1920),
        **overrides,
    }
    return facts(**values)


def test_a_valid_feed_post_and_a_valid_story_have_no_errors_and_no_warnings() -> None:
    for subject in (facts(), story()):
        result = v.validate_submission(subject)
        assert result.ok and result.errors == () and result.warnings == ()


def test_ac_d3_a_story_without_media_fails_with_content_media_required() -> None:
    result = v.validate_submission(story(media=None))
    assert not result.ok
    assert codes(result.errors) == [v.CONTENT_MEDIA_REQUIRED]
    assert result.errors[0].field == "media_asset_id"


def test_a_feed_post_without_media_also_needs_an_image() -> None:
    assert v.CONTENT_MEDIA_REQUIRED in codes(v.validate_submission(facts(media=None)).errors)


def test_media_that_is_not_ready_is_reported_with_its_status() -> None:
    result = v.validate_submission(facts(media=v.MediaFacts("deleted", 1080, 1350)))
    assert codes(result.errors) == [v.MEDIA_NOT_READY]
    assert result.errors[0].params == {"status": "deleted"}


def test_a_feed_post_needs_a_caption() -> None:
    for caption in (None, "", "   \n"):
        assert codes(v.validate_submission(facts(caption=caption)).errors) == [v.CAPTION_REQUIRED]


def test_the_caption_limit_is_2200_characters() -> None:
    assert v.validate_submission(facts(caption="a" * 2200)).ok
    result = v.validate_submission(facts(caption="a" * 2201))
    assert codes(result.errors) == [v.CAPTION_TOO_LONG]
    assert result.errors[0].params == {"length": 2201, "max": 2200}


def test_a_story_publishes_no_caption() -> None:
    result = v.validate_submission(story(caption="Bu görünmez"))
    assert codes(result.errors) == [v.CAPTION_NOT_ALLOWED]


@pytest.mark.parametrize(
    ("width", "height", "ok"),
    [
        (1080, 1350, True),  # 4:5 exactly
        (1080, 1080, True),
        (1910, 1000, True),  # 1.91:1 exactly
        (1080, 1351, False),  # a hair narrower than 4:5
        (1000, 1920, False),  # a portrait story-shaped image
        (2000, 1000, False),  # 2:1
    ],
)
def test_a_feed_image_must_be_between_4_5_and_1_91_to_1(width: int, height: int, ok: bool) -> None:
    result = v.validate_submission(facts(media=v.MediaFacts("ready", width, height)))
    assert result.ok is ok
    if not ok:
        assert codes(result.errors) == [v.ASPECT_RATIO_OUT_OF_RANGE]


def test_a_story_that_is_not_9_16_only_gets_a_warning() -> None:
    result = v.validate_submission(story(media=v.MediaFacts("ready", 1080, 1350)))
    assert result.ok
    assert codes(result.warnings) == [v.STORY_ASPECT_NOT_9_16]
    close = v.validate_submission(story(media=v.MediaFacts("ready", 1080, 1910)))
    assert close.warnings == ()  # within the tolerance of 9:16


def test_a_long_overlay_suggestion_only_gets_a_warning() -> None:
    too_wide = "x" * 41
    four_lines = "a\nb\nc\nd"
    result = v.validate_submission(
        story(overlay_text_suggestions=["kısa", too_wide, four_lines, "üç\nsatır\nolur"])
    )
    assert result.ok
    assert [(w.code, w.field) for w in result.warnings] == [
        (v.OVERLAY_TOO_LONG, "overlay_text_suggestions.1"),
        (v.OVERLAY_TOO_LONG, "overlay_text_suggestions.2"),
    ]


def test_claim_issues_in_the_caption_or_an_overlay_block_and_are_listed() -> None:
    caption_issue = {"code": "MONEY", "field": "caption", "text": "999 TL", "span": [0, 6]}
    overlay_issue = {
        "code": "PERCENT",
        "field": "overlay_text_suggestions.0",
        "text": "%40",
        "span": [0, 3],
    }
    result = v.validate_submission(facts(claim_issues=[caption_issue]))
    assert codes(result.errors) == [v.CLAIM_VALIDATION_FAILED]
    assert result.errors[0].params == {"issues": [caption_issue]}

    in_story = v.validate_submission(story(claim_issues=[overlay_issue]))
    assert codes(in_story.errors) == [v.CLAIM_VALIDATION_FAILED]
    assert in_story.errors[0].params["issues"][0]["field"] == "overlay_text_suggestions.0"


def test_a_schedule_error_is_passed_through() -> None:
    error = v.Issue(v.SCHEDULE_TOO_SOON_FOR_APPROVAL, "schedule", {"minutes": 15})
    result = v.validate_submission(facts(schedule_error=error))
    assert result.errors == (error,)


def test_no_account_or_a_disconnected_one_is_account_not_connected() -> None:
    assert codes(v.validate_submission(facts(account=None)).errors) == [v.ACCOUNT_NOT_CONNECTED]
    unavailable = v.AccountFacts(False, {"publish_feed_image": True})
    result = v.validate_submission(facts(account=unavailable))
    assert codes(result.errors) == [v.ACCOUNT_NOT_CONNECTED]


def test_the_account_needs_the_capability_of_the_content_type() -> None:
    only_feed = v.AccountFacts(True, {"publish_feed_image": True})
    assert v.validate_submission(facts(account=only_feed)).ok
    result = v.validate_submission(story(account=only_feed))
    assert codes(result.errors) == [v.CAPABILITY_MISSING]
    assert result.errors[0].params == {"capability": "publish_story_image"}
    falsy = v.AccountFacts(True, {"publish_feed_image": "yes"})  # only a real True counts
    assert codes(v.validate_submission(facts(account=falsy)).errors) == [v.CAPABILITY_MISSING]


def test_the_quota_forecast_is_an_error() -> None:
    result = v.validate_submission(facts(quota_exceeded=True))
    assert codes(result.errors) == [v.PUBLISH_QUOTA_FORECAST_EXCEEDED]


def test_every_problem_is_listed_at_once() -> None:
    result = v.validate_submission(facts(media=None, caption=None, account=None))
    assert codes(result.errors) == [
        v.CONTENT_MEDIA_REQUIRED,
        v.CAPTION_REQUIRED,
        v.ACCOUNT_NOT_CONNECTED,
    ]


def test_as_dict_carries_the_localised_message_only_when_asked() -> None:
    issue = v.Issue(v.CAPTION_TOO_LONG, "caption", {"length": 2300, "max": 2200})
    assert v.as_dict(issue) == {
        "code": "CAPTION_TOO_LONG",
        "field": "caption",
        "params": {"length": 2300, "max": 2200},
    }
    assert "2300" in v.as_dict(issue, "en")["message"]
    assert "2300" in v.as_dict(issue, "tr")["message"]
    assert v.as_dict(issue, "en")["message"] != v.as_dict(issue, "tr")["message"]


def test_every_item_code_has_a_text_in_both_languages() -> None:
    assert len(set(v.ALL_CODES)) == len(v.ALL_CODES) == 16
    for locale in ("tr", "en"):
        keys = catalog_keys(locale)
        for code in v.ALL_CODES:
            assert f"content.issue.{code}" in keys, (locale, code)
            assert t(f"content.issue.{code}", locale) != f"content.issue.{code}"
