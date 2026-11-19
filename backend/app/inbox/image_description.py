"""Photos and screenshots customers send, described for the owner (F-03, Feature Phase 2,
Session 03). Imported by ``load_handlers``.

Flow (workflows.md section C, background-jobs.md section 5):

1. ``request_image_descriptions`` runs inside the transaction that stores a customer message with
   image attachments. For the first few images it writes a ``pending``
   ``message_image_descriptions`` row and enqueues ``describe_message_image`` (an insert, no
   external call). An image with no URL is recorded as ``failed`` at once.
2. ``describe_message_image`` reads the row [T1, then the transaction is closed], downloads the
   image (capped, type checked) and runs the tool-less ``describe_image`` vision task **with no
   transaction open**, then stores the result [T3] after re-checking that the message still
   exists and is not erased.

What the description is, and is not (INV-03, INV-02, INV-04):

- It is **shown to the owner and nothing else**. The conversation is never handed back to the
  assistant because of it: no draft reads it (``inbox/context.py`` does not know this table), no
  reply is created, suggested or sent, and the conversation's handling and attention state are
  not touched. A photo with no words is still ``needs_human`` (rule R11, ``ATTACHMENT_ONLY``).
  Pre-filling a suggested reply from a description was **decided against** in this session.
- It is a machine's reading of customer content: the description and the text read from the
  picture are untrusted data, never a fact, never an instruction. The injection heuristics screen
  both; a match is stored as ``injection_suspected`` and shown to the owner as a warning. Nothing
  here acts on the text either way.
- The picture is held in memory during the job only; it is never stored, so there is no raw-image
  retention to apply. The words are erased with the message text (retention and every erasure
  path, ``inbox/image_erasure.py``).
"""

import re
import uuid
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.ai.injection import detect_injection
from app.ai.models import AgentRun
from app.ai.runner import run_task
from app.ai.runtime import get_runtime_settings, runner_deps
from app.ai.schemas import (
    MAX_IMAGE_DESCRIPTION_CHARS,
    MAX_IMAGE_VISIBLE_TEXT_CHARS,
    DescribeImageInput,
    ImageDescription,
)
from app.ai.tasks.describe_image import DESCRIBE_IMAGE
from app.audit import service as audit
from app.core.clock import Clock
from app.core.errors import RetryableError
from app.identity.models import Workspace
from app.inbox.models import Conversation, Message, MessageImageDescription
from app.inbox.payloads import (
    DescribeMessageImagePayload,
    DraftReplyPayload,
    describe_message_image_key,
    draft_reply_key,
)
from app.inbox.system import system_context
from app.integrations.instagram.models import SocialAccount
from app.integrations.vision import get_image_fetcher
from app.integrations.vision.errors import ImageError, ImageRejected
from app.integrations.vision.images import resolved_media_type
from app.jobs.models import Job
from app.jobs.queue import enqueue
from app.jobs.registry import JobContext, job_handler

IMAGE_TYPE = "image"
_ONE_DAY = timedelta(days=1)
# A download (twice its timeout at most) and a model call with at most one repair call.
DESCRIBE_TIMEOUT_SECONDS = 240

# How the runner's error codes become the reason shown to the owner.
_OUTCOME_REASONS = {
    "LLM_BUDGET_EXCEEDED": "IMAGE_QUOTA_EXCEEDED",
    "LLM_REFUSED": "IMAGE_DESCRIPTION_REJECTED",
    "LLM_OUTPUT_INVALID": "IMAGE_DESCRIPTION_REJECTED",
}
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def image_attachments(
    attachments: Sequence[dict[str, Any]] | None, limit: int
) -> list[tuple[int, dict[str, Any]]]:
    """The first ``limit`` image attachments of a message, each with its index."""
    found: list[tuple[int, dict[str, Any]]] = []
    for index, attachment in enumerate(attachments or []):
        if isinstance(attachment, dict) and attachment.get("type") == IMAGE_TYPE:
            found.append((index, attachment))
            if len(found) >= limit:
                break
    return found


