"""What a conversation needs from a person (state-machines.md §4, "Attention").

``compute_attention`` is pure; ``refresh`` reads the drafts and stores the result on the
conversation. Callers invoke ``refresh`` after every change that can move it.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.inbox.models import OPEN_DRAFT_STATUSES, Conversation, ReplyDraft


def compute_attention(
    *,
    open_draft_status: str | None,
    latest_draft_status: str | None,
    latest_draft_at: datetime | None,
    handling_mode: str,
    last_inbound_at: datetime | None,
    last_outbound_at: datetime | None,
) -> str:
    unanswered = last_inbound_at is not None and (
        last_outbound_at is None or last_inbound_at > last_outbound_at
    )
    if open_draft_status == "needs_human":
        return "needs_human"
    if handling_mode == "human" and unanswered:
        return "needs_human"
    if open_draft_status == "pending_approval":
        return "needs_approval"
    if (
        latest_draft_status in ("failed", "blocked")
        and latest_draft_at is not None
        and (last_outbound_at is None or latest_draft_at > last_outbound_at)
    ):
        return "failed"
    return "none"


def refresh(session: Session, conversation: Conversation) -> str:
    """Recompute and store the conversation's attention. No commit."""
    session.flush()
    drafts = session.scalars(
        select(ReplyDraft)
        .where(
            ReplyDraft.workspace_id == conversation.workspace_id,
            ReplyDraft.conversation_id == conversation.id,
        )
        .order_by(ReplyDraft.created_at.desc(), ReplyDraft.id)
        .limit(5)
    ).all()
    open_draft = next((d for d in drafts if d.status in OPEN_DRAFT_STATUSES), None)
    latest = drafts[0] if drafts else None
    attention = compute_attention(
        open_draft_status=open_draft.status if open_draft else None,
        latest_draft_status=latest.status if latest else None,
        latest_draft_at=latest.updated_at if latest else None,
        handling_mode=conversation.handling_mode,
        last_inbound_at=conversation.last_inbound_at,
        last_outbound_at=conversation.last_outbound_at,
    )
    conversation.attention = attention
    return attention


def customer_number(conversation_id: uuid.UUID) -> int:
    """A short stable number for customers without a known handle ("Customer #4821"); the
    client composes the localised label."""
    return conversation_id.int % 10000
