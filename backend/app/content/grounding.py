"""Claim validation of the texts of a content item and its ``fact_references`` (INV-02).

The texts of an item (caption, overlay suggestions) are **rendered** text (plan.md G6): a
generated caption already holds the display value of the facts it used. A person's edit is
plain text. Either way the validator scans the final text for critical values; whatever it
finds is reported as an issue and, because nothing in the text is a rendered span, shows up
as ungrounded. Issues never stop an edit (a human is reviewing), but they block submission
(P5-04).

A value that equals a **verified** fact's display is recorded as a ``fact_references`` row, so a
later change of that fact reaches the item (impact analysis, P5-07). This is the same matcher
the owner's own replies use (``inbox.service.text_warnings``).
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.knowledge import service as knowledge_service
from app.knowledge.claims import validate_claims
from app.knowledge.render import RenderResult


@dataclass(frozen=True)
class Grounding:
    report: dict[str, Any]  # what ``content_items.validation`` stores
    references: tuple[tuple[uuid.UUID, int], ...]  # (fact_id, version)


def texts_of(caption: str | None, overlay_text_suggestions: list[str]) -> dict[str, str]:
    """The checked texts by field name: ``caption`` and ``overlay_text_suggestions.{index}``."""
    texts: dict[str, str] = {}
    if caption:
        texts["caption"] = caption
    for index, suggestion in enumerate(overlay_text_suggestions):
        if suggestion:
            texts[f"overlay_text_suggestions.{index}"] = suggestion
    return texts


def check(
    session: Session, clock: Clock, ctx: WorkspaceContext, texts: Mapping[str, str]
) -> Grounding:
    """Validate ``texts`` and find the verified facts whose value they contain."""
    facts = knowledge_service.usable_facts(session, clock, ctx, locale=ctx.locale)
    issues: list[dict[str, Any]] = []
    references: dict[uuid.UUID, int] = {}
    for field, text in texts.items():
        report = validate_claims(text, RenderResult(text=text), ctx.locale)
        for issue in report.issues:
            matching = [f for f in facts if issue.text in f.display]
            for fact in matching:
                references[fact.fact_id] = fact.version
            issues.append(
                {
                    "code": issue.code,
                    "field": field,
                    "span": [issue.start, issue.end],
                    "text": issue.text,
                    "matches_verified": bool(matching),
                }
            )
    report_dict = {"passed": not issues, "issues": issues, "stale": False}
    return Grounding(report=report_dict, references=tuple(references.items()))
