"""Voice-note transcription pieces, offline: audio checks, the capped downloader (stub transport),
the fake provider and the OpenAI adapter (stub transport). No network, no key (INV-14)."""

import json
import struct
from collections.abc import Callable
from typing import Any

import httpx
import httpx2
import openai
import pytest

from app.core.config import ConfigError, Settings
from app.integrations.transcription import (
    FakeTranscriptionProvider,
    FixtureAudioFetcher,
    HttpsAudioFetcher,
    build_transcriber,
)
from app.integrations.transcription.audio import (
    FAKE_MAGIC,
    declared_type_allowed,
    extension_for,
    probe_duration_seconds,
    sniff_extension,
)
from app.integrations.transcription.base import AudioClip
from app.integrations.transcription.errors import (
    AudioFetchError,
    AudioRejected,
    TranscriptionConfigError,
    TranscriptionRejected,
    TranscriptionTransientError,
)
from app.integrations.transcription.fake import fixture_blob
from app.integrations.transcription.fetch import address_allowed, check_url, host_allowed
from app.integrations.transcription.openai_provider import OpenAITranscriptionProvider

GOOD_URL = "https://scontent-ist1-1.cdninstagram.com/v/t/voice.mp4?sig=secret"


def public_resolver(host: str, port: int, **kwargs: Any) -> list[Any]:
    return [(2, 1, 6, "", ("157.240.1.1", port))]


# --- fixtures of the audio containers ------------------------------------------------------


def mp4_clip(seconds: float, timescale: int = 1000) -> bytes:
    ftyp = struct.pack(">I4s4sI4s", 20, b"ftyp", b"M4A ", 0, b"M4A ")
    mvhd_body = struct.pack(">I", 0) + struct.pack(
        ">IIII", 0, 0, timescale, int(seconds * timescale)
    )
    mvhd = struct.pack(">I4s", 8 + len(mvhd_body), b"mvhd") + mvhd_body
    moov = struct.pack(">I4s", 8 + len(mvhd), b"moov") + mvhd
    return ftyp + moov + b"\x00" * 16


def wav_clip(seconds: float, byte_rate: int = 16000) -> bytes:
    fmt = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, byte_rate, 2, 16)
    data_size = int(seconds * byte_rate)
    return (
        b"RIFF"
        + struct.pack("<I", 36 + data_size)
        + b"WAVE"
        + fmt
        + b"data"
        + struct.pack("<I", data_size)
    )


def test_the_container_is_recognised_by_its_signature() -> None:
    assert sniff_extension(mp4_clip(3)) == "m4a"
    assert sniff_extension(wav_clip(1)) == "wav"
    assert sniff_extension(b"OggS\x00\x02" + b"\x00" * 20) == "ogg"
    assert sniff_extension(b"ID3\x04" + b"\x00" * 20) == "mp3"
    assert sniff_extension(b"<html>not audio</html>") is None
    assert sniff_extension(b"") is None


def test_the_duration_is_read_from_mp4_and_wav_and_unknown_otherwise() -> None:
    assert probe_duration_seconds(mp4_clip(12.5)) == pytest.approx(12.5)
    assert probe_duration_seconds(mp4_clip(7, timescale=44100)) == pytest.approx(7)
    assert probe_duration_seconds(wav_clip(2.0)) == pytest.approx(2.0)
    assert probe_duration_seconds(b"OggS\x00\x02" + b"\x00" * 20) is None
    assert probe_duration_seconds(b"ftyp") is None  # truncated: never raises


def test_a_truncated_or_hostile_mp4_never_raises() -> None:
    broken = struct.pack(">I4s", 12, b"ftyp") + b"M4A " + struct.pack(">I4s", 2**31, b"moov")
    assert probe_duration_seconds(broken) is None
    assert probe_duration_seconds(struct.pack(">I4s", 0, b"moov")) is None


def test_the_declared_type_must_be_audio_and_agree_with_the_signature() -> None:
    assert declared_type_allowed("audio/mp4; codecs=mp4a.40.2")
    assert declared_type_allowed("application/octet-stream")
    assert not declared_type_allowed("text/html")
    assert not declared_type_allowed(None)
    assert extension_for("audio/mp4", mp4_clip(1)) == "m4a"
    assert extension_for("video/mp4", mp4_clip(1)) == "mp4"
    assert extension_for("application/octet-stream", mp4_clip(1)) == "m4a"
    assert extension_for("audio/wav", mp4_clip(1)) is None  # a lie about the container
    assert extension_for("audio/mp4", b"<html>") is None


