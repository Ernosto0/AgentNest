"""Deterministic Gölkent Fitness fixture; never opens sockets or resolves DNS."""

from urllib.parse import urlsplit

from app.integrations.web.safe_fetch import FetchedPage
from app.integrations.web.urls import FetchRefused, parse_site_url

_PAGES = {
    "/": (
        '<h1>Gölkent Fitness</h1><p>Bucak / Burdur spor salonu.</p><a href="/fiya'
        'tlar">Fiyatlar</a><a href="/iletisim">İletişim</a><a href="/hakkimizda">'
        'Hakkımızda</a><a href="/blog">Blog</a><a href="https://external.example/'
        '">Dış bağlantı</a>'
    ),
    "/fiyatlar": (
        "<h1>Üyelik fiyatları</h1><p>Aylık üyelik 6.000 TL</p><p>3 aylık üyelik 16.500 TL</p>"
    ),
    "/iletisim": (
        '<h1>İletişim</h1><p>Tel: <a href="tel:05551234567">0555 123 45 67</a></p'
        '><p><a href="mailto:info@golkent-fitness.example">E-posta</a></p><addres'
        "s>Bucak / Burdur</address><p>Çalışma saatleri: Pazartesi-Cumartesi 09:00"
        "-22:00</p>"
    ),
    "/hakkimizda": (
        "<p>Gölkent Fitness, Bucak / Burdur bölgesinde bireysel antrenman ve grup"
        " dersleri sunar.</p>"
    ),
}


class FakeWebsiteFetcher:
    simulated = True

    def fetch(self, url: str) -> FetchedPage:
        parsed = parse_site_url(url)
        if parsed.host.endswith(".invalid"):
            raise FetchRefused("dns", host=parsed.host)
        html = _PAGES.get(urlsplit(parsed.url).path)
        if html is None:
            raise FetchRefused("status", host=parsed.host)
        return FetchedPage(
            parsed.url,
            parsed.host,
            parsed.host,
            200,
            "text/html; charset=utf-8",
            html.encode("utf-8"),
            0,
        )
