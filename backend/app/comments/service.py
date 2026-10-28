"""Serialized ingestion and bounded public reads. Caller owns the transaction."""

import json
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.agent.models import AgentEvent, AgentThread
from app.agent.repository import add_event_and_wake, scoped_account, scoped_thread
from app.agent.tools.broker import BrokerContext, ToolInputError
from app.ai.injection import neutralise_untrusted
from app.audit.service import record
from app.comments.codec import CommentEvent
from app.comments.models import PublicComment, PublicMedia, PublicThread
from app.core.clock import Clock
from app.core.errors import AppError
from app.core.ids import new_id
from app.integrations.instagram.models import SocialAccount


def scoped_media(
    db: Session, workspace: uuid.UUID, account: uuid.UUID, media: uuid.UUID
) -> PublicMedia:
    row = db.scalar(
        select(PublicMedia).where(
            PublicMedia.id == media,
            PublicMedia.workspace_id == workspace,
            PublicMedia.social_account_id == account,
        )
    )
    if row is None:
        raise AppError("NOT_FOUND")
    return row


def media_version(db: Session, thread: AgentThread) -> int | None:
    if thread.surface != "comment":
        return None
    return db.scalar(
        select(PublicMedia.version)
        .join(PublicThread, PublicThread.media_id == PublicMedia.id)
        .where(
            PublicThread.id == thread.public_thread_id,
            PublicThread.workspace_id == thread.workspace_id,
            PublicThread.social_account_id == thread.social_account_id,
            PublicMedia.workspace_id == thread.workspace_id,
            PublicMedia.social_account_id == thread.social_account_id,
        )
    )


def apply(db: Session, clock: Clock, account: SocialAccount, value: CommentEvent) -> bool:
    """A rejected source cannot leave partial media/parent mutations behind."""
    with db.begin_nested() as savepoint:
        accepted = _apply(db, clock, account, value)
        if not accepted:
            savepoint.rollback()
    return accepted