# --- the downloader ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://scontent.cdninstagram.com/a.mp4",  # not https
        "https://evil.example.com/a.mp4",  # host not allowed
        "https://cdninstagram.com.evil.example/a.mp4",  # a look-alike host
        "https://user:pw@scontent.cdninstagram.com/a.mp4",  # credentials
        "https://scontent.cdninstagram.com:8443/a.mp4",  # port
        "https://169.254.169.254/latest/meta-data",  # metadata address
        "file:///etc/passwd",
        "mock-audio://price_question_tr",
        "",
    ],
)
def test_the_downloader_refuses_urls_that_are_not_the_instagram_cdn(url: str) -> None:
    with pytest.raises(AudioFetchError) as caught:
        check_url(url, public_resolver)
    assert caught.value.code == "VOICE_URL_REFUSED"


def test_a_host_that_resolves_to_a_private_address_is_refused() -> None:
    def private(host: str, port: int, **kwargs: Any) -> list[Any]:
        return [(2, 1, 6, "", ("10.0.0.5", port))]

    with pytest.raises(AudioFetchError) as caught:
        check_url(GOOD_URL, private)
    assert caught.value.code == "VOICE_URL_REFUSED"


def test_an_unresolvable_host_is_a_retryable_download_failure() -> None:
    def broken(host: str, port: int, **kwargs: Any) -> list[Any]:
        raise OSError("dns")

    with pytest.raises(AudioFetchError) as caught:
        check_url(GOOD_URL, broken)
    assert (caught.value.code, caught.value.retryable) == ("VOICE_DOWNLOAD_FAILED", True)


def test_addresses_and_hosts() -> None:
    assert host_allowed("scontent.cdninstagram.com") and host_allowed("x.fbcdn.net")
    assert not host_allowed("cdninstagram.com") and not host_allowed("fbcdn.net.evil.io")
    assert address_allowed("157.240.1.1") and not address_allowed("127.0.0.1")
    assert not address_allowed("::ffff:10.0.0.1") and not address_allowed("fe80::1")


def fetcher(
    handler: Callable[[httpx.Request], httpx.Response], clock: Callable[[], float] | None = None
) -> HttpsAudioFetcher:
    kwargs: dict[str, Any] = {"transport": httpx.MockTransport(handler)}
    if clock is not None:
        kwargs["monotonic"] = clock
    return HttpsAudioFetcher(resolver=public_resolver, **kwargs)


def ok(content: bytes, content_type: str = "audio/mp4", **headers: str) -> httpx.Response:
    return httpx.Response(200, content=content, headers={"content-type": content_type, **headers})


def test_a_voice_note_is_downloaded_with_no_credentials_and_no_redirects() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return ok(mp4_clip(4))

    result = fetcher(handler).fetch(GOOD_URL, max_bytes=1_000_000, timeout_s=5)
    assert result.content_type == "audio/mp4" and sniff_extension(result.data) == "m4a"
    (request,) = seen
    assert "authorization" not in {k.lower() for k in request.headers}
    assert "cookie" not in {k.lower() for k in request.headers}


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (403, "VOICE_EXPIRED", False),
        (404, "VOICE_EXPIRED", False),
        (410, "VOICE_EXPIRED", False),
        (302, "VOICE_URL_REFUSED", False),
        (429, "VOICE_DOWNLOAD_FAILED", True),
        (503, "VOICE_DOWNLOAD_FAILED", True),
        (400, "VOICE_DOWNLOAD_FAILED", False),
    ],
)
def test_http_failures_map_to_reason_codes(status: int, code: str, retryable: bool) -> None:
    with pytest.raises(AudioFetchError) as caught:
        fetcher(lambda r: httpx.Response(status)).fetch(GOOD_URL, max_bytes=1000, timeout_s=5)
    assert (caught.value.code, caught.value.retryable) == (code, retryable)
    assert "secret" not in str(caught.value)  # the signed URL never reaches an error


def test_a_network_error_is_retryable_and_does_not_leak_the_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(AudioFetchError) as caught:
        fetcher(handler).fetch(GOOD_URL, max_bytes=1000, timeout_s=5)
    assert caught.value.retryable and "secret" not in str(caught.value)


