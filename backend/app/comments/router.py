"""Permission-checked public source pages; foreign account/media/thread IDs are 404."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_membership
from app.comments.models import PublicComment, PublicMedia, PublicThread
from app.comments.service import scoped_media
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError
from app.integrations.instagram import queries

router = APIRouter(
    prefix="/workspaces/{workspace_id}/accounts/{account_id}/comments", tags=["comments"]
)


class MediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    external_id: str
    caption: str | None
    state: str
    ownership_state: str
    version: int
    is_simulated: bool


class MediaPage(BaseModel):
    items: list[MediaOut]
    next_cursor: uuid.UUID | None


class ThreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    media_id: uuid.UUID
    root_external_id: str


class ThreadPage(BaseModel):
    items: list[ThreadOut]
    next_cursor: uuid.UUID | None


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    external_id: str
    media_id: uuid.UUID
    thread_id: uuid.UUID
    parent_id: uuid.UUID | None
    author_external_id: str | None
    text: str | None
    state: str
    version: int
    provider_timestamp: datetime | None
    is_owner: bool
    is_simulated: bool


class CommentPage(BaseModel):
    items: list[CommentOut]
    next_cursor: uuid.UUID | None


@router.get("", response_model=CommentPage)
def account_comments(
    account_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=50),
    cursor: uuid.UUID | None = None,
    media_id: uuid.UUID | None = None,
    ctx: WorkspaceContext = Depends(require_membership("comments.view")),
    db: Session = Depends(get_db),
) -> CommentPage:
    if queries.get_account_in_workspace(db, ctx.workspace_id, account_id) is None:
        raise AppError("NOT_FOUND")
    if media_id is not None:
        scoped_media(db, ctx.workspace_id, account_id, media_id)
    query = (
        select(PublicComment, PublicMedia.state)
        .join(PublicMedia, PublicMedia.id == PublicComment.media_id)
        .where(
            PublicComment.workspace_id == ctx.workspace_id,
            PublicComment.social_account_id == account_id,
            PublicMedia.workspace_id == ctx.workspace_id,
            PublicMedia.social_account_id == account_id,
        )
    )
    if media_id is not None:
        query = query.where(PublicComment.media_id == media_id)
    if cursor:
        query = query.where(PublicComment.id > cursor)
    rows = list(db.execute(query.order_by(PublicComment.id).limit(limit + 1)))
    items = []
    for row, media_state in rows[:limit]:
        item = CommentOut.model_validate(row)
        if media_state == "deleted":
            item.text, item.state = None, "deleted"
        items.append(item)
    return CommentPage(
        items=items, next_cursor=rows[limit - 1][0].id if len(rows) > limit else None
    )


@router.get("/media", response_model=MediaPage)
def media_page(
    account_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=50),
    cursor: uuid.UUID | None = None,
    ctx: WorkspaceContext = Depends(require_membership("comments.view")),
    db: Session = Depends(get_db),
) -> MediaPage:
    if queries.get_account_in_workspace(db, ctx.workspace_id, account_id) is None:
        raise AppError("NOT_FOUND")
    query = select(PublicMedia).where(
        PublicMedia.workspace_id == ctx.workspace_id, PublicMedia.social_account_id == account_id
    )
    if cursor:
        query = query.where(PublicMedia.id > cursor)
    rows = list(db.scalars(query.order_by(PublicMedia.id).limit(limit + 1)))
    return MediaPage(
        items=[MediaOut.model_validate(r) for r in rows[:limit]],
        next_cursor=rows[limit - 1].id if len(rows) > limit else None,
    )


@router.get("/media/{media_id}", response_model=MediaOut)
def media_detail(
    account_id: uuid.UUID,
    media_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("comments.view")),
    db: Session = Depends(get_db),
) -> MediaOut:
    return MediaOut.model_validate(scoped_media(db, ctx.workspace_id, account_id, media_id))


@router.get("/media/{media_id}/threads", response_model=ThreadPage)
def thread_page(
    account_id: uuid.UUID,
    media_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=50),
    cursor: uuid.UUID | None = None,
    ctx: WorkspaceContext = Depends(require_membership("comments.view")),
    db: Session = Depends(get_db),
) -> ThreadPage:
    scoped_media(db, ctx.workspace_id, account_id, media_id)
    query = select(PublicThread).where(
        PublicThread.workspace_id == ctx.workspace_id,
        PublicThread.social_account_id == account_id,
        PublicThread.media_id == media_id,
    )
    if cursor:
        query = query.where(PublicThread.id > cursor)
    rows = list(db.scalars(query.order_by(PublicThread.id).limit(limit + 1)))
    return ThreadPage(
        items=[ThreadOut.model_validate(r) for r in rows[:limit]],
        next_cursor=rows[limit - 1].id if len(rows) > limit else None,
    )


@router.get("/threads/{thread_id}", response_model=CommentPage)
def comment_page(
    account_id: uuid.UUID,
    thread_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=50),
    cursor: uuid.UUID | None = None,
    ctx: WorkspaceContext = Depends(require_membership("comments.view")),
    db: Session = Depends(get_db),
) -> CommentPage:
    thread = db.scalar(
        select(PublicThread).where(
            PublicThread.id == thread_id,
            PublicThread.workspace_id == ctx.workspace_id,
            PublicThread.social_account_id == account_id,
        )
    )
    if thread is None:
        raise AppError("NOT_FOUND")
    query = select(PublicComment).where(
        PublicComment.workspace_id == ctx.workspace_id,
        PublicComment.social_account_id == account_id,
        PublicComment.thread_id == thread_id,
    )
    if cursor:
        query = query.where(PublicComment.id > cursor)
    rows = list(db.scalars(query.order_by(PublicComment.id).limit(limit + 1)))
    items = [CommentOut.model_validate(r) for r in rows[:limit]]
    if scoped_media(db, ctx.workspace_id, account_id, thread.media_id).state == "deleted":
        for item in items:
            item.text, item.state = None, "deleted"
    return CommentPage(items=items, next_cursor=rows[limit - 1].id if len(rows) > limit else None)


def comment_scope(
    db: Session, ctx: WorkspaceContext, account: uuid.UUID, comment: uuid.UUID
) -> PublicComment:
    row = db.scalar(
        select(PublicComment).where(
            PublicComment.workspace_id == ctx.workspace_id,
            PublicComment.social_account_id == account,
            PublicComment.id == comment,
        )
    )
    if row is None:
        raise AppError("NOT_FOUND")
    return row


@router.get("/{comment_id}", response_model=CommentOut)
def comment_detail(
    account_id: uuid.UUID,
    comment_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("comments.view")),
    db: Session = Depends(get_db),
) -> CommentOut:
    row = comment_scope(db, ctx, account_id, comment_id)
    result = CommentOut.model_validate(row)
    if scoped_media(db, ctx.workspace_id, account_id, row.media_id).state == "deleted":
        result.text, result.state = None, "deleted"
    return result


@router.get("/{comment_id}/thread", response_model=CommentPage)
def comment_thread(
    account_id: uuid.UUID,
    comment_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=50),
    cursor: uuid.UUID | None = None,
    ctx: WorkspaceContext = Depends(require_membership("comments.view")),
    db: Session = Depends(get_db),
) -> CommentPage:
    row = comment_scope(db, ctx, account_id, comment_id)
    return comment_page(account_id, row.thread_id, limit, cursor, ctx, db)
