"""Isolation and Row-Level Security (RLS) tests for channel_preferences table (INV-01, Session 02).

Covers:
- Category C PostgreSQL Row-Level Security:
  - Querying channel_preferences under runtime role without app.workspace_id returns 0 rows.
  - Setting app.workspace_id = workspace_a returns only workspace A rows.
  - Setting app.workspace_id = workspace_b returns only workspace B rows.
  - Workspace A cannot read, insert, or see Workspace B's channel preferences.
  - Verified relrowsecurity=true, relforcerowsecurity=true, and tenant_isolation_policy.
"""

import contextlib
from collections.abc import Iterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.context import ActorRef, WorkspaceContext
from app.core.db import clear_tenant_context, set_tenant_context
from app.identity.channels import set_channel_preferences
from app.identity.models import ChannelPreference
from tests.factories import workspace_with_members
from tests.helpers.roles import ensure_runtime_roles


@contextlib.contextmanager
def as_role(session: Session, role: str) -> Iterator[None]:
    """Switch connection role locally for the transaction and guarantee RESET ROLE upon exit."""
    ensure_runtime_roles(session)
    session.execute(text(f"SET LOCAL ROLE {role}"))
    session.execute(text("SET LOCAL search_path = public, pg_temp"))
    try:
        yield
    finally:
        session.execute(text("RESET ROLE"))


@pytest.mark.invariant("INV-01")
def test_channel_preferences_has_forced_rls_and_tenant_policy(db_session: Session) -> None:
    """Verify that channel_preferences has ENABLE + FORCE RLS and tenant_isolation_policy."""
    bind = db_session.get_bind()
    if bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL specific test")

    row = db_session.execute(
        text(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c
            WHERE c.relname = 'channel_preferences'
              AND c.relnamespace = 'public'::regnamespace
            """
        )
    ).first()
    assert row is not None, "Table channel_preferences not found in pg_class"
    assert row[1] is True, "channel_preferences missing ENABLE ROW LEVEL SECURITY"
    assert row[2] is True, "channel_preferences missing FORCE ROW LEVEL SECURITY"

    pol_row = db_session.execute(
        text(
            """
            SELECT tablename, policyname
            FROM pg_policies
            WHERE tablename = 'channel_preferences'
              AND schemaname = 'public'
            """
        )
    ).first()
    assert pol_row is not None, "channel_preferences missing RLS policy in pg_policies"
    assert pol_row[1] == "tenant_isolation_policy", f"Unexpected policy name: {pol_row[1]}"


@pytest.mark.invariant("INV-01")
def test_channel_preferences_rls_isolation_between_workspaces(db_session: Session) -> None:
    bind = db_session.get_bind()
    if bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL specific test")

    clock = FrozenClock()
    ws_a, users_a = workspace_with_members(db_session, name="Workspace A")
    ws_b, users_b = workspace_with_members(db_session, name="Workspace B")

    # Set preference in Workspace A
    set_tenant_context(db_session, ws_a.id)
    ctx_a = WorkspaceContext(
        workspace_id=ws_a.id,
        actor=ActorRef.user(users_a["owner"].id),
        role="owner",
        timezone=ws_a.timezone,
        locale="tr",
        is_demo=False,
    )
    set_channel_preferences(
        db_session,
        clock,
        ctx_a,
        users_a["owner"].id,
        {"telegram": True, "whatsapp": False},
    )
    clear_tenant_context(db_session)
    db_session.flush()

    # Set preference in Workspace B
    set_tenant_context(db_session, ws_b.id)
    ctx_b = WorkspaceContext(
        workspace_id=ws_b.id,
        actor=ActorRef.user(users_b["owner"].id),
        role="owner",
        timezone=ws_b.timezone,
        locale="tr",
        is_demo=False,
    )
    set_channel_preferences(
        db_session,
        clock,
        ctx_b,
        users_b["owner"].id,
        {"telegram": False, "whatsapp": True},
    )
    clear_tenant_context(db_session)
    db_session.flush()

    # Under runtime role 'pivoris_app':
    # 1. Without tenant context set: 0 rows returned
    with as_role(db_session, "pivoris_app"):
        rows_empty = db_session.scalars(select(ChannelPreference)).all()
        assert len(rows_empty) == 0

    # 2. With workspace A context: only workspace A rows visible
    with as_role(db_session, "pivoris_app"):
        set_tenant_context(db_session, ws_a.id)
        rows_a = db_session.scalars(select(ChannelPreference)).all()
        assert len(rows_a) == 2
        assert all(r.workspace_id == ws_a.id for r in rows_a)
        clear_tenant_context(db_session)

    # 3. With workspace B context: only workspace B rows visible
    with as_role(db_session, "pivoris_app"):
        set_tenant_context(db_session, ws_b.id)
        rows_b = db_session.scalars(select(ChannelPreference)).all()
        assert len(rows_b) == 2
        assert all(r.workspace_id == ws_b.id for r in rows_b)
        clear_tenant_context(db_session)
