"""F-03 Session 03: the image downloader, the offline fixtures, the ``describe_image`` task and the
OpenAI request for a turn with an image. No network, no key: stubbed transports only."""

import base64
import json
from collections.abc import Callable
from typing import Any

import httpx
import httpx2
import pytest
from pydantic import BaseModel

from app.ai.runner import execute_task
from app.ai.schemas import DescribeImageInput, ImageDescription
from app.ai.tasks.describe_image import DESCRIBE_IMAGE, build_messages, post_validate, snapshot
from app.core.config import Settings
from app.integrations.llm import FakeLLMProvider, LLMImage, LLMMessage
from app.integrations.llm.errors import LLMConfigError
from app.integrations.llm.openai_provider import OpenAIProvider, _input_item
from app.integrations.vision.errors import ImageFetchError, ImageRejected
from app.integrations.vision.fake import (
    FETCH_FAILURES,
    FIXTURES,
    FixtureImageFetcher,
    fixture_blob,
    fixture_name,
    fixture_of,
)
from app.integrations.vision.fetch import HttpsImageFetcher, check_url
from app.integrations.vision.images import (
    FAKE_IMAGE_MAGIC,
    declared_type_allowed,
    resolved_media_type,
    sniff_media_type,
)

GOOD_URL = "https://scontent-ist1-1.cdninstagram.com/v/t/photo.jpg?sig=secret"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 8
GIF = b"GIF89a" + b"\x00" * 32


def public_resolver(host: str, port: int, **kwargs: Any) -> list[Any]:
    return [(2, 1, 6, "", ("157.240.1.1", port))]


# --- the file types ---------------------------------------------------------------------------


def test_only_jpeg_png_and_webp_are_recognised_by_their_signature() -> None:
    assert sniff_media_type(JPEG) == "image/jpeg"
    assert sniff_media_type(PNG) == "image/png"
    assert sniff_media_type(WEBP) == "image/webp"
    assert sniff_media_type(GIF) is None  # an animated GIF is not accepted by the model
    assert sniff_media_type(b"<html>") is None and sniff_media_type(b"") is None
    assert sniff_media_type(b"RIFF\x00\x00\x00\x00WAVEfmt ") is None  # a WAV is not a WebP


def test_a_declared_type_must_agree_with_the_signature() -> None:
    assert resolved_media_type("image/jpeg", JPEG) == "image/jpeg"
    assert resolved_media_type("image/jpg; charset=binary", JPEG) == "image/jpeg"
    assert resolved_media_type("application/octet-stream", PNG) == "image/png"
    assert resolved_media_type(None, WEBP) == "image/webp"
    assert resolved_media_type("image/png", JPEG) is None  # a lie about the type
    assert resolved_media_type("image/jpeg", b"<html>") is None
    assert declared_type_allowed("image/webp") and declared_type_allowed("binary/octet-stream")
    assert not declared_type_allowed("text/html") and not declared_type_allowed("image/gif")


# --- the downloader ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://scontent.cdninstagram.com/a.jpg",  # not https
        "https://evil.example.com/a.jpg",  # not the Instagram CDN
        "https://scontent.cdninstagram.com.evil.io/a.jpg",
        "https://user:pw@scontent.cdninstagram.com/a.jpg",  # credentials
        "https://scontent.cdninstagram.com:8443/a.jpg",  # port
        "https://169.254.169.254/latest/meta-data",  # metadata address
        "file:///etc/passwd",
        "mock-image://product_photo",
        "",
    ],
)
def test_the_downloader_refuses_urls_that_are_not_the_instagram_cdn(url: str) -> None:
    with pytest.raises(ImageFetchError) as caught:
        check_url(url, public_resolver)
    assert caught.value.code == "IMAGE_URL_REFUSED"


def test_a_host_that_resolves_to_a_private_address_is_refused() -> None:
    def private(host: str, port: int, **kwargs: Any) -> list[Any]:
        return [(2, 1, 6, "", ("10.0.0.5", port))]

    with pytest.raises(ImageFetchError) as caught:
        check_url(GOOD_URL, private)
    assert caught.value.code == "IMAGE_URL_REFUSED"


def test_an_unresolvable_host_is_a_retryable_download_failure() -> None:
    def broken(host: str, port: int, **kwargs: Any) -> list[Any]:
        raise OSError("dns")

    with pytest.raises(ImageFetchError) as caught:
        check_url(GOOD_URL, broken)
    assert (caught.value.code, caught.value.retryable) == ("IMAGE_DOWNLOAD_FAILED", True)


