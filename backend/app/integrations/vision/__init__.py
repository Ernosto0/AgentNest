"""Image download for the customer-image description task (F-03, Session 03).

A job handler receives only a session factory and a clock, so the process-wide fetchers are
resolved here. Tests swap them with ``override_vision``. Mock accounts read only ``mock-image://``
fixtures (no network); real accounts download over HTTPS from the Instagram CDN. The model call
itself is ``app.ai.tasks.describe_image`` (the LLM provider), not part of this package.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from app.integrations.vision.base import FetchedImage, ImageFetcher
from app.integrations.vision.fake import FixtureImageFetcher
from app.integrations.vision.fetch import HttpsImageFetcher

_fetcher_override: ImageFetcher | None = None
_mock_fetcher_override: ImageFetcher | None = None


def get_image_fetcher(*, simulated: bool) -> ImageFetcher:
    if simulated:
        return _mock_fetcher_override or FixtureImageFetcher()
    return _fetcher_override or HttpsImageFetcher()


@contextmanager
def override_vision(
    *, fetcher: ImageFetcher | None = None, mock_fetcher: ImageFetcher | None = None
) -> Iterator[None]:
    """Use these fetchers for jobs run inside the block (tests)."""
    global _fetcher_override, _mock_fetcher_override
    saved = (_fetcher_override, _mock_fetcher_override)
    _fetcher_override = fetcher or _fetcher_override
    _mock_fetcher_override = mock_fetcher or _mock_fetcher_override
    try:
        yield
    finally:
        _fetcher_override, _mock_fetcher_override = saved


__all__ = [
    "FetchedImage",
    "FixtureImageFetcher",
    "HttpsImageFetcher",
    "ImageFetcher",
    "get_image_fetcher",
    "override_vision",
]
