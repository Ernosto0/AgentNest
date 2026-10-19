"""Approved answers (business-knowledge.md §9): answers the owner approved once and wants
reused. This module is the single place that reads and writes the table.

Drafting reads the ``active`` and ``needs_review`` answers in the reply language. The model may
pick one by id; code renders its template from verified facts and runs the claim validator on
it like any other reply, so an answer with a stale literal value can never be sent. A template
therefore holds values only as ``{{fact:key}}`` placeholders, which is checked when it is saved.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity.permissions import has_permission
from app.knowledge import impact
from app.knowledge import repository as repo
from app.knowledge.claims import validate_claims
from app.knowledge.constants import APPROVED_ANSWER_INTENTS
from app.knowledge.models import ApprovedAnswer
from app.knowledge.render import PLACEHOLDER, RenderResult, placeholder_keys

DRAFTING_STATUSES = ("active", "needs_review")
MAX_TEMPLATE_BYTES = 900
MAX_EXAMPLES = 10
MAX_EXAMPLE_CHARS = 200
NEUTRAL = "▯"  # stands in for a placeholder while the rest of a template is scanned


@dataclass(frozen=True)
class AnswerView:
    id: uuid.UUID
    title: str
    intent: str
    example_questions: tuple[str, ...]
    answer_template: str
    language: str
    status: str
    version: int


def _view(answer: ApprovedAnswer) -> AnswerView:
    return AnswerView(
        id=answer.id,
        title=answer.title,
        intent=answer.intent,
        example_questions=tuple(answer.example_questions),
        answer_template=answer.answer_template,
        language=answer.language,
        status=answer.status,
        version=answer.version,
    )


def list_for_drafting(session: Session, ctx: WorkspaceContext, language: str) -> list[AnswerView]:
    rows = session.scalars(
        select(ApprovedAnswer)
        .where(
            ApprovedAnswer.workspace_id == ctx.workspace_id,
            ApprovedAnswer.language == language,
            ApprovedAnswer.status.in_(DRAFTING_STATUSES),
        )
        .order_by(ApprovedAnswer.created_at, ApprovedAnswer.id)
    )
    return [_view(row) for row in rows]


def get_answer(
    session: Session, ctx: WorkspaceContext, answer_id: uuid.UUID, *, lock: bool = False
) -> ApprovedAnswer | None:
    stmt = select(ApprovedAnswer).where(
        ApprovedAnswer.workspace_id == ctx.workspace_id, ApprovedAnswer.id == answer_id
    )
    return session.scalars(stmt.with_for_update() if lock else stmt).one_or_none()


def list_answers(
    session: Session, ctx: WorkspaceContext, *, status: str | None = None
) -> list[ApprovedAnswer]:
    stmt = select(ApprovedAnswer).where(ApprovedAnswer.workspace_id == ctx.workspace_id)
    if status is not None:
        stmt = stmt.where(ApprovedAnswer.status == status)
    return list(session.scalars(stmt.order_by(ApprovedAnswer.created_at, ApprovedAnswer.id)))


# --- writes (knowledge.verify: owners and managers) ------------------------------------------


def require(ctx: WorkspaceContext, permission: str) -> None:
    if ctx.role is None or not has_permission(ctx.role, permission):
        raise AppError("FORBIDDEN", permission=permission)


def _error(field: str, code: str, **params: object) -> AppError:
    return AppError(
        "VALIDATION_FAILED", errors=[{"field": field, "code": code, "params": dict(params)}]
    )


def _clean_examples(examples: list[str]) -> list[str]:
    cleaned = list(dict.fromkeys(e.strip() for e in examples if e.strip()))
    if not cleaned:
        raise _error("example_questions", "required")
    if len(cleaned) > MAX_EXAMPLES or any(len(e) > MAX_EXAMPLE_CHARS for e in cleaned):
        raise _error("example_questions", "too_long", max_items=MAX_EXAMPLES)
    return cleaned


def check_template(template: str, language: str) -> None:
    """No literal critical value may live in an approved answer (INV-02): prices, hours,
    contacts and links appear only as placeholders. Raises ``VALIDATION_FAILED`` listing the
    offending spans so that the owner can replace them."""
    if not template.strip():
        raise _error("answer_template", "required")
    if len(template.encode("utf-8")) > MAX_TEMPLATE_BYTES:
        raise _error("answer_template", "too_long", max_bytes=MAX_TEMPLATE_BYTES)
    scanned = PLACEHOLDER.sub(NEUTRAL, template)
    report = validate_claims(scanned, RenderResult(text=scanned), language)
    if not report.passed:
        raise _error(
            "answer_template", "LITERAL_VALUE", issues=[i.to_dict() for i in report.issues]
        )


def _references(
    session: Session, ctx: WorkspaceContext, template: str
) -> list[tuple[uuid.UUID, int]]:
    """The live facts a template quotes. A placeholder for a fact that does not exist is an
    error; one for an unverified fact is allowed (it just cannot render until verified)."""
    references: list[tuple[uuid.UUID, int]] = []
    for key in placeholder_keys(template):
        fact = repo.get_live_fact_by_key(session, ctx, key)
        if fact is None:
            raise _error("answer_template", "UNKNOWN_FACT", key=key)
        references.append((fact.id, fact.current_version))
    return references


def create_answer(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    title: str,
    intent: str,
    example_questions: list[str],
    answer_template: str,
    language: str,
    created_from_message_id: uuid.UUID | None = None,
) -> ApprovedAnswer:
    """Create an active answer and record the facts it quotes. Commits."""
    require(ctx, "knowledge.verify")
    if intent not in APPROVED_ANSWER_INTENTS:
        raise _error("intent", "invalid")
    if language not in ("tr", "en"):
        raise _error("language", "invalid")
    title = title.strip()
    if not title or len(title) > 120:
        raise _error("title", "invalid")
    examples = _clean_examples(example_questions)
    check_template(answer_template, language)
    references = _references(session, ctx, answer_template)
    answer = ApprovedAnswer(
        workspace_id=ctx.workspace_id,
        title=title,
        intent=intent,
        example_questions=examples,
        answer_template=answer_template,
        language=language,
        status="active",
        version=1,
        created_from_message_id=created_from_message_id,
        created_by_user_id=uuid.UUID(ctx.actor.id) if ctx.actor.id else None,
    )
    session.add(answer)
    session.flush()
    impact.replace_references(session, ctx, "approved_answer", answer.id, references)
    audit.record(
        session,
        ctx,
        "approved_answer.created",
        "approved_answer",
        answer.id,
        {"intent": intent, "language": language},
        clock=clock,
    )
    session.commit()
    return answer


def update_answer(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    answer_id: uuid.UUID,
    *,
    expected_version: int,
    title: str | None = None,
    intent: str | None = None,
    example_questions: list[str] | None = None,
    answer_template: str | None = None,
    status: str | None = None,
) -> ApprovedAnswer:
    """Edit an answer (optimistic concurrency). Editing the wording re-checks it and
    reactivates a ``needs_review`` answer; ``status`` may archive or restore. Commits."""
    require(ctx, "knowledge.verify")
    answer = get_answer(session, ctx, answer_id, lock=True)
    if answer is None:
        raise AppError("NOT_FOUND")
    if answer.version != expected_version:
        raise AppError("VERSION_CONFLICT", expected=expected_version, current=answer.version)
    if intent is not None and intent not in APPROVED_ANSWER_INTENTS:
        raise _error("intent", "invalid")
    if status is not None and status not in ("active", "archived"):
        raise _error("status", "invalid")
    if title is not None:
        if not title.strip() or len(title.strip()) > 120:
            raise _error("title", "invalid")
        answer.title = title.strip()
    if intent is not None:
        answer.intent = intent
    if example_questions is not None:
        answer.example_questions = _clean_examples(example_questions)
    if answer_template is not None and answer_template != answer.answer_template:
        check_template(answer_template, answer.language)
        impact.replace_references(
            session, ctx, "approved_answer", answer.id, _references(session, ctx, answer_template)
        )
        answer.answer_template = answer_template
        if answer.status == "needs_review":
            answer.status = "active"  # the owner has just looked at the wording
    if status is not None:
        answer.status = status
    answer.version += 1
    answer.updated_at = clock.now()
    audit.record(
        session,
        ctx,
        "approved_answer.updated",
        "approved_answer",
        answer.id,
        {"status": answer.status, "version": answer.version},
        clock=clock,
    )
    session.commit()
    return answer
