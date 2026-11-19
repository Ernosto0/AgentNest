"""Voice-note transcription (F-03, Feature Phase 2, Session 01). Imported by ``load_handlers``.

Flow (workflows.md section C, background-jobs.md section 5):

1. ``request_transcript`` runs inside the transaction that stores a customer message with an audio
   attachment. It writes a ``pending`` ``message_transcripts`` row and enqueues
   ``transcribe_voice_note`` (an insert, no external call). A voice note with no URL is recorded
   as ``failed`` at once.
2. ``transcribe_voice_note`` reads the row [T1, then the transaction is closed], downloads the
   audio (capped, content-type checked) and calls the provider **with no transaction open**, then
   stores the result [T3] after re-checking that the message still exists and is not erased.

A failure leaves the row ``failed`` with a reason code and the voice note stays a person-handled
attachment (rule R11). A success lets the drafting path read the transcript as labelled customer
text (Session 02): the draft job waits while the row is ``pending``, and this module wakes it
again, in the same transaction that finishes the row (``wake_drafting``), whether the transcript
succeeded or failed. The transcript is customer speech: untrusted data (INV-03), never a fact.
The audio is held in memory during the job only; it is never stored, so there is no raw-audio
retention to apply.
"""

import uuid
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.clock import Clock
from app.core.errors import RetryableError
from app.inbox.language import detect_language
from app.inbox.models import Conversation, Message, MessageTranscript
from app.inbox.payloads import (
    DraftReplyPayload,
    TranscribeVoiceNotePayload,
    draft_reply_key,
    transcribe_voice_note_key,
)
from app.inbox.system import system_context
from app.integrations.instagram.models import SocialAccount
from app.integrations.transcription import (
    AudioClip,
    get_audio_fetcher,
    get_transcriber,
    get_transcription_settings,
    transcription_enabled,
)
from app.integrations.transcription.audio import (
    extension_for,
    probe_duration_seconds,
)
from app.integrations.transcription.errors import (
    AudioRejected,
    TranscriptionTransientError,
    VoiceError,
)
from app.jobs.models import Job
from app.jobs.queue import enqueue
from app.jobs.registry import JobContext, job_handler

AUDIO_TYPE = "audio"
MAX_TRANSCRIPT_CHARS = 10_000
_ONE_DAY = timedelta(days=1)
# A download (twice its timeout at most) and one provider call, with room to spare.
TRANSCRIBE_TIMEOUT_SECONDS = 180

_PROVIDER_LANGUAGES = {
    "tr": "tr",
    "turkish": "tr",
    "en": "en",
    "english": "en",
    "ru": "ru",
    "russian": "ru",
    "de": "de",
    "german": "de",
    "ar": "ar",
    "arabic": "ar",
}


def first_audio_attachment(
    attachments: Sequence[dict[str, Any]] | None,
) -> tuple[int, dict[str, Any]] | None:
    """The first audio attachment of a message and its index, if any."""
    for index, attachment in enumerate(attachments or []):
        if isinstance(attachment, dict) and attachment.get("type") == AUDIO_TYPE:
            return index, attachment
    return None


def _language(text: str, provider_language: str | None) -> str | None:
    """A reply language, ``other`` or ``None``. The text wins; the provider's guess is the
    fallback when the text gives no evidence."""
    detected = detect_language(text)
    if detected is not None:
        return detected
    if provider_language:
        return _PROVIDER_LANGUAGES.get(provider_language.strip().lower(), "other")
    return None


# --- request (inside the message transaction) -------------------------------------------------


