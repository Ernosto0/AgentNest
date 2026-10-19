"""Inbox routes (api-design.md §2.6, §2.3 approved answers). Thin: validate, call the service,
map to a model. Every route is workspace-scoped (INV-01): foreign ids are simply not found."""

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_clock, require_membership
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.pagination import Page
from app.inbox import answers, drafts, service, views
from app.inbox.models import Conversation, ReplyDraft
from app.inbox.schemas import (
    AnswerFromMessageIn,
    ApprovedAnswerIn,
    ApprovedAnswerOut,
    ApprovedAnswerPatch,
    ConversationDetailOut,
    ConversationOut,
    DraftPatchIn,
    ManualReplyIn,
    ReplyDraftOut,
    ReplyWithWarningsOut,
)
from app.knowledge import approved_answers
from app.knowledge.models import ApprovedAnswer

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["inbox"])


def _conversation_out(
    db: Session, ctx: WorkspaceContext, conversation: Conversation
) -> ConversationOut:
    last = views.last_messages(db, ctx, [conversation.id]).get(conversation.id)
    return views.conversation_out(conversation, last)


def _draft_out(db: Session, ctx: WorkspaceContext, draft: ReplyDraft) -> ReplyDraftOut:
    conversation = service.get_conversation(db, ctx, draft.conversation_id)
    return views.draft_out(db, ctx, draft, conversation)


def _answer_out(answer: ApprovedAnswer) -> ApprovedAnswerOut:
    return ApprovedAnswerOut(
        id=answer.id,
        title=answer.title,
        intent=answer.intent,
        example_questions=list(answer.example_questions),
        answer_template=answer.answer_template,
        language=answer.language,
        status=answer.status,
        version=answer.version,
        created_from_message_id=answer.created_from_message_id,
        updated_at=answer.updated_at,
    )


# --- conversations -------------------------------------------------------------------------------


@router.get("/conversations", response_model=Page[ConversationOut])
def list_conversations(
    attention: str = Query(default="any"),
    ctx: WorkspaceContext = Depends(require_membership("reply.write")),
    db: Session = Depends(get_db),
) -> Page[ConversationOut]:
    found = service.list_conversations(db, ctx, attention_filter=attention)
    last = views.last_messages(db, ctx, [c.id for c in found])
    return Page(items=[views.conversation_out(c, last.get(c.id)) for c in found])


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(
    conversation_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("reply.write")),
    db: Session = Depends(get_db),
) -> ConversationDetailOut:
    conversation = service.get_conversation(db, ctx, conversation_id)
    open_draft = drafts.get_open_draft(db, ctx.workspace_id, conversation.id)
    recent = [
        d
        for d in drafts.recent_drafts(db, ctx.workspace_id, conversation.id)
        if open_draft is None or d.id != open_draft.id
    ]
    return ConversationDetailOut(
        conversation=_conversation_out(db, ctx, conversation),
        messages=[views.message_out(m) for m in service.recent_messages(db, ctx, conversation)],
        open_draft=views.draft_out(db, ctx, open_draft, conversation) if open_draft else None,
        recent_drafts=[views.draft_out(db, ctx, d, conversation) for d in recent],
    )


@router.post("/conversations/{conversation_id}/takeover", response_model=ConversationOut)
def takeover(
    conversation_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("conversation.takeover")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ConversationOut:
    return _conversation_out(db, ctx, service.takeover(db, clock, ctx, conversation_id))


@router.post("/conversations/{conversation_id}/release", response_model=ConversationOut)
def release(
    conversation_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("conversation.takeover")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ConversationOut:
    return _conversation_out(db, ctx, service.release(db, clock, ctx, conversation_id))


@router.post("/conversations/{conversation_id}/suggest-reply", status_code=202)
def suggest_reply(
    conversation_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("reply.write")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> Response:
    service.suggest_reply(db, clock, ctx, conversation_id)
    return Response(status_code=202)


@router.post(
    "/conversations/{conversation_id}/replies", response_model=ReplyWithWarningsOut, status_code=201
)
def submit_reply(
    conversation_id: uuid.UUID,
    body: ManualReplyIn,
    ctx: WorkspaceContext = Depends(require_membership("reply.write")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ReplyWithWarningsOut:
    draft, warnings = service.submit_manual_reply(
        db,
        clock,
        ctx,
        conversation_id,
        text=body.text,
        client_request_id=body.client_request_id,
        from_draft_id=body.from_draft_id,
    )
    return ReplyWithWarningsOut(draft=_draft_out(db, ctx, draft), warnings=warnings)


# --- reply drafts --------------------------------------------------------------------------------


@router.get("/reply-drafts/{draft_id}", response_model=ReplyDraftOut)
def get_draft(
    draft_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("reply.write")),
    db: Session = Depends(get_db),
) -> ReplyDraftOut:
    return _draft_out(db, ctx, service.get_draft(db, ctx, draft_id))


@router.patch("/reply-drafts/{draft_id}", response_model=ReplyWithWarningsOut)
def edit_draft(
    draft_id: uuid.UUID,
    body: DraftPatchIn,
    ctx: WorkspaceContext = Depends(require_membership("reply.write")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ReplyWithWarningsOut:
    draft, warnings = service.edit_draft(
        db,
        clock,
        ctx,
        draft_id,
        text=body.text,
        expected_version=body.expected_version,
        approve=body.approve,
    )
    return ReplyWithWarningsOut(draft=_draft_out(db, ctx, draft), warnings=warnings)


@router.post("/reply-drafts/{draft_id}/cancel", response_model=ReplyDraftOut)
def cancel_draft(
    draft_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("reply.write")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ReplyDraftOut:
    return _draft_out(db, ctx, service.cancel_draft(db, clock, ctx, draft_id))


# --- approved answers (owners and managers write; every member reads) ----------------------------


@router.get("/approved-answers", response_model=Page[ApprovedAnswerOut])
def list_answers(
    status: str | None = Query(default=None),
    ctx: WorkspaceContext = Depends(require_membership("approvals.view")),
    db: Session = Depends(get_db),
) -> Page[ApprovedAnswerOut]:
    return Page(
        items=[_answer_out(a) for a in approved_answers.list_answers(db, ctx, status=status)]
    )


@router.post("/approved-answers", response_model=ApprovedAnswerOut, status_code=201)
def create_answer(
    body: ApprovedAnswerIn,
    ctx: WorkspaceContext = Depends(require_membership("knowledge.verify")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ApprovedAnswerOut:
    return _answer_out(approved_answers.create_answer(db, clock, ctx, **body.model_dump()))


@router.patch("/approved-answers/{answer_id}", response_model=ApprovedAnswerOut)
def update_answer(
    answer_id: uuid.UUID,
    body: ApprovedAnswerPatch,
    ctx: WorkspaceContext = Depends(require_membership("knowledge.verify")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ApprovedAnswerOut:
    return _answer_out(
        approved_answers.update_answer(
            db, clock, ctx, answer_id, **body.model_dump(exclude_unset=True)
        )
    )


@router.post(
    "/approved-answers/from-message/{message_id}",
    response_model=ApprovedAnswerOut,
    status_code=201,
)
def answer_from_message(
    message_id: uuid.UUID,
    body: AnswerFromMessageIn,
    ctx: WorkspaceContext = Depends(require_membership("knowledge.verify")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ApprovedAnswerOut:
    return _answer_out(
        answers.save_from_message(
            db,
            clock,
            ctx,
            message_id,
            title=body.title,
            intent=body.intent,
            example_question=body.example_question,
            answer_template=body.answer_template,
        )
    )
