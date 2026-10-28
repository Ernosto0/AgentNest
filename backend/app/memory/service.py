"""Private memory writes are proposals with server-bound identity/source generations.

All mutations take the account lock first. No model or provider call occurs here.
"""

import hashlib
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import false, or_, select, true, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.agent.models import AgentAction, AgentSession, AgentStep, AgentThread
from app.agent.repository import AgentScopeError, scoped_account, scoped_thread
from app.audit.service import record
from app.core.clock import Clock
from app.core.config import get_settings
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity.permissions import has_permission
from app.inbox.models import Conversation, Message, ReplyDraft
from app.integrations.instagram.models import SocialAccount
from app.memory.models import (
    CustomerIdentity,
    CustomerMemory,
    MemorySource,
    MemoryVersion,
    SourceFence,
    SummaryVersion,
)


class MemoryProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: Literal["size", "schedule", "service", "language", "contact"]
    kind: Literal["preference", "customer_claim", "open_goal"]
    source_message_id: uuid.UUID
    quote: str = Field(min_length=3, max_length=240)


class MemoryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relevant_to: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=5, ge=1, le=5)


class MemoryChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    body: str = Field(min_length=3, max_length=240)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _ttl() -> timedelta:
    return timedelta(days=get_settings().retention_customer_memory_days)


def memory_deadline(memory: CustomerMemory) -> datetime:
    """A shorter configured retention policy also applies before the next sweep."""
    return min(memory.expires_at, memory.updated_at + _ttl())


def resolve_identity(db: Session, clock: Clock, thread: AgentThread) -> CustomerIdentity | None:
    """Only a provider-scoped DM participant ID establishes continuity, never handles."""
    if thread.surface != "dm" or thread.dm_conversation_id is None:
        return None
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.workspace_id == thread.workspace_id,
            Conversation.social_account_id == thread.social_account_id,
            Conversation.id == thread.dm_conversation_id,
        )
    )
    account = db.get(SocialAccount, thread.social_account_id)
    if conversation is None or account is None or account.status == "disconnected":
        return None
    key = digest(f"{account.provider_kind}:dm:{conversation.customer_external_id}")
    db.execute(
        pg_insert(CustomerIdentity)
        .values(
            id=uuid.uuid4(),
            workspace_id=thread.workspace_id,
            social_account_id=thread.social_account_id,
            provider_subject_hash=key,
            evidence_kind="provider_dm_participant",
            created_at=clock.now(),
        )
        .on_conflict_do_nothing()
    )
    identity = db.scalar(
        select(CustomerIdentity).where(
            CustomerIdentity.workspace_id == thread.workspace_id,
            CustomerIdentity.social_account_id == thread.social_account_id,
            CustomerIdentity.provider_subject_hash == key,
        )
    )
    if identity:
        # A prepopulated public/foreign identity reference is never trusted.
        thread.customer_identity_id = identity.id
        db.flush()
    return identity


def scoped_identity(
    db: Session, ctx: WorkspaceContext, account: uuid.UUID, customer: uuid.UUID
) -> CustomerIdentity:
    try:
        scoped_account(db, ctx.workspace_id, account, lock=True)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    identity = db.scalar(
        select(CustomerIdentity)
        .where(
            CustomerIdentity.workspace_id == ctx.workspace_id,
            CustomerIdentity.social_account_id == account,
            CustomerIdentity.id == customer,
        )
        .with_for_update()
    )
    if identity is None:
        raise AppError("NOT_FOUND")
    return identity


def _scope(identity: CustomerIdentity) -> dict[str, Any]:
    return {
        "workspace_id": identity.workspace_id,
        "social_account_id": identity.social_account_id,
        "customer_identity_id": identity.id,
    }


def _memories(db: Session, identity: CustomerIdentity) -> list[CustomerMemory]:
    return list(
        db.scalars(
            select(CustomerMemory)
            .filter_by(**_scope(identity))
            .order_by(CustomerMemory.updated_at.desc(), CustomerMemory.id)
            .limit(20)
        )
    )


