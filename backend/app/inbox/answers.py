"""Saving a sent reply as an approved answer (business-knowledge.md §9).

The values in the reply become ``{{fact:key}}`` placeholders again (from the spans recorded
when the draft was rendered), so the saved answer follows the facts when they change. A reply
that was typed by hand has no spans; it is saved as written and the knowledge module refuses
literal critical values, listing them so the owner can replace them.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.inbox import drafts
from app.inbox.language import detect_language
from app.inbox.models import Message
from app.knowledge import approved_answers
from app.knowledge.constants import APPROVED_ANSWER_INTENTS
from app.knowledge.models import ApprovedAnswer

TITLE_CHARS = 60


def template_from_draft_text(text: str, validation: dict[str, Any]) -> str:
    """The text with each rendered value turned back into its placeholder, and the automatic-reply
    notice (appended by code) removed."""
    suffix = validation.get("suffix_span")
    if isinstance(suffix, list) and len(suffix) == 2:
        text = text[: int(suffix[0])] + text[int(suffix[1]) :]
    rendered = validation.get("rendered", [])
    spans = sorted(
        ((int(r["span"][0]), int(r["span"][1]), str(r["key"])) for r in rendered),
        reverse=True,
    )
    for start, end, key in spans:
        if 0 <= start < end <= len(text):
            text = f"{text[:start]}{{{{fact:{key}}}}}{text[end:]}"
    return text.strip()


def save_from_message(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    message_id: uuid.UUID,
    *,
    title: str | None,
    intent: str | None,
    example_question: str | None,
    answer_template: str | None,
) -> ApprovedAnswer:
    """Create an approved answer from an outbound message. Commits."""
    message = session.scalars(
        select(Message).where(Message.workspace_id == ctx.workspace_id, Message.id == message_id)
    ).one_or_none()
    if message is None:
        raise AppError("NOT_FOUND")
    if message.direction != "outbound" or not (message.text or "").strip():
        raise AppError("CONFLICT_STATE", entity="message", reason="not_a_sent_reply")
    draft = (
        drafts.get_draft(session, ctx.workspace_id, message.reply_draft_id)
        if message.reply_draft_id
        else None
    )

    sent_text = message.text or ""
    if answer_template is None:
        answer_template = (
            template_from_draft_text(sent_text, draft.validation) if draft else sent_text.strip()
        )
    question = (example_question or _preceding_question(session, ctx, message) or "").strip()
    if not question:
        raise AppError(
            "VALIDATION_FAILED",
            errors=[{"field": "example_question", "code": "required", "params": {}}],
        )
    language = (draft.language if draft else None) or _language(sent_text)
    chosen_intent = intent or (
        draft.intent if draft and draft.intent in APPROVED_ANSWER_INTENTS else "faq"
    )
    return approved_answers.create_answer(
        session,
        clock,
        ctx,
        title=title or question[:TITLE_CHARS],
        intent=chosen_intent or "faq",
        example_questions=[question],
        answer_template=answer_template,
        language=language,
        created_from_message_id=message.id,
    )


def _preceding_question(session: Session, ctx: WorkspaceContext, message: Message) -> str | None:
    """The customer's message the reply answered: the latest one before it."""
    return session.scalar(
        select(Message.text)
        .where(
            Message.workspace_id == ctx.workspace_id,
            Message.conversation_id == message.conversation_id,
            Message.direction == "inbound",
            Message.provider_timestamp <= message.provider_timestamp,
            Message.text.is_not(None),
        )
        .order_by(Message.provider_timestamp.desc(), Message.created_at.desc())
        .limit(1)
    )


def _language(text: str) -> str:
    detected = detect_language(text)
    return detected if detected in ("tr", "en") else "tr"
