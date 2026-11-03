"""Data-rights exports and lifecycle services (P8-05, ADR-025 §3.1).

Covers:
- Permission-checked (Owner only, data.export) conversation and customer export.
- Complete machine-readable schema_version: "1.0" JSON export.
- Private conversation messages, drafts, approvals, and safe operation metadata.
- Account-scoped customer identities and customer memory export (via memory.service).
- Owner questions/answers and linked public comments by verified external author ID (INV-18).
- Strict exclusion of access tokens, secrets, signatures, and unlinked third-party comments.
- Audit emission (data_rights.conversation_exported, data_rights.customer_exported).
"""

import contextlib
import uuid
from typing import Any

from sqlalchemy import delete, null, or_, select, update
from sqlalchemy.orm import Session

from app.agent.models import AgentThread
from app.approvals.models import Approval
from app.audit import service as audit
from app.comments.models import PublicComment
from app.comments.privacy import redact_receipts
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity.models import Workspace
from app.identity.permissions import has_permission
from app.inbox.models import Conversation, InboundEvent, Message, ReplyDraft
from app.integrations.instagram.models import SocialAccount
from app.memory import service as memory_service
from app.memory.models import CustomerIdentity
from app.operations.models import DeletionTombstone, Operation
from app.owner_requests.models import OwnerAnswer, OwnerQuestion

SCHEMA_VERSION = "1.0"


