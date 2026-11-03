"""Isolation and Row-Level Security (RLS) tests for owner channel tables (INV-01, P9-01).

Covers:
- Category C PostgreSQL Row-Level Security:
  - Querying channel_links under runtime role without app.workspace_id returns 0 rows.
  - Querying channel_link_codes under runtime role without app.workspace_id returns 0 rows.
  - Setting app.workspace_id = workspace_a returns only workspace A rows.
  - Setting app.workspace_id = workspace_b returns only workspace B rows.
  - Workspace A cannot read or see Workspace B's channel links or link codes.
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
from app.identity.channels import generate_link_code, redeem_link_code
from app.identity.models import ChannelLink, ChannelLinkCode
from tests.factories import workspace_with_members


@contextlib.contextmanager
def as_role(session: Session, role: str) -> Iterator[None]:
    """Switch connection role locally for the transaction and guarantee RESET ROLE upon exit."""
    session.execute(text(f"SET LOCAL ROLE {role}"))
    session.execute(text("SET LOCAL search_path = public, pg_temp"))
    try:
        yield
    finally:
        session.execute(text("RESET ROLE"))


@pytest.mark.invariant("INV-01")
def test_channel_tables_have_forced_rls_and_tenant_policy(db_session: Session) -> None:
    """Verify that both channel_links and channel_link_codes have ENABLE + FORCE RLS and policy."""
    bind = db_session.get_bind()
    if bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL specific test")

    rows = db_session.execute(
        text(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c
            WHERE c.relname IN ('channel_links', 'channel_link_codes')
              AND c.relnamespace = 'public'::regnamespace
            """
        )
    ).all()
    class_map = {r[0]: (bool(r[1]), bool(r[2])) for r in rows}

    for tbl in ("channel_links", "channel_link_codes"):
        assert tbl in class_map, f"Table {tbl} not found"
        sec, force = class_map[tbl]
        assert sec is True, f"{tbl} missing ENABLE ROW LEVEL SECURITY"
        assert force is True, f"{tbl} missing FORCE ROW LEVEL SECURITY"

    pol_rows = db_session.execute(
        text(
            """
            SELECT tablename, policyname
            FROM pg_policies
            WHERE tablename IN ('channel_links', 'channel_link_codes')
              AND schemaname = 'public'
            """
        )
    ).all()
    policy_map = {r[0]: r[1] for r in pol_rows}
    for tbl in ("channel_links", "channel_link_codes"):
        assert policy_map.get(tbl) == "tenant_isolation_policy", (
            f"{tbl} missing tenant_isolation_policy"
        )


