"""Database backup role verification and post-restore worker fencing & reconciliation (P8-02).

Implements the post-restore safety guarantees required by ``ADR-025`` §1.1 & §3.3,
``INV-05``, ``INV-06``, ``INV-07``, ``INV-12``, ``INV-17``, ``INV-18``, and
``security-and-privacy.md`` §9:

1. Verify (and optionally provision) separated migration vs runtime PostgreSQL roles
   (``agentnest_migrator`` vs ``agentnest_app`` / ``agentnest_worker`` with
   ``NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`` and ``REVOKE UPDATE, DELETE``
   on append-only ``audit_logs`` and ``fact_versions``).
2. Fence restored workers before they start:
   - Pause all ``account_agents`` (``state = 'paused'``) and revoke active
     ``agent_delegations`` (``revoked_at = now()``).
   - Transition any ``operations`` in ``in_progress`` to ``outcome_unknown``
     (``last_error_code = 'RESTORED_FROM_BACKUP_OUTCOME_UNKNOWN'``) and any
     ``reply_drafts`` in ``sending`` to ``outcome_unknown``, enqueuing
     ``reconcile_send`` / ``reconcile_publish`` so a restored worker never blindly
     repeats an ambiguous external call.
   - Hold any ``content_items`` stuck in ``publishing`` or past their ``scheduled_at``
     (``status = 'on_hold'``, ``hold_reason = 'RESTORED_FROM_BACKUP'``).
   - Cancel active ``agent_sessions`` / ``agent_threads``, abandon in-flight
     ``agent_steps``, cancel queued/running outbound execution jobs, and release stale
     worker leases on idempotent jobs.
   - Re-apply post-snapshot customer, conversation, social-account, and workspace
     deletion tombstones so erased personal data from an older backup snapshot is
     purged before the restored environment serves traffic.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from sqlalchemy import delete, null, or_, select, text, update
from sqlalchemy.orm import Session

import app.operations.jobs as _operations_jobs  # noqa: F401
from app.agent.models import (
    ACTIVE_RUN_STATES,
    AccountAgent,
    AgentAction,
    AgentDelegation,
    AgentSession,
    AgentStep,
    AgentThread,
)
from app.audit import service as audit
from app.comments.models import PublicComment
from app.comments.privacy import erase_account as erase_public_account
from app.comments.privacy import redact_receipts
from app.content.models import ContentItem
from app.core.clock import Clock, FrozenClock
from app.identity.models import Workspace
from app.inbox.models import Conversation, InboundEvent, Message, ReplyDraft
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.jobs.queue import cancel_queued, enqueue
from app.knowledge.models import ApprovedAnswer, FactReference
from app.memory.models import (
    CustomerIdentity,
    CustomerMemory,
    MemorySource,
    MemoryVersion,
    SummaryVersion,
)
from app.memory.service import digest, erase_account, erase_identity
from app.operations import conversation_deletion
from app.operations.models import Operation
from app.operations.payloads import ReconcilePublishPayload, ReconcileSendPayload
from app.owner_requests.models import OwnerAnswer, OwnerQuestion

RESTORED_OUTCOME_UNKNOWN_CODE = "RESTORED_FROM_BACKUP_OUTCOME_UNKNOWN"
RESTORED_FENCED_CODE = "RESTORED_FROM_BACKUP_FENCED"
RESTORED_HOLD_REASON = "RESTORED_FROM_BACKUP"

OUTBOUND_FENCED_JOB_TYPES = (
    "send_reply",
    "publish_content",
    "agent_wake",
    "agent_continue",
    "agent_wake_due",
)
APPEND_ONLY_TABLES = ("audit_logs", "fact_versions")
REQUIRED_CORE_TABLES = (
    "alembic_version",
    "workspaces",
    "users",
    "social_accounts",
    "conversations",
    "messages",
    "reply_drafts",
    "operations",
    "audit_logs",
    "fact_versions",
    "account_agents",
    "agent_delegations",
)

_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _validate_identifier(identifier: str) -> str:
    cleaned = identifier.strip()
    if not _IDENTIFIER_RE.match(cleaned):
        raise ValueError(f"Unsafe SQL identifier: {identifier!r}")
    return cleaned


def _rowcount(result: object) -> int:
    return int(getattr(result, "rowcount", 0) or 0)


class CustomerTombstone(BaseModel):
    """Post-snapshot erasure record for a customer or conversation."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    workspace_id: uuid.UUID
    social_account_id: uuid.UUID | None = None
    customer_external_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("customer_external_id", "external_customer_id"),
    )
    customer_identity_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    erased_at: datetime | None = None
    reason: str | None = None

    @property
    def external_customer_id(self) -> str | None:
        return self.customer_external_id