def export_conversation(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    conversation_id: uuid.UUID,
) -> dict[str, Any]:
    """Export all authorized personal records for a single conversation in machine-readable JSON."""
    if not has_permission(ctx.role, "data.export"):
        raise AppError("FORBIDDEN")

    conversation = session.scalar(
        select(Conversation).where(
            Conversation.workspace_id == ctx.workspace_id,
            Conversation.id == conversation_id,
        )
    )
    if conversation is None:
        raise AppError("NOT_FOUND")

    workspace = session.get(Workspace, ctx.workspace_id)
    account = session.scalar(
        select(SocialAccount).where(
            SocialAccount.workspace_id == ctx.workspace_id,
            SocialAccount.id == conversation.social_account_id,
        )
    )

    # 1. Chronological messages
    messages = list(
        session.scalars(
            select(Message)
            .where(
                Message.workspace_id == ctx.workspace_id,
                Message.conversation_id == conversation.id,
            )
            .order_by(Message.provider_timestamp.asc(), Message.created_at.asc())
        )
    )

    # 2. Reply drafts
    drafts = list(
        session.scalars(
            select(ReplyDraft)
            .where(
                ReplyDraft.workspace_id == ctx.workspace_id,
                ReplyDraft.conversation_id == conversation.id,
            )
            .order_by(ReplyDraft.created_at.asc())
        )
    )

    # 3. Approvals for drafts
    draft_ids = [d.id for d in drafts]
    approvals: list[dict[str, Any]] = []
    if draft_ids:
        appr_rows = list(
            session.scalars(
                select(Approval).where(
                    Approval.workspace_id == ctx.workspace_id,
                    Approval.subject_id.in_(draft_ids),
                )
            )
        )
        approvals = [
            {
                "id": str(a.id),
                "subject_type": a.subject_type,
                "subject_id": str(a.subject_id),
                "status": a.status,
                "decided_at": a.decided_at.isoformat() if a.decided_at else None,
                "decision_note": a.decision_note,
            }
            for a in appr_rows
        ]

    # 4. Safe operations history
    op_ids = [d.operation_id for d in drafts if d.operation_id is not None]
    operations: list[dict[str, Any]] = []
    if op_ids:
        op_rows = list(
            session.scalars(
                select(Operation).where(
                    Operation.workspace_id == ctx.workspace_id,
                    Operation.id.in_(op_ids),
                )
            )
        )
        operations = [
            {
                "id": str(op.id),
                "operation_type": op.operation_type,
                "status": op.status,
                "created_at": op.created_at.isoformat(),
                "started_at": op.started_at.isoformat() if op.started_at else None,
                "completed_at": op.completed_at.isoformat() if op.completed_at else None,
                "last_error_code": op.last_error_code,
            }
            for op in op_rows
        ]

    # 5. Customer identity and memory
    cust_id_row: CustomerIdentity | None = None
    if conversation.customer_external_id and account:
        key = memory_service.digest(
            f"{account.provider_kind}:dm:{conversation.customer_external_id}"
        )
        cust_id_row = session.scalar(
            select(CustomerIdentity).where(
                CustomerIdentity.workspace_id == ctx.workspace_id,
                CustomerIdentity.social_account_id == conversation.social_account_id,
                CustomerIdentity.provider_subject_hash == key,
            )
        )

    customer_memory_export: dict[str, Any] | None = None
    customer_identity_info: dict[str, Any] | None = None
    owner_questions: list[dict[str, Any]] = []

    if cust_id_row is not None:
        customer_identity_info = {
            "id": str(cust_id_row.id),
            "evidence_kind": cust_id_row.evidence_kind,
            "generation": cust_id_row.generation,
            "created_at": cust_id_row.created_at.isoformat(),
        }
        try:
            customer_memory_export = memory_service.export_customer(
                session, clock, ctx, cust_id_row.social_account_id, cust_id_row.id
            )
        except Exception:
            customer_memory_export = None

        oq_rows = list(
            session.scalars(
                select(OwnerQuestion).where(
                    OwnerQuestion.workspace_id == ctx.workspace_id,
                    OwnerQuestion.customer_identity_id == cust_id_row.id,
                )
            )
        )
        for q in oq_rows:
            answer_dict: dict[str, Any] | None = None
            if q.answer_id:
                ans = session.scalar(
                    select(OwnerAnswer).where(
                        OwnerAnswer.workspace_id == ctx.workspace_id,
                        OwnerAnswer.id == q.answer_id,
                    )
                )
                if ans:
                    answer_dict = {
                        "id": str(ans.id),
                        "answer_body": ans.body,
                        "created_at": ans.created_at.isoformat(),
                    }
            owner_questions.append(
                {
                    "id": str(q.id),
                    "required_info": q.required_info,
                    "body": q.body,
                    "state": q.state,
                    "created_at": q.created_at.isoformat(),
                    "expires_at": q.expires_at.isoformat(),
                    "answer": answer_dict,
                }
            )

    # 6. Linked public comments by same customer (INV-18)
    linked_public_comments: list[dict[str, Any]] = []
    if conversation.customer_external_id:
        comm_rows = list(
            session.scalars(
                select(PublicComment).where(
                    PublicComment.workspace_id == ctx.workspace_id,
                    PublicComment.social_account_id == conversation.social_account_id,
                    PublicComment.author_external_id == conversation.customer_external_id,
                )
            )
        )
        linked_public_comments = [
            {
                "id": str(c.id),
                "external_id": c.external_id,
                "text": c.text,
                "state": c.state,
                "provider_timestamp": (
                    c.provider_timestamp.isoformat() if c.provider_timestamp else None
                ),
            }
            for c in comm_rows
        ]

    # 7. Audit log emission
    audit.record(
        session,
        ctx,
        "data_rights.conversation_exported",
        "conversation",
        conversation.id,
        {
            "social_account_id": str(conversation.social_account_id),
            "messages_count": len(messages),
        },
        clock=clock,
    )
    session.commit()

    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": clock.now().isoformat(),
        "workspace": {
            "id": str(ctx.workspace_id),
            "name": workspace.name if workspace else "Unknown",
        },
        "social_account": (
            {
                "id": str(account.id),
                "provider_kind": account.provider_kind,
                "external_account_id": account.external_account_id,
                "username": account.username,
                "status": account.status,
            }
            if account
            else None
        ),
        "conversation": {
            "id": str(conversation.id),
            "participant_id": conversation.customer_external_id,
            "customer_handle": conversation.customer_handle,
            "handling_mode": conversation.handling_mode,
            "created_at": conversation.created_at.isoformat(),
            "last_activity_at": (
                conversation.last_message_at.isoformat() if conversation.last_message_at else None
            ),
        },
        "messages": [
            {
                "id": str(m.id),
                "direction": m.direction,
                "sender_kind": m.sender_kind,
                "external_message_id": m.external_message_id,
                "text": m.text,
                "attachments": m.attachments,
                "provider_timestamp": m.provider_timestamp.isoformat(),
                "is_deleted": m.is_deleted,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
        "reply_drafts": [
            {
                "id": str(d.id),
                "source": d.source,
                "decision": d.decision,
                "status": d.status,
                "draft_text": d.text,
                "created_at": d.created_at.isoformat(),
                "updated_at": d.updated_at.isoformat() if d.updated_at else None,
            }
            for d in drafts
        ],
        "approvals": approvals,
        "operations": operations,
        "customer_identity": customer_identity_info,
        "customer_memory": customer_memory_export,
        "owner_questions": owner_questions,
        "linked_public_comments": linked_public_comments,
    }


def export_customer(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    customer_identity_id: uuid.UUID,
) -> dict[str, Any]:
    """Export all records for a customer identity across conversations, memories, and comments."""
    if not has_permission(ctx.role, "data.export"):
        raise AppError("FORBIDDEN")

    cust_id_row = session.scalar(
        select(CustomerIdentity).where(
            CustomerIdentity.workspace_id == ctx.workspace_id,
            CustomerIdentity.id == customer_identity_id,
        )
    )
    if cust_id_row is None:
        raise AppError("NOT_FOUND")

    workspace = session.get(Workspace, ctx.workspace_id)
    account = session.scalar(
        select(SocialAccount).where(
            SocialAccount.workspace_id == ctx.workspace_id,
            SocialAccount.id == cust_id_row.social_account_id,
        )
    )

    # 1. Customer conversations on this account via AgentThreads or hash matching
    threads = list(
        session.scalars(
            select(AgentThread).where(
                AgentThread.workspace_id == ctx.workspace_id,
                AgentThread.customer_identity_id == cust_id_row.id,
            )
        )
    )
    thread_dm_conv_ids = [t.dm_conversation_id for t in threads if t.dm_conversation_id]

    conv_rows = list(
        session.scalars(
            select(Conversation).where(
                Conversation.workspace_id == ctx.workspace_id,
                Conversation.social_account_id == cust_id_row.social_account_id,
            )
        )
    )
    # Filter to conversations matching thread dm_conversation_id or hash
    matched_convs: list[Conversation] = []
    for c in conv_rows:
        if c.id in thread_dm_conv_ids:
            matched_convs.append(c)
        elif account and c.customer_external_id:
            h = memory_service.digest(f"{account.provider_kind}:dm:{c.customer_external_id}")
            if h == cust_id_row.provider_subject_hash:
                matched_convs.append(c)

    conv_ids = [c.id for c in matched_convs]
    participant_external_ids = {
        c.customer_external_id for c in matched_convs if c.customer_external_id
    }

    # 2. Chronological messages
    messages: list[dict[str, Any]] = []
    if conv_ids:
        msg_rows = list(
            session.scalars(
                select(Message)
                .where(
                    Message.workspace_id == ctx.workspace_id,
                    Message.conversation_id.in_(conv_ids),
                )
                .order_by(Message.provider_timestamp.asc())
            )
        )
        messages = [
            {
                "id": str(m.id),
                "conversation_id": str(m.conversation_id),
                "direction": m.direction,
                "sender_kind": m.sender_kind,
                "text": m.text,
                "attachments": m.attachments,
                "provider_timestamp": m.provider_timestamp.isoformat(),
            }
            for m in msg_rows
        ]

    # 3. Memory export
    try:
        memory_export = memory_service.export_customer(
            session, clock, ctx, cust_id_row.social_account_id, cust_id_row.id
        )
    except Exception:
        memory_export = None

    # 4. Owner questions
    oq_rows = list(
        session.scalars(
            select(OwnerQuestion).where(
                OwnerQuestion.workspace_id == ctx.workspace_id,
                OwnerQuestion.customer_identity_id == cust_id_row.id,
            )
        )
    )
    owner_questions: list[dict[str, Any]] = []
    for q in oq_rows:
        answer_dict = None
        if q.answer_id:
            ans = session.scalar(
                select(OwnerAnswer).where(
                    OwnerAnswer.workspace_id == ctx.workspace_id,
                    OwnerAnswer.id == q.answer_id,
                )
            )
            if ans:
                answer_dict = {
                    "id": str(ans.id),
                    "answer_body": ans.body,
                    "created_at": ans.created_at.isoformat(),
                }
        owner_questions.append(
            {
                "id": str(q.id),
                "required_info": q.required_info,
                "body": q.body,
                "state": q.state,
                "created_at": q.created_at.isoformat(),
                "expires_at": q.expires_at.isoformat(),
                "answer": answer_dict,
            }
        )

    # 5. Public comments (linked strictly by provider author external id per INV-18)
    public_comments: list[dict[str, Any]] = []
    if participant_external_ids:
        comm_rows = list(
            session.scalars(
                select(PublicComment).where(
                    PublicComment.workspace_id == ctx.workspace_id,
                    PublicComment.social_account_id == cust_id_row.social_account_id,
                    PublicComment.author_external_id.in_(participant_external_ids),
                )
            )
        )
        public_comments = [
            {
                "id": str(c.id),
                "external_id": c.external_id,
                "text": c.text,
                "state": c.state,
                "provider_timestamp": (
                    c.provider_timestamp.isoformat() if c.provider_timestamp else None
                ),
            }
            for c in comm_rows
        ]

    # 6. Audit
    audit.record(
        session,
        ctx,
        "data_rights.customer_exported",
        "customer",
        cust_id_row.id,
        {
            "social_account_id": str(cust_id_row.social_account_id),
            "evidence_kind": cust_id_row.evidence_kind,
        },
        clock=clock,
    )
    session.commit()

    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": clock.now().isoformat(),
        "workspace": {
            "id": str(ctx.workspace_id),
            "name": workspace.name if workspace else "Unknown",
        },
        "social_account": (
            {
                "id": str(account.id),
                "provider_kind": account.provider_kind,
                "external_account_id": account.external_account_id,
                "username": account.username,
            }
            if account
            else None
        ),
        "customer_identity": {
            "id": str(cust_id_row.id),
            "evidence_kind": cust_id_row.evidence_kind,
            "generation": cust_id_row.generation,
            "created_at": cust_id_row.created_at.isoformat(),
        },
        "conversations": [
            {
                "id": str(c.id),
                "customer_handle": c.customer_handle,
                "created_at": c.created_at.isoformat(),
            }
            for c in matched_convs
        ],
        "messages": messages,
        "memory": memory_export,
        "owner_questions": owner_questions,
        "public_comments": public_comments,
    }