def _audit(
    db: Session,
    clock: Clock,
    identity: CustomerIdentity,
    action: str,
    ctx: WorkspaceContext | None = None,
    memory: CustomerMemory | None = None,
) -> None:
    account = db.get(SocialAccount, identity.social_account_id)
    record(
        db,
        ctx,
        action,
        "customer_identity",
        identity.id,
        {
            "generation": identity.generation,
            "revision": identity.revision,
            **({"memory_id": memory.id, "memory_version": memory.version} if memory else {}),
        },
        workspace_id=identity.workspace_id,
        is_simulated=bool(account and account.is_simulated),
        clock=clock,
    )


def invalidate(
    db: Session,
    clock: Clock,
    identity: CustomerIdentity,
    *,
    erase_bodies: bool = False,
    fence_sources: bool = True,
) -> None:
    """Fence models and projected drafts; clear every derived historical body/cache."""
    identity.generation += 1
    identity.revision += 1
    threads = list(
        db.scalars(
            select(AgentThread)
            .where(
                AgentThread.workspace_id == identity.workspace_id,
                AgentThread.social_account_id == identity.social_account_id,
                AgentThread.customer_identity_id == identity.id,
            )
            .with_for_update()
        )
    )
    thread_ids = [t.id for t in threads]
    for thread in threads:
        thread.deletion_generation += 1
    db.execute(
        update(SummaryVersion).filter_by(**_scope(identity)).values(body=None, query_hash="")
    )
    goals = select(AgentSession.id).where(
        AgentSession.workspace_id == identity.workspace_id, AgentSession.thread_id.in_(thread_ids)
    )
    steps = select(AgentStep.id).where(
        AgentStep.workspace_id == identity.workspace_id, AgentStep.session_id.in_(goals)
    )
    db.execute(update(AgentStep).where(AgentStep.id.in_(steps)).values(read_checkpoint=None))
    # Account-agent AgentRun snapshots/output contain only counts and tool names. Keep
    # that content-free usage/outcome evidence; no personal model output is persisted there.
    conversations = [t.dm_conversation_id for t in threads if t.dm_conversation_id]
    # Memory cannot invalidate a human/manual proposal that never consumed it.
    agent_draft_ids = list(
        db.scalars(
            select(ReplyDraft.id).where(
                ReplyDraft.workspace_id == identity.workspace_id,
                ReplyDraft.conversation_id.in_(conversations),
                or_(
                    ReplyDraft.origin == "agent",
                    ReplyDraft.validation.contains({"agent_proposal": {}}),
                ),
            )
        )
    )
    from app.agent.jobs import enqueue_cleanup
    from app.agent.transitions import transition_action
    from app.inbox import drafts
    from app.inbox.system import system_context

    draft_rows = list(
        db.scalars(
            select(ReplyDraft)
            .where(
                ReplyDraft.id.in_(agent_draft_ids),
                ReplyDraft.status.in_(("queued", "pending_approval", "needs_human")),
            )
            .with_for_update()
        )
    )
    pending_ids = [d.id for d in draft_rows]
    for action in db.scalars(
        select(AgentAction)
        .where(
            AgentAction.workspace_id == identity.workspace_id,
            AgentAction.social_account_id == identity.social_account_id,
            AgentAction.payload_ref.in_(pending_ids),
            AgentAction.status.in_(("proposed", "waiting_approval", "authorized", "queued")),
        )
        .with_for_update()
    ):
        transition_action(
            db,
            workspace_id=identity.workspace_id,
            action_id=action.id,
            expected_status=action.status,
            expected_version=action.version,
            next_status="cancelled",
            clock=clock,
        )
        db.refresh(action)
        action.outcome_code = "APPROVAL_STALE"
    mutation_ctx = system_context(db, identity.workspace_id, "memory.privacy")
    if mutation_ctx:
        for draft in draft_rows:
            drafts.transition(
                db,
                clock,
                mutation_ctx,
                draft,
                "expire" if draft.status == "needs_human" else "cancel",
                reason="APPROVAL_STALE",
            )
    if draft_rows:
        enqueue_cleanup(
            db,
            clock,
            identity.workspace_id,
            identity.social_account_id,
            f"memory:{identity.id}:{identity.generation}",
        )
    # Content-free provider-source tombstones use server-linked records, not model-supplied
    # timestamps or versions. Even physical deletion and re-ingestion cannot replay them.
    for source in db.scalars(
        select(Message).where(
            Message.workspace_id == identity.workspace_id,
            Message.social_account_id == identity.social_account_id,
            Message.conversation_id.in_(conversations),
            Message.direction == "inbound",
            true() if fence_sources else false(),
        )
    ):
        db.execute(
            pg_insert(SourceFence)
            .values(
                id=uuid.uuid4(),
                **_scope(identity),
                source_key=digest(source.external_message_id or str(source.id)),
            )
            .on_conflict_do_nothing()
        )
    # The exact personal proposal is never reconciliation evidence. Existing uncertain-send
    # text/IDs retain their ADR-022 lifecycle; validation can be erased immediately.
    db.execute(
        update(ReplyDraft)
        .where(
            ReplyDraft.workspace_id == identity.workspace_id,
            ReplyDraft.id.in_(agent_draft_ids),
        )
        .values(validation={}, template=None, suggestion_text=None)
    )
    db.execute(
        update(ReplyDraft)
        .where(
            ReplyDraft.workspace_id == identity.workspace_id,
            ReplyDraft.id.in_(agent_draft_ids),
            ReplyDraft.status.in_(
                (
                    "queued",
                    "pending_approval",
                    "needs_human",
                    "cancelled",
                    "expired",
                    "sending",
                    "outcome_unknown",
                )
                if erase_bodies
                else ("queued", "pending_approval", "needs_human", "cancelled")
            ),
        )
        .values(validation={"privacy_redacted": True})
    )
    db.execute(
        update(ReplyDraft)
        .where(
            ReplyDraft.workspace_id == identity.workspace_id,
            ReplyDraft.id.in_(pending_ids),
        )
        .values(text=None)
    )
    db.flush()


