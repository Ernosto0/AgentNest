"""Typed transcription and audio-fetch errors. The job maps ``code`` to the stored reason code.

Reason codes (stored on ``message_transcripts.reason_code``; none contains customer content):

====================================  ==========================================================
``VOICE_URL_MISSING``                 the attachment has no URL
``VOICE_URL_REFUSED``                 not https, host not allowed, not a public address, redirect
``VOICE_EXPIRED``                     the CDN answered 403, 404 or 410 (the link has expired)
``VOICE_DOWNLOAD_FAILED``             timeout, 5xx, 429 or another HTTP failure after retries
``VOICE_TOO_LARGE``                   more than ``TRANSCRIPTION_MAX_AUDIO_BYTES``
``VOICE_TOO_LONG``                    longer than ``TRANSCRIPTION_MAX_AUDIO_SECONDS``
``VOICE_UNSUPPORTED_TYPE``            content type or file signature is not a supported audio
``VOICE_EMPTY_AUDIO``                 the download had no bytes
``VOICE_NO_SPEECH``                   the provider returned no text
``VOICE_TRANSCRIPTION_REJECTED``      the provider refused the audio (a bad request)
``VOICE_TRANSCRIPTION_UNAVAILABLE``   provider down, timed out, rate limited or misconfigured
``VOICE_QUOTA_EXCEEDED``              ``TRANSCRIPTION_MAX_PER_WORKSPACE_PER_DAY`` reached
``VOICE_SOURCE_GONE``                 the message was deleted or erased before the transcript
                                      was stored
====================================  ==========================================================
"""


class VoiceError(Exception):
    """Base class. ``code`` is the stable reason code; ``retryable`` asks the job to retry."""

    code = "VOICE_TRANSCRIPTION_UNAVAILABLE"
    retryable = False

    def __init__(self, code: str | None = None, *, retryable: bool | None = None) -> None:
        super().__init__(code or self.code)
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable


class AudioFetchError(VoiceError):
    """The audio could not be obtained. Messages carry only the code, never the URL."""

    code = "VOICE_DOWNLOAD_FAILED"


class AudioRejected(VoiceError):
    """The audio itself is unusable (too large, too long, wrong type, empty)."""

    code = "VOICE_UNSUPPORTED_TYPE"


class TranscriptionError(VoiceError):
    """The provider call failed."""


class TranscriptionTransientError(TranscriptionError):
    """Timeout, 429, 5xx or connection failure: the job retries with backoff."""

    code = "VOICE_TRANSCRIPTION_UNAVAILABLE"
    retryable = True

    def __init__(self, detail: str | None = None, *, retry_after_seconds: float | None = None):
        super().__init__(self.code, retryable=True)
        self.detail = detail
        self.retry_after_seconds = retry_after_seconds


class TranscriptionConfigError(TranscriptionError):
    """Bad credentials, a missing permission or an unknown model. Retrying cannot help, and
    there is no silent fallback to the fake provider."""

    code = "VOICE_TRANSCRIPTION_UNAVAILABLE"


class TranscriptionRejected(TranscriptionError):
    """The provider rejected this audio (invalid or unsupported file)."""

    code = "VOICE_TRANSCRIPTION_REJECTED"
