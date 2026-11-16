"""Isolation and Row-Level Security for push_preferences (INV-01, F-01 part 2).

Proves: forced RLS and the tenant policy exist; under the runtime role no row is visible without a
tenant context; one workspace cannot read, change, delete or insert into another workspace's rows;
the unique key and the category check hold.
"""

import contextlib
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.db import clear_tenant_context, set_tenant_context
from app.notifications.models import PushPreference
from tests.factories import workspace_with_members


@contextlib.contextmanager
def as_role(session: Session, role: str) -> Iterator[None]:
    session.execute(text(f"SET LOCAL ROLE {role}"))
    session.execute(text("SET LOCAL search_path = public, pg_temp"))
    try:
        yield
    finally:
        session.execute(text("RESET ROLE"))


def preference(
    workspace_id: uuid.UUID, user_id: uuid.UUID, category: str = "approvals"
) -> PushPreference:
    return PushPreference(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        user_id=user_id,
        category=category,
        enabled=True,
    )


@pytest.mark.invariant("INV-01")
def test_the_table_has_forced_rls_and_the_tenant_policy(db_session: Session) -> None:
    row = db_session.execute(
        text(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = 'push_preferences' AND relnamespace = 'public'::regnamespace"
        )
    ).one()
    assert tuple(row) == (True, True)
    policies = (
        db_session.execute(
            text(
                "SELECT polname FROM pg_policy WHERE polrelid = 'public.push_preferences'::regclass"
            )
        )
        .scalars()
        .all()
    )
    assert policies == ["tenant_isolation_policy"]


@pytest.mark.invariant("INV-01")
def test_workspaces_see_only_their_own_preferences(db_session: Session) -> None:
    ws_a, users_a = workspace_with_members(db_session, name="Pref A")
    ws_b, users_b = workspace_with_members(db_session, name="Pref B")
    set_tenant_context(db_session, ws_a.id)
    pref_a = preference(ws_a.id, users_a["owner"].id)
    db_session.add(pref_a)
    db_session.flush()
    set_tenant_context(db_session, ws_b.id)
    pref_b = preference(ws_b.id, users_b["owner"].id)
    db_session.add(pref_b)
    db_session.commit()
    a_id, b_id = pref_a.id, pref_b.id
    db_session.expunge_all()

    clear_tenant_context(db_session)
    with as_role(db_session, "agentnest_app"):
        assert db_session.scalars(select(PushPreference)).all() == []  # fail closed

    set_tenant_context(db_session, ws_a.id)
    with as_role(db_session, "agentnest_app"):
        assert [r.id for r in db_session.scalars(select(PushPreference))] == [a_id]
        changed = db_session.execute(
            update(PushPreference).where(PushPreference.id == b_id).values(enabled=False)
        )
        assert changed.rowcount == 0
        deleted = db_session.execute(delete(PushPreference).where(PushPreference.id == b_id))
        assert deleted.rowcount == 0

    set_tenant_context(db_session, ws_b.id)
    with as_role(db_session, "agentnest_app"):
        (only,) = db_session.scalars(select(PushPreference)).all()
        assert only.id == b_id and only.enabled is True


@pytest.mark.invariant("INV-01")
def test_a_workspace_cannot_write_a_row_into_another(db_session: Session) -> None:
    ws_a, users_a = workspace_with_members(db_session, name="Pref W A")
    ws_b, _ = workspace_with_members(db_session, name="Pref W B")
    set_tenant_context(db_session, ws_a.id)
    with as_role(db_session, "agentnest_app"):
        with pytest.raises(DBAPIError), db_session.begin_nested():
            db_session.execute(
                insert(PushPreference).values(
                    id=uuid.uuid4(),
                    workspace_id=ws_b.id,
                    user_id=users_a["owner"].id,
                    category="approvals",
                    enabled=True,
                )
            )
        set_tenant_context(db_session, ws_b.id)
        assert db_session.scalars(select(PushPreference)).all() == []


def test_one_row_per_user_and_category_and_only_known_categories(db_session: Session) -> None:
    ws, users = workspace_with_members(db_session, name="Pref Unique")
    set_tenant_context(db_session, ws.id)
    db_session.add(preference(ws.id, users["owner"].id))
    db_session.flush()
    db_session.add(preference(ws.id, users["owner"].id))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    ws, users = workspace_with_members(db_session, name="Pref Check")
    set_tenant_context(db_session, ws.id)
    db_session.add(preference(ws.id, users["owner"].id, category="everything"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
