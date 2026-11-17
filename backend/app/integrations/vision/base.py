"""Fetching the images customers send (F-03, Feature Phase 2, Session 03).

Describing an image is an LLM task (``app.ai.tasks.describe_image``, no tools), so there is no
vision provider interface here: this package only gets the bytes. The image is downloaded by a
background job with no database transaction open, held in memory, never stored. Its content,
including any text inside it, is untrusted customer data (INV-03).
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FetchedImage:
    """The bytes of a download and the content type the server declared."""

    data: bytes
    content_type: str


class ImageFetcher(Protocol):
    def fetch(self, url: str, *, max_bytes: int, timeout_s: float) -> FetchedImage:
        """Download ``url`` into memory, never more than ``max_bytes``. Raises ``ImageFetchError``
        (and ``ImageRejected`` for a size or type problem); the URL never appears in a message."""
        ...
