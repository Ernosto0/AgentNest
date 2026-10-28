"""Read models of the inbox: conversations, messages and drafts as the API shows them."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.approvals import repository as approvals_repo
from app.core.context import WorkspaceContext
from app.identity.models import User
from app.inbox.attention import customer_number
from app.inbox.context import MESSAGING_WINDOW
from app.inbox.models import Conversation, Message, ReplyDraft
from app.inbox.schemas import (
    ApprovalStateOut,
    ConversationOut,
    MessageOut,
    RenderedFactOut,
    ReplyDraftOut,
    ValidationIssueOut,
    ValidationOut,
)
from app.knowledge.models import BusinessFact

PREVIEW_CHARS = 80


def window_end(conversation: Conversation) -> datetime | None:
    return conversation.last_inbound_at + MESSAGING_WINDOW if conversation.last_inbound_at else None


def last_messages(
    session: Session, ctx: WorkspaceContext, conversation_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Message]:
    """The newest message of each conversation, in one query."""
    if not conversation_ids:
        return {}
    rows = session.scalars(
        select(Message)
        .ext(distinct_on(Message.conversation_id))
        .where(
            Message.workspace_id == ctx.workspace_id,
            Message.conversation_id.in_(conversation_ids),
        )
        .order_by(
            Message.conversation_id, Message.provider_timestamp.desc(), Message.created_at.desc()
        )
    )
    return {row.conversation_id: row for row in rows}


def _preview(message: Message | None) -> str | None:
    if message is None or message.is_deleted:
        return None
    text = (message.text or "").strip()
    if not text and message.attachments:
        return "[attachment]"
    return text[:PREVIEW_CHARS] or None


def conversation_out(conversation: Conversation, last: Message | None) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        customer_handle=conversation.customer_handle,
        customer_number=customer_number(conversation.id),
        last_message_preview=_preview(last),
        last_message_at=conversation.last_message_at,
        attention=conversation.attention,
        handling_mode=conversation.handling_mode,
        window_ends_at=window_end(conversation),
        is_simulated=conversation.is_simulated,
    )


def message_out(message: Message) -> MessageOut:
    return MessageOut(
        id=message.id,
        direction=message.direction,
        sender_kind=message.sender_kind,
        text=None if message.is_deleted else message.text,
        attachments=[] if message.is_deleted else list(message.attachments or []),
        provider_timestamp=message.provider_timestamp,
        is_simulated=message.is_simulated,
    )


def issue_out(issue: dict[str, object], *, matches_verified: bool = False) -> ValidationIssueOut:
    span = issue.get("span")
    return ValidationIssueOut(
        code=str(issue.get("code", "")),
        span=[int(x) for x in span] if isinstance(span, list) else None,
        text=str(issue.get("text", "")),
        matches_verified=matches_verified or bool(issue.get("matches_verified")),
    )


def approval_state(
    session: Session, ctx: WorkspaceContext, draft: ReplyDraft
) -> ApprovalStateOut | None:
    """The state of the draft's approval, or ``None`` if it has none. Workspace-scoped; shows
    who decided and the note, never the payload."""
    if draft.approval_id is None:
        return None
    approval = approvals_repo.get_approval(session, ctx, draft.approval_id)
    if approval is None:
        return None
    name = (
        session.scalar(select(User.display_name).where(User.id == approval.decided_by_user_id))
        if approval.decided_by_user_id
        else None
    )
    return ApprovalStateOut(
        status=approval.status,
        expires_at=approval.expires_at,
        decided_by_name=name,
        decided_at=approval.decided_at,
        decision_note=approval.decision_note,
    )


def draft_out(
    session: Session, ctx: WorkspaceContext, draft: ReplyDraft, conversation: Conversation
) -> ReplyDraftOut:
    language = draft.language or "tr"
    rendered = list(draft.validation.get("rendered", []))
    fact_ids = [uuid.UUID(r["fact_id"]) for r in rendered]
    facts = (
        {
            f.id: f
            for f in session.scalars(
                select(BusinessFact).where(
                    BusinessFact.workspace_id == ctx.workspace_id, BusinessFact.id.in_(fact_ids)
                )
            )
        }
        if fact_ids
        else {}
    )
    rendered_facts = [
        RenderedFactOut(
            fact_id=uuid.UUID(r["fact_id"]),
            key=r["key"],
            label=_label(facts.get(uuid.UUID(r["fact_id"])), language, r["key"]),
            display=r["display"],
            version=int(r["version"]),
            span=[int(x) for x in r["span"]],
        )
        for r in rendered
    ]
    return ReplyDraftOut(
        id=draft.id,
        conversation_id=draft.conversation_id,
        status=draft.status,
        source=draft.source,
        language=draft.language,
        intent=draft.intent,
        flags=list(draft.flags),
        text=None if draft.validation.get("privacy_redacted") else draft.text,
        suggestion_text=None if draft.validation.get("privacy_redacted") else draft.suggestion_text,
        rendered_facts=rendered_facts,
        validation=ValidationOut(
            passed=bool(draft.validation.get("passed")),
            issues=[issue_out(i) for i in draft.validation.get("issues", [])],
        ),
        decision=draft.decision,
        decision_reasons=list(draft.decision_reasons),
        approval_id=draft.approval_id,
        approval_state=approval_state(session, ctx, draft),
        version=draft.version,
        failure_code=draft.failure_code,
        window_ends_at=window_end(conversation),
        created_at=draft.created_at,
        is_simulated=draft.is_simulated,
    )


def _label(fact: BusinessFact | None, language: str, fallback: str) -> str:
    if fact is None:
        return fallback
    return fact.label.get(language) or fact.label.get("tr") or fact.label.get("en") or fallback