def request_transcript(
    session: Session,
    clock: Clock,
    account: SocialAccount,
    message_id: uuid.UUID,
    attachments: Sequence[dict[str, Any]] | None,
    *,
    correlation_id: uuid.UUID | None,
) -> None:
    """Start the transcript of a new customer message, if it carries a voice note and
    transcription is on. The caller owns the transaction."""
    found = first_audio_attachment(attachments)
    if found is None or not transcription_enabled():
        return
    index, attachment = found
    url = attachment.get("url")
    row = MessageTranscript(
        workspace_id=account.workspace_id,
        message_id=message_id,
        attachment_index=index,
        is_simulated=account.is_simulated,
        # From the injected Clock (INV-19): drafting measures how long it has waited from this.
        created_at=clock.now(),
    )
    session.add(row)
    if not isinstance(url, str) or not url:
        # The message's own transaction queues the draft right after this: no wake-up needed.
        _mark_failed(
            session, clock, row, "VOICE_URL_MISSING", correlation_id=correlation_id, wake=False
        )
        return
    session.flush()
    enqueue(
        session,
        "transcribe_voice_note",
        TranscribeVoiceNotePayload(message_id=message_id),
        workspace_id=account.workspace_id,
        correlation_id=correlation_id,
        dedup_key=transcribe_voice_note_key(message_id),
        clock=clock,
    )


# --- state changes (each writes its audit entry in the same transaction) ----------------------


def _record(
    session: Session,
    clock: Clock,
    row: MessageTranscript,
    action: str,
    metadata: dict[str, Any],
    correlation_id: uuid.UUID | None,
) -> None:
    ctx = system_context(session, row.workspace_id, "transcription")
    if ctx is None:
        return
    audit.record(
        session,
        ctx,
        action,
        "message",
        row.message_id,
        {"message_id": row.message_id, **metadata},
        is_simulated=row.is_simulated,
        correlation_id=correlation_id,
        clock=clock,
    )


def _mark_failed(
    session: Session,
    clock: Clock,
    row: MessageTranscript,
    reason: str,
    *,
    correlation_id: uuid.UUID | None,
    provider: str | None = None,
    model: str | None = None,
    duration_seconds: float | None = None,
    audio_bytes: int | None = None,
    wake: bool = True,
) -> None:
    row.status, row.reason_code = "failed", reason
    row.text = None
    row.provider, row.model = provider, model
    row.duration_seconds, row.audio_bytes = duration_seconds, audio_bytes
    row.completed_at = clock.now()
    session.flush()
    _record(session, clock, row, "message.transcription_failed", {"reason": reason}, correlation_id)
    if wake and reason != "VOICE_SOURCE_GONE":  # the voice note falls back to a person
        wake_drafting(session, clock, row, correlation_id)


def wake_drafting(
    session: Session, clock: Clock, row: MessageTranscript, correlation_id: uuid.UUID | None
) -> None:
    """Make the draft job look at the conversation again now that this transcript is final.

    The draft job does not draft while a transcript is ``pending`` (``inbox.context.prepare``), so
    whoever finishes a transcript, successfully or not, must wake it. Same transaction as the row's
    new state: both happen or neither. The draft job's dedup key means a queued job already exists
    in the common case (the debounce is still running); it is pulled forward instead of being
    duplicated. A job that is running right now has either already read the final row or will
    reschedule itself (and look again within ``TRANSCRIPT_POLL_SECONDS``). Echoes, deleted
    messages, a conversation a person has taken over and one run by the account agent are left
    alone (an explicit "suggest reply" request is still woken)."""
    message = session.scalars(
        select(Message).where(
            Message.workspace_id == row.workspace_id, Message.id == row.message_id
        )
    ).one_or_none()
    if message is None or message.is_deleted or message.direction != "inbound":
        return
    conversation = session.scalars(
        select(Conversation).where(
            Conversation.workspace_id == row.workspace_id,
            Conversation.id == message.conversation_id,
        )
    ).one_or_none()
    if conversation is None:
        return
    from app.agent.models import AccountAgent, AgentThread

    controller = session.scalar(
        select(AccountAgent).where(
            AccountAgent.workspace_id == row.workspace_id,
            AccountAgent.social_account_id == conversation.social_account_id,
        )
    )
    if controller is not None and controller.controller_mode == "agent":
        thread = session.scalar(
            select(AgentThread).where(
                AgentThread.workspace_id == row.workspace_id,
                AgentThread.social_account_id == conversation.social_account_id,
                AgentThread.surface == "dm",
                (AgentThread.dm_conversation_id == conversation.id)
                | (AgentThread.source_ref == str(conversation.id)),
            )
        )
        if (
            thread is not None
            and thread.handling_mode == "agent"
            and thread.controller_epoch == controller.controller_epoch
            and controller.state in {"active", "paused"}
        ):
            from app.agent.repository import record_thread_event

            kind = (
                "message.transcript_ready"
                if row.status == "succeeded"
                else "message.transcription_failed"
            )
            record_thread_event(
                session,
                clock,
                workspace_id=row.workspace_id,
                account_id=conversation.social_account_id,
                thread_id=thread.id,
                kind=kind,
                source_kind="message_transcript",
                source_key=f"transcript:{row.id}",
                source_id=row.id,
                source_version=1,
            )
        return
    now = clock.now()
    keys = [draft_reply_key(conversation.id, requested=True)]
    if conversation.handling_mode == "automatic":
        key = draft_reply_key(conversation.id)
        enqueue(
            session,
            "draft_reply",
            DraftReplyPayload(conversation_id=conversation.id),
            workspace_id=row.workspace_id,
            correlation_id=correlation_id,
            run_at=now,
            dedup_key=key,
            clock=clock,
        )
        keys.append(key)
    session.execute(
        update(Job)
        .where(Job.dedup_key.in_(keys), Job.status == "queued", Job.run_at > now)
        .values(run_at=now)
        .execution_options(synchronize_session=False)
    )


