"""Phase 6 report routes (INV-01, AC-X1): a foreign workspace is a 404 on all three, nothing is
written there, and one workspace's numbers never include another's records."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.core.clock import FrozenClock
from app.reporting import service
from app.reporting.models import DailyReport
from app.reporting.periods import local_date_of
from tests.factories import knowledge_ctx
from tests.isolation.conftest import TwoWorkspaces

TODAY = "2026-01-15"  # the isolation fixtures' clock, in Istanbul


def _count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


@pytest.mark.invariant("INV-01")
def test_the_three_report_routes_are_404_for_a_foreign_workspace_and_write_nothing(
    two_workspaces: TwoWorkspaces, db_session: Session
) -> None:
    client, headers = two_workspaces.a_client, two_workspaces.a_headers
    base = f"/api/v1/workspaces/{two_workspaces.b.id}/reports/daily"
    reports_before = _count(db_session, DailyReport)
    audits_before = _count(db_session, AuditLog)

    requests = [
        ("GET", base, {}),
        ("GET", f"{base}?date={TODAY}", {}),
        ("GET", f"{base}/{TODAY}/metrics/inbound_messages", {}),
        ("POST", f"{base}/generate", {"json": {"date": TODAY}}),
    ]
    for method, url, kwargs in requests:
        response = client.request(method, url, headers=headers, **kwargs)
        assert response.status_code == 404, (method, url)
        assert response.json()["code"] == "NOT_FOUND"

    assert _count(db_session, DailyReport) == reports_before
    assert _count(db_session, AuditLog) == audits_before


@pytest.mark.invariant("INV-01")
def test_the_numbers_of_a_never_include_the_records_of_b(
    two_workspaces: TwoWorkspaces, db_session: Session
) -> None:
    clock = two_workspaces.app.state.clock
    assert isinstance(clock, FrozenClock)
    clock.advance(minutes=1)  # B's message (stamped at the old "now") falls inside the period

    # B really has an inbound message today: the test would catch a leak.
    b_report = service.get_report(
        db_session,
        clock,
        knowledge_ctx(two_workspaces.b),
        local_date_of(clock.now(), two_workspaces.b.timezone),
    )
    assert b_report.value("inbound_messages") == 1
    assert b_report.value("conversations_with_inbound") == 1

    client, headers = two_workspaces.a_client, two_workspaces.a_headers
    base = f"/api/v1/workspaces/{two_workspaces.a.id}/reports/daily"
    report = client.get(base, params={"date": TODAY}, headers=headers)
    assert report.status_code == 200
    values = {m["key"]: m["value"] for m in report.json()["metrics"]}
    assert values["inbound_messages"] == 0
    assert values["conversations_with_inbound"] == 0
    assert values["attention_now"] == 0
    assert values["pending_approvals_now"] == 0

    foreign_message = two_workspaces.foreign_ids["message_id"]
    for key in ("inbound_messages", "conversations_with_inbound", "pending_approvals_now"):
        drill = client.get(f"{base}/{TODAY}/metrics/{key}", headers=headers)
        assert drill.status_code == 200
        assert drill.json()["items"] == []
        assert foreign_message not in drill.text


@pytest.mark.invariant("INV-01")
def test_a_stored_report_of_b_is_not_readable_through_a(
    two_workspaces: TwoWorkspaces, db_session: Session
) -> None:
    clock = two_workspaces.app.state.clock
    yesterday = local_date_of(clock.now(), two_workspaces.b.timezone) - timedelta(days=1)
    service.generate_daily_report(
        db_session, clock, knowledge_ctx(two_workspaces.b), yesterday, scheduled=False
    )
    db_session.commit()

    client, headers = two_workspaces.a_client, two_workspaces.a_headers
    own = client.get(
        f"/api/v1/workspaces/{two_workspaces.a.id}/reports/daily",
        params={"date": yesterday.isoformat()},
        headers=headers,
    )
    assert own.status_code == 200
    stored_rows = db_session.scalars(select(DailyReport)).all()
    assert {r.workspace_id for r in stored_rows} == {two_workspaces.a.id, two_workspaces.b.id}
    # A's read stored A's own report: one row per workspace, none shared.
    assert len(stored_rows) == 2


@pytest.mark.invariant("INV-01")
def test_b_operation_is_not_found_through_any_workspace_url(
    two_workspaces: TwoWorkspaces,
) -> None:
    operation_id = two_workspaces.foreign_ids["operation_id"]
    client, headers = two_workspaces.a_client, two_workspaces.a_headers
    for workspace in (two_workspaces.a, two_workspaces.b):
        url = f"/api/v1/workspaces/{workspace.id}/operations/{operation_id}"
        response = client.get(url, headers=headers)
        assert response.status_code == 404, url
        assert response.json()["code"] == "NOT_FOUND"
        assert "OUTCOME_UNCONFIRMED" not in response.text