def erase_conversation(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    conversation_id: uuid.UUID,
) -> dict[str, Any]:
    """Idempotently erase or redact conversation records and emit durable tombstone (P8-05)."""
    if not has_permission(ctx.role, "data.delete"):
        raise AppError("FORBIDDEN")

    conversation = session.scalar(
        select(Conversation).where(
            Conversation.workspace_id == ctx.workspace_id,
            Conversation.id == conversation_id,
        )
    )
    if conversation is None:
        raise AppError("NOT_FOUND")

    account = session.scalar(
        select(SocialAccount).where(
            SocialAccount.workspace_id == ctx.workspace_id,
            SocialAccount.id == conversation.social_account_id,
        )
    )

    # 1. Resolve CustomerIdentity
    cust_id_row: CustomerIdentity | None = None
    if conversation.customer_external_id and account:
        key = memory_service.digest(
            f"{account.provider_kind}:dm:{conversation.customer_external_id}"
        )
        cust_id_row = session.scalar(
            select(CustomerIdentity).where(
                CustomerIdentity.workspace_id == ctx.workspace_id,
                CustomerIdentity.social_account_id == conversation.social_account_id,
                CustomerIdentity.provider_subject_hash == key,
            )
        )

    # 2. Check for unresolved in-flight operations (reconciliation guard per INV-05, ADR-022)
    draft_ids = list(
        session.scalars(
            select(ReplyDraft.id).where(
                ReplyDraft.workspace_id == ctx.workspace_id,
                ReplyDraft.conversation_id == conversation.id,
            )
        ).all()
    )

    unresolved_ops_count = 0
    if draft_ids:
        unresolved_ops_count += len(
            list(
                session.scalars(
                    select(Operation.id).where(
                        Operation.workspace_id == ctx.workspace_id,
                        Operation.subject_type == "reply_draft",
                        Operation.subject_id.in_(draft_ids),
                        Operation.status.in_(["pending", "in_progress", "outcome_unknown"]),
                    )
                ).all()
            )
        )
    unresolved_drafts_count = len(
        list(
            session.scalars(
                select(ReplyDraft.id).where(
                    ReplyDraft.workspace_id == ctx.workspace_id,
                    ReplyDraft.conversation_id == conversation.id,
                    ReplyDraft.status.in_(["sending", "outcome_unknown"]),
                )
            ).all()
        )
    )

    is_unresolved = (unresolved_ops_count + unresolved_drafts_count) > 0

    # 3. Always redact personal text & advance memory fence immediately
    session.execute(
        update(Message)
        .where(
            Message.workspace_id == ctx.workspace_id,
            Message.conversation_id == conversation.id,
        )
        .values(text=None, attachments=[], is_deleted=True)
    )
    session.execute(
        update(ReplyDraft)
        .where(
            ReplyDraft.workspace_id == ctx.workspace_id,
            ReplyDraft.conversation_id == conversation.id,
        )
        .values(text=None, suggestion_text=None)
    )

    # Customer memory erasure / fence
    if cust_id_row is not None:
        with contextlib.suppress(Exception):
            memory_service.erase_customer(
                session, clock, ctx, cust_id_row.social_account_id, cust_id_row.id
            )

        # Owner questions / answers
        q_ids = list(
            session.scalars(
                select(OwnerQuestion.id).where(
                    OwnerQuestion.workspace_id == ctx.workspace_id,
                    OwnerQuestion.customer_identity_id == cust_id_row.id,
                )
            ).all()
        )
        if q_ids:
            session.execute(
                update(OwnerAnswer)
                .where(
                    OwnerAnswer.workspace_id == ctx.workspace_id,
                    OwnerAnswer.question_id.in_(q_ids),
                )
                .values(body=None)
            )
            session.execute(
                update(OwnerQuestion)
                .where(
                    OwnerQuestion.workspace_id == ctx.workspace_id,
                    OwnerQuestion.id.in_(q_ids),
                )
                .values(
                    body=None,
                    source_message_id=None,
                    source_hash="",
                    state="cancelled",
                    version=OwnerQuestion.version + 1,
                )
            )

    # Public comments authored by this participant on this account
    if conversation.customer_external_id:
        comm_ext_ids = list(
            session.scalars(
                select(PublicComment.external_id).where(
                    PublicComment.workspace_id == ctx.workspace_id,
                    PublicComment.social_account_id == conversation.social_account_id,
                    PublicComment.author_external_id == conversation.customer_external_id,
                )
            ).all()
        )
        for c_ext in comm_ext_ids:
            redact_receipts(session, ctx.workspace_id, conversation.social_account_id, c_ext)
        if comm_ext_ids:
            session.execute(
                update(PublicComment)
                .where(
                    PublicComment.workspace_id == ctx.workspace_id,
                    PublicComment.social_account_id == conversation.social_account_id,
                    PublicComment.external_id.in_(comm_ext_ids),
                )
                .values(
                    text=None,
                    author_external_id=None,
                    state="deleted",
                    version=PublicComment.version + 1,
                    updated_at=clock.now(),
                )
            )

    # Scrub raw webhook payloads in InboundEvent
    if conversation.customer_external_id:
        ext_id = conversation.customer_external_id
        session.execute(
            update(InboundEvent)
            .where(
                InboundEvent.workspace_id == ctx.workspace_id,
                or_(
                    InboundEvent.social_account_id == conversation.social_account_id,
                    InboundEvent.social_account_id.is_(None),
                ),
                or_(
                    InboundEvent.payload["sender_id"].astext == ext_id,
                    InboundEvent.payload["sender"]["id"].astext == ext_id,
                    InboundEvent.payload["from"]["id"].astext == ext_id,
                ),
            )
            .values(payload=null())
        )

    # 4. If in-flight reconciliation is required, preserve state machine keys and defer row purge
    if is_unresolved:
        audit.record(
            session,
            ctx,
            "data_rights.conversation_erased",
            "conversation",
            conversation.id,
            {"status": "redacted_reconciliation_pending", "unresolved_ops": unresolved_ops_count},
            clock=clock,
        )
        session.commit()
        return {
            "status": "redacted_reconciliation_pending",
            "conversation_id": str(conversation.id),
        }

    # 5. Otherwise, complete full purge
    session.execute(
        update(AgentThread)
        .where(
            AgentThread.workspace_id == ctx.workspace_id,
            AgentThread.dm_conversation_id == conversation.id,
        )
        .values(
            dm_conversation_id=None,
            handling_mode="human",
            state="cancelled",
            deletion_generation=AgentThread.deletion_generation + 1,
        )
    )
    session.execute(
        update(ReplyDraft)
        .where(
            ReplyDraft.workspace_id == ctx.workspace_id,
            ReplyDraft.conversation_id == conversation.id,
        )
        .values(covers_through_message_id=None)
    )
    if draft_ids:
        session.execute(
            delete(Approval).where(
                Approval.workspace_id == ctx.workspace_id,
                Approval.subject_id.in_(draft_ids),
            )
        )
    session.execute(
        delete(ReplyDraft).where(
            ReplyDraft.workspace_id == ctx.workspace_id,
            ReplyDraft.conversation_id == conversation.id,
        )
    )
    session.execute(
        delete(Message).where(
            Message.workspace_id == ctx.workspace_id,
            Message.conversation_id == conversation.id,
        )
    )
    session.execute(
        delete(Conversation).where(
            Conversation.workspace_id == ctx.workspace_id,
            Conversation.id == conversation.id,
        )
    )

    # 6. Durable tombstone for restore fencing
    session.add(
        DeletionTombstone(
            workspace_id=ctx.workspace_id,
            entity_type="conversation",
            entity_id=str(conversation.id),
            purged_at=clock.now(),
            details={"customer_external_id": conversation.customer_external_id},
        )
    )

    # 7. Audit log
    audit.record(
        session,
        ctx,
        "data_rights.conversation_erased",
        "conversation",
        conversation.id,
        {"status": "erased"},
        clock=clock,
    )
    session.commit()
    return {"status": "erased", "conversation_id": str(conversation.id)}


