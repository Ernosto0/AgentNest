"""F-04: reading story references out of attachments (pure parts of ``inbox.stories``)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.inbox import stories
from app.inbox.stories import StoryContent, StoryRef
from app.integrations.instagram import webhook_format as wf

REPLY = {"type": "story_reply", "url": "https://cdn.test/s.jpg", "note": "123"}
MENTION = {"type": "story_mention", "url": "https://cdn.test/m.jpg", "note": None}
PHOTO = {"type": "image", "url": "https://cdn.test/p.jpg", "note": None}


def test_a_story_reply_carries_the_story_id_and_link() -> None:
    assert stories.story_ref([REPLY]) == StoryRef("reply", "123", "https://cdn.test/s.jpg")


def test_a_reply_without_an_id_is_still_a_reply() -> None:
    ref = stories.story_ref([{"type": "story_reply", "url": None, "note": None}])
    assert ref == StoryRef("reply", None, None)


def test_a_mention_carries_only_a_link_and_a_reply_wins_over_it() -> None:
    assert stories.story_ref([MENTION]) == StoryRef("mention", None, "https://cdn.test/m.jpg")
    assert stories.story_ref([MENTION, REPLY]) is not None
    assert stories.story_ref([MENTION, REPLY]).kind == "reply"  # type: ignore[union-attr]


@pytest.mark.parametrize("attachments", [None, [], [PHOTO], [{"type": "unsupported"}]])
def test_other_attachments_are_not_stories(attachments) -> None:  # type: ignore[no-untyped-def]
    assert stories.story_ref(attachments) is None


@pytest.mark.parametrize(
    ("messages", "expected"),
    [
        ([(None, [MENTION])], True),
        ([("", [MENTION]), ("  ", [MENTION])], True),
        ([], False),
        ([("hello", [MENTION])], False),
        ([(None, [MENTION, PHOTO])], False),
        ([(None, [PHOTO])], False),
        ([(None, [])], False),
        ([(None, [MENTION]), (None, [PHOTO])], False),
        ([(None, [REPLY])], False),
    ],
)
def test_only_a_text_less_mention_is_a_plain_mention(messages, expected) -> None:  # type: ignore[no-untyped-def]
    assert stories.is_mention_only(messages) is expected


def content(**overrides: object) -> StoryContent:
    base: dict[str, object] = {
        "content_id": uuid.uuid4(),
        "title": "Yaz kampanyası",
        "objective": None,
        "overlay_lines": (),
        "media_asset_id": None,
        "media_deleted": False,
        "published_at": datetime(2026, 11, 16, tzinfo=UTC),
        "expired": False,
    }
    return StoryContent(**{**base, **overrides})  # type: ignore[arg-type]


def test_the_prompt_text_lists_what_is_known_and_nothing_else() -> None:
    text = stories.prompt_text(
        content(objective="Promote the summer plan", overlay_lines=("Yaz fırsatı", "Bize yazın"))
    )
    assert text == (
        "title: Yaz kampanyası\nabout: Promote the summer plan\n"
        "text on the story: Yaz fırsatı / Bize yazın"
    )
    assert stories.prompt_text(None) is None
    assert stories.prompt_text(content(title="", expired=True)) == "the story is no longer live"


def test_the_prompt_text_is_bounded() -> None:
    text = stories.prompt_text(content(objective="x" * 5000))
    assert text is not None and len(text) <= stories.MAX_CONTEXT_CHARS


def test_a_placeholder_never_carries_a_value_into_the_prompt() -> None:
    assert stories._plain("Sadece {{fact:pricing.membership_monthly}}!") == (
        "Sadece [membership monthly]!"
    )
    assert stories._lines(["{{fact:pricing.x|short}}", "", 3]) == ("[x]",)  # type: ignore[list-item]


def test_a_story_lasts_24_hours() -> None:
    assert timedelta(hours=24) == stories.STORY_LIFETIME


# --- the simulator builds what the parser reads back ---------------------------------------------


def test_the_builder_writes_a_story_reply_as_reply_to_and_the_parser_reads_it_back() -> None:
    now = datetime(2026, 11, 16, tzinfo=UTC)
    payload = wf.build_message_payload(
        "biz", "cust", "m-1", "Bu ne kadar?", now, attachments=[REPLY]
    )
    message = payload["entry"][0]["messaging"][0]["message"]
    assert message["reply_to"] == {"story": {"id": "123", "url": "https://cdn.test/s.jpg"}}
    assert "attachments" not in message
    (event,) = wf.parse(payload)
    assert event.attachments == [REPLY]


def test_the_builder_keeps_other_attachments_next_to_a_story_reply() -> None:
    now = datetime(2026, 11, 16, tzinfo=UTC)
    payload = wf.build_message_payload(
        "biz", "cust", "m-1", None, now, attachments=[REPLY, MENTION]
    )
    (event,) = wf.parse(payload)
    assert [a["type"] for a in event.attachments] == ["story_reply", "story_mention"]
