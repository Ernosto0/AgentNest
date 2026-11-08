"""Integration tests for Google & Mock Calendar integration and Agent appointment booking."""

import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.agent.calendar import CalendarEvidence
from app.agent.control import ControllerChange, change_controller
from app.agent.delegation import ACTIONS, ActionRule, DelegationChange, DelegationPolicy, apply
from app.agent.grounding import ReplyValidationArgs
from app.agent.models import AccountAgent, AgentAction, AgentThread
from app.agent.tools.broker import BrokerContext, build_default_broker
from app.approvals import service as approvals
from app.approvals.models import Approval
from app.core.config import Settings
from app.inbox.models import ReplyDraft
from app.integrations.calendar.models import (
    CalendarAppointment,
    CalendarConnection,
    SimCalendarEvent,
)
from app.integrations.instagram.models import SimSentMessage, SocialAccount
from app.integrations.llm.fake import FakeLLMProvider
from app.operations import calendar as calendar_ops
from app.operations.models import Operation
from tests.factories import create_fact, knowledge_ctx, workspace_with_members
from tests.helpers.gym import HOURS, WEEK
from tests.integration.agent.test_coordinator import deps, result
from tests.integration.agent.test_dm import deliver, drain, process_inbound

pytestmark = pytest.mark.commits


def _setup_calendar_world(
    factory,
    clock,
    *,
    book_mode: str = "automatic",
    reschedule_mode: str = "automatic",
    cancel_mode: str = "automatic",
    dm_mode: str = "automatic",
):
    settings = Settings(
        _env_file=None,
        llm_provider="fake",
        instagram_enabled_providers="mock",
        calendar_enabled_providers="mock",
        media_storage_backend="local",
    )
    with factory() as db:
        workspace, users = workspace_with_members(db, default_locale="en")
        workspace.reply_languages = ["en", "tr"]
        create_fact(db, workspace, HOURS, WEEK, clock=clock)
        ctx = knowledge_ctx(workspace, users["owner"], "owner")
        social = SocialAccount(
            workspace_id=workspace.id,
            provider_kind="mock",
            external_account_id=uuid.uuid4().hex,
            capabilities={"messaging": True},
            status="connected",
        )
        db.add(social)
        db.flush()

        conn = calendar_ops.connect_mock_calendar(
            db,
            clock,
            ctx,
            settings,
            account_email="studio@example.com",
            calendar_summary="Main Studio Calendar",
            default_slot_duration_minutes=60,
        )

        account = db.scalar(select(AccountAgent).where(AccountAgent.social_account_id == social.id))
        assert account is not None
        rules = {name: ActionRule(mode="off") for name in ACTIONS}
        rules["dm.send"] = ActionRule(mode=dm_mode)
        rules["calendar.book"] = ActionRule(mode=book_mode)
        rules["calendar.reschedule"] = ActionRule(mode=reschedule_mode)
        rules["calendar.cancel"] = ActionRule(mode=cancel_mode)
        policy = DelegationPolicy(actions=rules)
        apply(
            db,
            clock,
            ctx,
            social.id,
            DelegationChange(
                expected_config_version=account.config_version,
                expected_delegation_version=None,
                client_request_id=uuid.uuid4(),
                policy=policy,
            ),
        )
        change_controller(
            db,
            clock,
            ctx,
            social.id,
            ControllerChange(
                expected_config_version=account.config_version,
                client_request_id=uuid.uuid4(),
            ),
        )
        db.commit()
        return ctx, social.id, social.external_account_id, settings, conn.id


