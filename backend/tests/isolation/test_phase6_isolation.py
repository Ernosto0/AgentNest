"""Phase 6 routes that the other isolation modules do not cover (INV-01, AC-X1): members, invites,
system health, and the dev reset and health-check routes.

Reports, drill-down, activity and the operation detail are in ``test_reports_isolation.py`` and
``test_activity_isolation.py``; the generic ``test_workspace_isolation.py`` also calls every
``/workspaces/{id}/...`` route with B's workspace id and B's ids. Here each route is also called
the other way round: **A's own workspace with B's identifiers**, and the listings are read for
leaks. Nothing may change in B.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.identity.models import Invite, Workspace, WorkspaceMember
from app.jobs.models import Job
from tests.isolation.conftest import TwoWorkspaces

BASE = "/api/v1/workspaces"
DEV = "/api/v1/dev/workspaces"


def _assert_404(response: object) -> None:
    status = response.status_code  # type: ignore[attr-defined]
    assert status == 404, (status, response.text)  # type: ignore[attr-defined]
    assert response.json()["code"] == "NOT_FOUND"  # type: ignore[attr-defined]


def _members_of_b(db: Session, tw: TwoWorkspaces) -> list[tuple[str, str]]:
    db.expire_all()
    rows = db.scalars(select(WorkspaceMember).where(WorkspaceMember.workspace_id == tw.b.id)).all()
    return sorted((str(m.user_id), m.role) for m in rows)


def _invites(db: Session, workspace: Workspace) -> list[Invite]:
    db.expire_all()
    return list(db.scalars(select(Invite).where(Invite.workspace_id == workspace.id)))


# --- members ----------------------------------------------------------------------------------


@pytest.mark.invariant("INV-01")
def test_members_of_b_are_neither_listed_nor_changed_through_a(
    two_workspaces: TwoWorkspaces, db_session: Session
) -> None:
    tw = two_workspaces
    client, headers = tw.a_client, tw.a_headers
    before = _members_of_b(db_session, tw)
    assert before, "B has a member: the test needs a real foreign user"

    listing = client.get(f"{BASE}/{tw.a.id}/members", headers=headers)
    assert listing.status_code == 200
    assert {m["user_id"] for m in listing.json()["items"]} == {str(tw.a_owner.id)}
    assert tw.foreign_ids["user_id"] not in listing.text

    # B's user through A's workspace: not a member there, so a 404 (never a 403).
    foreign_user = tw.foreign_ids["user_id"]
    _assert_404(
        client.patch(
            f"{BASE}/{tw.a.id}/members/{foreign_user}", json={"role": "staff"}, headers=headers
        )
    )
    _assert_404(client.delete(f"{BASE}/{tw.a.id}/members/{foreign_user}", headers=headers))
    # B's workspace with A's own user, and with B's user.
    for user_id in (str(tw.a_owner.id), foreign_user):
        _assert_404(client.get(f"{BASE}/{tw.b.id}/members", headers=headers))
        _assert_404(
            client.patch(
                f"{BASE}/{tw.b.id}/members/{user_id}", json={"role": "staff"}, headers=headers
            )
        )
        _assert_404(client.delete(f"{BASE}/{tw.b.id}/members/{user_id}", headers=headers))

    assert _members_of_b(db_session, tw) == before  # nothing changed in B
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == tw.a.id)
        )
        == 1
    )  # and A still has its owner


# --- invites ----------------------------------------------------------------------------------


@pytest.mark.invariant("INV-01")
def test_invites_of_b_are_neither_listed_nor_revoked_nor_created_through_a(
    two_workspaces: TwoWorkspaces, db_session: Session
) -> None:
    tw = two_workspaces
    client, headers = tw.a_client, tw.a_headers
    foreign_invite = tw.foreign_ids["invite_id"]
    assert [str(i.id) for i in _invites(db_session, tw.b)] == [foreign_invite]

    # A's listing has no row of B (A has no invite at all).
    listing = client.get(f"{BASE}/{tw.a.id}/invites", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["items"] == []
    assert foreign_invite not in listing.text

    # B's invite through A's workspace: a 404, and it stays pending.
    _assert_404(client.post(f"{BASE}/{tw.a.id}/invites/{foreign_invite}/revoke", headers=headers))
    # Every invite route of B's workspace.
    _assert_404(client.get(f"{BASE}/{tw.b.id}/invites", headers=headers))
    _assert_404(client.post(f"{BASE}/{tw.b.id}/invites", json={"role": "staff"}, headers=headers))
    _assert_404(client.post(f"{BASE}/{tw.b.id}/invites/{foreign_invite}/revoke", headers=headers))

    (still_pending,) = _invites(db_session, tw.b)
    assert still_pending.revoked_at is None and still_pending.accepted_at is None
    assert _invites(db_session, tw.a) == []  # nothing was created for A either


# --- system health ----------------------------------------------------------------------------


@pytest.mark.invariant("INV-01")
def test_the_system_health_of_a_never_counts_the_rows_of_b(
    two_workspaces: TwoWorkspaces, db_session: Session
) -> None:
    tw = two_workspaces
    client, headers = tw.a_client, tw.a_headers
    # B has a failed operation, a queued job and a dead job; A has none of them.
    db_session.add_all(
        [
            Job(
                workspace_id=tw.b.id,
                job_type="send_reply",
                payload={},
                status="queued",
                run_at=tw.app.state.clock.now(),
                max_attempts=3,
            ),
            Job(
                workspace_id=tw.b.id,
                job_type="send_reply",
                payload={},
                status="dead",
                run_at=tw.app.state.clock.now(),
                max_attempts=3,
                finished_at=tw.app.state.clock.now(),
            ),
        ]
    )
    db_session.commit()

    own = client.get(f"{BASE}/{tw.a.id}/system-health", headers=headers)
    assert own.status_code == 200
    body = own.json()
    assert body["accounts"] == []
    assert body["operations"]["latest_failures"] == []
    assert body["jobs"]["queued"] == 0 and body["jobs"]["dead_24h"] == 0
    assert body["webhooks"]["received_24h"] == 0
    for leak in (
        tw.foreign_ids["operation_id"],
        tw.foreign_ids["account_id"],
        "OUTCOME_UNCONFIRMED",
        "b.demo",
    ):
        assert leak not in own.text, leak

    _assert_404(client.get(f"{BASE}/{tw.b.id}/system-health", headers=headers))


# --- dev routes -------------------------------------------------------------------------------


@pytest.mark.invariant("INV-01")
def test_the_dev_reset_and_health_check_of_b_are_404_through_a_and_change_nothing(
    two_workspaces: TwoWorkspaces, db_session: Session
) -> None:
    tw = two_workspaces
    client, headers = tw.a_client, tw.a_headers
    b_demo = db_session.get(Workspace, tw.b.id)
    assert b_demo is not None
    workspaces_before = db_session.scalar(select(func.count()).select_from(Workspace))

    _assert_404(client.post(f"{DEV}/{tw.b.id}/reset", headers=headers))
    _assert_404(client.post(f"{DEV}/{tw.b.id}/health-check", headers=headers))

    db_session.expire_all()
    assert db_session.get(Workspace, tw.b.id) is not None  # B was not deleted or re-created
    assert db_session.scalar(select(func.count()).select_from(Workspace)) == workspaces_before


@pytest.mark.invariant("INV-01")
def test_the_dev_job_listing_of_a_never_shows_the_jobs_of_b(
    two_workspaces: TwoWorkspaces, db_session: Session
) -> None:
    tw = two_workspaces
    clock = tw.app.state.clock
    own = Job(
        workspace_id=tw.a.id, job_type="test.own", payload={}, run_at=clock.now(), max_attempts=1
    )
    foreign = Job(
        workspace_id=tw.b.id,
        job_type="test.foreign",
        payload={},
        run_at=clock.now(),
        max_attempts=1,
    )
    db_session.add_all([own, foreign])
    db_session.commit()

    response = tw.a_client.get("/api/v1/dev/jobs", headers=tw.a_headers)
    assert response.status_code == 200
    types = {job["job_type"] for job in response.json()["items"]}
    assert "test.own" in types
    assert "test.foreign" not in types