def _clear(db: Session, memory: CustomerMemory, now: Any) -> None:
    memory.body = None
    memory.source_cutoff = now
    db.execute(
        update(MemoryVersion)
        .where(
            MemoryVersion.workspace_id == memory.workspace_id, MemoryVersion.memory_id == memory.id
        )
        .values(body=None)
    )
    db.execute(
        update(MemorySource)
        .where(
            MemorySource.workspace_id == memory.workspace_id, MemorySource.memory_id == memory.id
        )
        .values(removed=True)
    )


_SENSITIVE = re.compile(
    r"\b(diagnos\w*|diabet\w*|pregnan\w*|cancer|disabil\w*|religio\w*|muslim|christian|"
    r"gay|lesbian|sexual\w*|politic\w*|hastal\w*|hamile\w*|dinim|inanc\w*|ırk\w*|"
    r"race|ethnic\w*|password|token|secret)\b",
    re.I,
)
_SELF_REPORT = re.compile(
    r"\b(I|my|me|prefer|want|need|ben|benim|istiyorum|tercih|giyiyorum|uygunum)\b", re.I
)
_TOPIC_CUES = {
    "size": r"\b(size|wear|beden|numara|giyiyorum)\b",
    "schedule": (
        r"\b(schedule|morning|evening|afternoon|weekend|weekday|time|monday|tuesday|"
        r"wednesday|thursday|friday|saturday|sunday|sabah|akşam|öğlen|saat|hafta)\b"
    ),
    "service": (
        r"\b(service|appointment|booking|order|bought|product|class|consultation|"
        r"massage|hizmet|randevu|sipariş|ürün|ders|istiyorum|want|need)\b"
    ),
    "language": r"\b(language|english|turkish|türkçe|ingilizce|dil)\b",
    "contact": r"\b(contact|email|phone|message|whatsapp|iletişim|posta|telefon|mesaj)\b",
}