def _apply(db: Session, clock: Clock, account: SocialAccount, value: CommentEvent) -> bool:
    controller = scoped_account(db, account.workspace_id, account.id, lock=True)
    # Provisional v1 supports a root and direct replies only. Reject ambiguous
    # nested lineage instead of guessing or later merging public conversations.
    if (value.parent_id is None and value.root_id != value.id) or (
        value.parent_id is not None
        and (value.parent_id != value.root_id or value.id == value.root_id)
    ):
        return False
    media = db.scalar(
        select(PublicMedia).where(
            PublicMedia.social_account_id == account.id,
            PublicMedia.external_id == value.media_id,
            PublicMedia.workspace_id == account.workspace_id,
        )
    )
    if media is None:
        media = PublicMedia(
            id=new_id(),
            workspace_id=account.workspace_id,
            social_account_id=account.id,
            external_id=value.media_id,
            updated_at=clock.now(),
            is_simulated=account.is_simulated,
        )
        db.add(media)
        db.flush()
    thread = db.scalar(
        select(PublicThread).where(
            PublicThread.social_account_id == account.id,
            PublicThread.root_external_id == value.root_id,
            PublicThread.workspace_id == account.workspace_id,
        )
    )
    if thread is not None and thread.media_id != media.id:
        return False
    if thread is None:
        thread = PublicThread(
            id=new_id(),
            workspace_id=account.workspace_id,
            social_account_id=account.id,
            media_id=media.id,
            root_external_id=value.root_id,
        )
        db.add(thread)
        db.flush()

    def comment(external: str) -> PublicComment | None:
        row = db.scalar(
            select(PublicComment).where(
                PublicComment.workspace_id == account.workspace_id,
                PublicComment.social_account_id == account.id,
                PublicComment.external_id == external,
            )
        )
        if row and (row.thread_id != thread.id or row.media_id != media.id):
            return None
        if row is None:
            row = PublicComment(
                id=new_id(),
                workspace_id=account.workspace_id,
                social_account_id=account.id,
                media_id=media.id,
                thread_id=thread.id,
                external_id=external,
                updated_at=clock.now(),
                is_simulated=account.is_simulated,
            )
            db.add(row)
            db.flush()
        return row

    row = comment(value.id)
    if row is None:
        return False
    from app.comments.privacy import redact_media_caches, redact_receipts

    if row.author_external_id and value.author_id and row.author_external_id != value.author_id:
        return False
    if row.state == "deleted":
        redact_receipts(db, account.workspace_id, account.id, row.external_id)
    if media.state == "deleted":
        redact_media_caches(db, media)
    if (
        media.state != "deleted"
        and (value.media_verified or value.media_deleted)
        and (value.media_version > media.provider_version or value.media_deleted)
    ):
        media.provider_version = value.media_version
        media.provider_timestamp = value.timestamp
        media.version += 1
        media.updated_at = clock.now()
        if value.media_deleted:
            media.state, media.caption = "deleted", None
        elif value.media_verified:
            media.state, media.ownership_state = "visible", "verified_synthetic"
            media.caption = value.media_caption
        record(
            db,
            None,
            "comment.media_changed",
            "public_media",
            media.id,
            {"version": media.version, "state": media.state},
            workspace_id=account.workspace_id,
            is_simulated=account.is_simulated,
            clock=clock,
        )
    if media.state == "deleted":
        redact_media_caches(db, media)
        db.execute(
            update(PublicComment)
            .where(
                PublicComment.workspace_id == account.workspace_id,
                PublicComment.social_account_id == account.id,
                PublicComment.media_id == media.id,
                PublicComment.state != "deleted",
            )
            .values(text=None, state="deleted", version=PublicComment.version + 1)
        )
    # A tombstone is terminal even if a later redelivery claims a higher revision.
    if (
        row.state == "deleted"
        or value.version < row.provider_version
        or (value.version == row.provider_version and value.state != "deleted")
    ):
        return True
    parent = comment(value.parent_id) if value.parent_id else None
    if value.parent_id and (parent is None or parent.id == row.id):
        return False
    if row.parent_id is not None and row.parent_id != (parent.id if parent else None):
        return False
    row.parent_id = parent.id if parent else None
    row.provider_version = value.version
    row.version += 1
    row.provider_timestamp = value.timestamp
    row.updated_at = clock.now()
    row.state = value.state
    row.text = value.text if value.state == "visible" else None
    # Provider IDs alone establish identity; display names are deliberately absent.
    row.author_external_id = row.author_external_id or value.author_id
    row.is_owner = row.author_external_id == account.external_account_id
    if row.state == "deleted":
        row.author_external_id = None
        redact_receipts(db, account.workspace_id, account.id, row.external_id)
    if media.state == "deleted":
        redact_media_caches(db, media)
        # A terminal post deletion suppresses all related public bodies, including
        # delayed creates. The media version independently fences sibling claims.
        row.text, row.state = None, "deleted"
    agent = db.scalar(
        select(AgentThread).where(
            AgentThread.workspace_id == account.workspace_id,
            AgentThread.social_account_id == account.id,
            AgentThread.surface == "comment",
            AgentThread.source_ref == str(thread.id),
        )
    )
    eligible = row.state == "visible" and not row.is_owner and media.state != "deleted"
    record(
        db,
        None,
        "comment.source_ingested",
        "public_comment",
        row.id,
        {"version": row.version, "state": row.state, "thread_id": thread.id},
        workspace_id=account.workspace_id,
        is_simulated=account.is_simulated,
        clock=clock,
    )
    if controller.controller_mode != "agent" or controller.state not in {"active", "paused"}:
        return True
    if agent is None and eligible:
        agent = AgentThread(
            workspace_id=account.workspace_id,
            social_account_id=account.id,
            surface="comment",
            source_ref=str(thread.id),
            public_thread_id=thread.id,
            controller_epoch=controller.controller_epoch,
        )
        db.add(agent)
        db.flush()
    if agent is not None:
        if row.is_owner:
            agent.ownership_generation += 1
        if row.state == "deleted" or media.state == "deleted":
            agent.deletion_generation += 1
        if agent.handling_mode == "agent" and agent.controller_epoch == controller.controller_epoch:
            add_event_and_wake(
                db,
                workspace_id=account.workspace_id,
                account_id=account.id,
                thread_id=agent.id,
                kind="customer_comment" if eligible else "public_source_changed",
                source_kind="comment",
                source_key=f"{row.id}:{row.version}",
                source_id=str(row.id),
                source_version=row.version,
                clock=clock,
            )
    db.flush()
    return True


class PublicRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=5, ge=1, le=8)
    cursor: uuid.UUID | None = None


