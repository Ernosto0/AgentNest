"""Call-back definition, CSV safety, authorization and audit evidence, entirely offline."""

import csv
import io
import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.agent.models import AgentAction, AgentSession, AgentThread
from app.audit.models import AuditLog
from app.integrations.calendar.models import CalendarAppointment, CalendarConnection
from app.knowledge.models import BusinessFact, FactReference
from app.reporting import definitions, leads
from app.reporting.weekly_sources import WEEKLY_DEFINITIONS
from tests.integration.reporting.test_missed_customers import (
    MONDAY,
    NOW,
    _api,
    _extra_account,
    _world,
    at,
)

PERIOD = {"from": "2026-03-09", "to": "2026-03-15"}


@pytest.fixture(autouse=True)
def frozen_clock(clock):
    clock.advance(NOW - clock.now())


def question(world, *, when=None, intent="pricing", conversation=None, builder=None):
    b = builder or world.real
    when = when or at(MONDAY, 10)
    c = conversation or b.conversation(when)
    c.customer_handle = "müşteri"
    m = b.message(c, "inbound", when)
    m.text = "Fiyat nedir?"
    d = b.draft(c, m, source="ai", decision="auto", status="cancelled", created_at=when)
    d.intent = intent
    world.session.flush()
    return c, m, d


def page(world, **kwargs):
    world.session.flush()
    return leads.list_leads(
        world.session,
        world.clock,
        world.ctx(),
        MONDAY,
        MONDAY + timedelta(days=6),
        limit=kwargs.get("limit", 50),
        offset=kwargs.get("offset", 0),
    )


def appointment(world, conversation, *, status="scheduled", when=None, simulated=False):
    connection = world.session.scalar(
        select(CalendarConnection).where(CalendarConnection.workspace_id == world.workspace.id)
    )
    if connection is None:
        connection = CalendarConnection(
            workspace_id=world.workspace.id, provider_kind="mock", external_account_id="test"
        )
        world.session.add(connection)
        world.session.flush()
    row = CalendarAppointment(
        workspace_id=world.workspace.id,
        calendar_connection_id=connection.id,
        conversation_id=conversation.id,
        title="Appointment",
        status=status,
        created_by_source="customer",
        is_simulated=simulated,
        timezone="Europe/Istanbul",
        start_at=NOW + timedelta(days=1),
        end_at=NOW + timedelta(days=1, hours=1),
        created_at=when or at(MONDAY, 11),
    )
    world.session.add(row)
    world.session.flush()
    return row


def test_latest_question_ties_status_and_pagination(db_session):
    w = _world(db_session)
    c, _, _ = question(w)
    _, m, d = question(w, when=at(MONDAY, 12), conversation=c)
    m.text = "Randevu alabilir miyim?"
    d.intent = "booking"
    # Same message also classified as pricing: booking wins regardless of draft id.
    extra = w.real.draft(c, m, source="ai", decision="auto", status="cancelled", created_at=NOW)
    extra.intent = "pricing"
    second, _, _ = question(w, when=at(MONDAY, 12))
    w.real.message(c, "outbound", at(MONDAY, 13), kind="business_app")
    result = page(w)
    assert result.total == 2
    assert [r.conversation_id for r in result.items] == sorted([c.id, second.id], reverse=True)
    lead = next(r for r in result.items if r.conversation_id == c.id)
    assert (lead.last_question, lead.intent, lead.last_question_at) == (
        m.text,
        "booking",
        m.provider_timestamp,
    )
    assert lead.link["route"] == f"/w/{w.workspace.id}/inbox/{c.id}"
    pages = [page(w, limit=1, offset=n) for n in range(3)]
    assert all(p.total == 2 for p in pages)
    assert sum(len(p.items) for p in pages) == 2


@pytest.mark.parametrize(
    "kind",
    [
        "hours",
        "greeting",
        "null",
        "deleted",
        "message_sim",
        "conversation_sim",
        "draft_sim",
        "mock",
        "before",
        "end",
    ],
)
def test_exclusions(db_session, kind):
    w = _world(db_session)
    b = _extra_account(w, simulated=False) if kind == "mock" else w.real
    when = at(MONDAY, 0)
    if kind == "before":
        when -= timedelta(microseconds=1)
    if kind == "end":
        when += timedelta(days=7)
    c, m, d = question(w, when=when, builder=b)
    if kind in {"hours", "greeting", "null"}:
        d.intent = None if kind == "null" else kind
    if kind == "deleted":
        m.is_deleted = True
    if kind == "message_sim":
        m.is_simulated = True
    if kind == "conversation_sim":
        c.is_simulated = True
    if kind == "draft_sim":
        d.is_simulated = True
    assert page(w).total == 0