# --- the job ----------------------------------------------------------------------------------


def _on_dead(job: JobContext, error_code: str) -> None:
    """Every retry failed (or an unexpected error): the message stays person-handled."""
    payload = job.payload
    if not isinstance(payload, TranscribeVoiceNotePayload) or job.workspace_id is None:
        return
    reason = error_code if error_code.startswith("VOICE_") else "VOICE_TRANSCRIPTION_UNAVAILABLE"
    with job.session_factory() as session:
        row = _locked_row(session, job.workspace_id, payload.message_id)
        if row is not None and row.status == "pending":
            _mark_failed(session, job.clock, row, reason, correlation_id=job.correlation_id)
        session.commit()


def _locked_row(
    session: Session, workspace_id: uuid.UUID, message_id: uuid.UUID
) -> MessageTranscript | None:
    return session.scalars(
        select(MessageTranscript)
        .where(
            MessageTranscript.workspace_id == workspace_id,
            MessageTranscript.message_id == message_id,
        )
        .with_for_update()
    ).one_or_none()


def _fail_now(job: JobContext, message_id: uuid.UUID, reason: str, **metadata: Any) -> None:
    with job.session_factory() as session:
        row = _locked_row(session, job.workspace_id, message_id)  # type: ignore[arg-type]
        if row is not None and row.status == "pending":
            _mark_failed(
                session, job.clock, row, reason, correlation_id=job.correlation_id, **metadata
            )
        session.commit()