def test_dm_customer_checks_availability_and_books_appointment_automatically(
    session_factory, clock, monkeypatch
):
    """Customer asks 'Is tomorrow 12:00 available?'; Agent checks availability and books."""
    ctx, account_id, external_id, settings, conn_id = _setup_calendar_world(
        session_factory, clock, book_mode="automatic"
    )
    world = (ctx, account_id, external_id, settings)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))

    tz = ZoneInfo(ctx.timezone)
    tomorrow = (clock.now().astimezone(tz) + timedelta(days=1)).date()
    date_str = tomorrow.isoformat()

    # Step 1: Agent calls calendar.availability for tomorrow
    fake.queue_step(
        result(
            "tool",
            tool_name="calendar.availability",
            tool_arguments={
                "local_date": date_str,
                "local_time": "12:00",
                "duration_minutes": 60,
            },
        )
    )
    # Step 2: Agent calls calendar.book for 12:00 tomorrow
    fake.queue_step(
        result(
            "tool",
            tool_name="calendar.book",
            tool_arguments={
                "local_date": date_str,
                "local_time": "12:00",
                "duration_minutes": 60,
                "title": "Trial Pilates Session",
                "customer_name": "Ada",
                "customer_contact": "@ada",
                "description": "First visit",
            },
        )
    )
    # Deliver inbound DM
    deliver(
        session_factory,
        clock,
        world,
        text="Hi! Is tomorrow at 12:00 available for a trial session?",
        customer="customer-ada",
    )

    # Run jobs until calendar.book effect executes and wakes the agent.
    for _ in range(15):
        from app.jobs.queue import claim_one
        from app.jobs.worker import execute_job

        job = claim_one(session_factory, clock, f"w-{uuid.uuid4().hex}", 120)
        if job is None:
            break
        if job.job_type == "agent_wake" and len(fake.step_calls) >= 2:
            with session_factory() as db:
                appt = db.scalar(select(CalendarAppointment))
                assert appt is not None and appt.status == "scheduled"
                reply_args = ReplyValidationArgs(
                    template="ignored when calendar_evidence is set",
                    language="en",
                    calendar_evidence=CalendarEvidence(
                        kind="booked",
                        appointment_id=appt.id,
                        appointment_version=appt.version,
                    ),
                )
                fake.queue_step(
                    result(
                        "tool",
                        tool_name="dm.send",
                        tool_arguments=reply_args.model_dump(mode="json"),
                    )
                )
                fake.queue_step(result())
        assert execute_job(session_factory, clock, job, lease_seconds=120) == "succeeded"

    drain(session_factory, clock)

    with session_factory() as db:
        appts = db.scalars(select(CalendarAppointment)).all()
        assert len(appts) == 1
        appt = appts[0]
        assert appt.status == "scheduled"
        assert appt.title == "Trial Pilates Session"
        assert appt.customer_name == "Ada"
        assert appt.external_event_id is not None

        sim_events = db.scalars(select(SimCalendarEvent)).all()
        assert len(sim_events) == 1
        assert sim_events[0].external_event_id == appt.external_event_id

        sent = db.scalars(select(SimSentMessage)).all()
        assert len(sent) == 1
        assert "Trial Pilates Session" in sent[0].text
        assert "12:00" in sent[0].text
        draft = db.scalar(select(ReplyDraft))
        assert draft is not None and draft.status == "sent"


def test_calendar_availability_respects_business_hours_and_busy_slots(session_factory, clock):
    """Availability slots are intersected with verified WeeklyHoursValue and booked appointments."""
    ctx, account_id, external_id, settings, conn_id = _setup_calendar_world(
        session_factory, clock, book_mode="automatic"
    )
    tz = ZoneInfo(ctx.timezone)
    tomorrow = (clock.now().astimezone(tz) + timedelta(days=1)).date()
    day_start = datetime.combine(tomorrow, time(0, 0), tzinfo=tz).astimezone(UTC)
    day_end = datetime.combine(tomorrow + timedelta(days=1), time(0, 0), tzinfo=tz).astimezone(UTC)
    req_start = datetime.combine(tomorrow, time(12, 0), tzinfo=tz).astimezone(UTC)

    avail_before = calendar_ops.check_availability(
        session_factory,
        clock,
        settings,
        ctx.workspace_id,
        window_start=day_start,
        window_end=day_end,
        duration_minutes=60,
        requested_start_at=req_start,
    )
    assert avail_before.calendar_connected is True
    assert avail_before.requested_slot_available is True
    assert any(s.local_start_time == "12:00" for s in avail_before.available_slots)

    with session_factory() as db:
        # Add a simulated busy event at 12:00-13:00 local time
        db.add(
            SimCalendarEvent(
                workspace_id=ctx.workspace_id,
                calendar_connection_id=conn_id,
                external_event_id=f"busy_{uuid.uuid4().hex[:8]}",
                title="Busy block",
                start_at=req_start,
                end_at=req_start + timedelta(hours=1),
                timezone=ctx.timezone,
                status="confirmed",
            )
        )
        db.commit()

    avail_after = calendar_ops.check_availability(
        session_factory,
        clock,
        settings,
        ctx.workspace_id,
        window_start=day_start,
        window_end=day_end,
        duration_minutes=60,
        requested_start_at=req_start,
    )
    assert avail_after.requested_slot_available is False
    assert not any(s.local_start_time == "12:00" for s in avail_after.available_slots)
    assert any(s.local_start_time == "13:00" for s in avail_after.available_slots)


