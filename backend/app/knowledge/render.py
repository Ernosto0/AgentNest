"""Placeholder rendering (business-knowledge.md §7.1, INV-02).

Critical values reach customer-facing or published text only through ``{{fact:<key>}}``
placeholders that **code** replaces with the value of a *usable* fact. The renderer records the
exact character span of every inserted value, which the claim validator needs: values inside
those spans are trusted, everything else is checked.

Rendering is all-or-nothing: an unknown or unusable key is an error (``FACT_NOT_USABLE``) and
no partial text is returned, so a half-grounded sentence can never be sent by accident.
"""

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from app.core.i18n import DEFAULT_LOCALE
from app.knowledge.formatting import format_money_amount, format_value

# ``{{fact:<key>}}`` or ``{{fact:<key>|short}}``; the key shape is the fact-key pattern.
PLACEHOLDER = re.compile(
    r"\{\{\s*fact:(?P<key>[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)(?:\|(?P<fmt>[a-z]+))?\s*\}\}"
)
KNOWN_FORMATS = frozenset({"short"})

FACT_NOT_USABLE = "FACT_NOT_USABLE"
PLACEHOLDER_INVALID = "PLACEHOLDER_INVALID"


class RenderableFact(Protocol):
    """The part of a usable fact the renderer needs (``knowledge.service.UsableFact`` fits)."""

    @property
    def fact_id(self) -> uuid.UUID: ...
    @property
    def key(self) -> str: ...
    @property
    def value_type(self) -> str: ...
    @property
    def value(self) -> dict[str, Any]: ...
    @property
    def version(self) -> int: ...


@dataclass(frozen=True)
class RenderedSpan:
    """One inserted value: ``text[start:end]`` of the final text."""

    key: str
    fact_id: uuid.UUID
    version: int
    start: int
    end: int
    display: str


@dataclass(frozen=True)
class RenderError:
    code: str  # FACT_NOT_USABLE | PLACEHOLDER_INVALID
    key: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class RenderResult:
    text: str
    used: tuple[tuple[uuid.UUID, int], ...] = ()  # (fact_id, version), first use order
    spans: tuple[RenderedSpan, ...] = ()
    errors: tuple[RenderError, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def used_keys(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for span in self.spans:
            seen.setdefault(span.key)
        return tuple(seen)


def placeholder_keys(template: str) -> list[str]:
    """Keys referenced by ``template``, in order of first appearance (duplicates removed)."""
    seen: dict[str, None] = {}
    for match in PLACEHOLDER.finditer(template):
        seen.setdefault(match.group("key"))
    return list(seen)


def _display(fact: RenderableFact, fmt: str | None, locale: str, fallback_locale: str) -> str:
    if fmt == "short" and fact.value_type == "money":
        return format_money_amount(
            Decimal(str(fact.value["amount"])), str(fact.value["currency"]), locale
        )
    return format_value(fact.value_type, fact.value, locale, fallback_locale)


def render(
    template: str,
    usable_facts: Iterable[RenderableFact],
    locale: str,
    *,
    fallback_locale: str = DEFAULT_LOCALE,
) -> RenderResult:
    """Replace every placeholder with the fact's value formatted for ``locale``.

    ``usable_facts`` must be the *usable* facts only (``knowledge.service.usable_facts``): a
    key that is not in the collection is treated as not usable, whatever the reason.
    """
    by_key = {fact.key: fact for fact in usable_facts}
    errors: list[RenderError] = []
    pieces: list[str] = []
    spans: list[RenderedSpan] = []
    used: dict[tuple[uuid.UUID, int], None] = {}
    cursor = 0
    length = 0

    for match in PLACEHOLDER.finditer(template):
        before = template[cursor : match.start()]
        pieces.append(before)
        length += len(before)
        cursor = match.end()
        key, fmt = match.group("key"), match.group("fmt")
        if fmt is not None and fmt not in KNOWN_FORMATS:
            errors.append(RenderError(PLACEHOLDER_INVALID, key, f"unknown format {fmt!r}"))
            continue
        fact = by_key.get(key)
        if fact is None:
            errors.append(RenderError(FACT_NOT_USABLE, key))
            continue
        shown = _display(fact, fmt, locale, fallback_locale)
        pieces.append(shown)
        spans.append(
            RenderedSpan(key, fact.fact_id, fact.version, length, length + len(shown), shown)
        )
        length += len(shown)
        used.setdefault((fact.fact_id, fact.version))
    tail = template[cursor:]
    pieces.append(tail)

    # Anything that still looks like a template token was malformed: never let it through.
    if "{{" in tail or "}}" in tail or any("{{" in p or "}}" in p for p in pieces[:-1]):
        errors.append(RenderError(PLACEHOLDER_INVALID, None, "malformed placeholder"))
    if errors:
        return RenderResult(text="", errors=tuple(errors))
    return RenderResult(
        text="".join(pieces),
        used=tuple(used),
        spans=tuple(spans),
    )