@job_handler(
    "transcribe_voice_note",
    TranscribeVoiceNotePayload,
    max_attempts=3,
    timeout=TRANSCRIBE_TIMEOUT_SECONDS,
    on_dead=_on_dead,
    backoff=(10, 60, 300),
)
def transcribe_voice_note(job: JobContext) -> None:
    """Three phases; the download and the provider call run with **no transaction open**."""
    payload = job.payload
    if not isinstance(payload, TranscribeVoiceNotePayload) or job.workspace_id is None:
        return
    settings = get_transcription_settings()
    with job.session_factory() as session:  # [T1] read-only
        row = session.scalars(
            select(MessageTranscript).where(
                MessageTranscript.workspace_id == job.workspace_id,
                MessageTranscript.message_id == payload.message_id,
            )
        ).one_or_none()
        if row is None or row.status != "pending":
            return  # done, erased or never requested: nothing to do (idempotent)
        message = session.scalars(
            select(Message).where(
                Message.workspace_id == job.workspace_id, Message.id == payload.message_id
            )
        ).one_or_none()
        found = (
            first_audio_attachment(message.attachments)
            if message is not None and not message.is_deleted
            else None
        )
        url = found[1].get("url") if found else None
        simulated = row.is_simulated
        used_in_last_day = int(
            session.scalar(
                select(func.count())
                .select_from(MessageTranscript)
                .where(
                    MessageTranscript.workspace_id == job.workspace_id,
                    MessageTranscript.provider.is_not(None),
                    MessageTranscript.created_at >= job.clock.now() - _ONE_DAY,
                )
            )
            or 0
        )
        session.commit()
    if found is None:
        return _fail_now(job, payload.message_id, "VOICE_SOURCE_GONE")
    if not isinstance(url, str) or not url:
        return _fail_now(job, payload.message_id, "VOICE_URL_MISSING")
    transcriber = get_transcriber()
    if transcriber is None:  # switched off after the job was queued
        return _fail_now(job, payload.message_id, "VOICE_TRANSCRIPTION_UNAVAILABLE")
    if used_in_last_day >= settings.transcription_max_per_workspace_per_day:
        return _fail_now(job, payload.message_id, "VOICE_QUOTA_EXCEEDED")

    audio_bytes: int | None = None
    duration: float | None = None
    try:  # no transaction is open from here to [T3]
        fetched = get_audio_fetcher(simulated=simulated).fetch(
            url,
            max_bytes=settings.transcription_max_audio_bytes,
            timeout_s=settings.transcription_download_timeout_seconds,
        )
        job.heartbeat()
        audio_bytes = len(fetched.data)
        if audio_bytes == 0:
            raise AudioRejected("VOICE_EMPTY_AUDIO")
        if audio_bytes > settings.transcription_max_audio_bytes:
            raise AudioRejected("VOICE_TOO_LARGE")
        if extension_for(fetched.content_type, fetched.data) is None:
            raise AudioRejected("VOICE_UNSUPPORTED_TYPE")
        duration = probe_duration_seconds(fetched.data)
        if duration is not None and duration > settings.transcription_max_audio_seconds:
            raise AudioRejected("VOICE_TOO_LONG")
        result = transcriber.transcribe_audio(
            AudioClip(fetched.data, fetched.content_type, duration),
            model=settings.transcription_model,
            timeout_s=settings.transcription_timeout_seconds,
        )
        job.heartbeat()
    except VoiceError as exc:
        if exc.retryable:  # the worker retries, and calls ``_on_dead`` after the last attempt
            raise RetryableError(
                exc.code,
                retry_after_seconds=exc.retry_after_seconds
                if isinstance(exc, TranscriptionTransientError)
                else None,
            ) from None
        return _fail_now(
            job, payload.message_id, exc.code, audio_bytes=audio_bytes, duration_seconds=duration
        )
    del fetched  # the audio is never kept

    duration = duration if duration is not None else result.duration_seconds
    text = result.text.strip()[:MAX_TRANSCRIPT_CHARS]
    reason: str | None = None
    if duration is not None and duration > settings.transcription_max_audio_seconds:
        reason = "VOICE_TOO_LONG"  # a container that did not say how long it was
    elif not text:
        reason = "VOICE_NO_SPEECH"

    with job.session_factory() as session:  # [T3]
        row = _locked_row(session, job.workspace_id, payload.message_id)
        message = session.scalars(
            select(Message).where(
                Message.workspace_id == job.workspace_id, Message.id == payload.message_id
            )
        ).one_or_none()
        if row is None or row.status != "pending":
            session.commit()
            return
        # The message may have been deleted or erased while the provider ran: store nothing.
        if (
            message is None
            or message.is_deleted
            or first_audio_attachment(message.attachments) is None
        ):
            _mark_failed(
                session, job.clock, row, "VOICE_SOURCE_GONE", correlation_id=job.correlation_id
            )
        elif reason is not None:
            _mark_failed(
                session,
                job.clock,
                row,
                reason,
                correlation_id=job.correlation_id,
                provider=result.provider,
                model=result.model,
                duration_seconds=duration,
                audio_bytes=audio_bytes,
            )
        else:
            row.status, row.reason_code = "succeeded", None
            row.text = text
            row.language = _language(text, result.language)
            row.provider, row.model = result.provider, result.model
            row.duration_seconds, row.audio_bytes = duration, audio_bytes
            row.completed_at = job.clock.now()
            session.flush()
            _record(
                session,
                job.clock,
                row,
                "message.transcribed",
                {
                    "provider": result.provider,
                    "model": result.model,
                    "language": row.language,
                    "duration_seconds": duration,
                    "audio_bytes": audio_bytes,
                },
                job.correlation_id,
            )
            wake_drafting(session, job.clock, row, job.correlation_id)
        session.commit()