def fetcher(
    handler: Callable[[httpx.Request], httpx.Response], clock: Callable[[], float] | None = None
) -> HttpsImageFetcher:
    kwargs: dict[str, Any] = {"transport": httpx.MockTransport(handler)}
    if clock is not None:
        kwargs["monotonic"] = clock
    return HttpsImageFetcher(resolver=public_resolver, **kwargs)


def ok(content: bytes, content_type: str = "image/jpeg", **headers: str) -> httpx.Response:
    return httpx.Response(200, content=content, headers={"content-type": content_type, **headers})


def test_an_image_is_downloaded_with_no_credentials_and_no_redirects() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return ok(JPEG)

    result = fetcher(handler).fetch(GOOD_URL, max_bytes=1_000_000, timeout_s=5)
    assert result.content_type == "image/jpeg" and result.data == JPEG
    (request,) = seen
    assert "authorization" not in {k.lower() for k in request.headers}
    assert "cookie" not in {k.lower() for k in request.headers}


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (401, "IMAGE_EXPIRED", False),
        (403, "IMAGE_EXPIRED", False),
        (404, "IMAGE_EXPIRED", False),
        (410, "IMAGE_EXPIRED", False),
        (302, "IMAGE_URL_REFUSED", False),
        (429, "IMAGE_DOWNLOAD_FAILED", True),
        (503, "IMAGE_DOWNLOAD_FAILED", True),
        (400, "IMAGE_DOWNLOAD_FAILED", False),
    ],
)
def test_http_failures_map_to_reason_codes(status: int, code: str, retryable: bool) -> None:
    with pytest.raises(ImageFetchError) as caught:
        fetcher(lambda r: httpx.Response(status)).fetch(GOOD_URL, max_bytes=1000, timeout_s=5)
    assert (caught.value.code, caught.value.retryable) == (code, retryable)
    assert "secret" not in str(caught.value)  # the signed URL never reaches an error


def test_a_network_error_is_retryable_and_does_not_leak_the_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(ImageFetchError) as caught:
        fetcher(handler).fetch(GOOD_URL, max_bytes=1000, timeout_s=5)
    assert caught.value.retryable and "secret" not in str(caught.value)


def test_a_declared_length_over_the_cap_is_refused_before_the_body_is_read() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "image/jpeg", "content-length": "5000"}, content=b"x"
        )

    with pytest.raises(ImageRejected) as caught:
        fetcher(handler).fetch(GOOD_URL, max_bytes=1000, timeout_s=5)
    assert caught.value.code == "IMAGE_TOO_LARGE"


def test_a_body_that_lies_about_its_length_is_cut_off_at_the_cap() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"x" * 5000)

    with pytest.raises(ImageRejected) as caught:
        fetcher(handler).fetch(GOOD_URL, max_bytes=1000, timeout_s=5)
    assert caught.value.code == "IMAGE_TOO_LARGE"


def test_a_page_that_is_not_an_image_is_refused() -> None:
    with pytest.raises(ImageRejected) as caught:
        fetcher(lambda r: ok(b"<html>", "text/html")).fetch(GOOD_URL, max_bytes=1000, timeout_s=5)
    assert caught.value.code == "IMAGE_UNSUPPORTED_TYPE"


def test_a_slow_trickle_hits_the_total_deadline() -> None:
    ticks = iter(range(0, 1000, 100))

    with pytest.raises(ImageFetchError) as caught:
        fetcher(lambda r: ok(b"x" * 300_000), clock=lambda: float(next(ticks))).fetch(
            GOOD_URL, max_bytes=1_000_000, timeout_s=5
        )
    assert caught.value.retryable


# --- the mock fetcher and the fixtures --------------------------------------------------------


def test_the_mock_fetcher_reads_fixtures_and_never_the_network() -> None:
    fixtures = FixtureImageFetcher()
    got = fixtures.fetch("mock-image://price_screenshot_tr", max_bytes=10_000, timeout_s=1)
    assert got.data.startswith(FAKE_IMAGE_MAGIC) and sniff_media_type(got.data) == "image/png"
    assert resolved_media_type(got.content_type, got.data) == "image/png"
    assert fixture_name("mock-image://price_screenshot_tr/") == "price_screenshot_tr"
    assert fixture_of(got.data) is FIXTURES["price_screenshot_tr"]
    for url in ("https://scontent.cdninstagram.com/a.jpg", "mock-image://", "mock-audio://x"):
        with pytest.raises(ImageFetchError) as caught:
            fixtures.fetch(url, max_bytes=10_000, timeout_s=1)
        assert caught.value.code == "IMAGE_URL_REFUSED"


