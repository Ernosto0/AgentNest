"""Bounded business retrieval shared by agent context, tools and grounding.

No customer history or owner-only fact is a public knowledge source. Every SQL read
has a limit, including dependency checks; usability is applied before pagination.
"""

import re
import uuid
from typing import Any

from sqlalchemy import Text, and_, cast, exists, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.ai.injection import neutralise_untrusted
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.knowledge.claims import validate_claims
from app.knowledge.formatting import format_value
from app.knowledge.models import ApprovedAnswer, BusinessFact, FactCandidate, FactReference
from app.knowledge.render import placeholder_keys, render
from app.knowledge.service import UsableFact
from app.knowledge.usability import local_today

INTERNAL_CATEGORIES = ("escalation", "brand", "schedule")
INTERNAL_KEYS = ("policy.price_disclosure",)
MAX_FACTS = 20


def usable_predicate(ctx: WorkspaceContext, clock: Clock) -> ColumnElement[bool]:
    today = local_today(clock.now(), ctx.timezone)
    contested = exists().where(
        FactCandidate.workspace_id == ctx.workspace_id,
        FactCandidate.fact_key == BusinessFact.key,
        FactCandidate.status == "pending",
        FactCandidate.relation == "contest",
    )
    return and_(
        BusinessFact.workspace_id == ctx.workspace_id,
        BusinessFact.status == "verified",
        or_(BusinessFact.valid_from.is_(None), BusinessFact.valid_from <= today),
        or_(BusinessFact.valid_until.is_(None), BusinessFact.valid_until >= today),
        ~contested,
    )


def prices_shared(db: Session, clock: Clock, ctx: WorkspaceContext) -> bool:
    return (
        db.scalar(
            select(BusinessFact.id)
            .where(
                usable_predicate(ctx, clock),
                BusinessFact.key == "policy.price_disclosure",
                BusinessFact.value["value"].astext == "share",
            )
            .limit(1)
        )
        is not None
    )


def visible_predicate(db: Session, clock: Clock, ctx: WorkspaceContext) -> ColumnElement[bool]:
    predicates = [
        usable_predicate(ctx, clock),
        BusinessFact.category.not_in(INTERNAL_CATEGORIES),
        BusinessFact.key.not_in(INTERNAL_KEYS),
    ]
    if not prices_shared(db, clock, ctx):
        predicates.append(BusinessFact.category != "pricing")
        predicates.append(BusinessFact.value_type != "money")
    return and_(*predicates)


def as_usable(fact: BusinessFact, ctx: WorkspaceContext, language: str) -> UsableFact:
    return UsableFact(
        fact.id,
        fact.key,
        fact.category,
        fact.label,
        fact.value_type,
        fact.value,
        format_value(fact.value_type, fact.value, language, ctx.locale),
        fact.current_version,
        fact.criticality,
        "{{fact:" + fact.key + "}}",
    )


def fact_data(fact: BusinessFact, ctx: WorkspaceContext, language: str) -> dict[str, Any]:
    usable = as_usable(fact, ctx, language)
    return {
        "id": str(fact.id),
        "key": fact.key,
        "version": fact.current_version,
        "display": neutralise_untrusted(usable.display),
        "placeholder": usable.placeholder,
        "category": fact.category,
        "visibility": "public_business",
        "valid_from": fact.valid_from.isoformat() if fact.valid_from else None,
        "valid_until": fact.valid_until.isoformat() if fact.valid_until else None,
    }


def relevance_words(text: str) -> tuple[str, ...]:
    stop = {"this", "that", "what", "with", "your", "have", "hello", "merhaba", "icin", "için"}
    return tuple(
        dict.fromkeys(
            word.lower()[:24]
            for word in re.findall(r"[^\W\d_]{3,}", text)
            if word.lower() not in stop
        )
    )[:6]


def facts_page(
    db: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    limit: int = 10,
    cursor: str | None = None,
    language: str | None = None,
    relevant_to: str = "",
) -> dict[str, Any]:
    if not 1 <= limit <= MAX_FACTS or (cursor is not None and len(cursor) > 120):
        raise ValueError("invalid knowledge page")
    query = select(BusinessFact).where(visible_predicate(db, clock, ctx))
    if cursor is not None:
        query = query.where(BusinessFact.key > cursor)
    words = relevance_words(relevant_to)
    if words:
        haystack = BusinessFact.key + " " + cast(BusinessFact.label, Text)
        query = query.where(or_(*(haystack.icontains(word, autoescape=True) for word in words)))
    rows = list(db.scalars(query.order_by(BusinessFact.key).limit(limit + 1)))
    return {
        "facts": [fact_data(row, ctx, language or ctx.locale) for row in rows[:limit]],
        "next_cursor": rows[limit - 1].key if len(rows) > limit else None,
    }


def answers_page(
    db: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    language: str,
    limit: int = 5,
    cursor: uuid.UUID | None = None,
    relevant_to: str = "",
) -> dict[str, Any]:
    if language not in {"tr", "en"} or not 1 <= limit <= 10:
        raise ValueError("invalid answer page")
    # A reference is invalid if its current fact is absent, hidden, unusable or changed.
    visible = visible_predicate(db, clock, ctx)
    valid_dependency = (
        exists()
        .where(
            BusinessFact.id == FactReference.fact_id,
            BusinessFact.current_version == FactReference.fact_version,
            visible,
        )
        .correlate(FactReference)
    )
    invalid_dependency = exists().where(
        FactReference.workspace_id == ctx.workspace_id,
        FactReference.referrer_type == "approved_answer",
        FactReference.referrer_id == ApprovedAnswer.id,
        ~valid_dependency,
    )
    query = select(ApprovedAnswer).where(
        ApprovedAnswer.workspace_id == ctx.workspace_id,
        ApprovedAnswer.language == language,
        ApprovedAnswer.status == "active",
        ~invalid_dependency,
    )
    if cursor:
        query = query.where(ApprovedAnswer.id > cursor)
    words = relevance_words(relevant_to)
    if words:
        haystack = ApprovedAnswer.title + " " + ApprovedAnswer.answer_template
        query = query.where(or_(*(haystack.icontains(word, autoescape=True) for word in words)))
    rows = list(db.scalars(query.order_by(ApprovedAnswer.id).limit(limit + 1)))
    safe_answers: list[dict[str, Any]] = []
    for row in rows[:limit]:
        keys = placeholder_keys(row.answer_template)
        if len(keys) > MAX_FACTS:
            continue
        dependencies = (
            list(
                db.scalars(
                    select(BusinessFact)
                    .where(
                        visible,
                        BusinessFact.key.in_(keys),
                    )
                    .limit(MAX_FACTS)
                )
            )
            if keys
            else []
        )
        rendered = render(
            row.answer_template,
            [as_usable(item, ctx, language) for item in dependencies],
            language,
        )
        if not rendered.ok or not validate_claims(rendered.text, rendered, language).passed:
            continue
        safe_answers.append(
            {
                "id": str(row.id),
                "version": row.version,
                "language": row.language,
                "title": neutralise_untrusted(row.title),
                "template": neutralise_untrusted(row.answer_template),
                "fact_sources": [
                    {
                        "id": str(item.id),
                        "version": item.current_version,
                        "placeholder": "{{fact:" + item.key + "}}",
                    }
                    for item in dependencies
                ],
                "visibility": "public_business",
            }
        )
    return {
        "answers": safe_answers,
        "next_cursor": str(rows[limit - 1].id) if len(rows) > limit else None,
    }