def test_a_declared_length_over_the_cap_is_refused_before_the_body_is_read() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "audio/mp4", "content-length": "5000"}, content=b"x"
        )

    with pytest.raises(AudioRejected) as caught:
        fetcher(handler).fetch(GOOD_URL, max_bytes=1000, timeout_s=5)
    assert caught.value.code == "VOICE_TOO_LARGE"


def test_a_body_that_lies_about_its_length_is_cut_off_at_the_cap() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "audio/mp4"}, content=b"x" * 5000)

    with pytest.raises(AudioRejected) as caught:
        fetcher(handler).fetch(GOOD_URL, max_bytes=1000, timeout_s=5)
    assert caught.value.code == "VOICE_TOO_LARGE"


def test_a_page_that_is_not_audio_is_refused() -> None:
    with pytest.raises(AudioRejected) as caught:
        fetcher(lambda r: ok(b"<html>", "text/html")).fetch(GOOD_URL, max_bytes=1000, timeout_s=5)
    assert caught.value.code == "VOICE_UNSUPPORTED_TYPE"


def test_a_slow_trickle_hits_the_total_deadline() -> None:
    ticks = iter(range(0, 1000, 100))

    def handler(request: httpx.Request) -> httpx.Response:
        return ok(b"x" * 300_000)

    with pytest.raises(AudioFetchError) as caught:
        fetcher(handler, clock=lambda: float(next(ticks))).fetch(
            GOOD_URL, max_bytes=1_000_000, timeout_s=5
        )
    assert caught.value.retryable


# --- the fake provider and the mock fetcher ---------------------------------------------------


def test_the_mock_fetcher_reads_fixtures_and_never_the_network() -> None:
    fixtures = FixtureAudioFetcher()
    got = fixtures.fetch("mock-audio://price_question_tr", max_bytes=10_000, timeout_s=1)
    assert got.data.startswith(FAKE_MAGIC)
    for url in ("https://scontent.cdninstagram.com/a.mp4", "mock-audio://"):
        with pytest.raises(AudioFetchError) as caught:
            fixtures.fetch(url, max_bytes=10_000, timeout_s=1)
        assert caught.value.code == "VOICE_URL_REFUSED"
    with pytest.raises(AudioFetchError) as caught:
        fixtures.fetch("mock-audio://expired", max_bytes=10_000, timeout_s=1)
    assert caught.value.code == "VOICE_EXPIRED"
    with pytest.raises(AudioFetchError) as caught:
        fixtures.fetch("mock-audio://price_question_tr", max_bytes=5, timeout_s=1)
    assert caught.value.code == "VOICE_TOO_LARGE"


def test_the_fake_provider_is_deterministic_and_never_invents_text_for_real_audio() -> None:
    provider = FakeTranscriptionProvider()
    clip = AudioClip(fixture_blob("price_question_tr"), "audio/mp4", 6.0)
    first = provider.transcribe_audio(clip, model="m", timeout_s=1)
    second = provider.transcribe_audio(clip, model="m", timeout_s=1)
    assert first.text == second.text == "Merhaba, aylık üyelik ücreti ne kadar acaba?"
    assert (first.language, first.is_fake, first.provider) == ("tr", True, "fake")
    with pytest.raises(TranscriptionConfigError):
        provider.transcribe_audio(AudioClip(mp4_clip(3), "audio/mp4", 3), model="m", timeout_s=1)


def test_the_fake_provider_can_be_scripted() -> None:
    provider = FakeTranscriptionProvider()
    provider.queue(TranscriptionTransientError("down"))
    clip = AudioClip(fixture_blob("silence"), "audio/mp4", 3.0)
    with pytest.raises(TranscriptionTransientError):
        provider.transcribe_audio(clip, model="m", timeout_s=1)
    assert provider.transcribe_audio(clip, model="m", timeout_s=1).text == ""


# --- the OpenAI adapter against a stub transport ---------------------------------------------