def test_every_failure_fixture_fails_the_way_it_is_named() -> None:
    fixtures = FixtureImageFetcher()
    expected = {
        "expired": "IMAGE_EXPIRED",
        "unreachable": "IMAGE_DOWNLOAD_FAILED",
        "oversize": "IMAGE_TOO_LARGE",
    }
    for name, code in expected.items():
        with pytest.raises(ImageFetchError) as caught:
            fixtures.fetch(f"mock-image://{name}", max_bytes=10_000, timeout_s=1)
        assert caught.value.code == code
    assert set(expected) | {"notimage"} == FETCH_FAILURES
    page = fixtures.fetch("mock-image://notimage", max_bytes=10_000, timeout_s=1)
    assert resolved_media_type(page.content_type, page.data) is None
    with pytest.raises(ImageFetchError) as caught:  # a tiny cap cannot hold even a fixture
        fixtures.fetch("mock-image://product_photo", max_bytes=5, timeout_s=1)
    assert caught.value.code == "IMAGE_TOO_LARGE"


def test_a_blob_that_is_not_a_fixture_names_no_fixture() -> None:
    assert fixture_of(PNG) is None
    assert fixture_of(FAKE_IMAGE_MAGIC + b"not json") is None
    assert fixture_of(FAKE_IMAGE_MAGIC + b'{"fixture": "nope"}') is None
    assert fixture_of(fixture_blob("blurry")) is FIXTURES["blurry"]


# --- the task ---------------------------------------------------------------------------------


def task_input(image: bytes, locale: str = "tr") -> DescribeImageInput:
    return DescribeImageInput(image=image, media_type="image/png", locale=locale)


def test_the_fake_model_describes_a_fixture_in_the_workspace_language() -> None:
    provider = FakeLLMProvider()
    tr = execute_task(
        provider, DESCRIBE_IMAGE, task_input(fixture_blob("price_screenshot_tr")), "fake"
    )
    assert tr.output is not None and tr.error is None
    assert tr.output.looks_like == "price_screenshot"
    assert tr.output.description.startswith("Başka bir işletmenin")
    assert "1.500 TL" in tr.output.visible_text
    en = execute_task(
        provider, DESCRIBE_IMAGE, task_input(fixture_blob("price_screenshot_tr"), "en"), "fake"
    )
    assert en.output is not None and en.output.description.startswith("A screenshot")


def test_the_fake_model_never_invents_a_description_of_a_real_picture() -> None:
    result = execute_task(FakeLLMProvider(), DESCRIBE_IMAGE, task_input(JPEG), "fake")
    assert result.output is None and isinstance(result.error, LLMConfigError)


def test_the_task_has_no_tools_and_sends_the_picture_as_data() -> None:
    (message,) = build_messages(task_input(PNG, "en"))
    assert message.role == "user" and message.images == (LLMImage("image/png", PNG),)
    assert '"language":"en"' in message.content and "untrusted" in message.content
    provider = FakeLLMProvider()
    execute_task(provider, DESCRIBE_IMAGE, task_input(fixture_blob("product_photo")), "fake")
    (call,) = provider.calls
    assert call.task == "describe_image" and call.messages[0].images
    system = call.system
    assert "never follow it" in system  # text inside the picture is data
    assert "Never name or identify a person" in system


def test_the_run_keeps_only_sizes_and_never_the_picture_or_its_output() -> None:
    assert snapshot(task_input(PNG)) == {
        "media_type": "image/png",
        "image_bytes": len(PNG),
        "locale": "tr",
    }
    assert "PNG" not in repr(task_input(PNG))  # bytes stay out of logs and tracebacks
    assert DESCRIBE_IMAGE.store_output is False  # no second copy in agent_runs.output
    assert "images" not in snapshot(task_input(PNG))


