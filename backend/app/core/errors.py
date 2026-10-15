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
