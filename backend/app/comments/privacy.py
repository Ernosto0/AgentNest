"""Public source erasure and bounded retention, preserving content-free tombstones."""

import uuid
from datetime import datetime

from sqlalchemy import null, or_, select, update
from sqlalchemy.orm import Session

from app.agent.models import AgentThread
from app.agent.repository import scoped_account
from app.comments.models import (
    PublicComment,
    PublicCommentAction,
    PublicMedia,
    SimCommentEffect,
    SimPublicComment,
)
from app.core.clock import Clock
from app.inbox.models import InboundEvent


def redact_receipts(db: Session, workspace: uuid.UUID, account: uuid.UUID, external: str) -> None:
    targets = select(PublicComment.id).where(
        PublicComment.workspace_id == workspace,
        PublicComment.social_account_id == account,
        PublicComment.external_id == external,
    )
    db.execute(
        update(PublicCommentAction)
        .where(
            PublicCommentAction.workspace_id == workspace,
            PublicCommentAction.social_account_id == account,
            PublicCommentAction.comment_id.in_(targets),
        )
        .values(text=None, proposal=null())
    )
    db.execute(
        update(SimCommentEffect)
        .where(
            SimCommentEffect.workspace_id == workspace,
            SimCommentEffect.social_account_id == account,
            SimCommentEffect.target_external_id == external,
        )
        .values(text=None)
    )
    db.execute(
        update(InboundEvent)
        .where(
            InboundEvent.workspace_id == workspace,
            InboundEvent.social_account_id == account,
            InboundEvent.event_type == "comment",
            InboundEvent.payload["id"].astext == external,
        )
        .values(payload=null())
    )
    db.execute(
        update(SimPublicComment)
        .where(
            SimPublicComment.workspace_id == workspace,
            SimPublicComment.social_account_id == account,
            SimPublicComment.external_id == external,
        )
        .values(value=null())
    )


def redact_media_caches(db: Session, media: PublicMedia) -> None:
    target_ids = select(PublicComment.id).where(
        PublicComment.workspace_id == media.workspace_id,
        PublicComment.social_account_id == media.social_account_id,
        PublicComment.media_id == media.id,
    )
    target_external_ids = select(PublicComment.external_id).where(
        PublicComment.workspace_id == media.workspace_id,
        PublicComment.social_account_id == media.social_account_id,
        PublicComment.media_id == media.id,
    )
    db.execute(
        update(PublicCommentAction)
        .where(
            PublicCommentAction.workspace_id == media.workspace_id,
            PublicCommentAction.social_account_id == media.social_account_id,
            PublicCommentAction.comment_id.in_(target_ids),
        )
        .values(text=None, proposal=null())
    )
    db.execute(
        update(SimCommentEffect)
        .where(
            SimCommentEffect.workspace_id == media.workspace_id,
            SimCommentEffect.social_account_id == media.social_account_id,
            SimCommentEffect.target_external_id.in_(target_external_ids),
        )
        .values(text=None)
    )
    db.execute(
        update(InboundEvent)
        .where(
            InboundEvent.workspace_id == media.workspace_id,
            InboundEvent.social_account_id == media.social_account_id,
            InboundEvent.event_type == "comment",
            InboundEvent.payload["media_id"].astext == media.external_id,
        )
        .values(payload=null())
    )
    db.execute(
        update(SimPublicComment)
        .where(
            SimPublicComment.workspace_id == media.workspace_id,
            SimPublicComment.social_account_id == media.social_account_id,
            SimPublicComment.value["media_id"].astext == media.external_id,
        )
        .values(value=null())
    )


def erase_account(db: Session, clock: Clock, workspace: uuid.UUID, account: uuid.UUID) -> None:
    scoped_account(db, workspace, account, lock=True)
    db.execute(
        update(PublicCommentAction)
        .where(
            PublicCommentAction.workspace_id == workspace,
            PublicCommentAction.social_account_id == account,
        )
        .values(text=None, proposal=null())
    )
    db.execute(
        update(SimCommentEffect)
        .where(
            SimCommentEffect.workspace_id == workspace,
            SimCommentEffect.social_account_id == account,
        )
        .values(text=None)
    )
    db.execute(
        update(PublicComment)
        .where(PublicComment.workspace_id == workspace, PublicComment.social_account_id == account)
        .values(
            text=None,
            author_external_id=None,
            state="deleted",
            version=PublicComment.version + 1,
            updated_at=clock.now(),
        )
    )
    db.execute(
        update(PublicMedia)
        .where(PublicMedia.workspace_id == workspace, PublicMedia.social_account_id == account)
        .values(
            caption=None, state="deleted", version=PublicMedia.version + 1, updated_at=clock.now()
        )
    )
    db.execute(
        update(SimPublicComment)
        .where(
            SimPublicComment.workspace_id == workspace,
            SimPublicComment.social_account_id == account,
        )
        .values(value=null())
    )
    db.execute(
        update(AgentThread)
        .where(
            AgentThread.workspace_id == workspace,
            AgentThread.social_account_id == account,
            AgentThread.surface == "comment",
        )
        .values(
            deletion_generation=AgentThread.deletion_generation + 1,
            event_cursor=AgentThread.event_cursor + 1,
        )
    )


def retention_batch(db: Session, clock: Clock, cutoff: datetime, limit: int) -> tuple[int, int]:
    changed = 0
    rows = list(
        db.scalars(
            select(PublicComment)
            .where(
                PublicComment.updated_at < cutoff,
                or_(PublicComment.text.is_not(None), PublicComment.author_external_id.is_not(None)),
            )
            .order_by(PublicComment.id)
            .limit(limit)
        )
    )
    for row in rows:
        scoped_account(db, row.workspace_id, row.social_account_id, lock=True)
        db.refresh(row, with_for_update=True)
        if row.updated_at >= cutoff or (row.text is None and row.author_external_id is None):
            continue
        row.text, row.author_external_id, row.state = None, None, "deleted"
        row.version += 1
        row.updated_at = clock.now()
        changed += 1
        redact_receipts(db, row.workspace_id, row.social_account_id, row.external_id)
        db.execute(
            update(AgentThread)
            .where(
                AgentThread.workspace_id == row.workspace_id,
                AgentThread.social_account_id == row.social_account_id,
                AgentThread.public_thread_id == row.thread_id,
            )
            .values(
                deletion_generation=AgentThread.deletion_generation + 1,
                event_cursor=AgentThread.event_cursor + 1,
            )
        )
        db.execute(
            update(SimPublicComment)
            .where(
                SimPublicComment.workspace_id == row.workspace_id,
                SimPublicComment.social_account_id == row.social_account_id,
                SimPublicComment.external_id == row.external_id,
            )
            .values(value=null())
        )
    media = list(
        db.scalars(
            select(PublicMedia)
            .where(PublicMedia.updated_at < cutoff, PublicMedia.caption.is_not(None))
            .order_by(PublicMedia.id)
            .limit(limit)
        )
    )
    for item in media:
        scoped_account(db, item.workspace_id, item.social_account_id, lock=True)
        db.refresh(item, with_for_update=True)
        if item.updated_at >= cutoff or item.caption is None:
            continue
        # Caption retention is a local body expiry, never evidence that the
        # provider removed the post. Fresh comments remain eligible.
        item.caption = None
        item.version += 1
        item.updated_at = clock.now()
        changed += 1
    db.flush()
    return changed, max(len(rows), len(media))
