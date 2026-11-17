import pytest

from app.integrations.web.urls import FetchRefused, parse_site_url


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "gopher://example.com",
        "https://user:pass@example.com",
        "http://example.com:8080",
        "https://example.com:22",
        "http://example.com:6379",
        "https://example.com:8443",
        "https://example.com:80",
        *[
            "http://" + host
            for host in [
                "127.0.0.1",
                "[::1]",
                "[::ffff:127.0.0.1]",
                "169.254.169.254",
                "2130706433",
                "0x7f000001",
                "0x7f.1",
                "017700000001",
                "0177.0.0.1",
                "127.1",
                "1.1.1.1",
                "localhost",
                "foo.localhost",
                "x.internal",
                "local",
                "foo.local",
                "x.localdomain",
                "x.lan",
                "x.home.arpa",
                "x.intranet",
                "a..com",
                "a" * 64 + ".com",
                "bad_host.com",
                "127。0。0。1",
                "1。1。1。1",
                "example.com..",
            ]
        ],
        "https://example.com/" + "x" * 2000,
    ],
)
def test_refused(url):
    with pytest.raises(FetchRefused) as caught:
        parse_site_url(url)
    assert str(caught.value) == caught.value.reason
    assert url not in str(caught.value)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Example.COM.  ", "https://example.com/"),
        ("http://example.com:80", "http://example.com/"),
        ("https://example.com:443/x?q=abc#secret", "https://example.com/x?q=abc"),
        ("https://örnek.com", "https://xn--rnek-4qa.com/"),
    ],
)
def test_normalized(raw, expected):
    parsed = parse_site_url(raw)
    assert parsed.url == expected
    assert parsed.port in (80, 443)