def openai_provider(
    handler: Callable[[httpx2.Request], httpx2.Response],
) -> tuple[OpenAITranscriptionProvider, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def record(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return handler(request)

    client = httpx2.Client(transport=httpx2.MockTransport(record))
    return OpenAITranscriptionProvider("sk-test", http_client=client), seen


def json_response(status: int, body: dict[str, Any], **headers: str) -> httpx2.Response:
    return httpx2.Response(status, content=json.dumps(body).encode(), headers=headers)


CLIP = AudioClip(mp4_clip(5), "audio/mp4", 5.0)


def test_openai_sends_only_the_audio_and_returns_the_text() -> None:
    provider, seen = openai_provider(lambda r: json_response(200, {"text": " Merhaba dünya "}))
    result = provider.transcribe_audio(CLIP, model="gpt-4o-mini-transcribe", timeout_s=5)
    assert (result.text, result.provider, result.model) == (
        "Merhaba dünya",
        "openai",
        "gpt-4o-mini-transcribe",
    )
    assert not result.is_fake
    (request,) = seen
    assert request.url.path.endswith("/audio/transcriptions")
    body = request.read()
    assert b'name="model"' in body and b"gpt-4o-mini-transcribe" in body
    assert b'filename="voice.m4a"' in body
    assert b"json" in body  # response_format
    assert b'name="prompt"' not in body and b'name="language"' not in body


def test_openai_whisper_asks_for_verbose_json_and_reads_language_and_duration() -> None:
    provider, seen = openai_provider(
        lambda r: json_response(
            200, {"text": "hello", "language": "english", "duration": 4.2, "segments": []}
        )
    )
    result = provider.transcribe_audio(CLIP, model="whisper-1", timeout_s=5)
    assert (result.language, result.duration_seconds) == ("english", 4.2)
    assert b"verbose_json" in seen[0].read()


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (429, TranscriptionTransientError),
        (500, TranscriptionTransientError),
        (503, TranscriptionTransientError),
        (401, TranscriptionConfigError),
        (403, TranscriptionConfigError),
        (404, TranscriptionConfigError),
        (400, TranscriptionRejected),
        (422, TranscriptionRejected),
    ],
)
def test_openai_errors_become_typed_errors(status: int, error: type[Exception]) -> None:
    provider, _ = openai_provider(
        lambda r: json_response(
            status, {"error": {"message": "x", "type": "t"}}, **{"retry-after": "7"}
        )
    )
    with pytest.raises(error) as caught:
        provider.transcribe_audio(CLIP, model="m", timeout_s=5)
    assert "sk-test" not in str(caught.value)
    if status == 429:
        assert caught.value.retry_after_seconds == 7  # type: ignore[attr-defined]


def test_openai_connection_errors_are_transient() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("down", request=request)

    provider, _ = openai_provider(handler)
    with pytest.raises(TranscriptionTransientError):
        provider.transcribe_audio(CLIP, model="m", timeout_s=5)


def test_openai_refuses_a_clip_it_cannot_name_without_calling() -> None:
    provider, seen = openai_provider(lambda r: json_response(200, {"text": "x"}))
    with pytest.raises(TranscriptionRejected):
        provider.transcribe_audio(AudioClip(b"<html>", "audio/mp4", None), model="m", timeout_s=5)
    assert seen == []
    assert openai.__version__  # the SDK is importable only here and in the LLM adapter


# --- settings ----------------------------------------------------------------------------------


def make(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg, arg-type]


def test_auto_follows_the_llm_provider_and_off_disables() -> None:
    assert make().transcription_backend == "fake"
    assert make(llm_provider="openai", openai_api_key="sk-x").transcription_backend == "openai"
    assert make(transcription_provider="off").transcription_backend == "off"
    assert build_transcriber(make(transcription_provider="off")) is None
    assert isinstance(build_transcriber(make()), FakeTranscriptionProvider)
    assert isinstance(
        build_transcriber(make(transcription_provider="openai", openai_api_key="sk-x")),
        OpenAITranscriptionProvider,
    )


def test_openai_transcription_needs_a_key_and_production_refuses_the_fake() -> None:
    with pytest.raises(ConfigError):
        make(transcription_provider="openai")
    with pytest.raises(ConfigError) as caught:
        make(app_env="production", transcription_provider="fake")
    assert "TRANSCRIPTION_PROVIDER must be 'openai' or 'off' in production" in str(caught.value)


def test_limits_have_sane_bounds() -> None:
    settings = make()
    assert settings.transcription_max_audio_bytes == 10_485_760
    assert settings.transcription_max_audio_seconds == 120
    assert settings.transcription_model == "gpt-4o-mini-transcribe"
    with pytest.raises(ValueError):
        make(transcription_max_audio_bytes=30_000_000)
