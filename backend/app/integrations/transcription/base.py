"""The speech-to-text provider contract (F-03, Feature Phase 2; ADR-009 spirit).

A transcription provider is a small interface of its own, next to the LLM provider and not part
of it: it takes audio bytes and returns text. It has no tools, it never sees customer metadata
(no handle, no conversation, no workspace), and it is called only from a background job with no
database transaction open (INV, background-jobs.md section 5). Its text is untrusted customer
content: it is data, never instructions (INV-03).
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AudioClip:
    """One downloaded voice note, held in memory only. ``content_type`` is already checked."""

    data: bytes
    content_type: str
    duration_seconds: float | None  # from the container; ``None`` when it cannot be read


@dataclass(frozen=True)
class FetchedAudio:
    """The bytes of a download and the content type the server declared."""

    data: bytes
    content_type: str


class AudioFetcher(Protocol):
    def fetch(self, url: str, *, max_bytes: int, timeout_s: float) -> FetchedAudio:
        """Download ``url`` into memory, never more than ``max_bytes``. Raises ``AudioFetchError``
        (and ``AudioRejected`` for a size or type problem); the URL never appears in a message."""
        ...


@dataclass(frozen=True)
class TranscriptionResult:
    """What a provider returned. ``language`` is the provider's own ISO 639-1 guess, if any."""

    text: str
    language: str | None
    duration_seconds: float | None  # as reported by the provider, if it reports one
    provider: str
    model: str
    is_fake: bool
    latency_ms: int


class TranscriptionProvider(Protocol):
    name: str
    is_fake: bool

    def transcribe_audio(
        self, clip: AudioClip, *, model: str, timeout_s: float
    ) -> TranscriptionResult:
        """Transcribe one clip. Raises ``TranscriptionError`` subclasses; never returns partial
        or invented text."""
        ...
