"""What is approved, and the job that publishes it (workflows.md section E steps 4-6).

The **canonical approval payload** is exactly what the approver saw and what will be
published. Its hash binds the approval (INV-16); any change to the caption, the overlay
suggestions, the media, the account or the instant is a different hash. Key order never
matters: ``app.core.canonical`` sorts keys.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.content.models import ContentItem
from app.core.canonical import payload_hash

APPROVAL_ACTION = "content.publish"
APPROVAL_PERMISSION = "content.approve"


class PublishContentPayload(BaseModel):
    """Payload of the ``publish_content`` job (IDs only, background-jobs.md section 2)."""

    model_config = ConfigDict(extra="forbid")

    content_id: uuid.UUID
    version: int


def publish_job_key(content_id: uuid.UUID, version: int) -> str:
    """Dedup key of the ``publish_content`` job (and, with the same shape, of the operation)
    for one version of an item (workflows.md section E step 4)."""
    return f"publish:{content_id}:v{version}"


def approval_payload(
    item: ContentItem,
    *,
    version: int,
    social_account_id: uuid.UUID,
    media_sha256: str,
    scheduled_at: datetime,
) -> dict[str, Any]:
    """The canonical payload of a submission of ``item`` as version ``version`` (plan.md G5).

    ``overlay_text`` is the list of overlay suggestions: it is what the approver saw for a
    story (the story itself publishes no text). ``version`` and the schedule are passed in
    because a re-approval binds the *next* version and a new instant.
    """
    return {
        "content_id": item.id,
        "version": version,
        "content_type": item.content_type,
        "social_account_id": social_account_id,
        "caption": item.caption,
        "overlay_text": list(item.overlay_text_suggestions or []),
        "media_asset_id": item.media_asset_id,
        "media_sha256": media_sha256,
        "scheduled_at": scheduled_at,
    }


def approval_payload_hash(payload: dict[str, Any]) -> str:
    return payload_hash(payload)


def approval_summary(item: ContentItem, scheduled_at: datetime) -> dict[str, Any]:
    """What the approvals list shows: ids, the internal title and the instant. The caption is
    read from the item itself in the detail view, not copied here."""
    return {
        "content_id": str(item.id),
        "content_type": item.content_type,
        "title": item.title,
        "scheduled_at": scheduled_at.isoformat(),
    }


class GenerateContentPayload(BaseModel):
    """Payload of the ``generate_content`` job: which draft, at which version it was asked for
    (the brief lives on the queued ``agent_runs`` row, not in the job)."""

    model_config = ConfigDict(extra="forbid")

    content_id: uuid.UUID
    version: int


def generate_job_key(content_id: uuid.UUID) -> str:
    return f"generate_content:{content_id}"
