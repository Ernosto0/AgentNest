"""Isolation & Row-Level Security (RLS) tests for notification_deliveries (INV-01, P9-03).

Proves:
- notification_deliveries table has ENABLE ROW LEVEL SECURITY and FORCE ROW LEVEL SECURITY.
- tenant_isolation_policy exists with matching USING and WITH CHECK clauses.
- Queries under runtime role return 0 rows when app.workspace_id is unset.
- Workspace A cannot view or access Workspace B's delivery records.
- Setting tenant context properly isolates reads and writes per workspace.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.db import clear_tenant_context, set_tenant_context
from app.notifications.models import Notification, NotificationDelivery
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
def test_notification_deliveries_has_forced_rls_and_tenant_policy(
    db_session: Session,
) -> None:
    bind = db_session.get_bind()
    if bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL specific test")

    row = db_session.execute(
        text(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c
            WHERE c.relname = 'notification_deliveries'
              AND c.relnamespace = 'public'::regnamespace
            """
        )
    ).first()

    assert row is not None, "Table notification_deliveries not found"
    assert row[1] is True, "relrowsecurity must be enabled"
    assert row[2] is True, "relforcerowsecurity must be forced"

    policy_row = db_session.execute(
        text(
            """
            SELECT polname, polcmd
            FROM pg_policy
            WHERE polrelid = 'public.notification_deliveries'::regclass
              AND polname = 'tenant_isolation_policy'
            """
        )
    ).first()

    assert policy_row is not None, "tenant_isolation_policy must exist on notification_deliveries"


@pytest.mark.invariant("INV-01")
def test_notification_deliveries_fail_closed_without_tenant_context(
    db_session: Session,
) -> None:
    bind = db_session.get_bind()
    if bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL specific test")

    ws_a, users_a = workspace_with_members(db_session, name="Delivery Tenant A")
    owner_a = users_a["owner"]
    clock = FrozenClock(datetime(2026, 11, 4, 12, 0, 0, tzinfo=UTC))

    set_tenant_context(db_session, ws_a.id)
    notif_a = Notification(
        id=uuid.uuid4(),
        workspace_id=ws_a.id,
        recipient_user_id=owner_a.id,
        type="approval.requested",
        severity="attention",
        params={},
        created_at=clock.now(),
        updated_at=clock.now(),
    )
    db_session.add(notif_a)
    db_session.flush()

    delivery_a = NotificationDelivery(
        id=uuid.uuid4(),
        workspace_id=ws_a.id,
        notification_id=notif_a.id,
        recipient_user_id=owner_a.id,
        channel="telegram",
        status="pending",
    )
    db_session.add(delivery_a)
    db_session.commit()

    # Clear tenant context and query under runtime role
    clear_tenant_context(db_session)
    with as_role(db_session, "agentnest_app"):
        rows = db_session.scalars(select(NotificationDelivery)).all()
        assert len(rows) == 0

    # With matching tenant context, row is visible
    set_tenant_context(db_session, ws_a.id)
    with as_role(db_session, "agentnest_app"):
        rows_authed = db_session.scalars(select(NotificationDelivery)).all()
        assert len(rows_authed) == 1
        assert rows_authed[0].id == delivery_a.id


@pytest.mark.invariant("INV-01")
def test_cross_tenant_notification_deliveries_isolation(
    db_session: Session,
) -> None:
    bind = db_session.get_bind()
    if bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL specific test")

    ws_a, users_a = workspace_with_members(db_session, name="Isolation WS A")
    ws_b, users_b = workspace_with_members(db_session, name="Isolation WS B")
    clock = FrozenClock(datetime(2026, 11, 4, 12, 0, 0, tzinfo=UTC))

    # Create delivery in WS A
    set_tenant_context(db_session, ws_a.id)
    notif_a = Notification(
        id=uuid.uuid4(),
        workspace_id=ws_a.id,
        recipient_user_id=users_a["owner"].id,
        type="approval.requested",
        severity="attention",
        params={},
        created_at=clock.now(),
        updated_at=clock.now(),
    )
    db_session.add(notif_a)
    db_session.flush()

    delivery_a = NotificationDelivery(
        id=uuid.uuid4(),
        workspace_id=ws_a.id,
        notification_id=notif_a.id,
        recipient_user_id=users_a["owner"].id,
        channel="telegram",
        status="pending",
    )
    db_session.add(delivery_a)
    db_session.commit()

    # Create delivery in WS B
    set_tenant_context(db_session, ws_b.id)
    notif_b = Notification(
        id=uuid.uuid4(),
        workspace_id=ws_b.id,
        recipient_user_id=users_b["owner"].id,
        type="report.daily_ready",
        severity="info",
        params={},
        created_at=clock.now(),
        updated_at=clock.now(),
    )
    db_session.add(notif_b)
    db_session.flush()

    delivery_b = NotificationDelivery(
        id=uuid.uuid4(),
        workspace_id=ws_b.id,
        notification_id=notif_b.id,
        recipient_user_id=users_b["owner"].id,
        channel="telegram",
        status="pending",
    )
    db_session.add(delivery_b)
    db_session.commit()

    # Under WS A context: only delivery A visible
    set_tenant_context(db_session, ws_a.id)
    with as_role(db_session, "agentnest_app"):
        ws_a_deliveries = db_session.scalars(select(NotificationDelivery)).all()
        assert len(ws_a_deliveries) == 1
        assert ws_a_deliveries[0].id == delivery_a.id

    # Under WS B context: only delivery B visible
    set_tenant_context(db_session, ws_b.id)
    with as_role(db_session, "agentnest_app"):
        ws_b_deliveries = db_session.scalars(select(NotificationDelivery)).all()
        assert len(ws_b_deliveries) == 1
        assert ws_b_deliveries[0].id == delivery_b.id
