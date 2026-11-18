"""Story context for direct messages (F-04).

Two kinds of DM refer to one of the business's Instagram stories:

- a **story reply**: the customer answers a story. The webhook carries ``reply_to.story`` (the
  story id and a short-lived CDN URL), which ``webhook_format`` stores as a ``story_reply``
  attachment (``note`` = story id).
- a **story mention**: the customer posts a story that tags the business. The webhook carries a
  ``story_mention`` attachment with the customer's story URL only.

What we can say about a story we did not publish is nothing: the Graph API exposes no caption for
a story (stories have no caption field; unverified, see integrations.md), so a reply to a story
that is not in our own ``content_items`` has no context and keeps the old behaviour. For a story
AgentNest published the stored content record is the context: its internal title, its objective and
the overlay text the owner approved. That record is owner-authored data, still passed to the model
as labelled data and never as instructions (INV-03), with fact placeholders reduced to a plain
label so that no value reaches the model outside a placeholder it may copy (INV-02).

Nothing here writes. The module reads ``content_items`` by workspace and account (INV-01).
"""

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content.models import ContentItem, MediaAsset
from app.knowledge.render import PLACEHOLDER

STORY_REPLY = "story_reply"
STORY_MENTION = "story_mention"
STORY_LIFETIME = timedelta(hours=24)  # an Instagram story disappears after 24 hours
MAX_CONTEXT_CHARS = 600
MAX_LINES = 5

StoryKind = Literal["reply", "mention"]


@dataclass(frozen=True)
class StoryRef:
    """The story a message refers to, as far as the webhook told us."""

    kind: StoryKind
    story_id: str | None  # a reply carries the story's media id; a mention does not
    url: str | None


@dataclass(frozen=True)
class StoryContent:
    """What we know about one of our own stories."""

    content_id: uuid.UUID
    title: str
    objective: str | None
    overlay_lines: tuple[str, ...]
    media_asset_id: uuid.UUID | None
    media_deleted: bool
    published_at: datetime | None
    expired: bool  # the message arrived 24 hours or more after the story was published


def story_ref(attachments: Iterable[Mapping[str, Any]] | None) -> StoryRef | None:
    """The first story reference among a message's attachments (a reply wins over a mention)."""
    found: StoryRef | None = None
    for attachment in attachments or ():
        kind = attachment.get("type")
        if kind == STORY_REPLY:
            note, url = attachment.get("note"), attachment.get("url")
            return StoryRef(
                "reply",
                note if isinstance(note, str) and note else None,
                url if isinstance(url, str) and url else None,
            )
        if kind == STORY_MENTION and found is None:
            url = attachment.get("url")
            found = StoryRef("mention", None, url if isinstance(url, str) and url else None)
    return found


def is_mention_only(
    messages: Sequence[tuple[str | None, Sequence[Mapping[str, Any]] | None]],
) -> bool:
    """True when every message waiting for a reply is a text-less story mention.

    Anything else (a typed question, a photo, an unknown attachment next to the mention) is not a
    plain mention: a person or the normal pipeline handles it.
    """
    if not messages:
        return False
    for text, attachments in messages:
        if (text or "").strip():
            return False
        refs = [a for a in attachments or () if isinstance(a, Mapping)]
        if not refs or any(a.get("type") != STORY_MENTION for a in refs):
            return False
    return True


def _plain(text: str) -> str:
    """The text with each ``{{fact:key}}`` shown as ``[name]`` (the last part of the key)."""
    return PLACEHOLDER.sub(
        lambda m: f"[{m.group('key').rsplit('.', 1)[-1].replace('_', ' ')}]", text
    )


def _lines(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    cleaned = (_plain(item).strip() for item in raw if isinstance(item, str))
    return tuple(line for line in cleaned if line)[:MAX_LINES]


def own_story(
    session: Session,
    workspace_id: uuid.UUID,
    social_account_id: uuid.UUID,
    story_id: str,
    *,
    message_time: datetime,
) -> StoryContent | None:
    """The story AgentNest published under this media id on this account, else ``None``."""
    item = session.scalars(
        select(ContentItem)
        .where(
            ContentItem.workspace_id == workspace_id,
            ContentItem.social_account_id == social_account_id,
            ContentItem.content_type == "story_image",
            ContentItem.status == "published",
            ContentItem.external_media_id == story_id,
        )
        .order_by(ContentItem.published_at.desc().nulls_last(), ContentItem.id)
        .limit(1)
    ).first()
    if item is None:
        return None
    published = item.published_at
    media_status = (
        session.scalar(
            select(MediaAsset.status).where(
                MediaAsset.workspace_id == workspace_id,
                MediaAsset.id == item.media_asset_id,
                MediaAsset.kind == "image",
            )
        )
        if item.media_asset_id is not None
        else None
    )
    return StoryContent(
        content_id=item.id,
        title=_plain(item.title).strip(),
        objective=_plain(item.objective).strip() if item.objective else None,
        overlay_lines=_lines(item.overlay_text_suggestions),
        media_asset_id=item.media_asset_id,
        media_deleted=item.media_asset_id is not None and media_status in (None, "deleted"),
        published_at=published,
        expired=published is not None and message_time - published >= STORY_LIFETIME,
    )


def reply_context(
    session: Session,
    workspace_id: uuid.UUID,
    social_account_id: uuid.UUID,
    messages: Iterable[tuple[Sequence[Mapping[str, Any]] | None, datetime]],
) -> StoryContent | None:
    """The context of the newest story reply among the messages, if it is one of our stories."""
    for attachments, moment in reversed(list(messages)):
        ref = story_ref(attachments)
        if ref is None or ref.kind != "reply":
            continue
        if ref.story_id is None:
            return None
        return own_story(
            session, workspace_id, social_account_id, ref.story_id, message_time=moment
        )
    return None


def prompt_text(content: StoryContent | None) -> str | None:
    """What the model is told about the story, as plain data (bounded)."""
    if content is None:
        return None
    parts = [f"title: {content.title}"] if content.title else []
    if content.objective:
        parts.append(f"about: {content.objective}")
    if content.overlay_lines:
        parts.append("text on the story: " + " / ".join(content.overlay_lines))
    if content.expired:
        parts.append("the story is no longer live")
    return "\n".join(parts)[:MAX_CONTEXT_CHARS] or None