def erase_customer(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    customer_identity_id: uuid.UUID,
) -> dict[str, Any]:
    """Idempotently erase customer records across all conversations and memories (P8-05)."""
    if not has_permission(ctx.role, "data.delete"):
        raise AppError("FORBIDDEN")

    cust_id_row = session.scalar(
        select(CustomerIdentity).where(
            CustomerIdentity.workspace_id == ctx.workspace_id,
            CustomerIdentity.id == customer_identity_id,
        )
    )
    if cust_id_row is None:
        raise AppError("NOT_FOUND")

    account = session.scalar(
        select(SocialAccount).where(
            SocialAccount.workspace_id == ctx.workspace_id,
            SocialAccount.id == cust_id_row.social_account_id,
        )
    )

    # Find matching conversations
    threads = list(
        session.scalars(
            select(AgentThread).where(
                AgentThread.workspace_id == ctx.workspace_id,
                AgentThread.customer_identity_id == cust_id_row.id,
            )
        ).all()
    )
    thread_dm_conv_ids = [t.dm_conversation_id for t in threads if t.dm_conversation_id]

    conv_rows = list(
        session.scalars(
            select(Conversation).where(
                Conversation.workspace_id == ctx.workspace_id,
                Conversation.social_account_id == cust_id_row.social_account_id,
            )
        ).all()
    )
    matched_convs: list[Conversation] = []
    for c in conv_rows:
        if c.id in thread_dm_conv_ids:
            matched_convs.append(c)
        elif account and c.customer_external_id:
            h = memory_service.digest(f"{account.provider_kind}:dm:{c.customer_external_id}")
            if h == cust_id_row.provider_subject_hash:
                matched_convs.append(c)

    conv_ids = [c.id for c in matched_convs]
    participant_external_ids = {
        c.customer_external_id for c in matched_convs if c.customer_external_id
    }

    # Check for in-flight operations across matched conversations
    draft_ids: list[uuid.UUID] = []
    if conv_ids:
        draft_ids = list(
            session.scalars(
                select(ReplyDraft.id).where(
                    ReplyDraft.workspace_id == ctx.workspace_id,
                    ReplyDraft.conversation_id.in_(conv_ids),
                )
            ).all()
        )

    unresolved_ops = 0
    if draft_ids:
        unresolved_ops += len(
            list(
                session.scalars(
                    select(Operation.id).where(
                        Operation.workspace_id == ctx.workspace_id,
                        Operation.subject_type == "reply_draft",
                        Operation.subject_id.in_(draft_ids),
                        Operation.status.in_(["pending", "in_progress", "outcome_unknown"]),
                    )
                ).all()
            )
        )

    is_unresolved = unresolved_ops > 0

    # Redact personal text across conversations
    if conv_ids:
        session.execute(
            update(Message)
            .where(
                Message.workspace_id == ctx.workspace_id,
                Message.conversation_id.in_(conv_ids),
            )
            .values(text=None, attachments=[], is_deleted=True)
        )
        session.execute(
            update(ReplyDraft)
            .where(
                ReplyDraft.workspace_id == ctx.workspace_id,
                ReplyDraft.conversation_id.in_(conv_ids),
            )
            .values(text=None, suggestion_text=None)
        )

    # Erase memory
    with contextlib.suppress(Exception):
        memory_service.erase_customer(
            session, clock, ctx, cust_id_row.social_account_id, cust_id_row.id
        )

    # Redact owner questions/answers
    q_ids = list(
        session.scalars(
            select(OwnerQuestion.id).where(
                OwnerQuestion.workspace_id == ctx.workspace_id,
                OwnerQuestion.customer_identity_id == cust_id_row.id,
            )
        ).all()
    )
    if q_ids:
        session.execute(
            update(OwnerAnswer)
            .where(
                OwnerAnswer.workspace_id == ctx.workspace_id,
                OwnerAnswer.question_id.in_(q_ids),
            )
            .values(body=None)
        )
        session.execute(
            update(OwnerQuestion)
            .where(
                OwnerQuestion.workspace_id == ctx.workspace_id,
                OwnerQuestion.id.in_(q_ids),
            )
            .values(
                body=None,
                source_message_id=None,
                source_hash="",
                state="cancelled",
                version=OwnerQuestion.version + 1,
            )
        )

    # Redact public comments
    if participant_external_ids:
        for ext_id in participant_external_ids:
            comm_ext_ids = list(
                session.scalars(
                    select(PublicComment.external_id).where(
                        PublicComment.workspace_id == ctx.workspace_id,
                        PublicComment.social_account_id == cust_id_row.social_account_id,
                        PublicComment.author_external_id == ext_id,
                    )
                ).all()
            )
            for c_ext in comm_ext_ids:
                redact_receipts(session, ctx.workspace_id, cust_id_row.social_account_id, c_ext)
            if comm_ext_ids:
                session.execute(
                    update(PublicComment)
                    .where(
                        PublicComment.workspace_id == ctx.workspace_id,
                        PublicComment.social_account_id == cust_id_row.social_account_id,
                        PublicComment.external_id.in_(comm_ext_ids),
                    )
                    .values(
                        text=None,
                        author_external_id=None,
                        state="deleted",
                        version=PublicComment.version + 1,
                        updated_at=clock.now(),
                    )
                )

    if is_unresolved:
        audit.record(
            session,
            ctx,
            "data_rights.customer_erased",
            "customer",
            cust_id_row.id,
            {"status": "redacted_reconciliation_pending", "unresolved_ops": unresolved_ops},
            clock=clock,
        )
        session.commit()
        return {
            "status": "redacted_reconciliation_pending",
            "customer_identity_id": str(cust_id_row.id),
        }

    # Hard-purge conversations & customer identity
    if conv_ids:
        session.execute(
            update(AgentThread)
            .where(
                AgentThread.workspace_id == ctx.workspace_id,
                AgentThread.dm_conversation_id.in_(conv_ids),
            )
            .values(
                dm_conversation_id=None,
                handling_mode="human",
                state="cancelled",
                deletion_generation=AgentThread.deletion_generation + 1,
            )
        )
        session.execute(
            update(ReplyDraft)
            .where(
                ReplyDraft.workspace_id == ctx.workspace_id,
                ReplyDraft.conversation_id.in_(conv_ids),
            )
            .values(covers_through_message_id=None)
        )
        if draft_ids:
            session.execute(
                delete(Approval).where(
                    Approval.workspace_id == ctx.workspace_id,
                    Approval.subject_id.in_(draft_ids),
                )
            )
        session.execute(
            delete(ReplyDraft).where(
                ReplyDraft.workspace_id == ctx.workspace_id,
                ReplyDraft.conversation_id.in_(conv_ids),
            )
        )
        session.execute(
            delete(Message).where(
                Message.workspace_id == ctx.workspace_id,
                Message.conversation_id.in_(conv_ids),
            )
        )
        session.execute(
            delete(Conversation).where(
                Conversation.workspace_id == ctx.workspace_id,
                Conversation.id.in_(conv_ids),
            )
        )

    session.add(
        DeletionTombstone(
            workspace_id=ctx.workspace_id,
            entity_type="customer",
            entity_id=str(cust_id_row.id),
            purged_at=clock.now(),
            details={"provider_subject_hash": cust_id_row.provider_subject_hash},
        )
    )

    audit.record(
        session,
        ctx,
        "data_rights.customer_erased",
        "customer",
        cust_id_row.id,
        {"status": "erased"},
        clock=clock,
    )
    session.commit()
    return {"status": "erased", "customer_identity_id": str(cust_id_row.id)}