def test_local_first_and_last_instants_and_message_id_tie(db_session):
    w = _world(db_session)
    question(w, when=at(MONDAY, 0))  # previous UTC date, still in local period
    c, m, _ = question(w, when=at(MONDAY, 0) + timedelta(days=7, microseconds=-1))
    _, other, d = question(w, when=m.provider_timestamp, conversation=c, intent="booking")
    expected = max((m, other), key=lambda r: r.id)
    assert page(w).total == 2
    assert page(w).items[0].intent == ("booking" if expected.id == other.id else "pricing")


@pytest.mark.parametrize(
    ("status", "delta", "simulated", "excluded"),
    [
        ("scheduled", 0, False, True),
        ("completed", 1, False, True),
        ("scheduled", 20, True, True),
        ("cancelled", 1, False, False),
        ("scheduled", -1, False, False),
    ],
)
def test_conversion_from_first_question_not_last_or_period_end(
    db_session, status, delta, simulated, excluded
):
    w = _world(db_session)
    c, m, _ = question(w)
    question(w, when=at(MONDAY, 12), conversation=c)
    appointment(
        w, c, status=status, when=m.provider_timestamp + timedelta(days=delta), simulated=simulated
    )
    assert page(w).total == (0 if excluded else 1)


def test_other_conversation_booking_and_unclassified_agent_do_not_convert(db_session):
    w = _world(db_session)
    question(w)
    other, _, _ = question(w, intent=None)
    appointment(w, other)
    assert page(w).total == 1


def test_agent_pricing_fact_reference_and_tenant_scope(db_session):
    w = _world(db_session)
    c, _, draft = question(w, intent=None)
    thread = AgentThread(
        workspace_id=w.workspace.id,
        social_account_id=w.real.account.id,
        surface="dm",
        source_ref=str(c.id),
        dm_conversation_id=c.id,
    )
    db_session.add(thread)
    db_session.flush()
    run = AgentSession(
        workspace_id=w.workspace.id,
        thread_id=thread.id,
        initiating_event_cursor=0,
        goal_key="reply",
    )
    db_session.add(run)
    db_session.flush()
    action = AgentAction(
        workspace_id=w.workspace.id,
        social_account_id=w.real.account.id,
        thread_id=thread.id,
        session_id=run.id,
        intent_key="response",
        action_type="dm.send",
        target_ref=str(c.id),
        payload_hash="a" * 64,
        initiating_cursor=0,
    )
    db_session.add(action)
    db_session.flush()
    draft.origin = "agent"
    draft.agent_action_id = action.id
    fact = db_session.scalar(
        select(BusinessFact).where(
            BusinessFact.workspace_id == w.workspace.id, BusinessFact.category == "pricing"
        )
    )
    ref = FactReference(
        workspace_id=w.workspace.id,
        fact_id=fact.id,
        fact_version=1,
        referrer_type="reply_draft",
        referrer_id=draft.id,
    )
    db_session.add(ref)
    assert page(w).items[0].intent == "pricing"
    # Non-agent null-intent drafts do not inherit the extension.
    draft.origin = "legacy"
    draft.agent_action_id = None
    assert page(w).total == 0


