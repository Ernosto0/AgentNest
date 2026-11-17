"""Isolation and Row-Level Security for delegation_suggestions (INV-01, D-02).

Proves: forced RLS and the tenant policy exist; under the runtime role no row is visible without a
tenant context; a workspace cannot read, change or insert into another's rows; and the owner of one
workspace gets 404 for another workspace's suggestion on every endpoint that takes its ID.
"""

import contextlib
import uuid
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.agent.delegation import ACTIONS
from app.agent.models import DelegationSuggestion
from app.core.clock import FrozenClock
from app.core.db import clear_tenant_context, set_tenant_context
from app.integrations.instagram.models import SocialAccount
from tests.factories import workspace_with_members
from tests.isolation.conftest import TwoWorkspaces


@contextlib.contextmanager
def as_role(session: Session, role: str) -> Iterator[None]:
    session.execute(text(f"SET LOCAL ROLE {role}"))
    session.execute(text("SET LOCAL search_path = public, pg_temp"))
    try:
        yield
    finally:
        session.execute(text("RESET ROLE"))


def suggestion(workspace_id: uuid.UUID, account_id: uuid.UUID, week: date) -> DelegationSuggestion:
    now = FrozenClock().now()
    return DelegationSuggestion(
        workspace_id=workspace_id,
        social_account_id=account_id,
        week=week,
        intent="hours",
        action_class="reply.hours",
        counts={"unchanged": 20, "edited": 0, "rejected": 0, "failed": 0},
        status="pending",
        created_at=now,
        expires_at=now + timedelta(days=7),
    )


def insert_row(session: Session, row: DelegationSuggestion) -> None:
    session.add(row)
    session.flush()


def account(session: Session, workspace_id: uuid.UUID, external: str) -> SocialAccount:
    row = SocialAccount(
        workspace_id=workspace_id,
        provider_kind="meta",
        external_account_id=external,
        status="connected",
    )
    session.add(row)
    session.flush()
    return row


@pytest.mark.invariant("INV-01")
def test_the_table_has_forced_rls_and_the_tenant_policy(db_session: Session) -> None:
    row = db_session.execute(
        text(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = 'delegation_suggestions' AND relnamespace = 'public'::regnamespace"
        )
    ).one()
    assert tuple(row) == (True, True)
    policies = (
        db_session.execute(
            text(
                "SELECT polname FROM pg_policy "
                "WHERE polrelid = 'public.delegation_suggestions'::regclass"
            )
        )
        .scalars()
        .all()
    )
    assert policies == ["tenant_isolation_policy"]


@pytest.mark.invariant("INV-01")
def test_workspaces_see_only_their_own_suggestions(db_session: Session) -> None:
    ws_a, _ = workspace_with_members(db_session, name="Ladder A")
    ws_b, _ = workspace_with_members(db_session, name="Ladder B")
    set_tenant_context(db_session, ws_a.id)
    acc_a = account(db_session, ws_a.id, "ig-ladder-a")
    row_a = suggestion(ws_a.id, acc_a.id, date(2026, 1, 12))
    db_session.add(row_a)
    db_session.flush()
    set_tenant_context(db_session, ws_b.id)
    acc_b = account(db_session, ws_b.id, "ig-ladder-b")
    row_b = suggestion(ws_b.id, acc_b.id, date(2026, 1, 12))
    db_session.add(row_b)
    db_session.commit()
    a_id, b_id = row_a.id, row_b.id
    db_session.expunge_all()

    clear_tenant_context(db_session)
    with as_role(db_session, "agentnest_app"):
        assert db_session.scalars(select(DelegationSuggestion)).all() == []  # fail closed

    set_tenant_context(db_session, ws_a.id)
    with as_role(db_session, "agentnest_app"):
        assert [r.id for r in db_session.scalars(select(DelegationSuggestion))] == [a_id]
        changed = db_session.execute(
            update(DelegationSuggestion)
            .where(DelegationSuggestion.id == b_id)
            .values(status="dismissed")
        )
        assert changed.rowcount == 0  # a foreign row is simply not there

    set_tenant_context(db_session, ws_b.id)
    with as_role(db_session, "agentnest_app"):
        [seen] = db_session.scalars(select(DelegationSuggestion)).all()
        assert (seen.id, seen.status) == (b_id, "pending")


