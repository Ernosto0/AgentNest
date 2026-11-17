"""Select the offline demo or live pinned fetcher from explicit settings."""

from app.core.config import Settings
from app.integrations.web.fake import FakeWebsiteFetcher
from app.integrations.web.safe_fetch import PageFetcher, SafeFetcher


def get_page_fetcher(settings: Settings) -> PageFetcher:
    kind = settings.website_import_fetcher
    if kind == "auto":
        kind = "fake" if settings.llm_provider == "fake" else "live"
    return FakeWebsiteFetcher() if kind == "fake" else SafeFetcher()
