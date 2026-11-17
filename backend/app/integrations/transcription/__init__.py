"""Voice-note transcription: provider interface, fake and OpenAI implementations, audio fetch.

A job handler receives only a session factory and a clock, so the process-wide provider and
fetchers are resolved here (built once from ``TRANSCRIPTION_PROVIDER``; ``auto`` follows
``LLM_PROVIDER``). Tests swap them with ``override_transcription``. There is never a silent
fallback to the fake provider.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.integrations.transcription.base import (
    AudioClip,
    AudioFetcher,
    FetchedAudio,
    TranscriptionProvider,
    TranscriptionResult,
)
from app.integrations.transcription.fake import FakeTranscriptionProvider, FixtureAudioFetcher
from app.integrations.transcription.fetch import HttpsAudioFetcher


def build_transcriber(settings: Settings) -> TranscriptionProvider | None:
    """The provider selected by ``TRANSCRIPTION_PROVIDER``; ``None`` when transcription is off."""
    backend = settings.transcription_backend
    if backend == "off":
        return None
    if backend == "openai":
        # Imported here so the SDK is only loaded when the real provider is configured.
        from app.integrations.transcription.openai_provider import OpenAITranscriptionProvider

        return OpenAITranscriptionProvider(settings.openai_api_key.get_secret_value())
    return FakeTranscriptionProvider()


_transcriber_override: TranscriptionProvider | None = None
_settings_override: Settings | None = None
_fetcher_override: AudioFetcher | None = None
_mock_fetcher_override: AudioFetcher | None = None


@lru_cache
def _default_transcriber() -> TranscriptionProvider | None:
    return build_transcriber(get_settings())


def get_transcription_settings() -> Settings:
    return _settings_override or get_settings()


def get_transcriber() -> TranscriptionProvider | None:
    if _settings_override is not None and _transcriber_override is None:
        return build_transcriber(_settings_override)
    return _transcriber_override or _default_transcriber()


def transcription_enabled() -> bool:
    return get_transcription_settings().transcription_backend != "off"


def get_audio_fetcher(*, simulated: bool) -> AudioFetcher:
    """Mock accounts read only ``mock-audio://`` fixtures (no network); real accounts download
    over HTTPS from the Instagram CDN."""
    if simulated:
        return _mock_fetcher_override or FixtureAudioFetcher()
    return _fetcher_override or HttpsAudioFetcher()


@contextmanager
def override_transcription(
    *,
    transcriber: TranscriptionProvider | None = None,
    settings: Settings | None = None,
    fetcher: AudioFetcher | None = None,
    mock_fetcher: AudioFetcher | None = None,
) -> Iterator[None]:
    """Use these providers and settings for jobs run inside the block (tests)."""
    global _transcriber_override, _settings_override, _fetcher_override, _mock_fetcher_override
    saved = (_transcriber_override, _settings_override, _fetcher_override, _mock_fetcher_override)
    _transcriber_override = transcriber or _transcriber_override
    _settings_override = settings or _settings_override
    _fetcher_override = fetcher or _fetcher_override
    _mock_fetcher_override = mock_fetcher or _mock_fetcher_override
    try:
        yield
    finally:
        (
            _transcriber_override,
            _settings_override,
            _fetcher_override,
            _mock_fetcher_override,
        ) = saved


def reset_default_transcriber() -> None:
    """Forget the cached provider (after changing environment in tests)."""
    _default_transcriber.cache_clear()


__all__ = [
    "AudioClip",
    "AudioFetcher",
    "FakeTranscriptionProvider",
    "FetchedAudio",
    "FixtureAudioFetcher",
    "HttpsAudioFetcher",
    "TranscriptionProvider",
    "TranscriptionResult",
    "build_transcriber",
    "get_audio_fetcher",
    "get_transcriber",
    "get_transcription_settings",
    "override_transcription",
    "reset_default_transcriber",
    "transcription_enabled",
]