@pytest.mark.invariant("INV-01")
def test_channel_links_rls_isolation_between_workspaces(db_session: Session) -> None:
    clock = FrozenClock()
    ws_a, users_a = workspace_with_members(db_session, name="Workspace A")
    ws_b, users_b = workspace_with_members(db_session, name="Workspace B")

    # Generate and redeem a link in Workspace A
    set_tenant_context(db_session, ws_a.id)
    ctx_a = WorkspaceContext(
        workspace_id=ws_a.id,
        actor=ActorRef.user(users_a["owner"].id),
        role="owner",
        timezone=ws_a.timezone,
        locale="tr",
        is_demo=False,
    )
    code_a, _ = generate_link_code(db_session, clock, ctx_a, channel="telegram")
    clear_tenant_context(db_session)
    link_a = redeem_link_code(
        db_session,
        clock,
        channel="telegram",
        channel_user_id="tg_user_a",
        channel_chat_id="tg_chat_a",
        raw_code=code_a,
    )

    # Generate and redeem a link in Workspace B
    set_tenant_context(db_session, ws_b.id)
    ctx_b = WorkspaceContext(
        workspace_id=ws_b.id,
        actor=ActorRef.user(users_b["owner"].id),
        role="owner",
        timezone=ws_b.timezone,
        locale="tr",
        is_demo=False,
    )
    code_b, _ = generate_link_code(db_session, clock, ctx_b, channel="telegram")
    clear_tenant_context(db_session)
    link_b = redeem_link_code(
        db_session,
        clock,
        channel="telegram",
        channel_user_id="tg_user_b",
        channel_chat_id="tg_chat_b",
        raw_code=code_b,
    )

    link_a_id = link_a.id
    link_b_id = link_b.id

    bind = db_session.get_bind()
    if bind.dialect.name == "postgresql":
        # Under runtime application role:
        with as_role(db_session, "agentnest_app"):
            # 1. Without setting app.workspace_id, tenant queries return 0 rows under RLS
            clear_tenant_context(db_session)
            db_session.expunge_all()
            links_no_tenant = db_session.scalars(select(ChannelLink)).all()
            codes_no_tenant = db_session.scalars(select(ChannelLinkCode)).all()
            assert len(links_no_tenant) == 0
            assert len(codes_no_tenant) == 0

            # 2. In Workspace A context: only Workspace A rows are visible
            set_tenant_context(db_session, ws_a.id)
            links_a = db_session.scalars(select(ChannelLink)).all()
            codes_a = db_session.scalars(select(ChannelLinkCode)).all()
            assert len(links_a) == 1
            assert links_a[0].id == link_a_id
            assert links_a[0].workspace_id == ws_a.id
            assert all(c.workspace_id == ws_a.id for c in codes_a)
            # Querying B's link under A returns None
            assert db_session.scalar(select(ChannelLink).where(ChannelLink.id == link_b_id)) is None

            # 3. In Workspace B context: only Workspace B rows are visible
            set_tenant_context(db_session, ws_b.id)
            links_b = db_session.scalars(select(ChannelLink)).all()
            codes_b = db_session.scalars(select(ChannelLinkCode)).all()
            assert len(links_b) == 1
            assert links_b[0].id == link_b_id
            assert links_b[0].workspace_id == ws_b.id
            assert all(c.workspace_id == ws_b.id for c in codes_b)
            # Querying A's link under B returns None
            assert db_session.scalar(select(ChannelLink).where(ChannelLink.id == link_a_id)) is None


@pytest.mark.invariant("INV-01")
def test_channel_link_codes_tenant_scoping(db_session: Session) -> None:
    clock = FrozenClock()
    ws_a, users_a = workspace_with_members(db_session, name="Workspace A")
    ws_b, users_b = workspace_with_members(db_session, name="Workspace B")

    set_tenant_context(db_session, ws_a.id)
    ctx_a = WorkspaceContext(
        workspace_id=ws_a.id,
        actor=ActorRef.user(users_a["owner"].id),
        role="owner",
        timezone=ws_a.timezone,
        locale="tr",
        is_demo=False,
    )
    code_a, _ = generate_link_code(db_session, clock, ctx_a, channel="telegram")

    set_tenant_context(db_session, ws_b.id)
    ctx_b = WorkspaceContext(
        workspace_id=ws_b.id,
        actor=ActorRef.user(users_b["owner"].id),
        role="owner",
        timezone=ws_b.timezone,
        locale="tr",
        is_demo=False,
    )
    code_b, _ = generate_link_code(db_session, clock, ctx_b, channel="telegram")

    bind = db_session.get_bind()
    if bind.dialect.name == "postgresql":
        with as_role(db_session, "agentnest_app"):
            # With A's tenant set:
            set_tenant_context(db_session, ws_a.id)
            visible_codes_a = db_session.scalars(select(ChannelLinkCode)).all()
            assert len(visible_codes_a) == 1
            assert visible_codes_a[0].workspace_id == ws_a.id

            # With B's tenant set:
            set_tenant_context(db_session, ws_b.id)
            visible_codes_b = db_session.scalars(select(ChannelLinkCode)).all()
            assert len(visible_codes_b) == 1
            assert visible_codes_b[0].workspace_id == ws_b.id

            # Without tenant set:
            clear_tenant_context(db_session)
            assert len(db_session.scalars(select(ChannelLinkCode)).all()) == 0
