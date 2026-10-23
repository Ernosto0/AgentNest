"""Error code catalog (single source; observability.md §4).

Every code has an HTTP status (if API-facing), a retryable flag and i18n keys
``errors.<CODE>.what`` and ``errors.<CODE>.next`` in both catalogs (a test enforces this).
Codes used only by later phases are added by those phases.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ErrorSpec:
    http_status: int | None
    retryable: bool | None = None  # None: not applicable


ERROR_CATALOG: dict[str, ErrorSpec] = {
    "AUTH_REQUIRED": ErrorSpec(401),
    "INVALID_CREDENTIALS": ErrorSpec(401),
    "CSRF_FAILED": ErrorSpec(403),
    "FORBIDDEN": ErrorSpec(403),
    "NOT_FOUND": ErrorSpec(404),
    "VALIDATION_FAILED": ErrorSpec(422),
    "CONFLICT_STATE": ErrorSpec(409),
    "VERSION_CONFLICT": ErrorSpec(409),
    "FACT_VERSION_CONFLICT": ErrorSpec(409),
    "APPROVAL_ALREADY_DECIDED": ErrorSpec(409),
    "APPROVAL_EXPIRED": ErrorSpec(409),
    "APPROVAL_STALE": ErrorSpec(409),
    "MESSAGING_WINDOW_CLOSED": ErrorSpec(409),
    "ACCOUNT_NOT_CONNECTED": ErrorSpec(409),
    "INVITE_INVALID": ErrorSpec(400),
    "OAUTH_STATE_INVALID": ErrorSpec(400),
    "ACCOUNT_MISMATCH": ErrorSpec(409),
    "LAST_OWNER_REQUIRED": ErrorSpec(409),
    "REPORT_EVIDENCE_UNAVAILABLE": ErrorSpec(409),
    "REPORT_SOURCES_RETAINED_OUT": ErrorSpec(409),
    # Submitting content: the blocking item codes are in params.errors / the problem's ``errors``.
    "CONTENT_VALIDATION_FAILED": ErrorSpec(422),
    "MEDIA_INVALID": ErrorSpec(422),
    "MEDIA_TOO_LARGE": ErrorSpec(413),
    # Not API errors: why a publish failed (``content_items.last_error_code``, shown by
    # ``query.explain_failure`` and the content screen) and what a command could not find.
    "MEDIA_REJECTED": ErrorSpec(None, retryable=False),
    "PUBLISH_DEADLINE_PASSED": ErrorSpec(None, retryable=False),
    "PUBLISH_QUOTA_EXHAUSTED": ErrorSpec(None, retryable=True),
    "PROVIDER_UNAVAILABLE": ErrorSpec(None, retryable=True),
    "PROVIDER_RATE_LIMITED": ErrorSpec(None, retryable=True),
    "PROVIDER_REJECTED": ErrorSpec(None, retryable=False),
    "CAPABILITY_MISSING": ErrorSpec(None, retryable=False),
    "ACCOUNT_NEEDS_REAUTH": ErrorSpec(None, retryable=False),
    "OUTCOME_UNKNOWN": ErrorSpec(None),  # reconciled, not retried
    "OUTCOME_UNCONFIRMED": ErrorSpec(None, retryable=False),
    "REFERENCE_NOT_FOUND": ErrorSpec(None),
    # Not API errors: reasons recorded on commands, agent runs and render results.
    "FACT_NOT_USABLE": ErrorSpec(None, retryable=False),
    "FACT_CHANGED_MEANWHILE": ErrorSpec(None, retryable=False),
    "LLM_UNAVAILABLE": ErrorSpec(None, retryable=True),
    "LLM_OUTPUT_INVALID": ErrorSpec(None, retryable=False),
    "LLM_REFUSED": ErrorSpec(None, retryable=False),
    "LLM_BUDGET_EXCEEDED": ErrorSpec(None, retryable=False),
    "JOB_PAYLOAD_INVALID": ErrorSpec(None, retryable=False),
    "INTERNAL_ERROR": ErrorSpec(500),
}


class AppError(Exception):
    """A domain/API error identified by a catalog code plus machine-readable params."""

    def __init__(self, code: str, http_status: int | None = None, **params: Any) -> None:
        if code not in ERROR_CATALOG:
            raise ValueError(f"Unknown error code: {code}")
        super().__init__(code)
        self.code = code
        self.http_status = http_status or ERROR_CATALOG[code].http_status
        self.params = params


class RetryableError(Exception):
    """Raised by a job handler to request a retry with backoff (background-jobs.md §3)."""

    def __init__(
        self,
        code: str,
        detail: str | None = None,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail
        self.retry_after_seconds = retry_after_seconds