def write_proposal(
    db: Session, clock: Clock, context: Any, proposal: MemoryProposal
) -> dict[str, Any]:
    if context.surface != "dm":
        raise ValueError("private memory only")
    scoped_account(db, context.workspace.workspace_id, context.account_id, lock=True)
    thread = scoped_thread(
        db, context.workspace.workspace_id, context.account_id, context.thread_id, lock=True
    )
    identity = resolve_identity(db, clock, thread)
    if (
        identity is None
        or context.memory_generation is None
        or context.memory_generation != identity.generation
    ):
        raise ValueError("stale memory generation")
    source = db.scalar(
        select(Message).where(
            Message.workspace_id == identity.workspace_id,
            Message.social_account_id == identity.social_account_id,
            Message.conversation_id == thread.dm_conversation_id,
            Message.id == proposal.source_message_id,
            Message.direction == "inbound",
            Message.is_deleted.is_(False),
            Message.text.is_not(None),
        )
    )
    # Re-ingestion after physical source deletion must resolve the same privacy fence.
    # A database UUID is not stable provider evidence for a replay without a message ID.
    if (
        source is None
        or not (source.external_message_id or "").strip()
        or proposal.quote not in (source.text or "")
    ):
        raise ValueError("source is not an evidenced customer statement")
    if (
        _SENSITIVE.search(proposal.quote)
        or not _SELF_REPORT.search(proposal.quote)
        or not re.search(_TOPIC_CUES[proposal.topic], proposal.quote, re.I)
    ):
        raise ValueError("only useful self-reported non-sensitive preferences/claims")
    memory = db.scalar(select(CustomerMemory).filter_by(**_scope(identity), topic=proposal.topic))
    source_key = digest(source.external_message_id or str(source.id))
    if db.scalar(select(SourceFence.id).filter_by(**_scope(identity), source_key=source_key)):
        raise ValueError("source is covered by a privacy tombstone")
    if memory:
        seen = db.scalar(
            select(MemorySource).where(
                MemorySource.memory_id == memory.id, MemorySource.source_key == source_key
            )
        )
        if seen:
            if seen.removed:
                raise ValueError("source was forgotten")
            return {"memory_id": str(memory.id), "version": memory.version, "duplicate": True}
        # Conflicting statements create another version; never silently keep old derived text.
        invalidate(db, clock, identity, fence_sources=False)
        _clear(db, memory, clock.now())
        memory.version += 1
    else:
        memory = CustomerMemory(
            **_scope(identity), topic=proposal.topic, kind=proposal.kind, version=1
        )
        db.add(memory)
        identity.revision += 1
    memory.body, memory.kind = proposal.quote, proposal.kind
    memory.updated_at = clock.now()
    memory.expires_at = clock.now() + _ttl()
    db.flush()
    db.add(
        MemoryVersion(
            **_scope(identity),
            memory_id=memory.id,
            version=memory.version,
            body=memory.body,
            provenance="customer_self_report",
            created_at=clock.now(),
        )
    )
    db.add(
        MemorySource(
            **_scope(identity),
            memory_id=memory.id,
            memory_version=memory.version,
            message_id=source.id,
            source_key=source_key,
            observed_at=source.created_at,
        )
    )
    _audit(db, clock, identity, "memory.written", context.workspace, memory)
    db.flush()
    return {
        "memory_id": str(memory.id),
        "version": memory.version,
        "authority": "customer_statement_only",
    }


def relevant(
    db: Session, clock: Clock, identity: CustomerIdentity, query: str, limit: int = 5
) -> list[dict[str, Any]]:
    words = set(re.findall(r"\w{3,}", query.casefold())) - {
        "the",
        "and",
        "you",
        "your",
        "can",
        "please",
        "what",
        "have",
        "prefer",
        "want",
        "need",
        "like",
        "would",
        "tercih",
        "istiyorum",
        "benim",
    }
    result = []
    for row in _memories(db, identity):
        if not row.body or memory_deadline(row) <= clock.now():
            continue
        terms = set(re.findall(r"\w{3,}", f"{row.topic} {row.body}".casefold()))
        score = len(words & terms)
        if score:
            result.append((score, row))
    result.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "id": str(row.id),
            "kind": row.kind,
            "topic": row.topic,
            "body": row.body,
            "version": row.version,
            "authority": "customer_statement_only",
        }
        for _, row in result[: min(limit, 5)]
    ]


def source_visible(db: Session, identity_id: uuid.UUID | None, message: Message) -> bool:
    if identity_id is None:
        return True
    return (
        db.scalar(
            select(SourceFence.id).where(
                SourceFence.workspace_id == message.workspace_id,
                SourceFence.social_account_id == message.social_account_id,
                SourceFence.customer_identity_id == identity_id,
                SourceFence.source_key == digest(message.external_message_id or str(message.id)),
            )
        )
        is None
    )