def _image_url(message: Message | None, index: int) -> tuple[bool, str | None]:
    """(the attachment at ``index`` is still an image, its URL)."""
    if message is None or message.is_deleted:
        return False, None
    attachments = message.attachments or []
    if index >= len(attachments):
        return False, None
    item = attachments[index]
    if not isinstance(item, dict) or item.get("type") != IMAGE_TYPE:
        return False, None
    url = item.get("url")
    return True, url if isinstance(url, str) and url else None


def clean_text(text: str, limit: int, *, single_line: bool = False) -> str:
    """Model text made safe to store and show: no control characters, bounded, tidy blank lines."""
    text = _CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    if single_line:
        text = " ".join(text.split())
    else:
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:limit]


# --- request (inside the message transaction) -------------------------------------------------


def request_image_descriptions(
    session: Session,
    clock: Clock,
    account: SocialAccount,
    message_id: uuid.UUID,
    attachments: Sequence[dict[str, Any]] | None,
    *,
    correlation_id: uuid.UUID | None,
) -> None:
    """Start the description of each image (up to the per-message limit) of a new customer
    message, if image description is on. The caller owns the transaction."""
    settings = get_runtime_settings()
    if not settings.image_description_enabled:
        return
    for index, attachment in image_attachments(
        attachments, settings.image_description_max_per_message
    ):
        row = MessageImageDescription(
            workspace_id=account.workspace_id,
            message_id=message_id,
            attachment_index=index,
            is_simulated=account.is_simulated,
            created_at=clock.now(),
        )
        session.add(row)
        url = attachment.get("url")
        if not isinstance(url, str) or not url:
            _mark_failed(
                session, clock, row, "IMAGE_URL_MISSING", correlation_id=correlation_id, wake=False
            )
            continue
        session.flush()
        enqueue(
            session,
            "describe_message_image",
            DescribeMessageImagePayload(message_id=message_id, attachment_index=index),
            workspace_id=account.workspace_id,
            correlation_id=correlation_id,
            dedup_key=describe_message_image_key(message_id, index),
            clock=clock,
        )


# --- state changes (each writes its audit entry in the same transaction) ----------------------


def _record(
    session: Session,
    clock: Clock,
    row: MessageImageDescription,
    action: str,
    metadata: dict[str, Any],
    correlation_id: uuid.UUID | None,
) -> None:
    ctx = system_context(session, row.workspace_id, "image_description")
    if ctx is None:
        return
    audit.record(
        session,
        ctx,
        action,
        "message",
        row.message_id,
        {"message_id": row.message_id, "attachment_index": row.attachment_index, **metadata},
        is_simulated=row.is_simulated,
        correlation_id=correlation_id,
        clock=clock,
    )


def _mark_failed(
    session: Session,
    clock: Clock,
    row: MessageImageDescription,
    reason: str,
    *,
    correlation_id: uuid.UUID | None,
    provider: str | None = None,
    model: str | None = None,
    media_type: str | None = None,
    image_bytes: int | None = None,
    agent_run_id: uuid.UUID | None = None,
    wake: bool = True,
) -> None:
    row.status, row.reason_code = "failed", reason
    row.description = row.visible_text = row.looks_like = None
    row.injection_suspected = False
    row.provider, row.model = provider, model
    row.media_type, row.image_bytes = media_type, image_bytes
    row.agent_run_id = agent_run_id
    row.completed_at = clock.now()
    session.flush()
    _record(
        session, clock, row, "message.image_description_failed", {"reason": reason}, correlation_id
    )
    if wake and reason != "IMAGE_SOURCE_GONE":
        wake_after_image_description(session, clock, row, correlation_id)