def test_calendar_book_in_ask_mode_waits_for_owner_approval(session_factory, clock, monkeypatch):
    """When calendar.book is 'ask', booking creates a pending approval until owner approves."""
    ctx, account_id, external_id, settings, conn_id = _setup_calendar_world(
        session_factory, clock, book_mode="ask"
    )
    world = (ctx, account_id, external_id, settings)
    fake = FakeLLMProvider()
    monkeypatch.setattr("app.agent.jobs.deps_for", lambda _: deps(session_factory, clock, fake))

    tz = ZoneInfo(ctx.timezone)
    tomorrow = (clock.now().astimezone(tz) + timedelta(days=1)).date()
    date_str = tomorrow.isoformat()

    fake.queue_step(
        result(
            "tool",
            tool_name="calendar.book",
            tool_arguments={
                "local_date": date_str,
                "local_time": "14:00",
                "duration_minutes": 60,
                "title": "PT Consultation",
                "customer_name": "Bora",
            },
        )
    )
    deliver(
        session_factory,
        clock,
        world,
        text="Can I book 14:00 tomorrow for PT consultation?",
        customer="customer-bora",
    )
    drain(session_factory, clock)

    with session_factory() as db:
        # No calendar event created yet!
        assert db.scalars(select(SimCalendarEvent)).all() == []
        action = db.scalar(select(AgentAction).where(AgentAction.action_type == "calendar.book"))
        assert action is not None and action.status == "waiting_approval"
        approval = db.get(Approval, action.approval_id)
        assert approval is not None and approval.status == "pending"
        assert approval.action == "calendar.book"

        # Owner approves
        approvals.decide(
            db,
            clock,
            ctx,
            approval.id,
            decision="approve",
            payload_hash=approval.payload_hash,
        )
        db.commit()

    fake.queue_step(result())
    drain(session_factory, clock)

    with session_factory() as db:
        appt = db.scalar(select(CalendarAppointment))
        assert appt is not None and appt.status == "scheduled"
        assert appt.external_event_id is not None
        assert len(db.scalars(select(SimCalendarEvent)).all()) == 1


