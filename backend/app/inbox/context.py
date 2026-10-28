"""Everything the drafting pipeline needs, gathered in one short transaction (workflows.md §C
step 3, parts 1 to 4).

``prepare`` either returns a :class:`DraftContext` or a :class:`DraftSkip` saying why there is
nothing to do. It reads; it never writes. The language is decided here, by code, before any
model is involved, and only **usable** facts (verified, in their validity window, uncontested)
are ever collected (INV-02).
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.identity.models import Workspace
from app.identity.schemas import WorkspaceSettings
from app.inbox import drafts
from app.inbox.language import ReplyLanguage, choose_reply_language
from app.inbox.models import Conversation, Message, ReplyDraft
from app.inbox.system import system_context
from app.integrations.instagram import queries
from app.knowledge import approved_answers
from app.knowledge import readiness as readiness_module
from app.knowledge import service as knowledge_service
from app.knowledge.service import UsableFact

MESSAGING_WINDOW = timedelta(hours=24)
HISTORY_MESSAGES = 10
HISTORY_CHARS = 1000
# Categories the model does not need to see: owner-only settings and the voice, which is
# passed separately. (Prices are removed separately when they must not be shared.)
INTERNAL_CATEGORIES = frozenset({"escalation", "brand", "schedule"})
INTERNAL_KEYS = frozenset({"policy.price_disclosure"})
AUTO_STATUSES = ("queued", "sending", "outcome_unknown", "sent")

DEFAULT_DISCLOSURE = {
    "tr": "Bu yanıt otomatik olarak hazırlanmıştır.",
    "en": "This reply was prepared automatically.",
}


@dataclass(frozen=True)
class DraftSkip:
    """Nothing to draft. ``retry`` means "try again soon" (an earlier reply is in flight)."""

    reason: str
    retry: bool = False


@dataclass(frozen=True)
class InboundText:
    message_id: uuid.UUID
    text: str | None
    attachments: int
    provider_timestamp: datetime


@dataclass(frozen=True)
class Disclosure:
    enabled: bool
    text: str


@dataclass(frozen=True)
class DraftContext:
    ctx: WorkspaceContext
    workspace_id: uuid.UUID
    conversation_id: uuid.UUID
    social_account_id: uuid.UUID
    account_status: str
    account_capabilities: dict[str, object]
    handling_mode: str
    is_simulated: bool
    requested: bool
    unanswered: list[InboundText]  # oldest first
    covers_through_message_id: uuid.UUID
    history: list[tuple[str, str]]  # (role customer|business, text), oldest first
    language: ReplyLanguage
    facts: list[UsableFact]  # every usable fact, displayed in the reply language
    price_disclosure: str  # share | do_not_share
    approved_answers: list[approved_answers.AnswerView]
    brand_voice: str | None
    escalation_keywords: list[str]
    disclosure: Disclosure
    window_end: datetime | None
    readiness_level: str
    auto_replies_last_hour: int
    usable_keys: frozenset[str] = field(default_factory=frozenset)
    unusable_keys: frozenset[str] = field(default_factory=frozenset)  # exist, but not usable
    controller_cutover_generation: int = 0

    @property
    def customer_text(self) -> str:
        return "\n".join(m.text for m in self.unanswered if m.text)

    @property
    def attachment_only(self) -> bool:
        return not any((m.text or "").strip() for m in self.unanswered)


def _fact(facts: list[UsableFact], key: str) -> UsableFact | None:
    return next((f for f in facts if f.key == key), None)


def _localized(value: dict[str, object], language: str) -> str | None:
    text = value.get(language) or value.get("tr") or value.get("en")
    return str(text) if text else None


def _newest_inbound(
    session: Session, workspace_id: uuid.UUID, conversation_id: uuid.UUID
) -> Message | None:
    return session.scalars(
        select(Message)
        .where(
            Message.workspace_id == workspace_id,
            Message.conversation_id == conversation_id,
            Message.direction == "inbound",
        )
        .order_by(Message.provider_timestamp.desc(), Message.created_at.desc(), Message.id)
        .limit(1)
    ).first()


def _unanswered(session: Session, conversation: Conversation) -> list[Message]:
    stmt = select(Message).where(
        Message.workspace_id == conversation.workspace_id,
        Message.conversation_id == conversation.id,
        Message.direction == "inbound",
    )
    if conversation.last_outbound_at is not None:
        stmt = stmt.where(Message.provider_timestamp > conversation.last_outbound_at)
    return list(session.scalars(stmt.order_by(Message.provider_timestamp, Message.created_at)))


def _history(session: Session, conversation: Conversation) -> list[tuple[str, str]]:
    rows = session.scalars(
        select(Message)
        .where(
            Message.workspace_id == conversation.workspace_id,
            Message.conversation_id == conversation.id,
            Message.is_deleted.is_(False),
        )
        .order_by(Message.provider_timestamp.desc(), Message.created_at.desc())
        .limit(HISTORY_MESSAGES)
    ).all()
    history: list[tuple[str, str]] = []
    for message in reversed(rows):
        text = (message.text or "").strip() or ("[attachment]" if message.attachments else "")
        if text:
            role = "customer" if message.direction == "inbound" else "business"
            history.append((role, text[:HISTORY_CHARS]))
    return history


def _auto_replies_last_hour(session: Session, clock: Clock, conversation: Conversation) -> int:
    since = clock.now() - timedelta(hours=1)
    return int(
        session.scalar(
            select(func.count())
            .select_from(ReplyDraft)
            .where(
                ReplyDraft.workspace_id == conversation.workspace_id,
                ReplyDraft.conversation_id == conversation.id,
                ReplyDraft.decision == "auto",
                ReplyDraft.status.in_(AUTO_STATUSES),
                ReplyDraft.created_at >= since,
            )
        )
        or 0
    )


def _drafting_facts(facts: list[UsableFact], price_disclosure: str) -> list[UsableFact]:
    """What the model may quote: no internal settings, and no prices when they are not shared."""
    visible = [
        f for f in facts if f.category not in INTERNAL_CATEGORIES and f.key not in INTERNAL_KEYS
    ]
    if price_disclosure == "do_not_share":
        visible = [f for f in visible if f.category != "pricing"]
    return visible


def prepare(
    session: Session,
    clock: Clock,
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    message_id: uuid.UUID | None,
    requested: bool,
) -> DraftContext | DraftSkip:
    ctx = system_context(session, workspace_id, "drafting")
    conversation = session.scalars(
        select(Conversation).where(
            Conversation.workspace_id == workspace_id, Conversation.id == conversation_id
        )
    ).one_or_none()
    if ctx is None or conversation is None:
        return DraftSkip("conversation_missing")
    from app.agent.models import AccountAgent

    controller = session.scalar(
        select(AccountAgent).where(
            AccountAgent.workspace_id == workspace_id,
            AccountAgent.social_account_id == conversation.social_account_id,
        )
    )
    if controller is not None and controller.controller_mode == "agent":
        return DraftSkip("agent_controller")
    if conversation.handling_mode == "human" and not requested:
        return DraftSkip("human_mode")
    newest = _newest_inbound(session, workspace_id, conversation_id)
    if newest is None:
        return DraftSkip("no_unanswered")
    if message_id is not None and newest.id != message_id:
        return DraftSkip("newer_message")  # that message's own job will draft
    unanswered = _unanswered(session, conversation)
    if not unanswered:
        return DraftSkip("no_unanswered")  # the owner already answered

    open_draft = drafts.get_open_draft(session, workspace_id, conversation_id)
    if open_draft is not None:
        if open_draft.status in ("queued", "sending", "outcome_unknown"):
            return DraftSkip("reply_in_flight", retry=True)
        covered = session.get(Message, open_draft.covers_through_message_id)
        if covered is not None and covered.provider_timestamp >= newest.provider_timestamp:
            return DraftSkip("draft_exists")

    account = queries.get_account_in_workspace(
        session, workspace_id, conversation.social_account_id
    )
    workspace = session.get(Workspace, workspace_id)
    if account is None or workspace is None:
        return DraftSkip("conversation_missing")
    settings = WorkspaceSettings.model_validate(workspace.settings)

    texts_newest_first = [m.text for m in reversed(unanswered) if m.text]
    language = choose_reply_language(
        texts_newest_first,
        default_locale=workspace.default_locale,
        reply_languages=list(workspace.reply_languages),
    )
    usable: list[UsableFact] = []
    unusable: set[str] = set()
    answers: list[approved_answers.AnswerView] = []
    if language.code is not None:
        usable = knowledge_service.usable_facts(session, clock, ctx, locale=language.code)
        unusable = knowledge_service.unusable_fact_keys(session, clock, ctx)
        answers = approved_answers.list_for_drafting(session, ctx, language.code)
    disclosure_fact = _fact(usable, "policy.price_disclosure")
    # An unknown policy is treated as "do not share": a price is never guessed into a reply.
    price_disclosure = (
        "share"
        if disclosure_fact is not None and disclosure_fact.value.get("value") == "share"
        else "do_not_share"
    )
    voice_fact = _fact(usable, "brand.voice_guidelines")
    keywords_fact = _fact(usable, "escalation.keywords")
    suffix = settings.disclosure_text.model_dump().get(language.code or workspace.default_locale)
    last_inbound = conversation.last_inbound_at

    return DraftContext(
        ctx=ctx,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        social_account_id=account.id,
        account_status=account.status,
        account_capabilities=dict(account.capabilities),
        handling_mode=conversation.handling_mode,
        is_simulated=conversation.is_simulated,
        requested=requested,
        unanswered=[
            InboundText(m.id, m.text, len(m.attachments or []), m.provider_timestamp)
            for m in unanswered
        ],
        covers_through_message_id=newest.id,
        history=_history(session, conversation),
        language=language,
        facts=usable,
        price_disclosure=price_disclosure,
        controller_cutover_generation=controller.cutover_generation
        if controller is not None
        else 0,
        approved_answers=answers,
        brand_voice=_localized(voice_fact.value, language.code or "tr") if voice_fact else None,
        escalation_keywords=[
            str(k) for k in (keywords_fact.value.get("items", []) if keywords_fact else [])
        ],
        disclosure=Disclosure(
            settings.disclosure_enabled,
            suffix or DEFAULT_DISCLOSURE.get(language.code or workspace.default_locale, ""),
        ),
        window_end=last_inbound + MESSAGING_WINDOW if last_inbound else None,
        readiness_level=readiness_module.readiness(session, clock, ctx).level,
        auto_replies_last_hour=_auto_replies_last_hour(session, clock, conversation),
        usable_keys=frozenset(f.key for f in usable),
        unusable_keys=frozenset(unusable),
    )


def model_facts(context: DraftContext) -> list[UsableFact]:
    """The facts the model is shown."""
    return _drafting_facts(context.facts, context.price_disclosure)
