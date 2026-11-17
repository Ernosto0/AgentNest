"""Typed image-download errors. The job maps ``code`` to the stored reason code.

Reason codes (stored on ``message_image_descriptions.reason_code``; none contains customer
content or a URL):

====================================  ==========================================================
``IMAGE_URL_MISSING``                 the attachment has no URL
``IMAGE_URL_REFUSED``                 not https, host not allowed, not a public address, redirect
``IMAGE_EXPIRED``                     the CDN answered 401, 403, 404 or 410 (the link has expired)
``IMAGE_DOWNLOAD_FAILED``             timeout, 5xx, 429 or another HTTP failure after retries
``IMAGE_TOO_LARGE``                   more than ``IMAGE_DESCRIPTION_MAX_BYTES``
``IMAGE_UNSUPPORTED_TYPE``            content type or file signature is not JPEG, PNG or WebP
``IMAGE_EMPTY``                       the download had no bytes
``IMAGE_DESCRIPTION_REJECTED``        the model refused it or returned an invalid description
``IMAGE_DESCRIPTION_UNAVAILABLE``     provider down, timed out, rate limited or misconfigured
``IMAGE_QUOTA_EXCEEDED``              the per-workspace image limit or the daily LLM budget
                                      was reached
``IMAGE_SOURCE_GONE``                 the message was deleted or erased before the description
                                      was stored
====================================  ==========================================================
"""


class ImageError(Exception):
    """Base class. ``code`` is the stable reason code; ``retryable`` asks the job to retry."""

    code = "IMAGE_DESCRIPTION_UNAVAILABLE"
    retryable = False

    def __init__(self, code: str | None = None, *, retryable: bool | None = None) -> None:
        super().__init__(code or self.code)
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable


class ImageFetchError(ImageError):
    """The image could not be obtained. Messages carry only the code, never the URL."""

    code = "IMAGE_DOWNLOAD_FAILED"


class ImageRejected(ImageError):
    """The image itself is unusable (too large, wrong type, empty)."""

    code = "IMAGE_UNSUPPORTED_TYPE"