def test_cross_customer_isolation_on_list_and_modify_appointments(session_factory, clock):
    """INV-03: Customer B in DM cannot view, reschedule, or cancel Customer A's appointments."""
    ctx, account_id, external_id, settings, conn_id = _setup_calendar_world(session_factory, clock)
    world = (ctx, account_id, external_id, settings)

    # Deliver messages from Customer A and Customer B to establish two DM threads & identities
    deliver(session_factory, clock, world, text="Hello from A", customer="customer-a")
    process_inbound(session_factory, clock)
    deliver(session_factory, clock, world, text="Hello from B", customer="customer-b")
    process_inbound(session_factory, clock)

    tz = ZoneInfo(ctx.timezone)
    tomorrow = (clock.now().astimezone(tz) + timedelta(days=1)).date()
    date_str = tomorrow.isoformat()

    broker = build_default_broker()
    with session_factory() as db:
        threads = db.scalars(
            select(AgentThread).where(AgentThread.surface == "dm").order_by(AgentThread.created_at)
        ).all()
        assert len(threads) == 2
        thread_a, thread_b = threads[0], threads[1]
        assert thread_a.customer_identity_id != thread_b.customer_identity_id

        ctx_a = BrokerContext(ctx, account_id, thread_a.id, "dm", "customer")
        ctx_b = BrokerContext(ctx, account_id, thread_b.id, "dm", "customer")

        # Customer A books an appointment
        book_res = broker.dispatch(
            db,
            clock,
            ctx_a,
            name="calendar.book",
            version="v1",
            arguments={
                "local_date": date_str,
                "local_time": "15:00",
                "duration_minutes": 60,
                "title": "Customer A Session",
                "customer_name": "Customer A",
            },
        )
        assert book_res.ok, book_res
        db.commit()

    drain(session_factory, clock)

    with session_factory() as db:
        appt = db.scalar(select(CalendarAppointment))
        assert appt is not None and appt.status == "scheduled"
        appt_id = str(appt.id)
        ctx_a = BrokerContext(ctx, account_id, thread_a.id, "dm", "customer")
        ctx_b = BrokerContext(ctx, account_id, thread_b.id, "dm", "customer")

        # Customer A can list their appointment
        list_a = broker.dispatch(
            db, clock, ctx_a, name="calendar.list_appointments", version="v1", arguments={}
        )
        assert list_a.ok and len(list_a.data["appointments"]) == 1

        # Customer B sees zero appointments
        list_b = broker.dispatch(
            db, clock, ctx_b, name="calendar.list_appointments", version="v1", arguments={}
        )
        assert list_b.ok and list_b.data["appointments"] == []

        # Customer B attempting to cancel Customer A's appointment fails closed
        mod_b = broker.dispatch(
            db,
            clock,
            ctx_b,
            name="calendar.modify",
            version="v1",
            arguments={
                "appointment_id": appt_id,
                "expected_version": appt.version,
                "operation": "cancel",
                "reason": "Unauthorized cancel attempt",
            },
        )
        assert mod_b.ok and mod_b.data.get("ok") is False

        # Customer A reschedules their own appointment to 16:00
        mod_a = broker.dispatch(
            db,
            clock,
            ctx_a,
            name="calendar.modify",
            version="v1",
            arguments={
                "appointment_id": appt_id,
                "expected_version": appt.version,
                "operation": "reschedule",
                "new_local_date": date_str,
                "new_local_time": "16:00",
                "duration_minutes": 60,
            },
        )
        assert mod_a.ok and mod_a.data.get("ok") is True
        db.commit()

    drain(session_factory, clock)

    with session_factory() as db:
        appt = db.get(CalendarAppointment, uuid.UUID(appt_id))
        assert appt is not None and appt.status == "scheduled"
        assert appt.start_at.astimezone(tz).strftime("%H:%M") == "16:00"

        # Customer A cancels their appointment
        ctx_a = BrokerContext(ctx, account_id, thread_a.id, "dm", "customer")
        cancel_a = broker.dispatch(
            db,
            clock,
            ctx_a,
            name="calendar.modify",
            version="v1",
            arguments={
                "appointment_id": appt_id,
                "expected_version": appt.version,
                "operation": "cancel",
                "reason": "Change of plans",
            },
        )
        assert cancel_a.ok and cancel_a.data.get("ok") is True
        db.commit()

    drain(session_factory, clock)

    with session_factory() as db:
        appt = db.get(CalendarAppointment, uuid.UUID(appt_id))
        assert appt is not None and appt.status == "cancelled"
        sim_ev = db.scalar(
            select(SimCalendarEvent).where(
                SimCalendarEvent.external_event_id == appt.external_event_id
            )
        )
        assert sim_ev is not None and sim_ev.status == "cancelled"


