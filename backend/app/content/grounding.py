"""Claim validation of the texts of a content item and its ``fact_references`` (INV-02).

The texts of an item (caption, overlay suggestions) are **rendered** text (plan.md G6): a
generated caption already holds the display value of the facts it used, and a person's edit is
plain text. The stored text has no rendered spans, so the validator scans it for critical
values and every one it finds is an issue.

An issue is **grounded** when its value is the current display of a verified, usable fact
(``matches_verified``): the same whole-token matcher the owner's own replies use
(``inbox.service.text_warnings``), made strict for content because here the result decides
whether the text may be submitted. A grounded value is recorded as a ``fact_references`` row, so
a later change of that fact reaches the item (impact analysis, P5-07), and does not block. A
value that matches no current verified fact (invented, rounded, or the old price after a change)
stays blocking, and so does a ``{{fact:key}}`` that was never rendered.

Discount words (``ücretsiz``, ``free``, ...) are grounded only the way the validator grounds
them in rendered text: when the text holds the whole display of a verified ``promotion.*`` fact.
"""

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.knowledge import service as knowledge_service
from app.knowledge.claims import DISCOUNT_WORD, fold, validate_claims
from app.knowledge.render import PLACEHOLDER, RenderResult
from app.knowledge.service import UsableFact

# A ``{{fact:key}}`` that is still in the stored text would be published as it is: the stored
# text is the rendered text (plan.md G6), so a placeholder here was never rendered.
PLACEHOLDER_UNRENDERED = "PLACEHOLDER_UNRENDERED"
# A commercial claim the model made that no rendered fact backs (agent-runtime.md section 5).
CLAIM_UNBACKED = "CLAIM_UNBACKED"


@dataclass(frozen=True)
class Grounding:
    report: dict[str, Any]  # what ``content_items.validation`` stores
    references: tuple[tuple[uuid.UUID, int], ...]  # (fact_id, version)

    @property
    def blocking(self) -> list[dict[str, Any]]:
        """The issues that stop a submission: every one that is not a verified value."""
        return [i for i in self.report["issues"] if not i["matches_verified"]]


def texts_of(caption: str | None, overlay_text_suggestions: list[str]) -> dict[str, str]:
    """The checked texts by field name: ``caption`` and ``overlay_text_suggestions.{index}``."""
    texts: dict[str, str] = {}
    if caption:
        texts["caption"] = caption
    for index, suggestion in enumerate(overlay_text_suggestions):
        if suggestion:
            texts[f"overlay_text_suggestions.{index}"] = suggestion
    return texts


def _is_token(haystack: str, start: int, end: int) -> bool:
    """``haystack[start:end]`` is not part of a longer word or number (``500 ₺`` is not in
    ``1.500 ₺``, ``07:00`` is not in ``107:00``)."""
    before = haystack[start - 1] if start > 0 else ""
    after = haystack[end] if end < len(haystack) else ""
    after_next = haystack[end + 1] if end + 1 < len(haystack) else ""
    if before and (
        before.isalnum() or (before in ".,:" and start >= 2 and haystack[start - 2].isdigit())
    ):
        return False
    return not (after and (after.isalnum() or (after in ".,:" and after_next.isdigit())))


def occurs_as_token(needle: str, haystack: str) -> bool:
    """``needle`` occurs in ``haystack`` as a whole token (both are compared folded)."""
    needle, haystack = fold(needle), fold(haystack)
    if not needle:
        return False
    start = haystack.find(needle)
    while start >= 0:
        if _is_token(haystack, start, start + len(needle)):
            return True
        start = haystack.find(needle, start + 1)
    return False


def _grounding_facts(
    issue_code: str, issue_text: str, text: str, facts: Iterable[UsableFact]
) -> list[UsableFact]:
    """The usable facts that make this value a verified one (none: it is not grounded)."""
    if issue_code == DISCOUNT_WORD:
        return [
            f
            for f in facts
            if f.key.startswith("promotion.") and fold(" ".join(f.display.split())) in fold(text)
        ]
    return [f for f in facts if occurs_as_token(issue_text, f.display)]


def check(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    texts: Mapping[str, str],
    *,
    rendered: Iterable[tuple[uuid.UUID, int]] = (),
    unbacked_claims: Iterable[str] = (),
) -> Grounding:
    """Validate ``texts`` and find the verified facts whose value they contain.

    ``rendered`` are the ``(fact_id, version)`` pairs that generation rendered into the texts
    (G6): they are references even when their value is not a critical one (an address).
    ``unbacked_claims`` are commercial claims the model declared that no rendered fact backs;
    each is a blocking ``CLAIM_UNBACKED`` issue.
    """
    facts = knowledge_service.usable_facts(session, clock, ctx, locale=ctx.locale)
    issues: list[dict[str, Any]] = []
    references: dict[uuid.UUID, int] = dict(rendered)
    for field, text in texts.items():
        report = validate_claims(text, RenderResult(text=text), ctx.locale)
        for issue in report.issues:
            matching = _grounding_facts(issue.code, issue.text, text, facts)
            for fact in matching:
                references[fact.fact_id] = fact.version
            issues.append(
                {
                    "code": issue.code,
                    "field": field,
                    "span": [issue.start, issue.end],
                    "text": issue.text,
                    # The value is a verified fact's current display: right, and recorded as a
                    # reference of this item, so it does not block.
                    "matches_verified": bool(matching),
                    "fact_key": matching[0].key if matching else None,
                }
            )
        for found in PLACEHOLDER.finditer(text):
            issues.append(
                {
                    "code": PLACEHOLDER_UNRENDERED,
                    "field": field,
                    "span": [found.start(), found.end()],
                    "text": found.group(0),
                    "matches_verified": False,
                    "fact_key": found.group("key"),
                }
            )
    for claim in unbacked_claims:
        issues.append(
            {
                "code": CLAIM_UNBACKED,
                "field": "caption",
                "span": None,
                "text": claim,
                "matches_verified": False,
                "fact_key": None,
            }
        )
    passed = all(i["matches_verified"] for i in issues)
    report_dict = {"passed": passed, "issues": issues, "stale": False}
    return Grounding(report=report_dict, references=tuple(references.items()))
