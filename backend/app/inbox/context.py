"""Everything the drafting pipeline needs, gathered in one short transaction (workflows.md §C
step 3, parts 1 to 4).

``prepare`` either returns a :class:`DraftContext` or a :class:`DraftSkip` saying why there is
nothing to do. It reads; it never writes. The language is decided here, by code, before any
model is involved, and only **usable** facts (verified, in their validity window, uncontested)
are ever collected (INV-02).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.identity.models import Workspace
from app.identity.schemas import WorkspaceSettings
from app.inbox import drafts, stories
from app.inbox.language import ReplyLanguage, choose_reply_language
from app.inbox.models import Conversation, Message, MessageTranscript, ReplyDraft
from app.inbox.system import system_context
from app.integrations.instagram import queries
from app.knowledge import approved_answers
from app.knowledge import readiness as readiness_module
from app.knowledge import service as knowledge_service
from app.knowledge.approved_answers import AnswerView
from app.knowledge.service import UsableFact

MESSAGING_WINDOW = timedelta(hours=24)
HISTORY_MESSAGES = 10
HISTORY_CHARS = 1000
# Categories the model does not need to see: owner-only settings and the voice, which is
# passed separately. (Prices are removed separately when they must not be shared.)
INTERNAL_CATEGORIES = frozenset({"escalation", "brand", "schedule"})
INTERNAL_KEYS = frozenset({"policy.price_disclosure"})
AUTO_STATUSES = ("queued", "sending", "outcome_unknown", "sent")
# A voice note's transcript is shown to the model under this role (it is the customer's speech,
# transcribed by a machine); see ``DraftMessage.source`` and the draft_reply prompt.
TRANSCRIPT_ROLE = "customer_transcript"
# How long drafting waits for a ``pending`` transcript before it gives up and treats the voice
# note as it always was (an attachment a person handles). The transcription job's own retries
# end well before this (3 attempts, 180 s timeout, 10 s / 60 s backoff), so this only matters if
# a job is lost; it keeps a stuck row from leaving a conversation unhandled for ever.
TRANSCRIPT_WAIT_LIMIT = timedelta(minutes=20)
# While waiting, the draft job looks again after this long (the transcription job also pulls the
# draft job forward the moment it finishes, so this is only the safety net).
TRANSCRIPT_POLL_SECONDS = 30

DEFAULT_DISCLOSURE = {
    "tr": "Bu yanıt otomatik olarak hazırlanmıştır.",
    "en": "This reply was prepared automatically.",
}


@dataclass(frozen=True)
class DraftSkip:
    """Nothing to draft. ``retry`` means "try again soon" (an earlier reply is in flight)."""

    reason: str
    retry: bool = False


def _clean_transcript(text: str | None) -> str:
    """One line of plain words: a transcript cannot start a new "business:" line of its own."""
    return " ".join((text or "").split())


@dataclass(frozen=True)
class TranscriptView:
    """The transcript of a voice note as drafting needs it (status, words, language)."""

    status: str  # pending | succeeded | failed
    text: str | None = None
    language: str | None = None
    reason_code: str | None = None
    created_at: datetime | None = None

    @property
    def words(self) -> str:
        """The transcript text, usable only when the transcription succeeded."""
        return _clean_transcript(self.text) if self.status == "succeeded" else ""


@dataclass(frozen=True)
class InboundText:
    message_id: uuid.UUID
    text: str | None
    attachments: int
    provider_timestamp: datetime
    transcript: TranscriptView | None = None

    @property
    def transcript_words(self) -> str:
        return self.transcript.words if self.transcript is not None else ""

    @property
    def reading(self) -> str:
        """Everything the customer said in this message: typed text and transcript."""
        parts = [(self.text or "").strip(), self.transcript_words]
        return "\n".join(p for p in parts if p)


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
    # Messages whose transcript text the model is shown (the unanswered ones and those in the
    # history). Set by code from stored rows, never by the model: it is what forces approval.
    transcript_message_ids: tuple[uuid.UUID, ...] = ()
    # F-04: what we know about the story a customer replied to (prompt text), and, for a plain
    # story mention, the owner's thank-you template in the reply language (None: not set up).
    story_context: str | None = None
    story_mention: bool = False
    story_mention_template: AnswerView | None = None

    @property
    def customer_text(self) -> str:
        """What the customer said, typed or spoken: the text every pre-check scans (injection,
        escalation words, flags), so a transcript is screened like any other message."""
        return "\n".join(m.reading for m in self.unanswered if m.reading)

    @property
    def attachment_only(self) -> bool:
        return not any(m.reading for m in self.unanswered)

    @property
    def transcript_based(self) -> bool:
        return bool(self.transcript_message_ids)


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


def _history_rows(session: Session, conversation: Conversation) -> list[Message]:
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
    return list(reversed(rows))


def transcripts_for(
    session: Session, workspace_id: uuid.UUID, message_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, TranscriptView]:
    """The transcripts of these messages, by message id (workspace-scoped)."""
    if not message_ids:
        return {}
    rows = session.scalars(
        select(MessageTranscript).where(
            MessageTranscript.workspace_id == workspace_id,
            MessageTranscript.message_id.in_(list(message_ids)),
        )
    )
    return {
        row.message_id: TranscriptView(
            row.status, row.text, row.language, row.reason_code, row.created_at
        )
        for row in rows
    }


def _history(
    rows: Sequence[Message], transcripts: dict[uuid.UUID, TranscriptView]
) -> list[tuple[str, str]]:
    """(role, text) of the recent messages, oldest first. A voice note whose transcript
    succeeded is shown as its transcript, under its own role, never as typed text."""
    history: list[tuple[str, str]] = []
    for message in rows:
        typed = (message.text or "").strip()
        spoken = transcripts[message.id].words if message.id in transcripts else ""
        role = "customer" if message.direction == "inbound" else "business"
        if typed:
            history.append((role, typed[:HISTORY_CHARS]))
        if spoken and message.direction == "inbound":
            history.append((TRANSCRIPT_ROLE, spoken[:HISTORY_CHARS]))
        elif not typed and message.attachments:
            history.append((role, "[attachment]"))
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
    history_rows = _history_rows(session, conversation)
    transcripts = transcripts_for(
        session,
        workspace_id,
        [m.id for m in unanswered] + [m.id for m in history_rows],
    )
    if _waiting_for_transcript(clock, unanswered, transcripts):
        return DraftSkip("transcript_pending")  # the transcription job wakes this job
    inbound = [
        InboundText(
            m.id,
            m.text,
            len(m.attachments or []),
            m.provider_timestamp,
            transcripts.get(m.id),
        )
        for m in unanswered
    ]
    gathered = gather_workspace_inputs(
        session,
        clock,
        ctx,
        workspace,
        [m.reading for m in reversed(inbound) if m.reading],
    )
    last_inbound = conversation.last_inbound_at
    spoken = {m.id for m in unanswered} | {m.id for m in history_rows}
    # A plain story mention has no words and no audio, so it never waits for a transcript above.
    mention = stories.is_mention_only([(m.text, m.attachments) for m in unanswered])
    story_content = (
        None
        if mention
        else stories.reply_context(
            session,
            workspace_id,
            conversation.social_account_id,
            [(m.attachments, m.provider_timestamp) for m in unanswered],
        )
    )

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
        unanswered=inbound,
        covers_through_message_id=newest.id,
        history=_history(history_rows, transcripts),
        language=gathered.language,
        facts=gathered.facts,
        price_disclosure=gathered.price_disclosure,
        controller_cutover_generation=controller.cutover_generation
        if controller is not None
        else 0,
        approved_answers=gathered.approved_answers,
        brand_voice=gathered.brand_voice,
        escalation_keywords=gathered.escalation_keywords,
        disclosure=gathered.disclosure,
        window_end=last_inbound + MESSAGING_WINDOW if last_inbound else None,
        readiness_level=gathered.readiness_level,
        auto_replies_last_hour=_auto_replies_last_hour(session, clock, conversation),
        usable_keys=frozenset(f.key for f in gathered.facts),
        unusable_keys=frozenset(gathered.unusable_keys),
        transcript_message_ids=tuple(
            sorted(
                (mid for mid in spoken if mid in transcripts and transcripts[mid].words),
                key=str,
            )
        ),
        story_context=stories.prompt_text(story_content),
        story_mention=mention,
        story_mention_template=(
            approved_answers.story_mention_template(session, ctx, gathered.language.code)
            if mention and gathered.language.code is not None
            else None
        ),
    )


def _waiting_for_transcript(
    clock: Clock, unanswered: Sequence[Message], transcripts: dict[uuid.UUID, TranscriptView]
) -> bool:
    """True while a voice note among the unanswered messages has a transcript on its way.

    A ``pending`` row older than ``TRANSCRIPT_WAIT_LIMIT`` no longer counts: drafting proceeds
    without it (the voice note stays a person-handled attachment). ``failed`` never waits."""
    now = clock.now()
    for message in unanswered:
        view = transcripts.get(message.id)
        if view is None or view.status != "pending":
            continue
        if view.created_at is None or now - view.created_at < TRANSCRIPT_WAIT_LIMIT:
            return True
    return False


@dataclass(frozen=True)
class WorkspaceDraftInputs:
    """What drafting needs from the *workspace* (not from a conversation): the reply language,
    the usable facts and approved answers, the voice, the escalation words and the notice."""

    language: ReplyLanguage
    facts: list[UsableFact]
    unusable_keys: set[str]
    approved_answers: list[approved_answers.AnswerView]
    price_disclosure: str
    brand_voice: str | None
    escalation_keywords: list[str]
    disclosure: Disclosure
    readiness_level: str


def gather_workspace_inputs(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    workspace: Workspace,
    texts_newest_first: list[str],
) -> WorkspaceDraftInputs:
    """Shared by the real drafting job (``prepare``) and the owner's test chat, so that both are
    answered from exactly the same facts, rules and language choice."""
    settings = WorkspaceSettings.model_validate(workspace.settings)
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
    return WorkspaceDraftInputs(
        language=language,
        facts=usable,
        unusable_keys=unusable,
        approved_answers=answers,
        price_disclosure=price_disclosure,
        brand_voice=_localized(voice_fact.value, language.code or "tr") if voice_fact else None,
        escalation_keywords=[
            str(k) for k in (keywords_fact.value.get("items", []) if keywords_fact else [])
        ],
        disclosure=Disclosure(
            settings.disclosure_enabled,
            suffix or DEFAULT_DISCLOSURE.get(language.code or workspace.default_locale, ""),
        ),
        readiness_level=readiness_module.readiness(session, clock, ctx).level,
    )


def model_facts(context: DraftContext) -> list[UsableFact]:
    """The facts the model is shown."""
    return _drafting_facts(context.facts, context.price_disclosure)
