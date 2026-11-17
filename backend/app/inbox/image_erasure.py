"""Erasure and export of image descriptions (F-03, Session 03). A tiny module on purpose, like
``transcripts.py``: the retention job, the data-rights workflows, account erasure and provider
deletion all call it without importing the description job.

A description and the text read from a picture are a machine's reading of customer content: they
are erased wherever message text is erased (INV-17 / ADR-022 bounded privacy writes).
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import case, select, update
from sqlalchemy.orm import Session

from app.inbox.models import MessageImageDescription


def erase_image_descriptions(session: Session, now: datetime, *conditions: Any) -> int:
    """Erase description text wherever message text is erased (retention, erasure, provider
    deletion). The row stays, so the fact that a description existed is not lost; a row still
    ``pending`` becomes ``failed`` (``IMAGE_SOURCE_GONE``) so no job stores text later."""
    result = session.execute(
        update(MessageImageDescription)
        .where(*conditions, MessageImageDescription.erased_at.is_(None))
        .values(
            description=None,
            visible_text=None,
            erased_at=now,
            status=case(
                (MessageImageDescription.status == "pending", "failed"),
                else_=MessageImageDescription.status,
            ),
            reason_code=case(
                (MessageImageDescription.status == "pending", "IMAGE_SOURCE_GONE"),
                else_=MessageImageDescription.reason_code,
            ),
        )
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount)  # type: ignore[attr-defined]


def export_image_descriptions(
    session: Session, workspace_id: uuid.UUID, message_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """The data-subject export of the descriptions of these messages (access right): what the
    machine wrote about the customer's pictures and how it was produced. No image is kept."""
    if not message_ids:
        return {}
    rows = session.scalars(
        select(MessageImageDescription)
        .where(
            MessageImageDescription.workspace_id == workspace_id,
            MessageImageDescription.message_id.in_(list(message_ids)),
        )
        .order_by(MessageImageDescription.attachment_index)
    )
    result: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(row.message_id, []).append(
            {
                "source": row.source,
                "attachment_index": row.attachment_index,
                "status": row.status,
                "reason_code": row.reason_code,
                "looks_like": row.looks_like,
                "description": row.description,
                "visible_text": row.visible_text,
                "provider": row.provider,
                "model": row.model,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            }
        )
    return result
