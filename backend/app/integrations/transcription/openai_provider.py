"""OpenAI speech-to-text adapter (``audio.transcriptions``).

- One call per voice note, no tools, no prompt text, no customer metadata: only the audio.
- ``max_retries=0``: retry policy belongs to the job (10 s / 60 s / 300 s), not here.
- ``gpt-4o*-transcribe`` models accept only ``json`` output (no language, no duration);
  ``whisper-1`` is asked for ``verbose_json`` so it also reports both.
- This module imports the ``openai`` SDK next to the LLM adapter; import-linter allows both.
- **Never run against the real API** in this repository's tests (no key is used); the model ID
  is configuration (``TRANSCRIPTION_MODEL``).
"""

import time

import httpx2 as httpx
import openai
from openai.types.audio import Transcription, TranscriptionVerbose

from app.integrations.transcription.audio import extension_for
from app.integrations.transcription.base import AudioClip, TranscriptionResult
from app.integrations.transcription.errors import (
    TranscriptionConfigError,
    TranscriptionRejected,
    TranscriptionTransientError,
)

_RETRY_AFTER = "retry-after"


def _retry_after(exc: openai.RateLimitError) -> float | None:
    value = exc.response.headers.get(_RETRY_AFTER) if exc.response is not None else None
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


class OpenAITranscriptionProvider:
    name = "openai"
    is_fake = False

    def __init__(self, api_key: str, *, http_client: httpx.Client | None = None) -> None:
        self._client = openai.OpenAI(api_key=api_key, max_retries=0, http_client=http_client)

    def transcribe_audio(
        self, clip: AudioClip, *, model: str, timeout_s: float
    ) -> TranscriptionResult:
        extension = extension_for(clip.content_type, clip.data)
        if extension is None:
            raise TranscriptionRejected()
        started = time.monotonic()
        verbose = model.startswith("whisper")
        response: Transcription | TranscriptionVerbose
        try:
            if verbose:
                response = self._client.audio.transcriptions.create(
                    model=model,
                    file=(f"voice.{extension}", clip.data, clip.content_type),
                    response_format="verbose_json",
                    timeout=timeout_s,
                )
            else:
                response = self._client.audio.transcriptions.create(
                    model=model,
                    file=(f"voice.{extension}", clip.data, clip.content_type),
                    response_format="json",
                    timeout=timeout_s,
                )
        except openai.APITimeoutError as exc:
            raise TranscriptionTransientError("timeout") from exc
        except openai.APIConnectionError as exc:
            raise TranscriptionTransientError("connection error") from exc
        except openai.RateLimitError as exc:
            raise TranscriptionTransientError(
                "rate limited", retry_after_seconds=_retry_after(exc)
            ) from exc
        except openai.InternalServerError as exc:
            raise TranscriptionTransientError(f"server error {exc.status_code}") from exc
        except (openai.AuthenticationError, openai.PermissionDeniedError, openai.NotFoundError):
            raise TranscriptionConfigError() from None
        except (openai.BadRequestError, openai.UnprocessableEntityError):
            raise TranscriptionRejected() from None
        except openai.APIStatusError:
            raise TranscriptionConfigError() from None

        text = getattr(response, "text", None)
        if not isinstance(text, str):
            raise TranscriptionRejected()
        language = getattr(response, "language", None)
        duration = getattr(response, "duration", None)
        return TranscriptionResult(
            text=text.strip(),
            language=language if isinstance(language, str) else None,
            duration_seconds=float(duration) if isinstance(duration, int | float) else None,
            provider=self.name,
            model=model,
            is_fake=False,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
