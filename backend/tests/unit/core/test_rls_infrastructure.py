"""Phase 8 Session 05: RLS roles and transaction infrastructure tests (P8-03 foundations).

Covers:
- Database role separation (migrator, app, worker) and append-only privilege verification
- Transaction-local tenant context (app.workspace_id) GUC binding and fail-closed absence
- Reset on transaction commit / rollback and connection pool reuse without context bleeding
- Nested transaction / savepoint behavior
- Worker dispatch with automatic tenant context binding on JobContext.session_factory
- Narrow SECURITY DEFINER bootstrap functions (social account, invite, OAuth, periodic discovery)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.approvals.models import Approval
from app.commands.models import OwnerCommand
from app.core.clock import FrozenClock
from app.core.db import (
    clear_tenant_context,
    get_current_tenant_guc,
    set_tenant_context,
    tenant_session,
)
from app.core.security import hash_token
from app.identity.models import Invite, User, Workspace
from app.inbox.models import Conversation, Message, ReplyDraft
from app.integrations.instagram.models import OAuthState, SocialAccount
from app.jobs.queue import claim_one, enqueue
from app.jobs.registry import JobContext, job_handler
from app.jobs.worker import execute_job
from app.operations.backup_restore import (
    provision_database_roles,
    verify_database_roles,
)
from app.operations.models import Operation


def test_tenant_context_guc_binding_and_fail_closed(db_session: Session) -> None:
    """set_tenant_context sets app.workspace_id; absence or clear returns None (fail-closed)."""
    assert get_current_tenant_guc(db_session) is None

    ws_id = uuid.uuid4()
    set_tenant_context(db_session, ws_id)
    assert get_current_tenant_guc(db_session) == str(ws_id)

    clear_tenant_context(db_session)
    assert get_current_tenant_guc(db_session) is None


def test_tenant_context_invalid_uuid_rejected(db_session: Session) -> None:
    """Invalid workspace UUID strings are rejected fail-closed before SQL execution."""
    with pytest.raises(ValueError):
        set_tenant_context(db_session, "not-a-uuid")

    with pytest.raises(ValueError):
        set_tenant_context(db_session, "1; DROP TABLE users; --")

    assert get_current_tenant_guc(db_session) is None


@pytest.mark.commits
def test_tenant_context_resets_across_sessions_and_pool_reuse(
    session_factory: sessionmaker[Session],
) -> None:
    """A connection returned to the pool after commit/rollback does not leak tenant context."""
    ws1 = uuid.uuid4()
    ws2 = uuid.uuid4()

    # Session 1 binds ws1 and commits
    with session_factory() as s1:
        set_tenant_context(s1, ws1)
        assert get_current_tenant_guc(s1) == str(ws1)
        s1.commit()
        # In same session, new transaction re-applies ws1 via after_begin listener
        assert get_current_tenant_guc(s1) == str(ws1)

    # Session 2 (fresh from pool) has no context
    with session_factory() as s2:
        assert get_current_tenant_guc(s2) is None
        set_tenant_context(s2, ws2)
        assert get_current_tenant_guc(s2) == str(ws2)
        s2.rollback()
        assert get_current_tenant_guc(s2) == str(ws2)

    # Session 3 has no context
    with session_factory() as s3:
        assert get_current_tenant_guc(s3) is None


def test_tenant_context_nested_savepoints(db_session: Session) -> None:
    """Savepoints inherit app.workspace_id and preserve it on nested commit and rollback."""
    ws_id = uuid.uuid4()
    set_tenant_context(db_session, ws_id)
    assert get_current_tenant_guc(db_session) == str(ws_id)

    # Nested commit
    with db_session.begin_nested():
        assert get_current_tenant_guc(db_session) == str(ws_id)
    assert get_current_tenant_guc(db_session) == str(ws_id)

    # Nested rollback
    try:
        with db_session.begin_nested():
            assert get_current_tenant_guc(db_session) == str(ws_id)
            raise RuntimeError("simulated error inside savepoint")
    except RuntimeError:
        pass
    assert get_current_tenant_guc(db_session) == str(ws_id)


def test_tenant_session_context_manager(session_factory: sessionmaker[Session]) -> None:
    """tenant_session context manager automatically sets context and closes cleanly."""
    ws_id = uuid.uuid4()
    with tenant_session(ws_id, session_factory) as s:
        assert get_current_tenant_guc(s) == str(ws_id)

    with session_factory() as s2:
        assert get_current_tenant_guc(s2) is None


class DummyTenantJobPayload(BaseModel):
    check: bool = True


@pytest.mark.commits
def test_worker_dispatches_tenant_job_with_workspace_context(
    session_factory: sessionmaker[Session],
) -> None:
    """Worker execute_job binds job.workspace_id on ctx.session_factory for tenant jobs."""
    clock = FrozenClock()
    ws_id = uuid.uuid4()
    observed_tenant_gucs: list[str | None] = []

    @job_handler("test_tenant_dispatch_job", DummyTenantJobPayload, max_attempts=1)
    def handle_test_job(ctx: JobContext) -> None:
        with ctx.session_factory() as session:
            observed_tenant_gucs.append(get_current_tenant_guc(session))

    with session_factory() as session:
        ws = Workspace(
            id=ws_id,
            name="Test Tenant",
            slug=f"tenant-{ws_id.hex[:8]}",
            business_category="retail",
            market="tr",
            default_locale="tr",
            timezone="Europe/Istanbul",
            currency="TRY",
            status="active",
        )
        session.add(ws)
        session.flush()
        enqueue(
            session,
            "test_tenant_dispatch_job",
            DummyTenantJobPayload(check=True),
            workspace_id=ws_id,
            correlation_id=None,
            clock=clock,
        )
        session.commit()

    claimed_tenant_job = claim_one(session_factory, clock, "test-worker", lease_seconds=30.0)
    assert claimed_tenant_job is not None

    outcome = execute_job(session_factory, clock, claimed_tenant_job, lease_seconds=30.0)
    assert outcome == "succeeded"
    assert observed_tenant_gucs == [str(ws_id)]

    # Global job (workspace_id = None) opens sessions without tenant context
    observed_global_gucs: list[str | None] = []

    @job_handler("test_global_dispatch_job", DummyTenantJobPayload, max_attempts=1)
    def handle_global_job(ctx: JobContext) -> None:
        with ctx.session_factory() as session:
            observed_global_gucs.append(get_current_tenant_guc(session))

    with session_factory() as session:
        enqueue(
            session,
            "test_global_dispatch_job",
            DummyTenantJobPayload(check=True),
            workspace_id=None,
            correlation_id=None,
            clock=clock,
        )
        session.commit()

    claimed_global_job = claim_one(session_factory, clock, "test-worker", lease_seconds=30.0)
    assert claimed_global_job is not None

    outcome = execute_job(session_factory, clock, claimed_global_job, lease_seconds=30.0)
    assert outcome == "succeeded"
    assert observed_global_gucs == [None]


def test_narrow_bootstrap_functions(db_session: Session) -> None:
    """SECURITY DEFINER bootstrap functions resolve identifiers before tenant context exists."""
    now = datetime.now(UTC)
    ws_id = uuid.uuid4()
    ws = Workspace(
        id=ws_id,
        name="Test Tenant",
        slug=f"tenant-{ws_id.hex[:8]}",
        business_category="retail",
        market="tr",
        default_locale="tr",
        timezone="Europe/Istanbul",
        currency="TRY",
        status="active",
    )
    db_session.add(ws)
    db_session.flush()

    # 1. Social account bootstrap
    acc_id = uuid.uuid4()
    ext_id = f"ext-{acc_id.hex[:8]}"
    acc = SocialAccount(
        id=acc_id,
        workspace_id=ws_id,
        provider_kind="mock",
        external_account_id=ext_id,
        username="test_merchant",
        status="connected",
    )
    db_session.add(acc)

    # 2. Invite bootstrap
    inv_id = uuid.uuid4()
    inv_token = f"inv-{inv_id.hex}"
    inv_hash = hash_token(inv_token)
    inv = Invite(
        id=inv_id,
        workspace_id=ws_id,
        role="staff",
        token_hash=inv_hash,
        expires_at=now + timedelta(days=7),
    )
    db_session.add(inv)

    # 3. User & OAuth State bootstrap
    usr_id = uuid.uuid4()
    usr = User(
        id=usr_id,
        email=f"user-{usr_id.hex[:8]}@example.com",
        display_name="Test User",
        password_hash="argon2id$test",
    )
    db_session.add(usr)
    db_session.flush()

    oauth_id = uuid.uuid4()
    state_token = f"oauth-{oauth_id.hex}"
    state_hash = hash_token(state_token)
    oauth = OAuthState(
        id=oauth_id,
        workspace_id=ws_id,
        user_id=usr_id,
        state_hash=state_hash,
        purpose="connect",
        expires_at=now + timedelta(minutes=10),
    )
    db_session.add(oauth)

    # 4. Approvals discovery
    appr_id = uuid.uuid4()
    appr = Approval(
        id=appr_id,
        workspace_id=ws_id,
        kind="authorization",
        action="reply.send",
        subject_type="reply_draft",
        subject_id=uuid.uuid4(),
        subject_version=1,
        payload_hash="0" * 64,
        summary={},
        required_permission="approvals.decide",
        status="pending",
        requested_by_actor_type="agent",
        expires_at=now - timedelta(minutes=5),
    )
    db_session.add(appr)

    # 5. Conversations & ReplyDraft discovery
    conv_id = uuid.uuid4()
    conv = Conversation(
        id=conv_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        customer_external_id="cust-1",
        customer_handle="cust_user",
        last_inbound_at=now - timedelta(hours=25),  # messaging window closed (> 24h)
    )
    db_session.add(conv)

    msg_id = uuid.uuid4()
    msg = Message(
        id=msg_id,
        workspace_id=ws_id,
        conversation_id=conv_id,
        social_account_id=acc_id,
        direction="inbound",
        sender_kind="customer",
        provider_timestamp=now,
    )
    db_session.add(msg)

    draft_id = uuid.uuid4()
    draft = ReplyDraft(
        id=draft_id,
        workspace_id=ws_id,
        conversation_id=conv_id,
        covers_through_message_id=msg_id,
        source="ai",
        decision="approval_required",
        status="pending_approval",
        created_by_actor_type="agent",
    )
    db_session.add(draft)

    # 6. Owner command discovery
    cmd_id = uuid.uuid4()
    cmd = OwnerCommand(
        id=cmd_id,
        workspace_id=ws_id,
        user_id=usr_id,
        channel="web",
        client_request_id=f"req-{cmd_id.hex[:8]}",
        correlation_id=uuid.uuid4(),
        raw_text="show me report",
        status="needs_clarification",
        expires_at=now - timedelta(minutes=1),
    )
    db_session.add(cmd)

    # 7. Stuck operation discovery
    op_id = uuid.uuid4()
    op = Operation(
        id=op_id,
        workspace_id=ws_id,
        operation_type="publish_content",
        idempotency_key=f"op-{op_id.hex[:8]}",
        social_account_id=acc_id,
        subject_type="content",
        subject_id=uuid.uuid4(),
        provider_kind="mock",
        status="in_progress",
        started_at=now - timedelta(minutes=30),
        updated_at=now - timedelta(minutes=30),
    )
    db_session.add(op)
    # Flush to database so PostgreSQL functions see the rows
    db_session.flush()

    # Test resolve_social_account_by_external
    res_sa = db_session.execute(
        text(
            "SELECT id, workspace_id, status "
            "FROM public.resolve_social_account_by_external(:k, :ext)"
        ),
        {"k": "mock", "ext": ext_id},
    ).first()
    assert res_sa is not None
    assert res_sa.id == acc_id
    assert res_sa.workspace_id == ws_id

    # Test resolve_invite_by_token_hash
    res_inv = db_session.execute(
        text("SELECT id, workspace_id, role FROM public.resolve_invite_by_token_hash(:th)"),
        {"th": inv_hash},
    ).first()
    assert res_inv is not None
    assert res_inv.id == inv_id
    assert res_inv.workspace_id == ws_id
    assert res_inv.role == "staff"

    # Test resolve_oauth_state_by_hash
    res_oauth = db_session.execute(
        text("SELECT id, workspace_id, user_id FROM public.resolve_oauth_state_by_hash(:sh)"),
        {"sh": state_hash},
    ).first()
    assert res_oauth is not None
    assert res_oauth.id == oauth_id
    assert res_oauth.workspace_id == ws_id
    assert res_oauth.user_id == usr_id

    # Test discover_expired_approval_ids
    appr_rows = db_session.execute(
        text("SELECT id, workspace_id FROM public.discover_expired_approval_ids(:now, 100)"),
        {"now": now},
    ).all()
    assert any(r.id == appr_id and r.workspace_id == ws_id for r in appr_rows)

    # Test discover_expired_reply_draft_ids (24h cutoff)
    draft_rows = db_session.execute(
        text("SELECT id, workspace_id FROM public.discover_expired_reply_draft_ids(:cutoff, 100)"),
        {"cutoff": now - timedelta(hours=24)},
    ).all()
    assert any(r.id == draft_id and r.workspace_id == ws_id for r in draft_rows)

    # Test discover_expired_command_ids
    cmd_rows = db_session.execute(
        text("SELECT id, workspace_id FROM public.discover_expired_command_ids(:now, 100)"),
        {"now": now},
    ).all()
    assert any(r.id == cmd_id and r.workspace_id == ws_id for r in cmd_rows)

    # Test discover_stuck_operations
    op_rows = db_session.execute(
        text(
            "SELECT id, workspace_id, subject_type "
            "FROM public.discover_stuck_operations(:cutoff, 100)"
        ),
        {"cutoff": now - timedelta(minutes=15)},
    ).all()
    assert any(r.id == op_id and r.workspace_id == ws_id for r in op_rows)

    # Test discover_stuck_agent_sessions function exists and executes
    session_rows = db_session.execute(
        text("SELECT id, workspace_id FROM public.discover_stuck_agent_sessions(:cutoff, 100)"),
        {"cutoff": now - timedelta(minutes=15)},
    ).all()
    assert isinstance(session_rows, list)


@pytest.mark.commits
def test_provision_and_verify_database_roles(session_factory: sessionmaker[Session]) -> None:
    """provision_database_roles creates least-privilege non-bypass roles and revokes update/delete
    on append-only tables.
    """
    with session_factory() as session:
        provision_database_roles(
            session,
            migrator_role="agentnest_migrator",
            runtime_roles=["agentnest_app", "agentnest_worker"],
        )
        session.commit()

        report = verify_database_roles(
            session,
            migrator_role="agentnest_migrator",
            runtime_roles=("agentnest_app", "agentnest_worker"),
        )
        assert report.verified, f"Role verification failed: {report.errors}"
        assert report.migrator_exists
        assert "agentnest_app" in report.runtime_roles
        assert "agentnest_worker" in report.runtime_roles

        for role in ("agentnest_app", "agentnest_worker"):
            flags = report.role_flags[role]
            assert not flags["rolsuper"]
            assert not flags["rolcreatedb"]
            assert not flags["rolcreaterole"]
            assert not flags["rolbypassrls"]

            grants = report.append_only_grants[role]
            for tbl in ("audit_logs", "fact_versions"):
                assert grants[tbl]["SELECT"] is True
                assert grants[tbl]["INSERT"] is True
                assert grants[tbl]["UPDATE"] is False
                assert grants[tbl]["DELETE"] is False