def _rendered_bytes(value: str) -> int:
    # Context JSON is itself encoded inside the model request. Bound the final
    # escaped representation as well as Unicode/neutralisation expansion.
    return len(
        json.dumps(json.dumps(value, ensure_ascii=False), ensure_ascii=False).encode("utf-8")
    )


def display_text(value: str | None, budget: int) -> str:
    rendered = neutralise_untrusted(value or "")
    lower, upper = 0, len(rendered)
    while lower < upper:
        middle = (lower + upper + 1) // 2
        if _rendered_bytes(rendered[:middle]) <= budget:
            lower = middle
        else:
            upper = middle - 1
    return rendered[:lower]


def _comment_view(row: PublicComment) -> dict[str, Any]:
    author = row.author_external_id
    if author is not None and (
        neutralise_untrusted(author) != author or _rendered_bytes(author) > 100
    ):
        author = None
    return {
        "id": str(row.id),
        "version": row.version,
        "parent_id": str(row.parent_id) if row.parent_id else None,
        "author_id": author,
        "author_id_omitted": row.author_external_id is not None and author is None,
        "is_owner": row.is_owner,
        "text": display_text(row.text, 280),
    }


def model_context(db: Session, clock: Clock, ctx: BrokerContext) -> dict[str, Any]:
    data = public_context(db, clock, ctx, PublicRead())
    agent = scoped_thread(db, ctx.workspace.workspace_id, ctx.account_id, ctx.thread_id)
    event = db.scalar(
        select(AgentEvent).where(
            AgentEvent.workspace_id == agent.workspace_id,
            AgentEvent.social_account_id == ctx.account_id,
            AgentEvent.thread_id == agent.id,
            AgentEvent.cursor == agent.event_cursor,
            AgentEvent.source_kind == "comment",
        )
    )
    data["current_source"] = None
    if event is None or data["media"]["state"] == "deleted":
        return data
    try:
        source_id = uuid.UUID(event.source_id or "")
    except ValueError:
        return data
    row = db.scalar(
        select(PublicComment).where(
            PublicComment.id == source_id,
            PublicComment.workspace_id == agent.workspace_id,
            PublicComment.social_account_id == ctx.account_id,
            PublicComment.thread_id == agent.public_thread_id,
            PublicComment.version == event.source_version,
            PublicComment.state == "visible",
        )
    )
    if row is not None:
        item = _comment_view(row)
        data["current_source"] = item
        if not any(r["id"] == item["id"] for r in data["comments"]):
            data["comments"] = data["comments"][:4] + [item]
    return data


def public_context(
    db: Session, _clock: Clock, ctx: BrokerContext, args: BaseModel
) -> dict[str, Any]:
    request = PublicRead.model_validate(args)
    agent = scoped_thread(db, ctx.workspace.workspace_id, ctx.account_id, ctx.thread_id)
    if agent.surface != "comment" or agent.public_thread_id is None:
        raise ToolInputError("public thread unavailable")
    thread = db.scalar(
        select(PublicThread).where(
            PublicThread.id == agent.public_thread_id,
            PublicThread.workspace_id == ctx.workspace.workspace_id,
            PublicThread.social_account_id == ctx.account_id,
        )
    )
    if thread is None:
        raise ToolInputError("public thread unavailable")
    media = scoped_media(db, ctx.workspace.workspace_id, ctx.account_id, thread.media_id)
    query = select(PublicComment).where(
        PublicComment.workspace_id == ctx.workspace.workspace_id,
        PublicComment.social_account_id == ctx.account_id,
        PublicComment.thread_id == thread.id,
        PublicComment.state == "visible",
    )
    if request.cursor:
        query = query.where(PublicComment.id > request.cursor)
    rows = list(db.scalars(query.order_by(PublicComment.id).limit(request.limit + 1)))
    if media.state == "deleted":
        rows = []
    return {
        "event_cursor": agent.event_cursor,
        "is_simulated": media.is_simulated,
        "media": {
            "id": str(media.id),
            "version": media.version,
            "state": media.state,
            "ownership_state": media.ownership_state,
            "caption": display_text(media.caption, 320),
        },
        "comments": [_comment_view(r) for r in rows[: request.limit]],
        "next_cursor": str(rows[request.limit - 1].id) if len(rows) > request.limit else None,
    }
