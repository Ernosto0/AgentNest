"""The transcript rule for the account agent's replies (F-03, Feature Phase 2, Session 02).

The legacy drafting path gets the rule as R18 (``rules_reply.r18_transcript``). The account agent
decides through delegation (``agent.delegation``), whose ``require_human`` switch turns an
``automatic`` decision into an ``ask`` (a human approval). This module is the deterministic input
to that switch: if a customer's voice note with a finished transcript is among the recent
messages of the conversation, the agent's reply to it is never sent without a person, whatever the
delegation says. It reads stored rows only; no model output is involved.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.inbox.models import Message, MessageTranscript

RECENT_MESSAGES = 10  # inbound messages: the window the drafting path shows the model


def recent_transcript_present(
    session: Session, workspace_id: uuid.UUID, conversation_id: uuid.UUID
) -> bool:
    """True if one of the newest inbound messages of the conversation is a customer voice note whose
    transcript succeeded (and whose text has not been erased). Workspace-scoped."""
    recent = (
        select(Message.id)
        .where(
            Message.workspace_id == workspace_id,
            Message.conversation_id == conversation_id,
            Message.direction == "inbound",
            Message.is_deleted.is_(False),
        )
        .order_by(Message.provider_timestamp.desc(), Message.created_at.desc())
        .limit(RECENT_MESSAGES)
        .subquery()
    )
    found = session.scalar(
        select(MessageTranscript.id)
        .where(
            MessageTranscript.workspace_id == workspace_id,
            MessageTranscript.message_id.in_(select(recent.c.id)),
            MessageTranscript.status == "succeeded",
            MessageTranscript.text.is_not(None),
        )
        .limit(1)
    )
    return found is not None
