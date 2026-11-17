"""Bounded HTML text and navigation extraction using the standard library."""

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit


@dataclass(frozen=True)
class PageLink:
    url: str
    anchor: str


@dataclass(frozen=True)
class PageText:
    text: str
    links: list[PageLink]


MAX_DEPTH = 256  # bounds the cost of a hostile page that nests elements without closing them
_BLOCKS = {
    "p",
    "div",
    "li",
    "br",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "tr",
    "section",
    "header",
    "footer",
    "address",
    "table",
    "article",
    "main",
    "aside",
    "ul",
    "ol",
    "dl",
    "dt",
    "dd",
    "blockquote",
    "hr",
    "pre",
}
_DROP = {"script", "style", "noscript", "template", "svg"}
_VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class _Parser(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        # (tag, suppressed, in <head>, in <title>); flags are inherited, so no per-event stack scan
        self.stack: list[tuple[str, bool, bool, bool]] = []
        self.parts: list[str] = []
        self.title: list[str] = []
        self.description = ""
        self.links: list[PageLink] = []
        self.seen: set[str] = set()
        self.anchor: tuple[str, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        suppressed = (
            (self.stack[-1][1] if self.stack else False) or tag in _DROP or "hidden" in values
        )
        if not suppressed and tag == "meta" and (values.get("name") or "").lower() == "description":
            self.description = values.get("content") or ""
        if tag not in _VOID and len(self.stack) < MAX_DEPTH:
            parent_head, parent_title = (
                (self.stack[-1][2], self.stack[-1][3]) if self.stack else (False, False)
            )
            self.stack.append(
                (tag, suppressed, parent_head or tag == "head", parent_title or tag == "title")
            )
        if suppressed or (self.stack and self.stack[-1][2]):
            return
        if tag in _BLOCKS:
            self.parts.append("\n")
        if tag in ("td", "th"):
            self.parts.append(" | ")
        if tag == "a":
            self.anchor = (values.get("href") or "", [])

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        suppressed = bool(self.stack) and (self.stack[-1][1] or self.stack[-1][2])
        if not suppressed:
            if tag in _BLOCKS:
                self.parts.append("\n")
            if tag == "a" and self.anchor:
                href, text = self.anchor
                self.anchor = None
                if href.lower().startswith(("tel:", "mailto:")):
                    self.parts.append(" (" + href[:80] + ")")
                try:
                    url = urldefrag(urljoin(self.base, href))[0]
                    allowed = urlsplit(url).scheme in ("http", "https")
                except ValueError:
                    allowed = False
                if allowed and url not in self.seen and len(self.links) < 200:
                    self.seen.add(url)
                    self.links.append(PageLink(url, " ".join("".join(text).split())))
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data: str) -> None:
        if self.stack and self.stack[-1][1]:
            return
        in_head, in_title = (self.stack[-1][2], self.stack[-1][3]) if self.stack else (False, False)
        if in_title:
            self.title.append(data)
        elif not in_head:
            self.parts.append(data)
            if self.anchor:
                self.anchor[1].append(data)


class _CharsetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.encoding: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta" or self.encoding is not None:
            return
        values = dict(attrs)
        if values.get("charset"):
            self.encoding = values["charset"]
        elif (values.get("http-equiv") or "").lower() == "content-type":
            match = re.search(
                r"charset\s*=\s*[\"']?([^\s;\"'/>]+)", values.get("content") or "", re.I
            )
            if match:
                self.encoding = match.group(1)


def extract_page(body: bytes, content_type: str, base_url: str) -> PageText:
    charset = re.search(r"charset\s*=\s*[\"']?([^\s;\"'/>]+)", content_type, re.I)
    metadata = _CharsetParser()
    if not charset:
        metadata.feed(body[:2048].decode("ascii", errors="ignore"))
    encoding = charset.group(1) if charset else metadata.encoding or "utf-8"
    try:
        html = body.decode(encoding, errors="replace")
    except LookupError:
        html = body.decode("utf-8", errors="replace")
    parser = _Parser(base_url)
    parser.feed(html)
    lines: list[str] = []
    used = 0
    for raw in ["".join(parser.title), parser.description, *"".join(parser.parts).splitlines()]:
        line = " ".join(raw.split()).strip(" |")
        if not line or (lines and line == lines[-1]):
            continue
        if used + len(line) + bool(lines) > 20000:
            break
        lines.append(line)
        used += len(line) + (len(lines) > 1)
    return PageText("\n".join(lines), parser.links)


def chunk_text(text: str, size: int = 700) -> list[str]:
    if size < 1:
        raise ValueError("size must be positive")
    chunks: list[str] = []
    current = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if current and len(current) + len(line) + 1 <= size:
            current += "\n" + line
            continue
        if current:
            chunks.append(current)
            current = ""
        while len(line) > size:
            cut = max(line.rfind(" ", 0, size + 1), line.rfind(". ", 0, size))
            if cut <= 0:
                cut = size
            chunks.append(line[:cut].strip())
            line = line[cut:].strip()
        current = line
    if current:
        chunks.append(current)
    return chunks
