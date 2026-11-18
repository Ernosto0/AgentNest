"""Read models of the inbox: conversations, messages and drafts as the API shows them."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.approvals import repository as approvals_repo
from app.core.context import WorkspaceContext
from app.identity.models import User
from app.inbox import human_agent, stories
from app.inbox.attention import customer_number
from app.inbox.context import MESSAGING_WINDOW
from app.inbox.models import (
    Conversation,
    Message,
    MessageImageDescription,
    MessageTranscript,
    ReplyDraft,
)
from app.inbox.schemas import (
    ApprovalStateOut,
    ConversationOut,
    DraftTranscriptOut,
    FactSourceOut,
    ImageDescriptionOut,
    MessageOut,
    RenderedFactOut,
    ReplyDraftOut,
    StoryOut,
    TranscriptOut,
    ValidationIssueOut,
    ValidationOut,
)
from app.knowledge.sources import FactSource, fact_sources, unique_sources
from app.policy.message_tag import HUMAN_AGENT_WINDOW, WindowState

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


def conversation_out(
    conversation: Conversation,
    last: Message | None,
    *,
    now: datetime | None = None,
    human_agent_available: bool = False,
) -> ConversationOut:
    state: WindowState = "closed"
    until: datetime | None = None
    if now is not None:
        state = human_agent.state_for(
            conversation.last_inbound_at,
            now,
            human_agent_available=human_agent_available,
            margin=human_agent.NEW_REPLY_MARGIN,
        )
        if state == "human_agent_only" and conversation.last_inbound_at is not None:
            until = conversation.last_inbound_at + HUMAN_AGENT_WINDOW
    return ConversationOut(
        id=conversation.id,
        social_account_id=conversation.social_account_id,
        customer_handle=conversation.customer_handle,
        customer_number=customer_number(conversation.id),
        last_message_preview=_preview(last),
        last_message_at=conversation.last_message_at,
        attention=conversation.attention,
        handling_mode=conversation.handling_mode,
        window_ends_at=window_end(conversation),
        window_state=state,
        human_agent_until=until,
        is_simulated=conversation.is_simulated,
    )


def transcripts_by_message(
    session: Session, ctx: WorkspaceContext, message_ids: list[uuid.UUID]
) -> dict[uuid.UUID, MessageTranscript]:
    """The transcripts of these messages, in one query (workspace-scoped)."""
    if not message_ids:
        return {}
    rows = session.scalars(
        select(MessageTranscript).where(
            MessageTranscript.workspace_id == ctx.workspace_id,
            MessageTranscript.message_id.in_(message_ids),
        )
    )
    return {row.message_id: row for row in rows}


def transcript_out(row: MessageTranscript | None) -> TranscriptOut | None:
    if row is None:
        return None
    return TranscriptOut(
        status=row.status,
        text=row.text if row.status == "succeeded" else None,
        language=row.language,
        reason_code=row.reason_code,
        duration_seconds=row.duration_seconds,
    )


def image_descriptions_by_message(
    session: Session, ctx: WorkspaceContext, message_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[MessageImageDescription]]:
    """The image descriptions of these messages, in one query (workspace-scoped)."""
    if not message_ids:
        return {}
    rows = session.scalars(
        select(MessageImageDescription)
        .where(
            MessageImageDescription.workspace_id == ctx.workspace_id,
            MessageImageDescription.message_id.in_(message_ids),
        )
        .order_by(MessageImageDescription.attachment_index)
    )
    found: dict[uuid.UUID, list[MessageImageDescription]] = {}
    for row in rows:
        found.setdefault(row.message_id, []).append(row)
    return found


def image_description_out(row: MessageImageDescription) -> ImageDescriptionOut:
    done = row.status == "succeeded"
    return ImageDescriptionOut(
        attachment_index=row.attachment_index,
        status=row.status,
        looks_like=row.looks_like if done else None,
        description=row.description if done else None,
        visible_text=row.visible_text if done else None,
        injection_suspected=row.injection_suspected and done,
        reason_code=row.reason_code,
    )


def message_out(
    message: Message,
    transcript: MessageTranscript | None = None,
    image_descriptions: list[MessageImageDescription] | None = None,
    story: StoryOut | None = None,
) -> MessageOut:
    return MessageOut(
        id=message.id,
        direction=message.direction,
        sender_kind=message.sender_kind,
        text=None if message.is_deleted else message.text,
        attachments=[] if message.is_deleted else list(message.attachments or []),
        provider_timestamp=message.provider_timestamp,
        is_simulated=message.is_simulated,
        transcript=None if message.is_deleted else transcript_out(transcript),
        image_descriptions=[]
        if message.is_deleted
        else [image_description_out(row) for row in image_descriptions or []],
        story=story,
    )


def _story_out(
    session: Session, ctx: WorkspaceContext, conversation: Conversation, message: Message
) -> StoryOut | None:
    if message.is_deleted or message.direction != "inbound":
        return None
    ref = stories.story_ref(message.attachments)
    if ref is None:
        return None
    content = (
        stories.own_story(
            session,
            ctx.workspace_id,
            conversation.social_account_id,
            ref.story_id,
            message_time=message.provider_timestamp,
        )
        if ref.kind == "reply" and ref.story_id
        else None
    )
    if content is None:
        return StoryOut(
            kind=ref.kind,
            known=False,
            title=None,
            lines=[],
            media_asset_id=None,
            media_deleted=False,
            expired=False,
        )
    return StoryOut(
        kind=ref.kind,
        known=True,
        title=content.title or None,
        lines=list(content.overlay_lines),
        media_asset_id=content.media_asset_id,
        media_deleted=content.media_deleted,
        expired=content.expired,
    )


def messages_out(
    session: Session, ctx: WorkspaceContext, conversation: Conversation, messages: list[Message]
) -> list[MessageOut]:
    """The messages as the API shows them: each with its voice-note transcript, its image
    descriptions, and, for a story reply or mention, its story."""
    ids = [m.id for m in messages]
    transcripts = transcripts_by_message(session, ctx, ids)
    descriptions = image_descriptions_by_message(session, ctx, ids)
    return [
        message_out(
            m,
            transcripts.get(m.id),
            descriptions.get(m.id),
            _story_out(session, ctx, conversation, m),
        )
        for m in messages
    ]


def draft_transcripts_out(
    session: Session, ctx: WorkspaceContext, draft: ReplyDraft
) -> list[DraftTranscriptOut]:
    """The voice notes a reply was drafted from (recorded on the draft by code)."""
    raw = draft.validation.get("transcript_message_ids")
    if not isinstance(raw, list) or not raw:
        return []
    ids = []
    for item in raw:
        try:
            ids.append(uuid.UUID(str(item)))
        except ValueError:
            continue
    found = transcripts_by_message(session, ctx, ids)
    return [
        DraftTranscriptOut(
            message_id=i,
            text=found[i].text if found[i].status == "succeeded" else None,
            language=found[i].language,
        )
        for i in ids
        if i in found
    ]


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


def _facts_used_out(sources: list[FactSource]) -> list[FactSourceOut]:
    return [
        FactSourceOut(
            key=source.key,
            label=source.label,
            display=source.display,
            verified_at=source.verified_at,
        )
        for source in unique_sources(sources)
    ]


def facts_used_out(
    session: Session, ctx: WorkspaceContext, draft: ReplyDraft
) -> list[FactSourceOut]:
    """The verified facts a stored reply quotes, each once, with its source (D-01). Server-side
    for every view of a reply (inbox, approvals, agent approvals)."""
    sources = fact_sources(
        session, ctx.workspace_id, draft.validation.get("rendered", []), draft.language or "tr"
    )
    return _facts_used_out(sources)


def draft_out(
    session: Session, ctx: WorkspaceContext, draft: ReplyDraft, conversation: Conversation
) -> ReplyDraftOut:
    language = draft.language or "tr"
    sources = fact_sources(
        session, ctx.workspace_id, draft.validation.get("rendered", []), language
    )
    rendered_facts = [
        RenderedFactOut(
            fact_id=source.fact_id,
            key=source.key,
            label=source.label,
            display=source.display,
            version=source.version,
            span=[int(x) for x in span["span"]],
            verified_at=source.verified_at,
        )
        for source, span in zip(sources, draft.validation.get("rendered", []), strict=True)
    ]
    facts_used = _facts_used_out(sources)
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
        facts_used=facts_used,
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
        message_tag="HUMAN_AGENT" if draft.message_tag == "HUMAN_AGENT" else None,
        transcripts=draft_transcripts_out(session, ctx, draft),
    )
