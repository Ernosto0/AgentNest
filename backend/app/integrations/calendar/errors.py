"""Provider error taxonomy for Calendar adapters."""


class CalendarProviderError(Exception):
    """Base class. ``code`` is a stable machine-readable detail for logs and the ledger."""

    code = "CALENDAR_PROVIDER_ERROR"

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        super().__init__(detail or self.code)


class CalendarTransientError(CalendarProviderError):
    """Certainly not processed (connection refused, 503 before processing). Safe to retry."""

    code = "PROVIDER_UNAVAILABLE"


class CalendarRateLimited(CalendarProviderError):
    code = "PROVIDER_RATE_LIMITED"

    def __init__(self, retry_after_s: int | None = None, detail: str = "") -> None:
        self.retry_after_s = retry_after_s
        super().__init__(detail)


class CalendarAuthError(CalendarProviderError):
    """The token is invalid or revoked: the calendar connection needs re-authorisation."""

    code = "ACCOUNT_NEEDS_REAUTH"


class CalendarPermissionError(CalendarProviderError):
    """A required permission/scope is missing: the capability is unavailable."""

    code = "CAPABILITY_MISSING"


class CalendarInvalidRequest(CalendarProviderError):
    """The provider rejected the request itself (bad time range, event not found, etc.)."""

    code = "PROVIDER_REJECTED"

    def __init__(self, request_code: str = "", detail: str = "") -> None:
        self.request_code = request_code
        super().__init__(detail or request_code)


class CalendarOutcomeUnknown(CalendarProviderError):
    """The request may or may not have been accepted. Reconcile; never duplicate (INV-05)."""

    code = "OUTCOME_UNKNOWN"
