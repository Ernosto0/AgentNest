"""Provider error taxonomy (integrations.md §3.1).

Adapters translate every provider failure into exactly one of these. The ambiguity rule
decides between :class:`ProviderOutcomeUnknown` and :class:`ProviderTransientError`: if the
request **may have been accepted** (a read timeout after the request was sent, a 5xx on a
``messages``/``media_publish`` call, a connection reset after the body was sent) raise
``OutcomeUnknown``; raise ``Transient`` only when it certainly did not reach processing.
"""


class ProviderError(Exception):
    """Base class. ``code`` is a stable machine-readable detail for logs and the ledger."""

    code = "PROVIDER_ERROR"

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        super().__init__(detail or self.code)


class ProviderTransientError(ProviderError):
    """Certainly not processed (connection refused, 503 before processing). Safe to retry."""

    code = "PROVIDER_UNAVAILABLE"


class ProviderRateLimited(ProviderError):
    code = "PROVIDER_RATE_LIMITED"

    def __init__(self, retry_after_s: int | None = None, detail: str = "") -> None:
        self.retry_after_s = retry_after_s
        super().__init__(detail)


class ProviderAuthError(ProviderError):
    """The token is invalid or revoked: the account needs re-authorisation."""

    code = "ACCOUNT_NEEDS_REAUTH"


class ProviderPermissionError(ProviderError):
    """A required permission/scope is missing: the capability is unavailable."""

    code = "CAPABILITY_MISSING"


class ProviderInvalidRequest(ProviderError):
    """The provider rejected the request itself (text too long, bad recipient, bad media)."""

    code = "PROVIDER_REJECTED"

    def __init__(self, request_code: str = "", detail: str = "") -> None:
        self.request_code = request_code
        super().__init__(detail or request_code)


class ProviderWindowClosed(ProviderError):
    """The 24 h customer-service window is closed: the message cannot be sent."""

    code = "MESSAGING_WINDOW_CLOSED"


class ProviderOutcomeUnknown(ProviderError):
    """The request may or may not have been accepted. Reconcile; never resend (INV-05)."""

    code = "OUTCOME_UNKNOWN"