class AccountTombstone(BaseModel):
    """Post-snapshot erasure record for a disconnected social account."""

    model_config = ConfigDict(extra="ignore")

    workspace_id: uuid.UUID
    social_account_id: uuid.UUID
    erased_at: datetime | None = None


class ConversationTombstone(BaseModel):
    """Post-snapshot erasure record for a conversation."""

    model_config = ConfigDict(extra="ignore")

    workspace_id: uuid.UUID
    conversation_id: uuid.UUID
    erased_at: datetime | None = None


class TombstoneManifest(BaseModel):
    """External or exported manifest of deletions that occurred after a backup snapshot."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    schema_version: str = "1.0"
    generated_at: datetime | None = None
    workspaces: list[uuid.UUID] = Field(default_factory=list)
    social_accounts: list[AccountTombstone] = Field(
        default_factory=list,
        validation_alias=AliasChoices("social_accounts", "accounts"),
    )
    conversations: list[ConversationTombstone] = Field(default_factory=list)
    customers: list[CustomerTombstone] = Field(default_factory=list)

    @property
    def accounts(self) -> list[AccountTombstone]:
        return self.social_accounts

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TombstoneManifest:
        return cls.model_validate(payload)


def load_tombstone_manifest(path: Path) -> TombstoneManifest:
    """Load and validate a JSON tombstone manifest from disk."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("Tombstone manifest root must be a JSON object.")
    return TombstoneManifest.model_validate(raw)


class RoleVerificationReport(BaseModel):
    """Verification report for separated migration and runtime PostgreSQL roles."""

    migrator_role: str
    migrator_exists: bool
    runtime_roles: list[str]
    table_count: int
    non_owned_tables: list[str]
    role_flags: dict[str, dict[str, bool]]
    append_only_grants: dict[str, dict[str, dict[str, bool]]]
    passed: bool
    problems: list[str]

    @property
    def verified(self) -> bool:
        return self.passed

    @property
    def errors(self) -> list[str]:
        return self.problems

    def to_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["verified"] = self.passed
        data["errors"] = list(self.problems)
        return data


