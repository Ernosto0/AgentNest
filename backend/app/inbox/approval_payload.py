"""The exact content a reply approval authorises (ADR-014, INV-16).

The hash of this payload is stored on the approval and shown to the approver. The executor
recomputes it from the draft just before sending, so a draft that changed after approval can
never be sent under the old approval.
"""

import uuid
from typing import Any

from app.inbox.models import Conversation, ReplyDraft


def approval_payload(draft: ReplyDraft, conversation: Conversation) -> dict[str, Any]:
    return {
        "social_account_id": str(conversation.social_account_id),
        "conversation_id": str(conversation.id),
        "recipient_id": conversation.customer_external_id,
        "text": draft.text or "",
        "draft_id": str(draft.id),
        "draft_version": draft.version,
    }


def approval_summary(
    draft_id: uuid.UUID, conversation_id: uuid.UUID, reasons: list[str], window_ends_at: str
) -> dict[str, Any]:
    """What the approvals list shows. It carries ids and reasons, not the reply text: the
    detail view loads the draft itself."""
    return {
        "draft_id": str(draft_id),
        "conversation_id": str(conversation_id),
        "reasons": reasons,
        "window_ends_at": window_ends_at,
    }
