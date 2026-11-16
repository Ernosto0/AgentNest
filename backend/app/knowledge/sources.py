"""Where each value of a rendered reply comes from (D-01, INV-02).

A reply draft stores what the renderer put into it: for every ``{{fact:key}}`` placeholder the fact,
the fact version, the text and its span (``reply_drafts.validation["rendered"]``). This module turns
that record into what a person is shown next to the value: the fact's label and **when it was
verified**. The mapping is built here, on the server, once, for every surface that shows a draft
(the inbox, approvals, the test chat, Telegram); no client recomputes it.

The verified date is the date of the fact version the draft rendered, not of the fact's current
version: ``fact_versions`` is insert-only (INV-17), and its ``created_at`` is the instant the owner
entered, edited or verified that value (the service writes ``clock.now()`` to both
``business_facts.last_verified_at`` and the version row). So a draft rendered last week still says
"verified" on the day that price was verified, even if the price has changed since. ``None`` means
the history holds no verification of that version (it cannot be inferred, so it is not guessed).
"""

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge.models import BusinessFact, FactVersion

# The version rows that record a verification of the value (a fact created unverified has a
# ``created`` row that is not one; ``archived`` and ``restored`` do not verify anything).
_VERIFYING_KINDS = ("created", "value_changed", "verified")


@dataclass(frozen=True)
class FactSource:
    """One rendered value and its origin."""

    fact_id: uuid.UUID
    key: str
    label: str
    display: str
    version: int
    verified_at: datetime | None


def span_records(spans: Iterable[Any]) -> list[dict[str, Any]]:
    """The stored form of rendered placeholders (``reply_drafts.validation["rendered"]``): what
    ``fact_sources`` reads back. ``spans`` are ``RenderedSpan`` objects of ``knowledge.render``."""
    return [
        {
            "key": s.key,
            "fact_id": str(s.fact_id),
            "version": s.version,
            "span": [s.start, s.end],
            "display": s.display,
        }
        for s in spans
    ]


def pick_label(label: Mapping[str, Any] | None, language: str, fallback: str) -> str:
    """The fact label in ``language``, else Turkish, else English, else ``fallback``."""
    if not label:
        return fallback
    for code in (language, "tr", "en"):
        value = label.get(code)
        if isinstance(value, str) and value:
            return value
    return fallback


def fact_sources(
    session: Session,
    workspace_id: uuid.UUID,
    rendered: Sequence[Mapping[str, Any]],
    language: str,
) -> list[FactSource]:
    """One source per rendered span, in the order given. Workspace-scoped (INV-01).

    ``rendered`` is the validator's record (``key``, ``fact_id``, ``version``, ``display``).
    """
    if not rendered:
        return []
    fact_ids = {uuid.UUID(str(r["fact_id"])) for r in rendered}
    labels: dict[uuid.UUID, dict[str, Any]] = {
        row.id: row.label
        for row in session.execute(
            select(BusinessFact.id, BusinessFact.label).where(
                BusinessFact.workspace_id == workspace_id, BusinessFact.id.in_(fact_ids)
            )
        )
    }
    verifications: dict[uuid.UUID, list[tuple[int, datetime]]] = {}
    for fact_id, version, created_at in session.execute(
        select(FactVersion.fact_id, FactVersion.version, FactVersion.created_at)
        .where(
            FactVersion.workspace_id == workspace_id,
            FactVersion.fact_id.in_(fact_ids),
            FactVersion.change_kind.in_(_VERIFYING_KINDS),
            FactVersion.status == "verified",
        )
        .order_by(FactVersion.version)
    ):
        verifications.setdefault(fact_id, []).append((version, created_at))

    sources: list[FactSource] = []
    for item in rendered:
        fact_id = uuid.UUID(str(item["fact_id"]))
        version = int(item["version"])
        verified_at = None
        for number, created_at in verifications.get(fact_id, []):
            if number <= version:
                verified_at = created_at  # the newest verification at or before this version
        sources.append(
            FactSource(
                fact_id=fact_id,
                key=str(item["key"]),
                label=pick_label(labels.get(fact_id), language, str(item["key"])),
                display=str(item["display"]),
                version=version,
                verified_at=verified_at,
            )
        )
    return sources


def unique_sources(sources: Iterable[FactSource]) -> list[FactSource]:
    """The list a person reads: each fact once, in the order it first appears."""
    seen: set[str] = set()
    unique: list[FactSource] = []
    for source in sources:
        if source.key in seen:
            continue
        seen.add(source.key)
        unique.append(source)
    return unique


__all__ = ["FactSource", "fact_sources", "pick_label", "span_records", "unique_sources"]
