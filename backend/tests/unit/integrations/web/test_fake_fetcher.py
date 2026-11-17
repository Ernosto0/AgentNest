import socket

import pytest

from app.core.config import ConfigError, Settings
from app.integrations.web.fake import FakeWebsiteFetcher
from app.integrations.web.registry import get_page_fetcher
from app.integrations.web.safe_fetch import SafeFetcher
from app.integrations.web.urls import FetchRefused


def test_offline_deterministic(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("no socket or DNS permitted")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    fake = FakeWebsiteFetcher()
    assert fake.simulated
    for path in ("/", "/fiyatlar", "/iletisim", "/hakkimizda"):
        url = "http://gym.example" + path
        assert fake.fetch(url) == fake.fetch(url)
        assert fake.fetch(url).url == url
    for url, reason in [
        ("http://127.0.0.1", "ip_literal"),
        ("https://gym.invalid", "dns"),
        ("https://gym.example/blog", "status"),
    ]:
        with pytest.raises(FetchRefused, match=reason):
            fake.fetch(url)


def test_registry_and_production_safety():
    assert isinstance(get_page_fetcher(Settings(llm_provider="fake")), FakeWebsiteFetcher)
    assert isinstance(get_page_fetcher(Settings(website_import_fetcher="live")), SafeFetcher)
    with pytest.raises(ConfigError, match="WEBSITE_IMPORT_FETCHER"):
        Settings(app_env="production", website_import_fetcher="fake")
