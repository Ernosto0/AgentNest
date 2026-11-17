from app.integrations.web.html_text import chunk_text, extract_page


def extract(html, content_type="text/html"):
    return extract_page(html.encode(), content_type, "https://example.com/base/")


def test_text_and_links():
    page = extract("""<html><head><title>Başlık</title>
    <meta name="description" content="Açıklama"><p>HEAD</p></head>
    <script>BAD</script><style>BAD</style><noscript>BAD</noscript>
    <template>BAD</template><svg>BAD</svg>
    <div hidden><p>BAD</p><span>BAD</span></div>
    <p>ş ğ ı İ &amp; &ouml;</p><p>Tekrar</p><p>Tekrar</p>
    <table><tr><td>İlk</td><th>Son</th></tr></table>
    <a href="tel:05551234567">Telefon</a><a href="mailto:a@example.com">Posta</a>
    <a href="../fiyatlar#id">Fiyatlar</a><a href="../fiyatlar">Aynı</a>
    <a href="javascript:evil">Yok</a>""")
    assert page.text.startswith("Başlık\nAçıklama\n")
    assert "BAD" not in page.text and "HEAD" not in page.text
    assert "ş ğ ı İ & ö" in page.text and "İlk | Son" in page.text
    assert "Telefon (tel:05551234567)" in page.text
    assert "Posta (mailto:a@example.com)" in page.text
    assert page.text.count("Tekrar") == 1
    assert [(link.url, link.anchor) for link in page.links] == [
        ("https://example.com/fiyatlar", "Fiyatlar")
    ]


def test_charsets():
    html = '<meta charset="windows-1254"><p>ş ğ ı İ</p>'
    assert (
        extract_page(html.encode("windows-1254"), "text/html", "https://example.com").text
        == "ş ğ ı İ"
    )
    assert (
        extract_page(
            "<p>ş ğ ı İ</p>".encode("iso-8859-9"),
            "text/html; charset=iso-8859-9",
            "https://example.com",
        ).text
        == "ş ğ ı İ"
    )
    assert extract("<p>ş</p>", "text/html; charset=unknown").text == "ş"
    html = '<meta http-equiv="Content-Type" content="text/html; charset=windows-1254"><p>ş</p>'
    assert extract_page(html.encode("windows-1254"), "text/html", "https://example.com").text == "ş"


def test_caps_and_malformed():
    html = "".join(f"<p>{i}:" + "x" * 100 + "</p>" for i in range(400))
    page = extract(html)
    assert 19000 < len(page.text) <= 20000
    assert all(line.endswith("x" * 100) for line in page.text.splitlines())
    page = extract("".join(f'<a href="/{i}">{i}</a>' for i in range(300)))
    assert len(page.links) == 200
    assert extract('<div><p>hello</div><a href="http://[bad">bad</a>').text


def test_chunking():
    assert chunk_text("one\ntwo\nthree", 7) == ["one\ntwo", "three"]
    chunks = chunk_text("word " * 600)
    assert all(0 < len(chunk) <= 700 for chunk in chunks)
    assert " ".join(chunks) == ("word " * 600).strip()
    assert chunk_text("a" * 1401) == ["a" * 700, "a" * 700, "a"]
    assert chunk_text("") == []


def test_charset_comes_only_from_metadata_and_header_wins():
    html = "<script>charset=windows-1254</script><p>ş ğ ı İ</p>"
    assert extract(html).text == "ş ğ ı İ"
    assert extract('<meta charset="windows-1254"><p>ş</p>', "text/html; charset=utf-8").text == "ş"
    assert not extract('<head><a href="/contact">Hidden link</a></head><p>Visible</p>').links


def test_deeply_nested_page_is_bounded():
    import time

    start = time.monotonic()
    page = extract("<div>a" * 100_000 + "<p>Price 100 TL</p>")
    assert time.monotonic() - start < 5
    assert "a" in page.text
