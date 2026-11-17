"""Deterministic offline transcription and audio fixtures (INV-14: no key, no network).

The mock Instagram provider produces voice notes whose URL is ``mock-audio://<fixture>``. The
fixture fetcher turns that into a small in-memory "audio" blob that names its fixture and its
duration, and the fake provider reads the blob back and returns the fixture's transcript. Audio
that is not a fixture blob (anything real) is refused: the fake provider never invents a
transcript for real speech.

Failure fixtures let the demo and the tests exercise every failure path without a network:
``expired``, ``unreachable``, ``oversize``, ``notaudio`` (fetcher) and ``toolong`` (a fixture
whose duration is above any sensible cap).
"""

import json
import time
from collections import deque
from dataclasses import dataclass

from app.integrations.transcription.audio import FAKE_MAGIC
from app.integrations.transcription.base import AudioClip, FetchedAudio, TranscriptionResult
from app.integrations.transcription.errors import (
    AudioFetchError,
    TranscriptionConfigError,
    TranscriptionRejected,
)

MOCK_AUDIO_SCHEME = "mock-audio://"


@dataclass(frozen=True)
class Fixture:
    text: str
    language: str | None
    duration_seconds: float


FIXTURES: dict[str, Fixture] = {
    "price_question_tr": Fixture("Merhaba, aylık üyelik ücreti ne kadar acaba?", "tr", 6.0),
    "hours_question_tr": Fixture(
        "Selam, pazar günleri açık mısınız, kaçta kapanıyorsunuz?", "tr", 7.5
    ),
    "disfluent_tr": Fixture(
        "Şey ıı merhaba yani randevu almak istiyordum da ııı yarın akşam uygun mu acaba",
        "tr",
        9.0,
    ),
    "english_question": Fixture("Hi, do you have any free spot tomorrow afternoon?", "en", 5.0),
    "silence": Fixture("", None, 3.0),
    "toolong": Fixture("Çok uzun bir ses kaydı.", "tr", 900.0),
}

FETCH_FAILURES = frozenset({"expired", "unreachable", "oversize", "notaudio"})


def fixture_name(url: str | None) -> str | None:
    if not url or not url.startswith(MOCK_AUDIO_SCHEME):
        return None
    return url[len(MOCK_AUDIO_SCHEME) :].strip("/") or None


def fixture_blob(name: str) -> bytes:
    """The in-memory stand-in for the audio file of a fixture."""
    fixture = FIXTURES[name]
    meta = {"fixture": name, "duration": fixture.duration_seconds}
    return FAKE_MAGIC + json.dumps(meta).encode("utf-8")


class FixtureAudioFetcher:
    """The fetcher for mock accounts: resolves only ``mock-audio://`` URLs, never the network."""

    def fetch(self, url: str, *, max_bytes: int, timeout_s: float) -> FetchedAudio:
        name = fixture_name(url)
        if name is None:
            raise AudioFetchError("VOICE_URL_REFUSED")
        if name == "expired":
            raise AudioFetchError("VOICE_EXPIRED")
        if name == "unreachable":
            raise AudioFetchError("VOICE_DOWNLOAD_FAILED", retryable=True)
        if name == "oversize":
            raise AudioFetchError("VOICE_TOO_LARGE")
        if name == "notaudio":
            return FetchedAudio(b"<html>not audio</html>", "text/html")
        if name not in FIXTURES:
            raise AudioFetchError("VOICE_EXPIRED")  # an unknown fixture behaves like a gone file
        data = fixture_blob(name)
        if len(data) > max_bytes:
            raise AudioFetchError("VOICE_TOO_LARGE")
        return FetchedAudio(data, "audio/mp4")


Scripted = TranscriptionResult | Exception


class FakeTranscriptionProvider:
    name = "fake"
    is_fake = True

    def __init__(self) -> None:
        self._queued: deque[Scripted] = deque()
        self.calls: list[AudioClip] = []
        self.models: list[str] = []

    def queue(self, item: Scripted) -> None:
        """Override the next call (FIFO): a result, or an exception to raise."""
        self._queued.append(item)

    def reset(self) -> None:
        self._queued.clear()
        self.calls.clear()
        self.models.clear()

    def transcribe_audio(
        self, clip: AudioClip, *, model: str, timeout_s: float
    ) -> TranscriptionResult:
        started = time.monotonic()
        self.calls.append(clip)
        self.models.append(model)
        if self._queued:
            scripted = self._queued.popleft()
            if isinstance(scripted, Exception):
                raise scripted
            return scripted
        if not clip.data.startswith(FAKE_MAGIC):
            raise TranscriptionConfigError()  # the fake never invents text for real audio
        try:
            meta = json.loads(clip.data[len(FAKE_MAGIC) :].decode("utf-8"))
            fixture = FIXTURES[str(meta["fixture"])]
        except (ValueError, KeyError, UnicodeDecodeError):
            raise TranscriptionRejected() from None
        return TranscriptionResult(
            text=fixture.text,
            language=fixture.language,
            duration_seconds=fixture.duration_seconds,
            provider=self.name,
            model="fake",
            is_fake=True,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
