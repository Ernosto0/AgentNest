"""One deterministic, approval-only follow-up per legacy conversation (F-10).

All helpers participate in the caller's transaction. No model or external calls.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.agent.repository import scoped_account
from app.approvals import service as approvals
from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.ids import new_id
from app.identity.models import Workspace
from app.identity.schemas import WorkspaceSettings
from app.inbox import attention, drafts
from app.inbox.approval_payload import approval_payload, approval_summary
from app.inbox.context import MESSAGING_WINDOW
from app.inbox.models import Conversation, ConversationFollowUp, ReplyDraft
from app.inbox.payloads import FollowUpCheckPayload
from app.inbox.reply_workflow import _newest_inbound_id, deadlines
from app.integrations.instagram.models import SocialAccount
from app.jobs.queue import enqueue
from app.jobs.registry import RescheduleJob
from app.knowledge import impact
from app.knowledge import service as knowledge_service
from app.knowledge.claims import length_issue, validate_claims
from app.knowledge.render import render
from app.knowledge.sources import span_records
from app.policy.rules_reply import WINDOW_MARGIN

ANSWER_INTENTS = frozenset({"pricing", "booking"})
ANSWER_SOURCES = frozenset({"ai", "approved_answer"})
DEFAULT_TEXT_TR = "Başka bir konuda yardımcı olabilir miyiz?"
DEFAULT_TEXT_EN = "Can we help you with anything else?"
DEFAULT_TEXT = {"tr": DEFAULT_TEXT_TR, "en": DEFAULT_TEXT_EN}
APPROVAL_REASON = "FOLLOW_UP_REQUIRES_APPROVAL"


def settings_for(session: Session, workspace_id: uuid.UUID) -> WorkspaceSettings:
    workspace = session.get(Workspace, workspace_id)
    return WorkspaceSettings.model_validate(workspace.settings if workspace else {})


def schedule_after_answer(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    conversation: Conversation,
    draft: ReplyDraft,
    *,
    sent_at: datetime,
) -> None:
    settings = settings_for(session, ctx.workspace_id)
    if not settings.follow_up_enabled or not (
        draft.origin == "legacy"
        and draft.source in ANSWER_SOURCES
        and draft.intent in ANSWER_INTENTS
        and conversation.handling_mode == "automatic"
        and conversation.last_inbound_at is not None
        and draft.covers_through_message_id is not None
    ):
        return
    if (
        _newest_inbound_id(session, ctx.workspace_id, conversation.id)
        != draft.covers_through_message_id
    ):
        return
    controller = scoped_account(session, ctx.workspace_id, conversation.social_account_id)
    if controller.controller_mode != "legacy":
        return
    due_at = sent_at + timedelta(hours=settings.follow_up_hours)
    if conversation.last_inbound_at is None:
        return
    closed = due_at >= conversation.last_inbound_at + MESSAGING_WINDOW - WINDOW_MARGIN
    now = clock.now()
    values = {
        "answer_draft_id": draft.id,
        "covers_through_message_id": draft.covers_through_message_id,
        "answered_at": sent_at,
        "due_at": due_at,
        "status": "skipped" if closed else "scheduled",
        "reason_code": "MESSAGING_WINDOW_CLOSED" if closed else None,
        "updated_at": now,
    }
    row_id = session.scalar(
        insert(ConversationFollowUp)
        .values(
            id=new_id(),
            workspace_id=ctx.workspace_id,
            conversation_id=conversation.id,
            is_simulated=conversation.is_simulated,
            created_at=now,
            **values,
        )
        .on_conflict_do_update(
            index_elements=["workspace_id", "conversation_id"],
            set_=values,
            where=ConversationFollowUp.status.in_(("scheduled", "cancelled", "skipped")),
        )
        .returning(ConversationFollowUp.id)
    )
    if row_id is None:
        return
    if closed:
        row = session.get(ConversationFollowUp, row_id, populate_existing=True)
        if row is None:
            return
        _finish(session, clock, ctx, row, "skipped", "MESSAGING_WINDOW_CLOSED")
    else:
        enqueue(
            session,
            "follow_up_check",
            FollowUpCheckPayload(follow_up_id=row_id, answer_draft_id=draft.id),
            workspace_id=ctx.workspace_id,
            run_at=due_at,
            correlation_id=None,
            dedup_key=f"follow_up_check:{row_id}:{draft.id}",
            clock=clock,
        )


def _finish(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    row: ConversationFollowUp,
    status: str,
    reason: str,
) -> None:
    row.status, row.reason_code, row.updated_at = status, reason, clock.now()
    audit.record(
        session,
        ctx,
        f"follow_up.{status}",
        "conversation_follow_up",
        row.id,
        {
            "conversation_id": row.conversation_id,
            "answer_draft_id": row.answer_draft_id,
            "reason_code": reason,
        },
        is_simulated=row.is_simulated,
        clock=clock,
    )


def cancel_on_inbound(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    conversation: Conversation,
) -> None:
    # Caller holds the conversation lock. Do not take a follow-up lock before that lock.
    row = session.scalar(
        select(ConversationFollowUp)
        .where(
            ConversationFollowUp.workspace_id == ctx.workspace_id,
            ConversationFollowUp.conversation_id == conversation.id,
        )
        .with_for_update()
    )
    if row is None:
        return
    if row.status == "scheduled":
        _finish(session, clock, ctx, row, "cancelled", "CUSTOMER_REPLIED")
    elif row.status == "drafted" and row.reply_draft_id:
        draft = drafts.get_draft(session, ctx.workspace_id, row.reply_draft_id, lock=True)
        if draft and draft.status == "queued":
            drafts.transition(session, clock, ctx, draft, "cancel", reason="CUSTOMER_REPLIED")
            approvals.cancel_for_subject(
                session, clock, ctx, "reply_draft", draft.id, "CUSTOMER_REPLIED"
            )


def send_rejection(
    session: Session,
    ctx: WorkspaceContext,
    conversation: Conversation,
    draft: ReplyDraft,
) -> str | None:
    row_id = session.scalar(
        select(ConversationFollowUp.id).where(
            ConversationFollowUp.workspace_id == ctx.workspace_id,
            ConversationFollowUp.reply_draft_id == draft.id,
        )
    )
    if row_id is None:
        return None
    if (
        _newest_inbound_id(session, ctx.workspace_id, conversation.id)
        != draft.covers_through_message_id
    ):
        return "CUSTOMER_REPLIED"
    if not settings_for(session, ctx.workspace_id).follow_up_enabled:
        return "FOLLOW_UP_OFF"
    if conversation.handling_mode != "automatic":
        return "HUMAN_TAKEOVER"
    return None


def check(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    payload: FollowUpCheckPayload,
) -> None:
    query = select(ConversationFollowUp).where(
        ConversationFollowUp.workspace_id == ctx.workspace_id,
        ConversationFollowUp.id == payload.follow_up_id,
    )
    row = session.scalar(query)
    if row is None or row.status != "scheduled" or row.answer_draft_id != payload.answer_draft_id:
        return
    ref = session.scalar(
        select(Conversation).where(
            Conversation.workspace_id == ctx.workspace_id,
            Conversation.id == row.conversation_id,
        )
    )
    if ref is None:
        return
    controller = scoped_account(session, ctx.workspace_id, ref.social_account_id, lock=True)
    conversation = session.scalar(
        select(Conversation)
        .where(
            Conversation.workspace_id == ctx.workspace_id,
            Conversation.id == ref.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if conversation is None:
        return
    row = session.scalar(query.with_for_update().execution_options(populate_existing=True))
    if row is None or row.status != "scheduled" or row.answer_draft_id != payload.answer_draft_id:
        return
    settings = settings_for(session, ctx.workspace_id)
    if not settings.follow_up_enabled:
        _finish(session, clock, ctx, row, "cancelled", "FOLLOW_UP_OFF")
        return
    now = clock.now()
    due = row.answered_at + timedelta(hours=settings.follow_up_hours)
    if now < due:
        raise RescheduleJob(due)
    answer = drafts.get_draft(session, ctx.workspace_id, row.answer_draft_id)
    account = session.get(SocialAccount, conversation.social_account_id)
    window_end = (
        conversation.last_inbound_at + MESSAGING_WINDOW if conversation.last_inbound_at else None
    )
    reason = None
    status = "skipped"
    if (
        _newest_inbound_id(session, ctx.workspace_id, conversation.id)
        != row.covers_through_message_id
    ):
        reason, status = "CUSTOMER_REPLIED", "cancelled"
    elif conversation.last_outbound_at and conversation.last_outbound_at > row.answered_at:
        reason = "SOMEONE_ELSE_REPLIED"
    elif conversation.handling_mode != "automatic":
        reason = "HUMAN_TAKEOVER"
    elif (
        controller.controller_mode != "legacy"
        or answer is None
        or controller.cutover_generation
        != answer.validation.get("controller_cutover_generation", 0)
    ):
        reason = "CONTROLLER_CHANGED"
    elif (
        account is None
        or account.status != "connected"
        or account.capabilities.get("messaging") is not True
    ):
        reason = "ACCOUNT_NOT_CONNECTED"
    elif drafts.get_open_draft(session, ctx.workspace_id, conversation.id) is not None:
        reason = "OPEN_DRAFT_EXISTS"
    elif window_end is None or now >= window_end - WINDOW_MARGIN:
        reason = "MESSAGING_WINDOW_CLOSED"
    if reason:
        _finish(session, clock, ctx, row, status, reason)
        return
    if answer is None or window_end is None:
        return
    workspace = session.get(Workspace, ctx.workspace_id)
    if workspace is None:
        return
    language = (
        answer.language
        if answer.language in workspace.reply_languages
        else workspace.default_locale
    )
    language = language if language in ("tr", "en") else "tr"
    template = getattr(settings.follow_up_text, language) or DEFAULT_TEXT[language]
    rendered = render(
        template, knowledge_service.usable_facts(session, clock, ctx, locale=language), language
    )
    if not rendered.ok:
        _finish(session, clock, ctx, row, "skipped", "FACT_NOT_USABLE")
        return
    report = validate_claims(rendered.text, rendered, language)
    if not report.passed or length_issue(rendered.text, max_bytes=1000):
        _finish(session, clock, ctx, row, "skipped", "GROUNDING_FAILED")
        return
    # Row and conversation locks serialize duplicate checks and inbound cancellation. The
    # conditional update is a second fence; a lost claim rolls back the entire draft savepoint.
    with session.begin_nested() as savepoint:
        draft = ReplyDraft(
            workspace_id=ctx.workspace_id,
            conversation_id=conversation.id,
            covers_through_message_id=row.covers_through_message_id,
            source="approved_answer",
            origin="legacy",
            intent="follow_up",
            language=language,
            template=template,
            text=rendered.text,
            validation={
                "passed": True,
                "issues": [],
                "rendered": span_records(rendered.spans),
                "controller_cutover_generation": controller.cutover_generation,
            },
            decision="approval_required",
            decision_reasons=[APPROVAL_REASON],
            status="pending_approval",
            created_by_actor_type="system",
            is_simulated=conversation.is_simulated,
            created_at=now,
        )
        session.add(draft)
        session.flush()
        claimed = session.execute(
            update(ConversationFollowUp)
            .where(
                ConversationFollowUp.workspace_id == ctx.workspace_id,
                ConversationFollowUp.id == row.id,
                ConversationFollowUp.status == "scheduled",
                ConversationFollowUp.reply_draft_id.is_(None),
            )
            .values(status="drafted", reply_draft_id=draft.id, drafted_at=now, updated_at=now)
        )
        if claimed.rowcount != 1:  # type: ignore[attr-defined]
            savepoint.rollback()
            return
        impact.replace_references(session, ctx, "reply_draft", draft.id, rendered.used)
        expires_at, execute_before = deadlines(window_end, now)
        approval = approvals.request(
            session,
            clock,
            ctx,
            kind="authorization",
            action="reply.send",
            subject_type="reply_draft",
            subject_id=draft.id,
            subject_version=draft.version,
            payload=approval_payload(draft, conversation),
            summary=approval_summary(
                draft.id, conversation.id, [APPROVAL_REASON], window_end.isoformat()
            ),
            required_permission="reply.approve",
            expires_at=expires_at,
            execute_before=execute_before,
            is_simulated=draft.is_simulated,
        )
        draft.approval_id = approval.id
        audit.record(
            session,
            ctx,
            "reply_draft.created",
            "reply_draft",
            draft.id,
            {
                "conversation_id": conversation.id,
                "decision": "approval_required",
                "reasons": [APPROVAL_REASON],
                "status": "pending_approval",
                "intent": "follow_up",
            },
            is_simulated=draft.is_simulated,
            clock=clock,
        )
        audit.record(
            session,
            ctx,
            "follow_up.drafted",
            "conversation_follow_up",
            row.id,
            {
                "conversation_id": conversation.id,
                "reply_draft_id": draft.id,
                "reason_code": APPROVAL_REASON,
            },
            is_simulated=draft.is_simulated,
            clock=clock,
        )
        attention.refresh(session, conversation)
