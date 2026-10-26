"""Typed LLM provider errors (ADR-009, agent-runtime.md §2).

The task runner maps these to ``TaskOutcome`` error codes; adapters never decide retry policy.
"""

from app.integrations.llm.base import LLMUsage


class LLMError(Exception):
    """Base class. ``code`` is the stable app error code the runner reports."""

    code = "LLM_UNAVAILABLE"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or self.code)
        self.detail = detail


class LLMTransientError(LLMError):
    """Timeout, 429, 5xx or connection failure: the *job* retries with backoff."""

    code = "LLM_UNAVAILABLE"

    def __init__(self, detail: str | None = None, *, retry_after_seconds: float | None = None):
        super().__init__(detail)
        self.retry_after_seconds = retry_after_seconds


class LLMRefusal(LLMError):
    """The model refused or the content was filtered. Routed to a human, never retried."""

    code = "LLM_REFUSED"


class LLMConfigError(LLMError):
    """Bad credentials, missing permission or a rejected request. Retrying cannot help, and
    there is no silent fallback to the fake provider (ADR-009)."""

    code = "LLM_UNAVAILABLE"


class LLMInvalidOutput(LLMError):
    """The provider returned something that is not valid JSON for the schema, or was cut off.
    ``raw_text`` (if any) is given back to the model once in the repair call."""

    code = "LLM_OUTPUT_INVALID"

    def __init__(
        self,
        detail: str | None = None,
        *,
        raw_text: str | None = None,
        usage: LLMUsage | None = None,
    ) -> None:
        super().__init__(detail)
        self.raw_text = raw_text
        self.usage = usage