def test_reconcile_calendar_operation_recovers_outcome_unknown(session_factory, clock):
    """When a calendar operation is left in outcome_unknown, reconciliation recovers it."""
    ctx, account_id, external_id, settings, conn_id = _setup_calendar_world(session_factory, clock)
    world = (ctx, account_id, external_id, settings)
    deliver(session_factory, clock, world, text="Hello", customer="customer-rec")
    process_inbound(session_factory, clock)

    tz = ZoneInfo(ctx.timezone)
    tomorrow = (clock.now().astimezone(tz) + timedelta(days=1)).date()
    date_str = tomorrow.isoformat()

    broker = build_default_broker()
    with session_factory() as db:
        thread = db.scalar(select(AgentThread).where(AgentThread.surface == "dm"))
        assert thread is not None
        b_ctx = BrokerContext(ctx, account_id, thread.id, "dm", "customer")
        res = broker.dispatch(
            db,
            clock,
            b_ctx,
            name="calendar.book",
            version="v1",
            arguments={
                "local_date": date_str,
                "local_time": "11:00",
                "duration_minutes": 60,
                "title": "Reconcile Session",
                "customer_name": "Rec User",
            },
        )
        assert res.ok
        db.commit()

    # Let the operation execute first, then simulate crash before tx2 (outcome_unknown)
    drain(session_factory, clock)

    with session_factory() as db:
        op = db.scalar(select(Operation).where(Operation.operation_type == "calendar_create_event"))
        appt = db.scalar(select(CalendarAppointment))
        assert op is not None and appt is not None and appt.agent_action_id is not None
        appt_id = appt.id
        action = db.get(AgentAction, appt.agent_action_id)
        assert action is not None
        op.status = "outcome_unknown"
        appt.status = "pending"
        appt.external_event_id = None
        action.status = "outcome_unknown"
        db.commit()
        op_id = op.id

    status = calendar_ops.reconcile_calendar_operation(session_factory, clock, settings, op_id)
    assert status == "succeeded"

    with session_factory() as db:
        op = db.get(Operation, op_id)
        appt = db.get(CalendarAppointment, appt_id)
        assert op is not None and appt is not None and appt.agent_action_id is not None
        action = db.get(AgentAction, appt.agent_action_id)
        assert action is not None
        assert op.status == "succeeded"
        assert appt.status == "scheduled" and appt.external_event_id is not None
        assert action.status == "succeeded"


def test_calendar_api_endpoints_and_oauth_flow(db_session, make_client, clock):
    """Test calendar REST endpoints (list, connect-mock, patch, appointments, disconnect)."""
    from tests.helpers.env import build_env

    env = build_env(db_session, make_client, clock)
    # Initially empty
    res = env.call(env.owner, "GET", "/calendar")
    assert res.status_code == 200
    assert res.json()["items"] == []

    # Staff cannot connect calendar
    res_staff = env.call(env.staff, "POST", "/calendar/connect-mock", json={})
    assert res_staff.status_code == 403

    # Owner connects mock calendar
    res_conn = env.call(
        env.owner,
        "POST",
        "/calendar/connect-mock",
        json={
            "account_email": "owner@golkent.test",
            "calendar_summary": "Golkent Bookings",
            "default_slot_duration_minutes": 45,
        },
    )
    assert res_conn.status_code == 201
    conn_data = res_conn.json()
    conn_id = conn_data["id"]
    assert conn_data["account_email"] == "owner@golkent.test"
    assert conn_data["default_slot_duration_minutes"] == 45
    assert conn_data["status"] == "connected"
    assert conn_data["is_simulated"] is True

    # Update slot duration
    res_patch = env.call(
        env.owner,
        "PATCH",
        f"/calendar/{conn_id}",
        json={"default_slot_duration_minutes": 60},
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["default_slot_duration_minutes"] == 60

    # List appointments
    res_appts = env.call(env.owner, "GET", "/calendar/appointments")
    assert res_appts.status_code == 200
    assert res_appts.json()["items"] == []

    # Disconnect
    res_disc = env.call(env.owner, "POST", f"/calendar/{conn_id}/disconnect")
    assert res_disc.status_code == 200
    assert res_disc.json()["status"] == "disconnected"
    conn_row = db_session.get(CalendarConnection, uuid.UUID(conn_id))
    assert conn_row is not None and conn_row.access_token_ciphertext is None