@pytest.mark.invariant("INV-01")
def test_a_workspace_cannot_write_a_suggestion_into_another(db_session: Session) -> None:
    ws_a, _ = workspace_with_members(db_session, name="Ladder W A")
    ws_b, _ = workspace_with_members(db_session, name="Ladder W B")
    acc_b = account(db_session, ws_b.id, "ig-ladder-wb")
    db_session.commit()
    set_tenant_context(db_session, ws_a.id)
    with (
        as_role(db_session, "agentnest_app"),
        pytest.raises(DBAPIError),
        db_session.begin_nested(),
    ):
        insert_row(db_session, suggestion(ws_b.id, acc_b.id, date(2026, 1, 12)))


@pytest.mark.invariant("INV-01")
def test_a_suggestion_cannot_point_at_another_workspaces_account(db_session: Session) -> None:
    ws_a, _ = workspace_with_members(db_session, name="Ladder F A")
    ws_b, _ = workspace_with_members(db_session, name="Ladder F B")
    acc_b = account(db_session, ws_b.id, "ig-ladder-fb")
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        insert_row(db_session, suggestion(ws_a.id, acc_b.id, date(2026, 1, 12)))


def test_one_suggestion_per_workspace_and_week(db_session: Session) -> None:
    ws, _ = workspace_with_members(db_session, name="Ladder Once")
    acc = account(db_session, ws.id, "ig-ladder-once")
    db_session.add(suggestion(ws.id, acc.id, date(2026, 1, 12)))
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        insert_row(db_session, suggestion(ws.id, acc.id, date(2026, 1, 12)))
    db_session.add(suggestion(ws.id, acc.id, date(2026, 1, 19)))
    db_session.flush()


@pytest.mark.invariant("INV-01")
def test_the_foreign_owner_gets_404_on_every_suggestion_endpoint(
    two_workspaces: TwoWorkspaces, db_session: Session
) -> None:
    b_acc = db_session.scalars(
        select(SocialAccount).where(SocialAccount.workspace_id == two_workspaces.b.id)
    ).one()  # the harness already gave B its (only) active account
    row = suggestion(two_workspaces.b.id, b_acc.id, date(2026, 1, 12))
    db_session.add(row)
    db_session.commit()
    client, headers = two_workspaces.a_client, two_workspaces.a_headers
    a, b = two_workspaces.a.id, two_workspaces.b.id

    def call(method: str, path: str, **kwargs: object) -> int:
        return client.request(method, f"/api/v1{path}", headers=headers, **kwargs).status_code  # type: ignore[arg-type]

    # B's workspace and B's ID, through A's owner session.
    assert call("GET", f"/workspaces/{b}/delegation-suggestions") == 404
    assert call("POST", f"/workspaces/{b}/delegation-suggestions/{row.id}/dismiss") == 404
    # A's own workspace with B's suggestion ID: the row is not visible.
    assert call("POST", f"/workspaces/{a}/delegation-suggestions/{row.id}/dismiss") == 404
    body = {
        "expected_config_version": 1,
        "expected_delegation_version": None,
        "client_request_id": str(row.id),
        "suggestion_id": str(row.id),
        "policy": {"actions": {name: {"mode": "off"} for name in ACTIONS}},
    }
    # B's account through A's workspace, and through B's own.
    assert (
        call("POST", f"/workspaces/{a}/accounts/{b_acc.id}/agent/delegation/preview", json=body)
        == 404
    )
    assert (
        call("POST", f"/workspaces/{b}/accounts/{b_acc.id}/agent/delegation/apply", json=body)
        == 404
    )
    db_session.expire_all()
    assert db_session.get(DelegationSuggestion, row.id).status == "pending"  # type: ignore[union-attr]