@pytest.mark.parametrize(("role", "status"), [("owner", 200), ("manager", 200), ("staff", 403)])
def test_roles_export_headers_and_audit(db_session, make_client, role, status):
    api = _api(db_session, make_client, role)
    c, m, _ = question(api.world, when=at(MONDAY, 0))
    path = f"{api.base}/leads"
    response = api.client.get(path, params=PERIOD, headers=api.headers)
    assert response.status_code == status
    assert not db_session.scalars(select(AuditLog).where(AuditLog.action == "leads.exported")).all()
    response = api.client.post(path + "/export", json=PERIOD, headers=api.headers)
    assert response.status_code == status, response.text
    logs = db_session.scalars(select(AuditLog).where(AuditLog.action == "leads.exported")).all()
    if status != 200:
        assert not logs
        return
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-row-count"] == "1"
    assert response.headers["x-truncated"] == "false"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="leads-2026-03-09_2026-03-15.csv"'
    )
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0] == ["customer_handle", "last_question", "date", "conversation_link"]
    assert len(rows[1]) == 4 and rows[1][2] == "2026-03-09"
    from app.core.config import get_settings

    cfg = get_settings()
    base = (cfg.frontend_origin or cfg.app_base_url).rstrip("/")
    assert rows[1][3] == f"{base}/w/{api.world.workspace.id}/inbox/{c.id}"
    assert len(logs) == 1
    log = logs[0]
    assert log.workspace_id == api.world.workspace.id and log.actor_type == "user"
    assert log.actor_id == str(api.world.owner.id) if role == "owner" else log.actor_id is not None
    assert log.metadata_ == {
        "period_from": PERIOD["from"],
        "period_to": PERIOD["to"],
        "row_count": 1,
        "truncated": False,
        "columns": 4,
    }
    meta = json.dumps(log.metadata_, ensure_ascii=False)
    assert all(value not in meta for value in (c.customer_handle, m.text, str(c.id), "/inbox/"))


@pytest.mark.parametrize(
    ("period", "code"),
    [
        ({"from": "2026-03-15", "to": "2026-03-09"}, "to_before_from"),
        ({"to": "2026-03-17"}, "in_future"),
        ({"from": "2025-01-01"}, "period_too_long"),
    ],
)
def test_validation_no_audit(db_session, make_client, period, code):
    api = _api(db_session, make_client)
    for response in (
        api.client.get(f"{api.base}/leads", params=period, headers=api.headers),
        api.client.post(f"{api.base}/leads/export", json=period, headers=api.headers),
    ):
        assert response.status_code == 422
        assert response.json()["errors"][0]["code"] == code
    assert not db_session.scalars(select(AuditLog).where(AuditLog.action == "leads.exported")).all()


def test_defaults_cap_and_anonymous(db_session, make_client, monkeypatch):
    api = _api(db_session, make_client)
    question(api.world)
    question(api.world)
    response = api.client.get(f"{api.base}/leads", headers=api.headers)
    assert response.json()["period_from"] == "2026-02-15"
    assert response.json()["period_to"] == "2026-03-16"
    monkeypatch.setattr(leads, "MAX_EXPORT_ROWS", 1)
    for _ in range(2):
        r = api.client.post(f"{api.base}/leads/export", json=PERIOD, headers=api.headers)
        assert (r.headers["x-row-count"], r.headers["x-truncated"]) == ("1", "true")
    logs = db_session.scalars(select(AuditLog).where(AuditLog.action == "leads.exported")).all()
    assert len(logs) == 2 and all(log.metadata_["truncated"] for log in logs)
    anonymous = make_client()
    assert anonymous.get(f"{api.base}/leads").status_code == 401
    assert anonymous.post(f"{api.base}/leads/export", json={}).status_code == 401


def test_audit_failure_returns_no_file(db_session, make_client, monkeypatch):
    from app.reporting import leads_router

    api = _api(db_session, make_client)

    def fail(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(leads_router.audit, "record", fail)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        api.client.post(f"{api.base}/leads/export", json=PERIOD, headers=api.headers)


def test_report_registries_unchanged():
    assert all("lead" not in d.key for d in WEEKLY_DEFINITIONS)
    assert all("lead" not in d.key for d in definitions.DEFINITIONS)


def test_question_cleaning_and_csv_newlines(db_session, make_client):
    api = _api(db_session, make_client)
    _, m, _ = question(api.world)
    m.text = "=a\nline\r\nother\x01" + "x" * 350
    db_session.flush()
    result = api.client.get(f"{api.base}/leads", params=PERIOD, headers=api.headers).json()
    text = result["items"][0]["last_question"]
    assert len(text) == 300 and text.endswith("…") and "\x00" not in text
    response = api.client.post(f"{api.base}/leads/export", json=PERIOD, headers=api.headers)
    cells = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert cells[1][1].startswith("'=a line") and "\n" not in cells[1][1]
