"""Isolation and Row-Level Security for push_subscriptions (INV-01, F-01).

Proves: forced RLS and the tenant policy exist; under the runtime role no row is visible without a
tenant context; one workspace cannot read, change, delete or insert into another's rows; the
unique key and the cascade behave.
"""

import contextlib
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.db import clear_tenant_context, set_tenant_context
from app.notifications.models import PushSubscription
from tests.factories import workspace_with_members
from tests.helpers.roles import ensure_runtime_roles


@contextlib.contextmanager
def as_role(session: Session, role: str) -> Iterator[None]:
    ensure_runtime_roles(session)
    session.execute(text(f"SET LOCAL ROLE {role}"))
    session.execute(text("SET LOCAL search_path = public, pg_temp"))
    try:
        yield
    finally:
        session.execute(text("RESET ROLE"))


def subscription(workspace_id: uuid.UUID, user_id: uuid.UUID, endpoint: str) -> PushSubscription:
    return PushSubscription(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        user_id=user_id,
        endpoint=endpoint,
        endpoint_hash=endpoint,  # any distinct text is enough here
        p256dh_ciphertext=b"x" * 40,
        auth_ciphertext=b"y" * 40,
        key_id="k1",
    )


@pytest.mark.invariant("INV-01")
def test_the_table_has_forced_rls_and_the_tenant_policy(db_session: Session) -> None:
    row = db_session.execute(
        text(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = 'push_subscriptions' AND relnamespace = 'public'::regnamespace"
        )
    ).one()
    assert tuple(row) == (True, True)
    policy = (
        db_session.execute(
            text(
                "SELECT polname FROM pg_policy "
                "WHERE polrelid = 'public.push_subscriptions'::regclass"
            )
        )
        .scalars()
        .all()
    )
    assert policy == ["tenant_isolation_policy"]
    ensure_runtime_roles(db_session)
    grants = set(
        db_session.execute(
            text(
                "SELECT grantee FROM information_schema.role_table_grants "
                "WHERE table_name = 'push_subscriptions' AND privilege_type = 'DELETE'"
            )
        ).scalars()
    )
    assert {"agentnest_app", "agentnest_worker"} <= grants


@pytest.mark.invariant("INV-01")
def test_workspaces_see_only_their_own_subscriptions(db_session: Session) -> None:
    ws_a, users_a = workspace_with_members(db_session, name="Push A")
    ws_b, users_b = workspace_with_members(db_session, name="Push B")
    set_tenant_context(db_session, ws_a.id)
    sub_a = subscription(ws_a.id, users_a["owner"].id, "https://push.example.com/a")
    db_session.add(sub_a)
    db_session.flush()
    set_tenant_context(db_session, ws_b.id)
    sub_b = subscription(ws_b.id, users_b["owner"].id, "https://push.example.com/b")
    db_session.add(sub_b)
    db_session.commit()
    a_id, b_id = sub_a.id, sub_b.id
    db_session.expunge_all()

    clear_tenant_context(db_session)
    with as_role(db_session, "agentnest_app"):
        assert db_session.scalars(select(PushSubscription)).all() == []  # fail closed

    set_tenant_context(db_session, ws_a.id)
    with as_role(db_session, "agentnest_app"):
        assert [r.id for r in db_session.scalars(select(PushSubscription))] == [a_id]
        assert (
            db_session.scalar(select(PushSubscription).where(PushSubscription.id == b_id)) is None
        )
        # A foreign row cannot be changed or deleted: it is simply not there.
        changed = db_session.execute(
            update(PushSubscription).where(PushSubscription.id == b_id).values(device_label="x")
        )
        assert changed.rowcount == 0
        assert (
            db_session.execute(delete(PushSubscription).where(PushSubscription.id == b_id)).rowcount
            == 0
        )

    set_tenant_context(db_session, ws_b.id)
    with as_role(db_session, "agentnest_app"):
        assert [r.id for r in db_session.scalars(select(PushSubscription))] == [b_id]
        assert db_session.scalars(select(PushSubscription.device_label)).one() == ""


@pytest.mark.invariant("INV-01")
def test_a_workspace_cannot_write_a_row_into_another(db_session: Session) -> None:
    ws_a, users_a = workspace_with_members(db_session, name="Push W A")
    ws_b, _ = workspace_with_members(db_session, name="Push W B")
    set_tenant_context(db_session, ws_a.id)
    with as_role(db_session, "agentnest_app"):
        with pytest.raises(DBAPIError), db_session.begin_nested():
            db_session.execute(
                insert(PushSubscription).values(
                    id=uuid.uuid4(),
                    workspace_id=ws_b.id,
                    user_id=users_a["owner"].id,
                    endpoint="https://push.example.com/x",
                    endpoint_hash="x",
                    p256dh_ciphertext=b"x",
                    auth_ciphertext=b"y",
                    key_id="k1",
                )
            )
        set_tenant_context(db_session, ws_b.id)
        assert db_session.scalars(select(PushSubscription)).all() == []


def test_the_same_endpoint_cannot_be_stored_twice_for_one_user_and_workspace(
    db_session: Session,
) -> None:
    ws, users = workspace_with_members(db_session, name="Push Unique")
    set_tenant_context(db_session, ws.id)
    db_session.add(subscription(ws.id, users["owner"].id, "https://push.example.com/same"))
    db_session.flush()
    db_session.add(subscription(ws.id, users["owner"].id, "https://push.example.com/same"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
