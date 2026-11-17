"""Erasure of voice-note transcripts (F-03). A tiny module on purpose: the retention job, the
data-rights workflows, account erasure and provider deletion all call it without importing the
transcription job. Transcript text is the customer's speech: it is erased wherever message
text is erased (INV-17 / ADR-022 bounded privacy writes)."""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import case, select, update
from sqlalchemy.orm import Session

from app.inbox.models import MessageTranscript


def erase_transcripts(session: Session, now: datetime, *conditions: Any) -> int:
    """Erase transcript text wherever message text is erased (retention, erasure, provider
    deletion). The row stays, so the fact that a transcript existed is not lost; a transcript
    still ``pending`` becomes ``failed`` (``VOICE_SOURCE_GONE``) so no job stores text later."""
    result = session.execute(
        update(MessageTranscript)
        .where(*conditions, MessageTranscript.erased_at.is_(None))
        .values(
            text=None,
            erased_at=now,
            status=case(
                (MessageTranscript.status == "pending", "failed"),
                else_=MessageTranscript.status,
            ),
            reason_code=case(
                (MessageTranscript.status == "pending", "VOICE_SOURCE_GONE"),
                else_=MessageTranscript.reason_code,
            ),
        )
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount)  # type: ignore[attr-defined]


def export_transcripts(
    session: Session, workspace_id: uuid.UUID, message_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, dict[str, Any]]:
    """The data-subject export of the transcripts of these messages (access right). Only what the
    customer said and how it was produced: no audio is kept, so there is none to export."""
    if not message_ids:
        return {}
    rows = session.scalars(
        select(MessageTranscript).where(
            MessageTranscript.workspace_id == workspace_id,
            MessageTranscript.message_id.in_(list(message_ids)),
        )
    )
    return {
        row.message_id: {
            "source": row.source,
            "status": row.status,
            "reason_code": row.reason_code,
            "text": row.text,
            "language": row.language,
            "provider": row.provider,
            "model": row.model,
            "duration_seconds": row.duration_seconds,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        }
        for row in rows
    }
