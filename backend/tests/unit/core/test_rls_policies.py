"""Session 06 tests: Tenant policies and isolation verification (P8-03, ADR-025 §1.3).

Proves:
1. Complete Category C schema coverage: all 49 strictly tenant-scoped tables have
   FORCE ROW LEVEL SECURITY and tenant_isolation_policy defined.
2. Category A (global/identity) and Category B (bootstrap/hybrid) tables are not
   blocked by tenant RLS.
3. Fail-closed behavior under non-bypass runtime roles (agentnest_app, agentnest_worker):
   - Zero rows visible on tenant tables when app.workspace_id is unset.
   - Insert fails closed when app.workspace_id is unset.
   - Foreign tenant reads return 0 rows.
   - Foreign tenant writes fail closed (WITH CHECK violation).
   - Tenant row workspace_id cannot be altered.
4. Same-tenant CRUD operations succeed under matching tenant context.
5. verify_database_roles reports category_c_rls_verified=True and zero unprotected tables.
"""

import contextlib
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from app.agent.models import AccountAgent
from app.core.db import (
    CATEGORY_C_TABLES,
    set_tenant_context,
)
from app.identity.models import Workspace
from app.integrations.instagram.models import SocialAccount
from app.operations.backup_restore import (
    post_restore_reconcile,
    provision_database_roles,
    verify_database_roles,
)
from app.operations.models import Operation


def _create_test_workspace(session: Session, name: str = "RLS Tenant") -> Workspace:
    ws_id = uuid.uuid4()
    ws = Workspace(
        id=ws_id,
        name=name,
        slug=f"ws-{ws_id.hex[:8]}",
        business_category="retail",
        market="tr",
        default_locale="tr",
        timezone="Europe/Istanbul",
        currency="TRY",
        status="active",
    )
    session.add(ws)
    session.flush()
    return ws


@contextlib.contextmanager
def as_role(session: Session, role: str) -> Iterator[None]:
    """Switch connection role locally for the transaction and guarantee RESET ROLE upon exit."""
    session.execute(text(f"SET LOCAL ROLE {role}"))
    try:
        yield
    finally:
        session.execute(text("RESET ROLE"))


@pytest.mark.commits
def test_all_49_category_c_tables_have_forced_rls(session_factory: sessionmaker[Session]) -> None:
    """Every Category C table has relrowsecurity=true, relforcerowsecurity=true
    and tenant_isolation_policy.
    """
    with session_factory() as session:
        rows = session.execute(
            text(
                """
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'
                """
            )
        ).all()
        class_map = {r[0]: (bool(r[1]), bool(r[2])) for r in rows}

        pol_rows = session.execute(
            text(
                """
                SELECT tablename, policyname, cmd, qual, with_check
                FROM pg_policies
                WHERE schemaname = 'public'
                """
            )
        ).all()
        policies_by_table = {r[0]: r[1] for r in pol_rows}

        assert len(CATEGORY_C_TABLES) == 49, (
            f"Expected 49 Category C tables, got {len(CATEGORY_C_TABLES)}"
        )

        missing_rls = []
        missing_force = []
        missing_policy = []

        for tbl in CATEGORY_C_TABLES:
            assert tbl in class_map, f"Category C table {tbl!r} not found in database!"
            sec, force = class_map[tbl]
            if not sec:
                missing_rls.append(tbl)
            if not force:
                missing_force.append(tbl)
            if policies_by_table.get(tbl) != "tenant_isolation_policy":
                missing_policy.append(tbl)

        assert not missing_rls, f"Tables missing ENABLE ROW LEVEL SECURITY: {missing_rls}"
        assert not missing_force, f"Tables missing FORCE ROW LEVEL SECURITY: {missing_force}"
        assert not missing_policy, f"Tables missing tenant_isolation_policy: {missing_policy}"


@pytest.mark.commits
def test_category_a_and_b_tables_not_blocked_by_tenant_rls(
    session_factory: sessionmaker[Session],
) -> None:
    """Category A and B tables do NOT have tenant_isolation_policy so bootstrap/global
    paths work.
    """
    with session_factory() as session:
        pol_rows = session.execute(
            text("SELECT tablename FROM pg_policies WHERE schemaname = 'public'")
        ).all()
        tables_with_policy = {r[0] for r in pol_rows}

        category_a = {"alembic_version", "users", "sessions", "workspaces"}
        category_b = {
            "workspace_members",
            "invites",
            "oauth_states",
            "inbound_events",
            "audit_logs",
            "jobs",
        }

        for tbl in category_a:
            assert tbl not in tables_with_policy, (
                f"Category A table {tbl!r} should not have tenant RLS!"
            )
        for tbl in category_b:
            assert tbl not in tables_with_policy, (
                f"Category B table {tbl!r} should not have tenant RLS!"
            )