def wake_after_image_description(
    session: Session,
    clock: Clock,
    row: MessageImageDescription,
    correlation_id: uuid.UUID | None,
) -> None:
    """Make the agent or legacy draft job look at the conversation again now that this
    image is final.
    """
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
                "message.image_described"
                if row.status == "succeeded"
                else "message.image_description_failed"
            )
            record_thread_event(
                session,
                clock,
                workspace_id=row.workspace_id,
                account_id=conversation.social_account_id,
                thread_id=thread.id,
                kind=kind,
                source_kind="message_image_description",
                source_key=f"image_desc:{row.id}",
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


def _locked_row(
    session: Session, workspace_id: uuid.UUID, message_id: uuid.UUID, index: int
) -> MessageImageDescription | None:
    return session.scalars(
        select(MessageImageDescription)
        .where(
            MessageImageDescription.workspace_id == workspace_id,
            MessageImageDescription.message_id == message_id,
            MessageImageDescription.attachment_index == index,
        )
        .with_for_update()
    ).one_or_none()


def _on_dead(job: JobContext, error_code: str) -> None:
    """Every retry failed (or an unexpected error): the owner sees why there is no description."""
    payload = job.payload
    if not isinstance(payload, DescribeMessageImagePayload) or job.workspace_id is None:
        return
    reason = error_code if error_code.startswith("IMAGE_") else "IMAGE_DESCRIPTION_UNAVAILABLE"
    with job.session_factory() as session:
        row = _locked_row(session, job.workspace_id, payload.message_id, payload.attachment_index)
        if row is not None and row.status == "pending":
            _mark_failed(session, job.clock, row, reason, correlation_id=job.correlation_id)
        session.commit()


def _fail_now(
    job: JobContext, payload: DescribeMessageImagePayload, reason: str, **details: Any
) -> None:
    with job.session_factory() as session:
        row = _locked_row(
            session,
            job.workspace_id,  # type: ignore[arg-type]
            payload.message_id,
            payload.attachment_index,
        )
        if row is not None and row.status == "pending":
            _mark_failed(
                session, job.clock, row, reason, correlation_id=job.correlation_id, **details
            )
        session.commit()


@job_handler(
    "describe_message_image",
    DescribeMessageImagePayload,
    max_attempts=3,
    timeout=DESCRIBE_TIMEOUT_SECONDS,
    on_dead=_on_dead,
    backoff=(10, 60, 300),
)
def describe_message_image(job: JobContext) -> None:
    """Three phases; the download and the model call run with **no transaction open**."""
    payload = job.payload
    if not isinstance(payload, DescribeMessageImagePayload) or job.workspace_id is None:
        return
    settings = get_runtime_settings()
    index = payload.attachment_index
    with job.session_factory() as session:  # [T1] read-only
        row = session.scalars(
            select(MessageImageDescription).where(
                MessageImageDescription.workspace_id == job.workspace_id,
                MessageImageDescription.message_id == payload.message_id,
                MessageImageDescription.attachment_index == index,
            )
        ).one_or_none()
        if row is None or row.status != "pending":
            return  # done, erased or never requested: nothing to do (idempotent)
        message = session.scalars(
            select(Message).where(
                Message.workspace_id == job.workspace_id, Message.id == payload.message_id
            )
        ).one_or_none()
        still_image, url = _image_url(message, index)
        simulated = row.is_simulated
        workspace = session.get(Workspace, job.workspace_id)
        locale = workspace.default_locale if workspace is not None else "tr"
        ctx = system_context(session, job.workspace_id, "image_description")
        used_in_last_day = int(
            session.scalar(
                select(func.count())
                .select_from(MessageImageDescription)
                .where(
                    MessageImageDescription.workspace_id == job.workspace_id,
                    MessageImageDescription.provider.is_not(None),
                    MessageImageDescription.created_at >= job.clock.now() - _ONE_DAY,
                )
            )
            or 0
        )
        session.commit()
    if not still_image or ctx is None:
        return _fail_now(job, payload, "IMAGE_SOURCE_GONE")
    if url is None:
        return _fail_now(job, payload, "IMAGE_URL_MISSING")
    if not settings.image_description_enabled:  # switched off after the job was queued
        return _fail_now(job, payload, "IMAGE_DESCRIPTION_UNAVAILABLE")
    if used_in_last_day >= settings.image_description_max_per_workspace_per_day:
        return _fail_now(job, payload, "IMAGE_QUOTA_EXCEEDED")

    image_bytes: int | None = None
    try:  # no transaction is open from here to [T3]
        fetched = get_image_fetcher(simulated=simulated).fetch(
            url,
            max_bytes=settings.image_description_max_bytes,
            timeout_s=settings.image_description_download_timeout_seconds,
        )
        job.heartbeat()
        image_bytes = len(fetched.data)
        if image_bytes == 0:
            raise ImageRejected("IMAGE_EMPTY")
        if image_bytes > settings.image_description_max_bytes:
            raise ImageRejected("IMAGE_TOO_LARGE")
        media_type = resolved_media_type(fetched.content_type, fetched.data)
        if media_type is None:
            raise ImageRejected("IMAGE_UNSUPPORTED_TYPE")
    except ImageError as exc:
        if exc.retryable:  # the worker retries, and calls ``_on_dead`` after the last attempt
            raise RetryableError(exc.code) from None
        return _fail_now(job, payload, exc.code, image_bytes=image_bytes)

    # A transient provider failure raises RetryableError out of ``run_task``: the job retries.
    outcome = run_task(  # no transaction is open here
        runner_deps(job.session_factory, job.clock),
        ctx,
        DESCRIBE_IMAGE,
        DescribeImageInput(image=fetched.data, media_type=media_type, locale=locale),
        job.correlation_id,
        job_id=job.job_id,
    )
    del fetched  # the picture is never kept
    job.heartbeat()

    reason: str | None = None
    description = visible_text = ""
    looks_like: str | None = None
    if outcome.output is not None and isinstance(outcome.output, ImageDescription):
        description = clean_text(
            outcome.output.description, MAX_IMAGE_DESCRIPTION_CHARS, single_line=True
        )
        visible_text = clean_text(outcome.output.visible_text, MAX_IMAGE_VISIBLE_TEXT_CHARS)
        looks_like = outcome.output.looks_like
        if not description:
            reason = "IMAGE_DESCRIPTION_REJECTED"
    else:
        reason = _OUTCOME_REASONS.get(outcome.error_code or "", "IMAGE_DESCRIPTION_UNAVAILABLE")
    provider_name, model_name = _run_provider_and_model(job, outcome.agent_run_id)
    # The words are customer content a model read: screen them like any customer text.
    suspected = (
        bool(detect_injection(f"{description}\n{visible_text}")) if reason is None else False
    )

    with job.session_factory() as session:  # [T3]
        row = _locked_row(session, job.workspace_id, payload.message_id, index)
        message = session.scalars(
            select(Message).where(
                Message.workspace_id == job.workspace_id, Message.id == payload.message_id
            )
        ).one_or_none()
        if row is None or row.status != "pending":
            session.commit()
            return
        # The message may have been deleted or erased while the model ran: store nothing.
        if not _image_url(message, index)[0]:
            _mark_failed(
                session, job.clock, row, "IMAGE_SOURCE_GONE", correlation_id=job.correlation_id
            )
        elif reason is not None:
            _mark_failed(
                session,
                job.clock,
                row,
                reason,
                correlation_id=job.correlation_id,
                provider=provider_name,
                model=model_name,
                media_type=media_type,
                image_bytes=image_bytes,
                agent_run_id=outcome.agent_run_id,
            )
        else:
            row.status, row.reason_code = "succeeded", None
            row.looks_like = looks_like
            row.description, row.visible_text = description, visible_text
            row.injection_suspected = suspected
            row.provider, row.model = provider_name, model_name
            row.media_type, row.image_bytes = media_type, image_bytes
            row.agent_run_id = outcome.agent_run_id
            row.completed_at = job.clock.now()
            session.flush()
            _record(
                session,
                job.clock,
                row,
                "message.image_described",
                {
                    "provider": provider_name,
                    "model": model_name,
                    "looks_like": looks_like,
                    "has_visible_text": bool(visible_text),
                    "injection_suspected": suspected,
                    "image_bytes": image_bytes,
                },
                job.correlation_id,
            )
            wake_after_image_description(session, job.clock, row, job.correlation_id)
        session.commit()


def _run_provider_and_model(job: JobContext, agent_run_id: uuid.UUID) -> tuple[str, str]:
    """The provider and model the run recorded (the ``agent_runs`` row is the source of truth)."""
    with job.session_factory() as session:
        run = session.get(AgentRun, agent_run_id)
        found = (run.provider or "unknown", run.model or "unknown") if run else ("unknown",) * 2
        session.commit()
    return found
