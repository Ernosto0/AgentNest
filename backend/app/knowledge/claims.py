"""Claim validator (business-knowledge.md §7.2, INV-02).

Scans the **final** text for critical values that did not come from a rendered placeholder:
money, percentages and discount words, times, dates, phone numbers, e-mails and URLs, and
any other number above the small-number allow-list. Values inside the renderer's spans and
the code-appended disclosure suffix are excluded; any match outside them is an issue.

Values the model *copies* from placeholders cannot be wrong (code inserts them); values it
*invents* match a pattern class and fail here. Matching runs on a length-preserving,
diacritic-insensitive Turkish fold, so every issue span indexes the original text.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.knowledge.render import RenderResult

# --- result types ---------------------------------------------------------------------------

MONEY = "MONEY"
PERCENT = "PERCENT"
DISCOUNT_WORD = "DISCOUNT_WORD"
TIME = "TIME"
DATE = "DATE"
PHONE = "PHONE"
EMAIL = "EMAIL"
URL = "URL"
NUMBER = "NUMBER"
TOO_LONG = "TOO_LONG"


@dataclass(frozen=True)
class ClaimIssue:
    code: str
    start: int
    end: int
    text: str

    @property
    def span(self) -> tuple[int, int]:
        return (self.start, self.end)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "span": [self.start, self.end], "text": self.text}


@dataclass(frozen=True)
class ClaimReport:
    issues: tuple[ClaimIssue, ...] = field(default=())

    @property
    def passed(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "issues": [issue.to_dict() for issue in self.issues]}


@dataclass(frozen=True)
class AllowList:
    """What may appear outside rendered spans. Configurable per locale."""

    small_number_max: int = 20
    # Exact phrases (compared on folded text) that are never claims, e.g. a brand name that
    # contains digits. Empty by default: a phrase here is a deliberate hole in INV-02.
    phrases: tuple[str, ...] = ()


ALLOW_LISTS: dict[str, AllowList] = {"tr": AllowList(), "en": AllowList()}

# --- folding --------------------------------------------------------------------------------

_FOLD = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def fold(text: str) -> str:
    """Lower case without Turkish diacritics, **same length as ``text``**.

    (``İ`` is mapped first: its plain ``lower()`` expands to two code points.)
    """
    folded = text.replace("İ", "i").replace("I", "i").lower().translate(_FOLD)
    return folded if len(folded) == len(text) else text.lower()


# --- patterns (applied to folded text) ------------------------------------------------------

_CUR_WORD = (
    r"(?<![a-z])(?:tl|try|lira|liras|eur|euro|euros|usd|dolar|dollars?|gbp|pounds?|sterlin)"
    r"(?![a-z])"
)
_CUR = rf"(?:₺|€|\$|£|{_CUR_WORD})"
_NUM = r"\d+(?:[.,\s]\d+)*"
_MULT = r"(?:bin|k|milyon|thousand|million)"

_MONTHS = (
    r"(?:ocak|subat|mart|nisan|mayis|haziran|temmuz|agustos|eylul|ekim|kasim|aralik"
    r"|january|february|march|april|may|june|july|august|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)"
)
_DAY = r"(?:0?[1-9]|[12]\d|3[01])"

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (code, re.compile(pattern))
    for code, pattern in (
        (EMAIL, r"[a-z0-9._%+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}"),
        (URL, r"(?:https?://|www\.)[^\s<>\"']*[^\s<>\"'.,;:!?)\]]"),
        (
            URL,
            r"(?<![@\w.-])(?:[a-z0-9-]+\.)+(?:com|net|org|io|me|app|co|tr|info|biz|gov|edu)"
            r"(?![a-z])(?:/[^\s<>\"']*[^\s<>\"'.,;:!?)\]])?",
        ),
        (
            PHONE,
            r"(?<!\d)(?:\+|00)\s*\d[\d\s().-]{7,}\d(?!\d)"
            r"|(?<!\d)0\s*\(?\d{3}\)?[\s.-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}(?!\d)",
        ),
        (MONEY, rf"{_NUM}\s*(?:{_MULT}\s*)?{_CUR}"),
        (MONEY, rf"{_CUR}\s*{_NUM}"),
        (
            PERCENT,
            r"%\s*\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?\s*%|yuzde\s*\d+|\d+\s*(?:percent|per\s*cent)",
        ),
        (
            TIME,
            r"(?<!\d)(?:[01]?\d|2[0-4])\s*[:.]\s*[0-5]\d(?!\d)"
            r"|(?<!\d)\d{1,2}\s*(?:am|pm|a\.m\.|p\.m\.)(?![a-z])"
            r"|(?<![a-z])saat\s*\d{1,2}(?!\d)"
            r"|(?<!\d)\d{1,2}\s*[-–—]\s*\d{1,2}\s*(?:arasi|arasinda|saatleri|saatler|hours|o'?clock)"
            r"|(?<!\d)\d{1,2}\s*ile\s*\d{1,2}(?!\d)"
            r"|(?<!\d)\d{1,2}\s*['’]?\s*(?:den|dan|ten|tan)\s+\d{1,2}\s*['’]?\s*(?:e|a|ye|ya)(?![a-z])"
            r"|between\s+\d{1,2}\s+and\s+\d{1,2}(?!\d)"
            r"|(?<!\d)\d{1,2}\s*o'?clock",
        ),
        (
            DATE,
            rf"(?<!\d){_DAY}(?:st|nd|rd|th)?\.?\s*{_MONTHS}(?![a-z])"
            rf"|(?<![a-z]){_MONTHS}\s+{_DAY}(?!\d)"
            rf"|(?<!\d){_DAY}[./](?:0?[1-9]|1[0-2])(?:[./](?:\d{{4}}|\d{{2}}))?(?![\d])"
            r"|(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)",
        ),
        (
            DISCOUNT_WORD,
            r"(?<![a-z])(?:indirim\w*|bedava\w*|ucretsiz\w*|discount\w*|complimentary|free(?![a-z]))",
        ),
    )
)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_PRIORITY = (EMAIL, URL, PHONE, MONEY, PERCENT, TIME, DATE, DISCOUNT_WORD)


def byte_length(text: str) -> int:
    """UTF-8 length: the Instagram DM limit is in bytes, not characters (INV-11)."""
    return len(text.encode("utf-8"))


def length_issue(
    text: str, *, max_bytes: int | None = None, max_chars: int | None = None
) -> ClaimIssue | None:
    """An issue when ``text`` exceeds a limit (callers include any suffix in ``text``)."""
    too_long = (max_bytes is not None and byte_length(text) > max_bytes) or (
        max_chars is not None and len(text) > max_chars
    )
    return ClaimIssue(TOO_LONG, 0, len(text), "") if too_long else None


def _overlaps(taken: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(start < b and a < end for a, b in taken)


def validate_claims(
    text: str,
    render_result: RenderResult,
    locale: str,
    *,
    allow_suffix_span: tuple[int, int] | None = None,
    allow: AllowList | None = None,
) -> ClaimReport:
    """Report every critical value in ``text`` that is not inside a rendered span.

    ``allow_suffix_span`` is the span of the disclosure suffix that code appended (never the
    model). ``locale`` selects the allow-list. Issue spans index ``text``.
    """
    rules = allow or ALLOW_LISTS.get(locale, AllowList())
    trusted: list[tuple[int, int]] = [(s.start, s.end) for s in render_result.spans]
    if allow_suffix_span is not None:
        trusted.append(allow_suffix_span)
    rendered_values = {fold(s.display) for s in render_result.spans}
    promotion_used = any(s.key.startswith("promotion.") for s in render_result.spans)

    # Mask trusted spans with spaces so neighbouring text cannot merge into a match.
    chars = list(fold(text))
    for start, end in trusted:
        for index in range(max(start, 0), min(end, len(chars))):
            chars[index] = " "
    masked = "".join(chars)
    for phrase in rules.phrases:
        masked = masked.replace(fold(phrase), " " * len(phrase))

    found: list[ClaimIssue] = []
    taken: list[tuple[int, int]] = []
    for code in _PRIORITY:
        for pattern_code, pattern in _PATTERNS:
            if pattern_code != code:
                continue
            for match in pattern.finditer(masked):
                start, end = match.span()
                matched = text[start:end].strip()
                if end == start or not matched or _overlaps(taken, start, end):
                    continue
                if code in (URL, EMAIL) and fold(matched) in rendered_values:
                    continue  # the exact value of a rendered fact, typed out
                if code == DISCOUNT_WORD and promotion_used:
                    continue  # backed by a usable promotion fact used in the same text
                taken.append((start, end))
                found.append(ClaimIssue(code, start, end, text[start:end]))

    for match in _NUMBER.finditer(masked):  # remaining numbers: small cardinals are fine
        start, end = match.span()
        if _overlaps(taken, start, end):
            continue
        literal = match.group()
        if literal.isdigit() and int(literal) <= rules.small_number_max:
            continue
        found.append(ClaimIssue(NUMBER, start, end, text[start:end]))

    found.sort(key=lambda issue: (issue.start, issue.end))
    return ClaimReport(tuple(found))


__all__: list[str] = [
    "ALLOW_LISTS",
    "AllowList",
    "ClaimIssue",
    "ClaimReport",
    "byte_length",
    "fold",
    "length_issue",
    "validate_claims",
]