@pytest.mark.commits
def test_verify_database_roles_validates_category_c_rls(
    session_factory: sessionmaker[Session],
) -> None:
    """verify_database_roles passes with category_c_rls_verified=True and zero
    unprotected tables.
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
        assert report.category_c_rls_verified is True
        assert report.unprotected_tables == []


@pytest.mark.commits
def test_non_bypass_runtime_role_fail_closed_without_tenant_context(
    session_factory: sessionmaker[Session],
) -> None:
    """Under agentnest_app, reads return 0 rows and writes fail closed when app.workspace_id
    is unset.
    """
    with session_factory() as session:
        provision_database_roles(
            session,
            migrator_role="agentnest_migrator",
            runtime_roles=["agentnest_app", "agentnest_worker"],
        )
        ws = _create_test_workspace(session)
        ws_id = ws.id
        session.commit()

    with session_factory() as session, as_role(session, "agentnest_app"):
        # 1. Without tenant context: SELECT returns 0 rows
        count = session.scalar(text("SELECT count(*) FROM public.business_facts"))
        assert count == 0

        # 2. Without tenant context: INSERT raises an RLS policy violation
        with pytest.raises((ProgrammingError, DBAPIError)) as exc_info:
            session.execute(
                text(
                    """
                    INSERT INTO public.business_facts
                        (id, workspace_id, category, key, value, label,
                         status, criticality, value_type, current_version)
                    VALUES
                        (:id, :ws_id, 'pricing', 'pricing.test', '\"100\"'::jsonb,
                         '{}'::jsonb, 'verified', 'standard', 'text', 1)
                    """
                ),
                {"id": uuid.uuid4(), "ws_id": ws_id},
            )
        assert "row-level security" in str(exc_info.value).lower()
        session.rollback()


@pytest.mark.commits
def test_tenant_isolation_reads_and_writes(session_factory: sessionmaker[Session]) -> None:
    """Under agentnest_app, tenant rows are visible only when app.workspace_id matches."""
    with session_factory() as session:
        provision_database_roles(
            session,
            migrator_role="agentnest_migrator",
            runtime_roles=["agentnest_app", "agentnest_worker"],
        )
        ws1 = _create_test_workspace(session, "Tenant 1")
        ws2 = _create_test_workspace(session, "Tenant 2")
        ws1_id = ws1.id
        ws2_id = ws2.id
        session.commit()

    # Insert rows for Tenant 1 and Tenant 2 under their respective contexts
    with session_factory() as session, as_role(session, "agentnest_app"):
        set_tenant_context(session, ws1_id)
        fact1_id = uuid.uuid4()
        session.execute(
            text(
                """
                INSERT INTO public.business_facts
                    (id, workspace_id, category, key, value, label,
                     status, criticality, value_type, current_version)
                VALUES
                    (:id, :ws_id, 'hours', 'hours.mon', '\"09:00-18:00\"'::jsonb,
                     '{}'::jsonb, 'verified', 'standard', 'text', 1)
                """
            ),
            {"id": fact1_id, "ws_id": ws1_id},
        )
        session.commit()

    with session_factory() as session, as_role(session, "agentnest_app"):
        set_tenant_context(session, ws2_id)
        fact2_id = uuid.uuid4()
        session.execute(
            text(
                """
                INSERT INTO public.business_facts
                    (id, workspace_id, category, key, value, label,
                     status, criticality, value_type, current_version)
                VALUES
                    (:id, :ws_id, 'hours', 'hours.mon', '\"10:00-20:00\"'::jsonb,
                     '{}'::jsonb, 'verified', 'standard', 'text', 1)
                """
            ),
            {"id": fact2_id, "ws_id": ws2_id},
        )
        session.commit()

    # Query under ws1: only fact1 is visible, fact2 is hidden
    with session_factory() as session, as_role(session, "agentnest_app"):
        set_tenant_context(session, ws1_id)

        rows = session.execute(text("SELECT id, workspace_id FROM public.business_facts")).all()
        visible_ids = {r[0] for r in rows}
        assert fact1_id in visible_ids
        assert fact2_id not in visible_ids

        # Attempt to insert row for ws2 while context is ws1 -> MUST FAIL
        with pytest.raises((ProgrammingError, DBAPIError)) as exc_info:
            session.execute(
                text(
                    """
                    INSERT INTO public.business_facts
                        (id, workspace_id, category, key, value, label,
                         status, criticality, value_type, current_version)
                    VALUES
                        (:id, :ws_id, 'policy', 'policy.return', '\"30 days\"'::jsonb,
                         '{}'::jsonb, 'verified', 'standard', 'text', 1)
                    """
                ),
                {"id": uuid.uuid4(), "ws_id": ws2_id},
            )
        assert "row-level security" in str(exc_info.value).lower()
        session.rollback()

    # Query under ws2: only fact2 is visible, fact1 is hidden
    with session_factory() as session, as_role(session, "agentnest_app"):
        set_tenant_context(session, ws2_id)

        rows = session.execute(text("SELECT id, workspace_id FROM public.business_facts")).all()
        visible_ids = {r[0] for r in rows}
        assert fact2_id in visible_ids
        assert fact1_id not in visible_ids


@pytest.mark.commits
def test_cannot_modify_row_workspace_id(session_factory: sessionmaker[Session]) -> None:
    """Updating a row to change workspace_id violates the WITH CHECK policy."""
    with session_factory() as session:
        provision_database_roles(
            session,
            migrator_role="agentnest_migrator",
            runtime_roles=["agentnest_app", "agentnest_worker"],
        )
        ws1 = _create_test_workspace(session, "Tenant 1")
        ws2 = _create_test_workspace(session, "Tenant 2")
        ws1_id = ws1.id
        ws2_id = ws2.id
        session.commit()

    with session_factory() as session, as_role(session, "agentnest_app"):
        set_tenant_context(session, ws1_id)
        fact_id = uuid.uuid4()
        session.execute(
            text(
                """
                INSERT INTO public.business_facts
                    (id, workspace_id, category, key, value, label,
                     status, criticality, value_type, current_version)
                VALUES
                    (:id, :ws_id, 'location', 'location.address', '\"Istanbul\"'::jsonb,
                     '{}'::jsonb, 'verified', 'standard', 'text', 1)
                """
            ),
            {"id": fact_id, "ws_id": ws1_id},
        )
        session.commit()

    # Attempt to change workspace_id to ws2 while context is ws1
    with session_factory() as session, as_role(session, "agentnest_app"):
        set_tenant_context(session, ws1_id)

        with pytest.raises((ProgrammingError, DBAPIError)) as exc_info:
            session.execute(
                text("UPDATE public.business_facts SET workspace_id = :new_ws WHERE id = :id"),
                {"new_ws": ws2_id, "id": fact_id},
            )
        assert "row-level security" in str(exc_info.value).lower()
        session.rollback()


@pytest.mark.commits
def test_foreign_delete_is_noop(session_factory: sessionmaker[Session]) -> None:
    """A delete query specifying a foreign row id matches zero rows under RLS."""
    with session_factory() as session:
        provision_database_roles(
            session,
            migrator_role="agentnest_migrator",
            runtime_roles=["agentnest_app", "agentnest_worker"],
        )
        ws1 = _create_test_workspace(session, "Tenant 1")
        ws2 = _create_test_workspace(session, "Tenant 2")
        ws1_id = ws1.id
        ws2_id = ws2.id
        session.commit()

    with session_factory() as session, as_role(session, "agentnest_app"):
        set_tenant_context(session, ws2_id)
        fact_id = uuid.uuid4()
        session.execute(
            text(
                """
                INSERT INTO public.business_facts
                    (id, workspace_id, category, key, value, label,
                     status, criticality, value_type, current_version)
                VALUES
                    (:id, :ws_id, 'policy', 'policy.secret', '\"Secret Value\"'::jsonb,
                     '{}'::jsonb, 'verified', 'standard', 'text', 1)
                """
            ),
            {"id": fact_id, "ws_id": ws2_id},
        )
        session.commit()

    # Tenant 1 attempts to delete Tenant 2's row: executes without error but deletes 0 rows
    with session_factory() as session, as_role(session, "agentnest_app"):
        set_tenant_context(session, ws1_id)

        res = session.execute(
            text("DELETE FROM public.business_facts WHERE id = :id"),
            {"id": fact_id},
        )
        assert res.rowcount == 0
        session.commit()

    # Verify fact still exists under ws2
    with session_factory() as session, as_role(session, "agentnest_app"):
        set_tenant_context(session, ws2_id)

        row = session.scalar(
            text("SELECT id FROM public.business_facts WHERE id = :id"),
            {"id": fact_id},
        )
        assert row == fact_id


@pytest.mark.commits
def test_phase_7_5_and_inbox_models_isolation(session_factory: sessionmaker[Session]) -> None:
    """Phase 7.5 models (account_agents) and inbox models (conversations, messages) obey RLS."""
    now = datetime.now(UTC)
    with session_factory() as session:
        provision_database_roles(
            session,
            migrator_role="agentnest_migrator",
            runtime_roles=["agentnest_app", "agentnest_worker"],
        )
        ws1 = _create_test_workspace(session, "Tenant 1")
        ws2 = _create_test_workspace(session, "Tenant 2")
        ws1_id = ws1.id
        ws2_id = ws2.id
        session.commit()

    # Populate ws1 entities
    with session_factory() as session, as_role(session, "agentnest_app"):
        set_tenant_context(session, ws1_id)

        acc1_id = uuid.uuid4()
        session.execute(
            text(
                """
                INSERT INTO public.social_accounts
                    (id, workspace_id, provider_kind, external_account_id, username, status)
                VALUES
                    (:id, :ws_id, 'mock', 'ext-1', 'merchant1', 'connected')
                """
            ),
            {"id": acc1_id, "ws_id": ws1_id},
        )

        conv1_id = uuid.uuid4()
        session.execute(
            text(
                """
                INSERT INTO public.conversations
                    (id, workspace_id, social_account_id, customer_external_id,
                     customer_handle, handling_mode, attention)
                VALUES
                    (:id, :ws_id, :acc_id, 'cust-1', 'customer_one', 'automatic', 'none')
                """
            ),
            {"id": conv1_id, "ws_id": ws1_id, "acc_id": acc1_id},
        )

        msg1_id = uuid.uuid4()
        session.execute(
            text(
                """
                INSERT INTO public.messages
                    (id, workspace_id, conversation_id, social_account_id,
                     direction, sender_kind, provider_timestamp)
                VALUES
                    (:id, :ws_id, :conv_id, :acc_id, 'inbound', 'customer', :now)
                """
            ),
            {"id": msg1_id, "ws_id": ws1_id, "conv_id": conv1_id, "acc_id": acc1_id, "now": now},
        )
        session.commit()

    # Verify ws2 cannot see any of ws1's agents, accounts, conversations, or messages
    with session_factory() as session, as_role(session, "agentnest_app"):
        set_tenant_context(session, ws2_id)

        assert session.scalar(text("SELECT count(*) FROM public.social_accounts")) == 0
        assert session.scalar(text("SELECT count(*) FROM public.account_agents")) == 0
        assert session.scalar(text("SELECT count(*) FROM public.conversations")) == 0
        assert session.scalar(text("SELECT count(*) FROM public.messages")) == 0

    # Verify ws1 sees all of them (account_agent was automatically created by trigger)
    with session_factory() as session, as_role(session, "agentnest_app"):
        set_tenant_context(session, ws1_id)

        assert session.scalar(text("SELECT count(*) FROM public.social_accounts")) == 1
        assert session.scalar(text("SELECT count(*) FROM public.account_agents")) == 1
        assert session.scalar(text("SELECT count(*) FROM public.conversations")) == 1
        assert session.scalar(text("SELECT count(*) FROM public.messages")) == 1


@pytest.mark.commits
def test_post_restore_reconcile_under_forced_rls(session_factory: sessionmaker[Session]) -> None:
    """post_restore_reconcile successfully fences across workspaces with forced RLS enabled."""
    now = datetime.now(UTC)
    with session_factory() as session:
        provision_database_roles(
            session,
            migrator_role="agentnest_migrator",
            runtime_roles=["agentnest_app", "agentnest_worker"],
        )
        ws = _create_test_workspace(session, "Reconcile Tenant")
        ws_id = ws.id

        set_tenant_context(session, ws_id)
        acc_id = uuid.uuid4()
        acc = SocialAccount(
            id=acc_id,
            workspace_id=ws_id,
            provider_kind="mock",
            external_account_id="ext-rec",
            username="reconcile_merchant",
            status="connected",
        )
        session.add(acc)
        session.flush()

        agent = session.scalar(select(AccountAgent).where(AccountAgent.workspace_id == ws_id))
        assert agent is not None
        agent.controller_mode = "agent"
        agent.state = "active"

        op = Operation(
            workspace_id=ws_id,
            operation_type="publish_content",
            idempotency_key=f"op-{uuid.uuid4().hex[:8]}",
            social_account_id=acc_id,
            subject_type="content",
            subject_id=uuid.uuid4(),
            provider_kind="mock",
            status="in_progress",
            started_at=now - timedelta(minutes=10),
        )
        session.add(op)
        session.commit()

    # Run post_restore_reconcile
    with session_factory() as session:
        report = post_restore_reconcile(session, now)
        assert report.paused_account_agents >= 1
        assert report.fenced_operations >= 1
        session.commit()

    # Verify agent is paused and operation is outcome_unknown
    with session_factory() as session:
        set_tenant_context(session, ws_id)
        refreshed_agent = session.scalar(
            select(AccountAgent).where(AccountAgent.workspace_id == ws_id)
        )
        assert refreshed_agent is not None
        assert refreshed_agent.state == "paused"

        refreshed_op = session.scalar(select(Operation).where(Operation.workspace_id == ws_id))
        assert refreshed_op is not None
        assert refreshed_op.status == "outcome_unknown"
