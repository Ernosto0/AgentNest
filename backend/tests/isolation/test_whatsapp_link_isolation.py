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

from __future__ import annotations

import contextlib
from collections.abc import Iterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.context import ActorRef, WorkspaceContext
from app.core.db import clear_tenant_context, set_tenant_context
from app.identity.channels import ChannelLinkService, generate_link_code, redeem_link_code
from app.identity.models import ChannelLink, ChannelLinkCode
from tests.factories import login, workspace_with_members
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
    code_a, _ = generate_link_code(db_session, clock, ctx_a, channel="whatsapp")
    clear_tenant_context(db_session)
    link_a = redeem_link_code(
        db_session,
        clock,
        channel="whatsapp",
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
    code_b, _ = generate_link_code(db_session, clock, ctx_b, channel="whatsapp")
    clear_tenant_context(db_session)
    link_b = redeem_link_code(
        db_session,
        clock,
        channel="whatsapp",
        channel_user_id="tg_user_b",
        channel_chat_id="tg_chat_b",
        raw_code=code_b,
    )

    link_a_id = link_a.id
    link_b_id = link_b.id

    bind = db_session.get_bind()
    if bind.dialect.name == "postgresql":
        # Under runtime application role:
        with as_role(db_session, "pivoris_app"):
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
    code_a, _ = generate_link_code(db_session, clock, ctx_a, channel="whatsapp")

    set_tenant_context(db_session, ws_b.id)
    ctx_b = WorkspaceContext(
        workspace_id=ws_b.id,
        actor=ActorRef.user(users_b["owner"].id),
        role="owner",
        timezone=ws_b.timezone,
        locale="tr",
        is_demo=False,
    )
    code_b, _ = generate_link_code(db_session, clock, ctx_b, channel="whatsapp")

    bind = db_session.get_bind()
    if bind.dialect.name == "postgresql":
        with as_role(db_session, "pivoris_app"):
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


def test_whatsapp_identity_supersedes_and_unlink_is_scoped(
    db_session: Session, clock: FrozenClock
) -> None:
    ws_a, users_a = workspace_with_members(db_session, name="WhatsApp A")
    ws_b, users_b = workspace_with_members(db_session, name="WhatsApp B")

    def code_for(ws, users):
        set_tenant_context(db_session, ws.id)
        ctx = WorkspaceContext(
            workspace_id=ws.id,
            actor=ActorRef.user(users["owner"].id),
            role="owner",
            timezone=ws.timezone,
            locale="tr",
            is_demo=False,
        )
        return generate_link_code(db_session, clock, ctx, channel="whatsapp")[0]

    code_a = code_for(ws_a, users_a)
    # Starting in B's context cannot redirect A's code: the server resolves its original owner.
    set_tenant_context(db_session, ws_b.id)
    link_a = redeem_link_code(
        db_session,
        clock,
        channel="whatsapp",
        channel_user_id="905550001111",
        channel_chat_id="905550001111",
        raw_code=code_a,
    )
    assert link_a.workspace_id == ws_a.id and link_a.user_id == users_a["owner"].id
    resolved = ChannelLinkService.resolve_channel_user(db_session, "whatsapp", "905550001111")
    assert resolved and resolved[1].id == ws_a.id

    code_b = code_for(ws_b, users_b)
    link_b = redeem_link_code(
        db_session,
        clock,
        channel="whatsapp",
        channel_user_id="905550001111",
        channel_chat_id="905550001111",
        raw_code=code_b,
    )
    db_session.refresh(link_a)
    assert link_a.status == "unlinked" and link_b.status == "active"
    resolved = ChannelLinkService.resolve_channel_user(db_session, "whatsapp", "905550001111")
    assert resolved and resolved[1].id == ws_b.id

    code_a2 = code_for(ws_a, users_a)
    link_a2 = redeem_link_code(
        db_session,
        clock,
        channel="whatsapp",
        channel_user_id="905550002222",
        channel_chat_id="905550002222",
        raw_code=code_a2,
    )
    ChannelLinkService.unlink_by_channel(db_session, clock, "whatsapp", "905550002222")
    assert link_a2.status == "unlinked"
    db_session.refresh(link_b)
    assert link_b.status == "active"


def test_global_whatsapp_dedup_runtime_grants(db_session: Session, clock: FrozenClock) -> None:
    # Explicit global ingress table: runtime inserts need no workspace context, only a hash.
    with as_role(db_session, "pivoris_app"):
        clear_tenant_context(db_session)
        db_session.execute(
            text(
                "INSERT INTO whatsapp_webhook_events (message_id, received_at, status) "
                "VALUES ('runtime-probe', :now, 'ignored')"
            ),
            {"now": clock.now()},
        )
        assert db_session.scalar(text("SELECT count(*) FROM whatsapp_webhook_events")) == 1


def test_whatsapp_foreign_link_api_returns_404(client, db_session: Session, clock: FrozenClock):
    ws_a, users_a = workspace_with_members(db_session, name="API A")
    ws_b, users_b = workspace_with_members(db_session, name="API B")
    ctx_a = WorkspaceContext(
        workspace_id=ws_a.id,
        actor=ActorRef.user(users_a["owner"].id),
        role="owner",
        timezone=ws_a.timezone,
        locale="tr",
        is_demo=False,
    )
    set_tenant_context(db_session, ws_a.id)
    code, _ = generate_link_code(db_session, clock, ctx_a, channel="whatsapp")
    link = redeem_link_code(
        db_session,
        clock,
        channel="whatsapp",
        channel_user_id="905550003333",
        channel_chat_id="905550003333",
        raw_code=code,
    )
    headers = login(client, users_b["owner"])
    assert client.get(f"/api/v1/workspaces/{ws_b.id}/channels/links", headers=headers).json() == []
    response = client.delete(
        f"/api/v1/workspaces/{ws_b.id}/channels/links/{link.id}",
        headers=headers,
    )
    assert response.status_code == 404
    response = client.post(
        f"/api/v1/workspaces/{ws_a.id}/channels/link-code",
        json={"channel": "whatsapp"},
        headers=headers,
    )
    assert response.status_code == 404