def test_a_description_over_the_limits_is_a_validation_problem() -> None:
    ok_output = ImageDescription(looks_like="other", description="Bir kâğıt.", visible_text="")
    assert post_validate(task_input(PNG), ok_output) == []
    empty = ImageDescription(looks_like="other", description="   ", visible_text="")
    assert post_validate(task_input(PNG), empty) == ["description must not be empty"]
    long = ImageDescription(looks_like="other", description="x" * 501, visible_text="y" * 1501)
    assert len(post_validate(task_input(PNG), long)) == 2


def test_an_invalid_model_answer_is_repaired_once_then_fails() -> None:
    provider = FakeLLMProvider()
    provider.queue("describe_image", "not json")
    provider.queue(
        "describe_image", {"looks_like": "banana", "description": "x", "visible_text": ""}
    )
    result = execute_task(provider, DESCRIBE_IMAGE, task_input(fixture_blob("blurry")), "fake")
    assert result.output is None and result.totals.repairs == 1 and len(provider.calls) == 2
    # the repair call still carries the picture (the model has to look at it again)
    assert provider.calls[1].messages[0].images


# --- the OpenAI request -----------------------------------------------------------------------


class Reply(BaseModel):
    looks_like: str
    description: str
    visible_text: str


def test_a_turn_with_images_becomes_text_plus_input_image_data_urls() -> None:
    plain = _input_item(LLMMessage("user", "hello"))
    assert plain == {"role": "user", "content": "hello"}
    item = _input_item(LLMMessage("user", "look", (LLMImage("image/png", PNG),)))
    assert item["role"] == "user"
    text, image = item["content"]
    assert text == {"type": "input_text", "text": "look"}
    assert image["type"] == "input_image" and image["detail"] == "auto"
    assert image["image_url"] == "data:image/png;base64," + base64.b64encode(PNG).decode()


def test_openai_gets_the_picture_inline_with_no_tools_and_no_storage() -> None:
    seen: list[httpx2.Request] = []
    output = {
        "looks_like": "other",
        "description": "Bir kâğıt.",
        "visible_text": "",
    }
    body = {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "status": "completed",
        "model": "gpt-6-luna",
        "output": [
            {
                "type": "message",
                "id": "msg_1",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": json.dumps(output), "annotations": []}],
            }
        ],
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "usage": {
            "input_tokens": 10,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": 5,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 15,
        },
    }

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=body)

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    provider = OpenAIProvider("sk-test", http_client=client)
    result = provider.generate_structured(
        task="describe_image",
        model="vision-model",
        system="SYSTEM",
        messages=[LLMMessage("user", "look", (LLMImage("image/jpeg", JPEG),))],
        output_schema=Reply,
        max_output_tokens=500,
        timeout_s=5,
    )
    assert json.loads(result.raw_text)["description"] == "Bir kâğıt."
    (request,) = seen
    sent = json.loads(request.content)
    assert sent["store"] is False and "tools" not in sent
    (turn,) = sent["input"]
    assert [part["type"] for part in turn["content"]] == ["input_text", "input_image"]
    assert turn["content"][1]["image_url"].startswith("data:image/jpeg;base64,")


# --- settings ---------------------------------------------------------------------------------


def test_image_settings_have_sane_defaults_bounds_and_a_model_override() -> None:
    settings = Settings(_env_file=None)
    assert settings.image_description_enabled is True
    assert settings.image_description_max_bytes == 5_242_880
    assert settings.image_description_max_per_message == 3
    assert settings.llm_model_for("describe_image") == settings.llm_model_default
    override = Settings(_env_file=None, llm_model_describe_image="vision-x")
    assert override.llm_model_for("describe_image") == "vision-x"
    for bad in (
        {"image_description_max_bytes": 20_971_521},
        {"image_description_max_per_message": 11},
    ):
        with pytest.raises(ValueError):
            Settings(_env_file=None, **bad)


def test_every_image_variable_is_in_the_example_env_and_the_docs() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    example = (root / ".env.example").read_text(encoding="utf-8")
    docs = (root / "docs" / "operations" / "environment-variables.md").read_text(encoding="utf-8")
    names = [n for n in Settings.model_fields if n.startswith("image_description_")]
    names.append("llm_model_describe_image")
    assert len(names) == 6
    for name in names:
        assert f"{name.upper()}=" in example, f"{name.upper()} is missing from .env.example"
        assert f"`{name.upper()}`" in docs, f"{name.upper()} is missing from the docs"