def private_context(db: Session, clock: Clock, context: Any, query: str) -> dict[str, Any] | None:
    if context.surface != "dm":
        return None
    scoped_account(db, context.workspace.workspace_id, context.account_id, lock=True)
    thread = scoped_thread(
        db, context.workspace.workspace_id, context.account_id, context.thread_id, lock=True
    )
    identity = resolve_identity(db, clock, thread)
    if identity is None:
        return None
    _expire_identity(db, clock, identity)
    items = relevant(db, clock, identity, query)
    fingerprint = digest(query.casefold())
    latest = db.scalar(
        select(SummaryVersion)
        .filter_by(**_scope(identity), thread_id=thread.id)
        .order_by(SummaryVersion.version.desc())
        .limit(1)
    )
    if latest is None or (
        latest.generation,
        latest.revision,
        latest.source_cursor,
        latest.query_hash,
    ) != (identity.generation, identity.revision, thread.event_cursor, fingerprint):
        latest = SummaryVersion(
            **_scope(identity),
            thread_id=thread.id,
            version=latest.version + 1 if latest else 1,
            generation=identity.generation,
            revision=identity.revision,
            source_cursor=thread.event_cursor,
            query_hash=fingerprint,
            body="\n".join(f"{i['kind']}: {i['body']}" for i in items)[:1500],
            created_at=clock.now(),
        )
        db.add(latest)
        db.flush()
    return {
        "customer_id": str(identity.id),
        "generation": identity.generation,
        "memories": items,
        "summary": {
            "version": latest.version,
            "source_cursor": latest.source_cursor,
            "body": latest.body,
            "authority": "derived_customer_context_only",
        },
    }


def change(
    db: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account: uuid.UUID,
    customer: uuid.UUID,
    memory_id: uuid.UUID,
    body: MemoryChange | None,
) -> None:
    if not has_permission(ctx.role, "memory.correct" if body else "memory.forget"):
        raise AppError("FORBIDDEN")
    identity = scoped_identity(db, ctx, account, customer)
    memory = db.scalar(select(CustomerMemory).filter_by(**_scope(identity), id=memory_id))
    if memory is None:
        raise AppError("NOT_FOUND")
    if body and body.expected_version != memory.version:
        raise AppError("CONFLICT_STATE")
    if body and _SENSITIVE.search(body.body):
        raise AppError("VALIDATION_FAILED")
    invalidate(db, clock, identity, erase_bodies=body is None)
    _clear(db, memory, clock.now())
    memory.version += 1
    memory.updated_at = clock.now()
    if body:
        memory.body = body.body
        memory.expires_at = clock.now() + _ttl()
        db.add(
            MemoryVersion(
                **_scope(identity),
                memory_id=memory.id,
                version=memory.version,
                body=body.body,
                provenance="member_correction",
                author_user_id=uuid.UUID(ctx.actor.id)
                if ctx.actor.type == "user" and ctx.actor.id
                else None,
                created_at=clock.now(),
            )
        )
    _audit(db, clock, identity, "memory.corrected" if body else "memory.forgotten", ctx, memory)
    db.flush()


def erase_identity(
    db: Session, clock: Clock, identity: CustomerIdentity, ctx: WorkspaceContext | None = None
) -> None:
    invalidate(db, clock, identity, erase_bodies=True)
    identity.source_cutoff = clock.now()
    for memory in _memories(db, identity):
        _clear(db, memory, clock.now())
    _audit(db, clock, identity, "memory.erased", ctx)
    db.flush()


def erase_account(db: Session, clock: Clock, workspace: uuid.UUID, account: uuid.UUID) -> None:
    scoped_account(db, workspace, account, lock=True)
    from app.owner_requests.service import redact

    redact(db, clock, workspace, account)
    for identity in db.scalars(
        select(CustomerIdentity)
        .where(
            CustomerIdentity.workspace_id == workspace,
            CustomerIdentity.social_account_id == account,
        )
        .with_for_update()
    ):
        erase_identity(db, clock, identity)
    # Unlink personal provenance before physical message removal; content-free source keys stay.
    db.execute(
        update(MemorySource)
        .where(MemorySource.workspace_id == workspace, MemorySource.social_account_id == account)
        .values(message_id=None, removed=True)
    )
    conversations = select(Conversation.id).where(
        Conversation.workspace_id == workspace, Conversation.social_account_id == account
    )
    db.execute(
        update(ReplyDraft)
        .where(ReplyDraft.workspace_id == workspace, ReplyDraft.conversation_id.in_(conversations))
        .values(validation={"privacy_redacted": True}, template=None, suggestion_text=None)
    )
    db.execute(
        update(ReplyDraft)
        .where(
            ReplyDraft.workspace_id == workspace,
            ReplyDraft.conversation_id.in_(conversations),
            ReplyDraft.status.not_in(("sending", "outcome_unknown")),
        )
        .values(text=None)
    )
    db.execute(
        update(Message)
        .where(Message.workspace_id == workspace, Message.social_account_id == account)
        .values(text=None, attachments=[])
    )