class PostRestoreReconcileReport(BaseModel):
    """Summary counts from post-restore worker fencing and tombstone reconciliation."""

    reconciled_at: datetime
    paused_account_agents: int
    revoked_agent_delegations: int
    fenced_operations: int
    fenced_reply_drafts: int
    held_content_items: int
    fenced_agent_actions: int
    cancelled_agent_sessions: int
    abandoned_agent_steps: int
    cancelled_agent_threads: int
    cancelled_outbound_jobs: int
    released_running_jobs: int
    enqueued_reconcile_jobs: int
    reapplied_customer_tombstones: int
    reapplied_conversation_tombstones: int
    reapplied_account_tombstones: int
    reapplied_workspace_tombstones: int

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def provision_database_roles(
    session: Session,
    *,
    migrator_role: str = "agentnest_migrator",
    runtime_roles: Sequence[str] | None = None,
    app_role: str | None = None,
    worker_role: str | None = None,
    migrator_password: str | None = None,
    runtime_password: str | None = None,
    app_password: str | None = None,
    worker_password: str | None = None,
) -> None:
    """Create/update separated migration and runtime roles and enforce append-only grants."""
    mig = _validate_identifier(migrator_role)
    if runtime_roles is not None:
        resolved_roles = list(dict.fromkeys(runtime_roles))
    elif app_role or worker_role:
        resolved_roles = list(dict.fromkeys([r for r in (app_role, worker_role) if r is not None]))
    else:
        resolved_roles = ["agentnest_app", "agentnest_worker"]
    r_roles = [_validate_identifier(r) for r in resolved_roles]
    effective_runtime_pw = runtime_password or app_password or worker_password

    mig_exists = session.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": mig})
    if not mig_exists:
        if migrator_password:
            session.execute(
                text("SELECT set_config('agentnest.tmp_role_pw', :pw, true)"),
                {"pw": migrator_password},
            )
            session.execute(
                text(
                    f"""
                    DO $$
                    BEGIN
                        EXECUTE format(
                            'CREATE ROLE %I LOGIN PASSWORD %L '
                            'NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS',
                            '{mig}',
                            current_setting('agentnest.tmp_role_pw')
                        );
                    END
                    $$;
                    """
                )
            )
        else:
            session.execute(
                text(f"CREATE ROLE {mig} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS")
            )

    for role in r_roles:
        exists = session.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role})
        if not exists:
            if effective_runtime_pw:
                session.execute(
                    text("SELECT set_config('agentnest.tmp_role_pw', :pw, true)"),
                    {"pw": effective_runtime_pw},
                )
                session.execute(
                    text(
                        f"""
                        DO $$
                        BEGIN
                            EXECUTE format(
                                'CREATE ROLE %I LOGIN PASSWORD %L '
                                'NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS',
                                '{role}',
                                current_setting('agentnest.tmp_role_pw')
                            );
                        END
                        $$;
                        """
                    )
                )
            else:
                session.execute(
                    text(
                        f"CREATE ROLE {role} NOLOGIN "
                        "NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"
                    )
                )
        else:
            if effective_runtime_pw:
                session.execute(
                    text("SELECT set_config('agentnest.tmp_role_pw', :pw, true)"),
                    {"pw": effective_runtime_pw},
                )
                session.execute(
                    text(
                        f"""
                        DO $$
                        BEGIN
                            EXECUTE format(
                                'ALTER ROLE %I LOGIN PASSWORD %L '
                                'NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS',
                                '{role}',
                                current_setting('agentnest.tmp_role_pw')
                            );
                        END
                        $$;
                        """
                    )
                )
            else:
                session.execute(
                    text(f"ALTER ROLE {role} NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS")
                )

    session.execute(text(f"GRANT USAGE, CREATE ON SCHEMA public TO {mig}"))
    tables = [
        row[0]
        for row in session.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
        ).all()
    ]
    for tbl in tables:
        safe_tbl = _validate_identifier(tbl)
        session.execute(text(f"ALTER TABLE public.{safe_tbl} OWNER TO {mig}"))

    sequences = [
        row[0]
        for row in session.execute(
            text(
                "SELECT sequencename FROM pg_sequences "
                "WHERE schemaname = 'public' ORDER BY sequencename"
            )
        ).all()
    ]
    for seq in sequences:
        safe_seq = _validate_identifier(seq)
        session.execute(text(f"ALTER SEQUENCE public.{safe_seq} OWNER TO {mig}"))

    for role in r_roles:
        session.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
        session.execute(
            text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}")
        )
        session.execute(text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}"))
        session.execute(text(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {role}"))
        session.execute(
            text(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {mig} IN SCHEMA public "
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}"
            )
        )
        session.execute(
            text(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {mig} IN SCHEMA public "
                f"GRANT USAGE, SELECT ON SEQUENCES TO {role}"
            )
        )
        session.execute(
            text(
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {mig} IN SCHEMA public "
                f"GRANT EXECUTE ON FUNCTIONS TO {role}"
            )
        )

    # Enforce append-only restrictions on audit_logs and fact_versions (ADR-025 §1.1, INV-12/17).
    for append_table in APPEND_ONLY_TABLES:
        if append_table in tables:
            session.execute(
                text(f"REVOKE UPDATE, DELETE, TRUNCATE ON TABLE public.{append_table} FROM PUBLIC")
            )
            for role in r_roles:
                session.execute(
                    text(
                        f"REVOKE UPDATE, DELETE, TRUNCATE ON TABLE public.{append_table} "
                        f"FROM {role}"
                    )
                )
                session.execute(
                    text(f"GRANT SELECT, INSERT ON TABLE public.{append_table} TO {role}")
                )


def verify_database_roles(
    session: Session,
    *,
    migrator_role: str = "agentnest_migrator",
    runtime_roles: Sequence[str] = ("agentnest_app", "agentnest_worker"),
) -> RoleVerificationReport:
    """Verify table ownership, non-bypass runtime role flags, and append-only table grants."""
    mig = _validate_identifier(migrator_role)
    r_roles = [_validate_identifier(r) for r in runtime_roles]
    problems: list[str] = []

    mig_row = session.execute(
        text("SELECT rolname FROM pg_roles WHERE rolname = :r"),
        {"r": mig},
    ).first()
    migrator_exists = mig_row is not None
    if not migrator_exists:
        problems.append(f"Migration owner role {mig!r} does not exist.")

    table_rows = session.execute(
        text(
            "SELECT tablename, tableowner FROM pg_tables "
            "WHERE schemaname = 'public' ORDER BY tablename"
        )
    ).all()
    existing_tables = {row[0] for row in table_rows}
    for req_tbl in REQUIRED_CORE_TABLES:
        if req_tbl not in existing_tables:
            problems.append(f"Required table {req_tbl!r} is missing from public schema.")

    non_owned_tables = [row[0] for row in table_rows if row[1] != mig]
    if non_owned_tables:
        problems.append(f"Tables in public schema not owned by {mig!r}: {sorted(non_owned_tables)}")

    role_flags: dict[str, dict[str, bool]] = {}
    append_only_grants: dict[str, dict[str, dict[str, bool]]] = {}

    for role in r_roles:
        r_row = session.execute(
            text(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls "
                "FROM pg_roles WHERE rolname = :r"
            ),
            {"r": role},
        ).first()
        if r_row is None:
            problems.append(f"Runtime role {role!r} does not exist.")
            continue
        flags = {
            "rolsuper": bool(r_row[0]),
            "rolcreatedb": bool(r_row[1]),
            "rolcreaterole": bool(r_row[2]),
            "rolbypassrls": bool(r_row[3]),
        }
        role_flags[role] = flags
        for flag_name, flag_val in flags.items():
            if flag_val:
                problems.append(f"Runtime role {role!r} must not have {flag_name}=true.")

        append_only_grants[role] = {}
        for tbl in APPEND_ONLY_TABLES:
            if tbl not in existing_tables:
                continue
            privs: dict[str, bool] = {}
            for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                has_priv = bool(
                    session.scalar(
                        text("SELECT has_table_privilege(:r, :t, :p)"),
                        {"r": role, "t": f"public.{tbl}", "p": priv},
                    )
                )
                privs[priv] = has_priv
            append_only_grants[role][tbl] = privs
            if not privs["SELECT"] or not privs["INSERT"]:
                problems.append(f"Runtime role {role!r} must have SELECT and INSERT on {tbl!r}.")
            if privs["UPDATE"] or privs["DELETE"]:
                problems.append(
                    f"Runtime role {role!r} must NOT have UPDATE or DELETE on append-only "
                    f"table {tbl!r} (found UPDATE={privs['UPDATE']}, DELETE={privs['DELETE']})."
                )

    return RoleVerificationReport(
        migrator_role=mig,
        migrator_exists=migrator_exists,
        runtime_roles=r_roles,
        table_count=len(table_rows),
        non_owned_tables=non_owned_tables,
        role_flags=role_flags,
        append_only_grants=append_only_grants,
        passed=len(problems) == 0,
        problems=problems,
    )


def _delete_conversations_and_messages(
    session: Session,
    clock: Clock,
    workspace_id: uuid.UUID,
    conversation_ids: Sequence[uuid.UUID],
) -> int:
    """Delete specified conversations and their messages/drafts after scrubbing references."""
    if not conversation_ids:
        return 0

    for conv_id in conversation_ids:
        cancel_queued(session, f"draft_reply:{conv_id}", clock)
        cancel_queued(session, f"draft_reply:{conv_id}:requested", clock)

    # Check if any conversation has an unresolved send_reply operation (INV-05).
    # Note: post_restore_reconcile fences in_progress -> outcome_unknown first; if a tombstone
    # targets an erased customer, we also cancel any pending/outcome_unknown send for that erased
    # conversation so no reconciliation re-exposes erased customer data, and scrub all bodies.
    draft_ids_stmt = select(ReplyDraft.id).where(
        ReplyDraft.workspace_id == workspace_id,
        ReplyDraft.conversation_id.in_(conversation_ids),
    )
    draft_id_list = list(session.scalars(draft_ids_stmt).all())
    message_ids_stmt = select(Message.id).where(
        Message.workspace_id == workspace_id,
        Message.conversation_id.in_(conversation_ids),
    )
    message_id_list = list(session.scalars(message_ids_stmt).all())

    if message_id_list:
        session.execute(
            update(MemorySource)
            .where(
                MemorySource.workspace_id == workspace_id,
                MemorySource.message_id.in_(message_id_list),
            )
            .values(message_id=None, removed=True)
        )
        session.execute(
            update(OwnerQuestion)
            .where(
                OwnerQuestion.workspace_id == workspace_id,
                OwnerQuestion.source_message_id.in_(message_id_list),
            )
            .values(body=None, source_message_id=None, source_hash="", state="cancelled")
        )
        session.execute(
            update(ApprovedAnswer)
            .where(
                ApprovedAnswer.workspace_id == workspace_id,
                ApprovedAnswer.created_from_message_id.in_(message_id_list),
            )
            .values(created_from_message_id=None)
        )

    if draft_id_list:
        session.execute(
            delete(FactReference).where(
                FactReference.workspace_id == workspace_id,
                FactReference.referrer_type == "reply_draft",
                FactReference.referrer_id.in_(draft_id_list),
            )
        )
        session.execute(
            update(Message)
            .where(
                Message.workspace_id == workspace_id,
                Message.reply_draft_id.in_(draft_id_list),
            )
            .values(reply_draft_id=None)
        )
        session.execute(
            update(ReplyDraft)
            .where(
                ReplyDraft.workspace_id == workspace_id,
                ReplyDraft.superseded_by_id.in_(draft_id_list),
            )
            .values(superseded_by_id=None)
        )
        session.execute(
            update(ReplyDraft)
            .where(
                ReplyDraft.workspace_id == workspace_id,
                ReplyDraft.id.in_(draft_id_list),
            )
            .values(covers_through_message_id=None)
        )

    session.execute(
        update(AgentThread)
        .where(
            AgentThread.workspace_id == workspace_id,
            AgentThread.dm_conversation_id.in_(conversation_ids),
        )
        .values(
            dm_conversation_id=None,
            handling_mode="human",
            state="cancelled",
            deletion_generation=AgentThread.deletion_generation + 1,
        )
    )

    session.execute(
        delete(ReplyDraft).where(
            ReplyDraft.workspace_id == workspace_id,
            ReplyDraft.conversation_id.in_(conversation_ids),
        )
    )
    session.execute(
        delete(Message).where(
            Message.workspace_id == workspace_id,
            Message.conversation_id.in_(conversation_ids),
        )
    )
    res = session.execute(
        delete(Conversation).where(
            Conversation.workspace_id == workspace_id,
            Conversation.id.in_(conversation_ids),
        )
    )
    return _rowcount(res)


def _apply_customer_tombstone(session: Session, clock: Clock, tombstone: CustomerTombstone) -> int:
    """Re-apply a post-snapshot customer erasure across memory, questions, comments, and DMs."""
    ws_id = tombstone.workspace_id
    now = clock.now()

    conv_stmt = select(Conversation).where(Conversation.workspace_id == ws_id)
    if tombstone.social_account_id is not None:
        conv_stmt = conv_stmt.where(Conversation.social_account_id == tombstone.social_account_id)
    if tombstone.conversation_id is not None and tombstone.customer_external_id:
        conv_stmt = conv_stmt.where(
            or_(
                Conversation.id == tombstone.conversation_id,
                Conversation.customer_external_id == tombstone.customer_external_id,
            )
        )
    elif tombstone.conversation_id is not None:
        conv_stmt = conv_stmt.where(Conversation.id == tombstone.conversation_id)
    elif tombstone.customer_external_id:
        conv_stmt = conv_stmt.where(
            Conversation.customer_external_id == tombstone.customer_external_id
        )
    else:
        conv_stmt = conv_stmt.where(text("false"))

    conversations = list(session.scalars(conv_stmt).all())
    conv_ids = [c.id for c in conversations]
    account_ids = {c.social_account_id for c in conversations} | (
        {tombstone.social_account_id} if tombstone.social_account_id else set()
    )
    ext_ids = {c.customer_external_id for c in conversations if c.customer_external_id} | (
        {tombstone.customer_external_id} if tombstone.customer_external_id else set()
    )

    # Resolve CustomerIdentity rows by explicit ID or provider_subject_hash.
    identity_hashes: set[str] = set()
    for acc_id in account_ids:
        acc = session.get(SocialAccount, acc_id)
        if acc is not None:
            for ext_id in ext_ids:
                identity_hashes.add(digest(f"{acc.provider_kind}:dm:{ext_id}"))

    id_conditions = []
    if tombstone.customer_identity_id is not None:
        id_conditions.append(CustomerIdentity.id == tombstone.customer_identity_id)
    if identity_hashes:
        id_conditions.append(CustomerIdentity.provider_subject_hash.in_(identity_hashes))

    identities: list[CustomerIdentity] = []
    if id_conditions:
        identities = list(
            session.scalars(
                select(CustomerIdentity).where(
                    CustomerIdentity.workspace_id == ws_id,
                    or_(*id_conditions),
                )
            ).all()
        )

    for identity in identities:
        erase_identity(session, clock, identity)
        # Redact any owner questions/answers tied to this customer identity.
        q_ids = list(
            session.scalars(
                select(OwnerQuestion.id).where(
                    OwnerQuestion.workspace_id == ws_id,
                    OwnerQuestion.customer_identity_id == identity.id,
                )
            ).all()
        )
        if q_ids:
            session.execute(
                update(OwnerAnswer)
                .where(
                    OwnerAnswer.workspace_id == ws_id,
                    OwnerAnswer.question_id.in_(q_ids),
                )
                .values(body=None)
            )
            session.execute(
                update(OwnerQuestion)
                .where(
                    OwnerQuestion.workspace_id == ws_id,
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
        # Hard-delete memory bodies/versions/summaries while keeping SourceFence tombstones.
        session.execute(
            delete(MemorySource).where(
                MemorySource.workspace_id == ws_id,
                MemorySource.customer_identity_id == identity.id,
            )
        )
        session.execute(
            delete(MemoryVersion).where(
                MemoryVersion.workspace_id == ws_id,
                MemoryVersion.customer_identity_id == identity.id,
            )
        )
        session.execute(
            delete(CustomerMemory).where(
                CustomerMemory.workspace_id == ws_id,
                CustomerMemory.customer_identity_id == identity.id,
            )
        )
        session.execute(
            delete(SummaryVersion).where(
                SummaryVersion.workspace_id == ws_id,
                SummaryVersion.customer_identity_id == identity.id,
            )
        )

    # Redact any public comments authored by the erased customer external ID.
    for acc_id in account_ids:
        for ext_id in ext_ids:
            comment_ext_ids = list(
                session.scalars(
                    select(PublicComment.external_id).where(
                        PublicComment.workspace_id == ws_id,
                        PublicComment.social_account_id == acc_id,
                        PublicComment.author_external_id == ext_id,
                    )
                ).all()
            )
            for c_ext in comment_ext_ids:
                redact_receipts(session, ws_id, acc_id, c_ext)
            if comment_ext_ids:
                session.execute(
                    update(PublicComment)
                    .where(
                        PublicComment.workspace_id == ws_id,
                        PublicComment.social_account_id == acc_id,
                        PublicComment.author_external_id == ext_id,
                    )
                    .values(
                        text=None,
                        author_external_id=None,
                        state="deleted",
                        version=PublicComment.version + 1,
                        updated_at=now,
                    )
                )
            # Scrub raw webhook payloads for this participant.
            session.execute(
                update(InboundEvent)
                .where(
                    InboundEvent.workspace_id == ws_id,
                    or_(
                        InboundEvent.social_account_id == acc_id,
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

    deleted_convs = _delete_conversations_and_messages(session, clock, ws_id, conv_ids)
    return 1 if (deleted_convs > 0 or len(identities) > 0) else 0


def _load_db_tombstones(session: Session) -> TombstoneManifest:
    """Read tombstones from ``deletion_tombstones`` table if present (S10 forward hook)."""
    has_table = session.scalar(
        text(
            "SELECT 1 FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename = 'deletion_tombstones'"
        )
    )
    if not has_table:
        return TombstoneManifest()

    rows = session.execute(
        text("SELECT entity_type, entity_id, workspace_id FROM public.deletion_tombstones")
    ).all()
    manifest = TombstoneManifest()
    for entity_type, entity_id, workspace_id in rows:
        try:
            ws_uuid = uuid.UUID(str(workspace_id)) if workspace_id else None
            ent_uuid = uuid.UUID(str(entity_id)) if entity_id else None
        except ValueError:
            continue
        if entity_type == "workspace" and (ent_uuid or ws_uuid):
            manifest.workspaces.append(ent_uuid or ws_uuid)  # type: ignore[arg-type]
        elif entity_type == "social_account" and ws_uuid and ent_uuid:
            manifest.social_accounts.append(
                AccountTombstone(workspace_id=ws_uuid, social_account_id=ent_uuid)
            )
        elif entity_type == "conversation" and ws_uuid and ent_uuid:
            manifest.conversations.append(
                ConversationTombstone(workspace_id=ws_uuid, conversation_id=ent_uuid)
            )
        elif entity_type == "customer" and ws_uuid:
            if ent_uuid:
                manifest.customers.append(
                    CustomerTombstone(workspace_id=ws_uuid, customer_identity_id=ent_uuid)
                )
            elif entity_id:
                manifest.customers.append(
                    CustomerTombstone(workspace_id=ws_uuid, customer_external_id=str(entity_id))
                )
    return manifest


def post_restore_reconcile(
    session: Session,
    clock_or_now: Clock | datetime,
    *,
    tombstone_manifest: TombstoneManifest | Mapping[str, Any] | None = None,
) -> PostRestoreReconcileReport:
    """Fence outbound automation/operations and re-apply deletion tombstones after DB restore."""
    if isinstance(clock_or_now, datetime):
        dt = clock_or_now if clock_or_now.tzinfo is not None else clock_or_now.replace(tzinfo=UTC)
        clock: Clock = FrozenClock(dt)
    else:
        clock = clock_or_now
    now = clock.now()

    # 1. Pause all account_agents and revoke active agent_delegations (ADR-025 §3.3).
    active_agents = list(
        session.scalars(
            select(AccountAgent)
            .where(or_(AccountAgent.state == "active", AccountAgent.controller_mode == "agent"))
            .with_for_update()
        ).all()
    )
    paused_agents_count = 0
    for agent in active_agents:
        if agent.state != "paused":
            agent.state = "paused"
            agent.controller_epoch += 1
            agent.config_version += 1
            agent.updated_at = now
            paused_agents_count += 1

    revoked_res = session.execute(
        update(AgentDelegation).where(AgentDelegation.revoked_at.is_(None)).values(revoked_at=now)
    )
    revoked_delegations_count = _rowcount(revoked_res)

    # 2. Transition in_progress operations -> outcome_unknown and sending drafts -> outcome_unknown.
    in_progress_ops = list(
        session.scalars(
            select(Operation).where(Operation.status == "in_progress").with_for_update()
        ).all()
    )
    fenced_ops_count = 0
    enqueued_reconcile_count = 0
    for op in in_progress_ops:
        op.status = "outcome_unknown"
        op.last_error_code = RESTORED_OUTCOME_UNKNOWN_CODE
        op.updated_at = now
        fenced_ops_count += 1
        if op.operation_type == "send_reply":
            enqueue(
                session,
                "reconcile_send",
                ReconcileSendPayload(operation_id=op.id, round=1),
                workspace_id=op.workspace_id,
                correlation_id=op.correlation_id,
                dedup_key=f"reconcile_send:{op.id}:1",
                clock=clock,
            )
            enqueued_reconcile_count += 1
        elif op.operation_type == "publish_content":
            enqueue(
                session,
                "reconcile_publish",
                ReconcilePublishPayload(operation_id=op.id),
                workspace_id=op.workspace_id,
                correlation_id=op.correlation_id,
                dedup_key=f"reconcile_publish:{op.id}",
                clock=clock,
            )
            enqueued_reconcile_count += 1

    sending_drafts = list(
        session.scalars(
            select(ReplyDraft).where(ReplyDraft.status == "sending").with_for_update()
        ).all()
    )
    fenced_drafts_count = 0
    for draft in sending_drafts:
        draft.status = "outcome_unknown"
        draft.updated_at = now
        fenced_drafts_count += 1
        session.execute(
            update(Conversation)
            .where(
                Conversation.workspace_id == draft.workspace_id,
                Conversation.id == draft.conversation_id,
            )
            .values(attention="none", updated_at=now)
        )

    # Hold publishing or overdue scheduled content items (security-and-privacy.md §9).
    held_items_res = session.execute(
        update(ContentItem)
        .where(
            or_(
                ContentItem.status == "publishing",
                (
                    ContentItem.status.in_(("scheduled", "retry_scheduled"))
                    & ContentItem.scheduled_at.is_not(None)
                    & (ContentItem.scheduled_at <= now)
                ),
            )
        )
        .values(
            status="on_hold",
            hold_reason=RESTORED_HOLD_REASON,
            updated_at=now,
        )
    )
    held_items_count = _rowcount(held_items_res)

    # Fence in_progress / pending agent_actions.
    fenced_in_progress_actions = session.execute(
        update(AgentAction)
        .where(AgentAction.status == "in_progress")
        .values(
            status="outcome_unknown",
            outcome_code=RESTORED_OUTCOME_UNKNOWN_CODE,
            updated_at=now,
        )
    )
    fenced_pending_actions = session.execute(
        update(AgentAction)
        .where(AgentAction.status.in_(("proposed", "waiting_approval", "authorized", "queued")))
        .values(
            status="cancelled",
            outcome_code=RESTORED_HOLD_REASON,
            updated_at=now,
        )
    )
    fenced_actions_count = _rowcount(fenced_in_progress_actions) + _rowcount(fenced_pending_actions)

    # 3. Cancel active agent_sessions / agent_threads, abandon steps, and fence/release jobs.
    cancelled_sessions_res = session.execute(
        update(AgentSession)
        .where(AgentSession.status.in_(ACTIVE_RUN_STATES))
        .values(
            status="cancelled",
            outcome_code=RESTORED_HOLD_REASON,
            completed_at=now,
            updated_at=now,
        )
    )
    cancelled_sessions_count = _rowcount(cancelled_sessions_res)

    abandoned_steps_res = session.execute(
        update(AgentStep)
        .where(AgentStep.status.in_(("claimed", "model_pending", "model_done", "dispatched")))
        .values(
            status="abandoned",
            lease_expires_at=None,
            updated_at=now,
        )
    )
    abandoned_steps_count = _rowcount(abandoned_steps_res)

    cancelled_threads_res = session.execute(
        update(AgentThread)
        .where(AgentThread.state.not_in(("completed", "cancelled", "failed")))
        .values(
            state="cancelled",
            handling_mode="human",
            updated_at=now,
        )
    )
    cancelled_threads_count = _rowcount(cancelled_threads_res)

    cancelled_jobs_res = session.execute(
        update(Job)
        .where(
            Job.status.in_(("queued", "running")),
            Job.job_type.in_(OUTBOUND_FENCED_JOB_TYPES),
        )
        .values(
            status="cancelled",
            last_error_code=RESTORED_FENCED_CODE,
            locked_by=None,
            lease_expires_at=None,
            finished_at=now,
            updated_at=now,
        )
    )
    cancelled_outbound_jobs_count = _rowcount(cancelled_jobs_res)

    released_jobs_res = session.execute(
        update(Job)
        .where(Job.status == "running")
        .values(
            status="queued",
            locked_by=None,
            lease_expires_at=None,
            updated_at=now,
        )
    )
    released_running_jobs_count = _rowcount(released_jobs_res)

    # 4. Re-apply deletion tombstones (manifest + DB deletion_tombstones table if present).
    parsed_manifest = (
        tombstone_manifest
        if isinstance(tombstone_manifest, TombstoneManifest)
        else TombstoneManifest.model_validate(tombstone_manifest)
        if tombstone_manifest is not None
        else TombstoneManifest()
    )
    db_manifest = _load_db_tombstones(session)

    all_customers = [*db_manifest.customers, *parsed_manifest.customers]
    all_conversations = [*db_manifest.conversations, *parsed_manifest.conversations]
    all_accounts = [*db_manifest.social_accounts, *parsed_manifest.social_accounts]
    all_workspaces = list(dict.fromkeys([*db_manifest.workspaces, *parsed_manifest.workspaces]))

    reapplied_customers = 0
    for cust_ts in all_customers:
        reapplied_customers += _apply_customer_tombstone(session, clock, cust_ts)

    reapplied_conversations = 0
    for conv_ts in all_conversations:
        reapplied_conversations += _delete_conversations_and_messages(
            session, clock, conv_ts.workspace_id, [conv_ts.conversation_id]
        )

    reapplied_accounts = 0
    for acc_ts in all_accounts:
        acc = session.scalar(
            select(SocialAccount)
            .where(
                SocialAccount.workspace_id == acc_ts.workspace_id,
                SocialAccount.id == acc_ts.social_account_id,
            )
            .with_for_update()
        )
        if acc is not None:
            acc.status = "disconnected"
            acc.token_ciphertext = None
            acc.token_key_id = None
            acc.token_expires_at = None
            acc.updated_at = now
            erase_account(session, clock, acc.workspace_id, acc.id)
            erase_public_account(session, clock, acc.workspace_id, acc.id)
            conversation_deletion.wipe(session, clock, acc.workspace_id, acc.id)
            reapplied_accounts += 1

    reapplied_workspaces = 0
    for ws_id in all_workspaces:
        ws = session.get(Workspace, ws_id)
        if ws is not None:
            # Disconnect and wipe all accounts in the workspace first, then delete the workspace.
            ws_accounts = list(
                session.scalars(
                    select(SocialAccount).where(SocialAccount.workspace_id == ws_id)
                ).all()
            )
            for acc in ws_accounts:
                erase_account(session, clock, ws_id, acc.id)
                erase_public_account(session, clock, ws_id, acc.id)
                conversation_deletion.wipe(session, clock, ws_id, acc.id)
            session.delete(ws)
            reapplied_workspaces += 1

    report = PostRestoreReconcileReport(
        reconciled_at=now,
        paused_account_agents=paused_agents_count,
        revoked_agent_delegations=revoked_delegations_count,
        fenced_operations=fenced_ops_count,
        fenced_reply_drafts=fenced_drafts_count,
        held_content_items=held_items_count,
        fenced_agent_actions=fenced_actions_count,
        cancelled_agent_sessions=cancelled_sessions_count,
        abandoned_agent_steps=abandoned_steps_count,
        cancelled_agent_threads=cancelled_threads_count,
        cancelled_outbound_jobs=cancelled_outbound_jobs_count,
        released_running_jobs=released_running_jobs_count,
        enqueued_reconcile_jobs=enqueued_reconcile_count,
        reapplied_customer_tombstones=reapplied_customers,
        reapplied_conversation_tombstones=reapplied_conversations,
        reapplied_account_tombstones=reapplied_accounts,
        reapplied_workspace_tombstones=reapplied_workspaces,
    )

    audit.record(
        session,
        None,
        "system.post_restore_reconciled",
        "database",
        None,
        report.model_dump(mode="json", exclude={"reconciled_at"}),
        clock=clock,
    )
    return report