def erase_source(db: Session, clock: Clock, message: Message) -> None:
    scoped_account(db, message.workspace_id, message.social_account_id, lock=True)
    from app.owner_requests.service import redact

    redact(db, clock, message.workspace_id, message.social_account_id, message.id)
    links = list(
        db.scalars(
            select(MemorySource).where(
                MemorySource.workspace_id == message.workspace_id,
                MemorySource.social_account_id == message.social_account_id,
                MemorySource.message_id == message.id,
            )
        )
    )
    touched = set()
    for thread in db.scalars(
        select(AgentThread).where(
            AgentThread.workspace_id == message.workspace_id,
            AgentThread.social_account_id == message.social_account_id,
            AgentThread.dm_conversation_id == message.conversation_id,
            AgentThread.surface == "dm",
        )
    ):
        identity = resolve_identity(db, clock, thread)
        if identity and identity.id not in touched:
            invalidate(db, clock, identity, erase_bodies=True)
            touched.add(identity.id)
    for link in links:
        identity = db.get(CustomerIdentity, link.customer_identity_id)
        memory = db.get(CustomerMemory, link.memory_id)
        if identity and memory:
            if identity.id not in touched:
                invalidate(db, clock, identity, erase_bodies=True)
                touched.add(identity.id)
            _clear(db, memory, clock.now())
        link.removed, link.message_id = True, None
    db.flush()


def export_customer(
    db: Session, clock: Clock, ctx: WorkspaceContext, account: uuid.UUID, customer: uuid.UUID
) -> dict[str, Any]:
    """Internal memory-only DSAR hook; general cross-domain rights API belongs to Phase 8."""
    if not has_permission(ctx.role, "data.export"):
        raise AppError("FORBIDDEN")
    identity = scoped_identity(db, ctx, account, customer)
    _expire_identity(db, clock, identity)
    memories = [m for m in _memories(db, identity) if m.body and memory_deadline(m) > clock.now()]
    return {
        "customer_id": str(identity.id),
        "generation": identity.generation,
        "memories": [
            {"id": str(m.id), "body": m.body, "version": m.version, "kind": m.kind}
            for m in memories
        ],
        "sources": [
            {
                "message_id": str(s.message_id),
                "memory_id": str(s.memory_id),
                "version": s.memory_version,
            }
            for s in db.scalars(select(MemorySource).filter_by(**_scope(identity), removed=False))
            if s.message_id
        ],
        "summaries": [
            {"version": s.version, "body": s.body, "source_cursor": s.source_cursor}
            for s in db.scalars(select(SummaryVersion).filter_by(**_scope(identity)))
            if s.body
        ],
    }


def erase_customer(
    db: Session, clock: Clock, ctx: WorkspaceContext, account: uuid.UUID, customer: uuid.UUID
) -> None:
    if not has_permission(ctx.role, "data.delete"):
        raise AppError("FORBIDDEN")
    erase_identity(db, clock, scoped_identity(db, ctx, account, customer), ctx)


def _expire_identity(db: Session, clock: Clock, identity: CustomerIdentity) -> None:
    expired = [m for m in _memories(db, identity) if m.body and memory_deadline(m) <= clock.now()]
    if expired:
        invalidate(db, clock, identity, erase_bodies=True)
        for memory in expired:
            _clear(db, memory, clock.now())
        db.flush()


def retention_batch(db: Session, clock: Clock, cutoff: Any, batch: int) -> int:
    rows = list(
        db.scalars(
            select(CustomerMemory)
            .where(
                CustomerMemory.body.is_not(None),
                or_(CustomerMemory.expires_at <= clock.now(), CustomerMemory.updated_at < cutoff),
            )
            .limit(batch)
        )
    )
    for memory in rows:
        scoped_account(db, memory.workspace_id, memory.social_account_id, lock=True)
        identity = db.get(CustomerIdentity, memory.customer_identity_id)
        if identity:
            invalidate(db, clock, identity, erase_bodies=True)
            _clear(db, memory, clock.now())
    db.flush()
    return len(rows)
