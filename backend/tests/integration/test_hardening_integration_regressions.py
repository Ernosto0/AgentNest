"""Targeted commits/PostgreSQL regression tests for calendar, Telegram, and recovery fixes."""

from __future__ import annotations

import contextlib
import json
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.agent.models import ACTIVE_RUN_STATES, AgentAction, AgentSession, AgentThread
from app.agent.tools.broker import BrokerContext, build_default_broker
from app.content.models import MediaAsset
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.db import set_tenant_context
from app.identity.channels import ChannelLinkService
from app.integrations.calendar.models import (
    CalendarAppointment,
    SimCalendarEvent,
)
from app.integrations.channels.telegram import TelegramClient, process_update
from app.integrations.channels.telegram.handlers import get_pending_media, set_pending_media
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.operations import calendar as calendar_ops
from app.operations.models import Operation
from app.owner_requests.models import OwnerQuestion
from tests.factories import knowledge_ctx, workspace_with_members
from tests.integration.agent.test_calendar_agent import _setup_calendar_world, open_goal
from tests.integration.agent.test_dm import deliver, process_inbound, setup

pytestmark = pytest.mark.commits


class _MockTelegramHandler:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        url_path = urlparse(str(request.url)).path
        method_name = url_path.split("/")[-1]
        body: dict[str, Any] = {}
        if request.headers.get("content-type", "").startswith("application/json"):
            body = json.loads(request.content.decode("utf-8"))
        elif request.content:
            with contextlib.suppress(Exception):
                body = {
                    k: v[0]
                    for k, v in parse_qs(request.content.decode("utf-8", errors="ignore")).items()
                }
        self.calls.append({"api_method": method_name, "body": body})
        if method_name in ("sendMessage", "editMessageText"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "message_id": len(self.calls) + 200,
                        "chat": {"id": body.get("chat_id", 123456), "type": "private"},
                        "text": body.get("text", ""),
                        "date": 1700000000,
                    },
                },
            )
        return httpx.Response(200, json={"ok": True, "result": True})


def test_serious6_unverified_hours_never_invented(
    session_factory: sessionmaker[Session], clock: FrozenClock
) -> None:
    """When weekly_hours is absent, availability returns empty slots and unavailable."""
    settings = Settings(
        _env_file=None,
        llm_provider="fake",
        instagram_enabled_providers="mock",
        calendar_enabled_providers="mock",
        media_storage_backend="local",
    )
    with session_factory() as db:
        ws, users = workspace_with_members(db, default_locale="en")
        ctx = knowledge_ctx(ws, users["owner"], "owner")
        calendar_ops.connect_mock_calendar(
            db,
            clock,
            ctx,
            settings,
            account_email="nohours@example.com",
            calendar_summary="No Hours Calendar",
            default_slot_duration_minutes=60,
        )
        db.commit()
        ws_id = ws.id
        tz = ZoneInfo(ws.timezone)

    tomorrow = (clock.now().astimezone(tz) + timedelta(days=1)).date()
    day_start = datetime.combine(tomorrow, time(0, 0), tzinfo=tz).astimezone(UTC)
    day_end = datetime.combine(tomorrow + timedelta(days=1), time(0, 0), tzinfo=tz).astimezone(UTC)
    noon = datetime.combine(tomorrow, time(12, 0), tzinfo=tz).astimezone(UTC)

    avail = calendar_ops.check_availability(
        session_factory,
        clock,
        settings,
        ws_id,
        window_start=day_start,
        window_end=day_end,
        duration_minutes=60,
        requested_start_at=noon,
    )
    assert avail.calendar_connected is True
    assert avail.hours_verified is False
    assert avail.requested_slot_available is False
    assert avail.available_slots == []


def test_serious5_pending_approval_holds_slot_and_db_rejects_overlap(
    session_factory: sessionmaker[Session], clock: FrozenClock
) -> None:
    """Pending approval holds block concurrent bookings; DB gist constraint rejects overlaps."""
    ctx, account_id, external_id, settings, conn_id = _setup_calendar_world(
        session_factory, clock, book_mode="ask"
    )
    world = (ctx, account_id, external_id, settings)
    deliver(session_factory, clock, world, text="Hello A", customer="cust-hold-a")
    process_inbound(session_factory, clock)
    deliver(session_factory, clock, world, text="Hello B", customer="cust-hold-b")
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
        open_goal(db, threads[0])
        open_goal(db, threads[1])
        ctx_a = BrokerContext(ctx, account_id, threads[0].id, "dm", "customer")
        ctx_b = BrokerContext(ctx, account_id, threads[1].id, "dm", "customer")

        # Mark both sessions waiting_active / running so calendar.book executes cleanly
        res_a = broker.dispatch(
            db,
            clock,
            ctx_a,
            name="calendar.book",
            version="v1",
            arguments={
                "local_date": date_str,
                "local_time": "14:00",
                "duration_minutes": 60,
                "title": "Customer A Booking",
                "customer_name": "Cust A",
            },
        )
        assert res_a.ok and res_a.data.get("status") == "waiting_approval"

        # Customer B trying the same slot sees SLOT_UNAVAILABLE while A's approval is pending
        res_b = broker.dispatch(
            db,
            clock,
            ctx_b,
            name="calendar.book",
            version="v1",
            arguments={
                "local_date": date_str,
                "local_time": "14:00",
                "duration_minutes": 60,
                "title": "Customer B Conflict",
                "customer_name": "Cust B",
            },
        )
        assert res_b.ok and res_b.data.get("ok") is False
        assert res_b.data.get("error") == "SLOT_UNAVAILABLE"

        # Direct overlapping scheduled CalendarAppointment hits ex_calendar_appointments_no_overlap
        start_at = datetime.combine(tomorrow, time(10, 0), tzinfo=tz).astimezone(UTC)
        end_at = start_at + timedelta(hours=1)
        db.add(
            CalendarAppointment(
                id=uuid.uuid4(),
                workspace_id=ctx.workspace_id,
                calendar_connection_id=conn_id,
                title="First",
                start_at=start_at,
                end_at=end_at,
                timezone=ctx.timezone,
                status="scheduled",
                created_by_source="customer",
                is_simulated=True,
            )
        )
        db.commit()

    with session_factory() as db:
        db.add(
            CalendarAppointment(
                id=uuid.uuid4(),
                workspace_id=ctx.workspace_id,
                calendar_connection_id=conn_id,
                title="Overlapping Second",
                start_at=start_at + timedelta(minutes=30),
                end_at=end_at + timedelta(minutes=30),
                timezone=ctx.timezone,
                status="scheduled",
                created_by_source="customer",
                is_simulated=True,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_serious7_calendar_reconcile_retries_with_backoff_then_succeeds(
    session_factory: sessionmaker[Session], clock: FrozenClock
) -> None:
    """Missing external event on round 1 schedules round 2 instead of prematurely staying stuck."""
    ctx, account_id, _external_id, settings, conn_id = _setup_calendar_world(
        session_factory, clock, book_mode="automatic"
    )
    world = (ctx, account_id, _external_id, settings)
    deliver(session_factory, clock, world, text="Book me", customer="cust-reconcile")
    process_inbound(session_factory, clock)

    tz = ZoneInfo(ctx.timezone)
    tomorrow = (clock.now().astimezone(tz) + timedelta(days=1)).date()
    start_at = datetime.combine(tomorrow, time(11, 0), tzinfo=tz).astimezone(UTC)
    end_at = start_at + timedelta(hours=1)
    op_key = f"cal:reconcile:{uuid.uuid4().hex}"

    broker = build_default_broker()
    with session_factory() as db:
        thread = db.scalar(select(AgentThread).where(AgentThread.surface == "dm"))
        assert thread is not None
        if (
            db.scalar(
                select(AgentSession).where(
                    AgentSession.thread_id == thread.id,
                    AgentSession.status.in_(ACTIVE_RUN_STATES),
                )
            )
            is None
        ):
            goal = AgentSession(
                workspace_id=thread.workspace_id,
                thread_id=thread.id,
                goal_key=f"event:{thread.event_cursor}",
                initiating_event_cursor=thread.event_cursor,
            )
            db.add(goal)
            db.flush()
            thread.current_goal_key = goal.goal_key
        res = broker.dispatch(
            db,
            clock,
            BrokerContext(ctx, account_id, thread.id, "dm", "customer"),
            name="calendar.book",
            version="v1",
            arguments={
                "local_date": tomorrow.isoformat(),
                "local_time": "11:00",
                "duration_minutes": 60,
                "title": "Delayed Event",
                "customer_name": "Rec User",
            },
        )
        assert res.ok
        action = db.scalar(select(AgentAction))
        assert action is not None and action.payload_ref is not None

        appt = CalendarAppointment(
            id=action.payload_ref,
            workspace_id=ctx.workspace_id,
            calendar_connection_id=conn_id,
            title="Delayed Event",
            start_at=start_at,
            end_at=end_at,
            timezone=ctx.timezone,
            status="scheduled",
            created_by_source="customer",
            is_simulated=True,
        )
        db.add(appt)
        db.flush()

        op = Operation(
            id=uuid.uuid4(),
            workspace_id=ctx.workspace_id,
            operation_type="calendar_create_event",
            idempotency_key=op_key,
            subject_type="calendar_appointment",
            subject_id=appt.id,
            social_account_id=account_id,
            provider_kind="mock",
            status="outcome_unknown",
            provider_ref={"calendar_connection_id": str(conn_id)},
            is_simulated=True,
            started_at=clock.now(),
            created_at=clock.now(),
        )
        db.add(op)
        db.flush()
        action.operation_id = op.id
        action.status = "outcome_unknown"
        db.commit()
        op_id = op.id
        appt_id = appt.id

    # Round 1: external event not visible yet -> schedules round 2 instead of terminal fail
    calendar_ops.reconcile_calendar_operation(
        session_factory, clock, settings, ctx.workspace_id, op_id, round_num=1
    )

    with session_factory() as db:
        op_after_r1 = db.get(Operation, op_id)
        assert op_after_r1 is not None and op_after_r1.status == "outcome_unknown"
        reconcile_jobs = db.scalars(
            select(Job).where(Job.job_type == "reconcile_calendar_effect")
        ).all()
        assert len(reconcile_jobs) == 1
        assert reconcile_jobs[0].payload.get("round_num") == 2

        # External provider event now appears before round 2
        db.add(
            SimCalendarEvent(
                id=uuid.uuid4(),
                workspace_id=ctx.workspace_id,
                calendar_connection_id=conn_id,
                external_event_id=f"sim_evt_{uuid.uuid4().hex[:10]}",
                operation_key=op_key,
                title="Delayed Event",
                start_at=start_at,
                end_at=end_at,
                status="confirmed",
            )
        )
        db.commit()

    clock.advance(minutes=1)
    calendar_ops.reconcile_calendar_operation(
        session_factory, clock, settings, ctx.workspace_id, op_id, round_num=2
    )

    with session_factory() as db:
        op_final = db.get(Operation, op_id)
        appt_final = db.get(CalendarAppointment, appt_id)
        assert op_final is not None and op_final.status == "succeeded"
        assert appt_final is not None and appt_final.status == "scheduled"
        assert appt_final.external_event_id is not None


def test_serious8_telegram_messages_not_swallowed_and_target_replied_question(
    session_factory: sessionmaker[Session], clock: FrozenClock
) -> None:
    """Owner replies target quoted Q-<id>; unquoted replies clarify instead of swallowing."""
    world = setup(session_factory, clock, "automatic")
    ctx, account_id, _ext_id, _settings = world

    deliver(session_factory, clock, world, "Question about early bird?", customer="cust-q1")
    process_inbound(session_factory, clock)
    deliver(session_factory, clock, world, "Question about group discount?", customer="cust-q2")
    process_inbound(session_factory, clock)

    broker = build_default_broker()
    with session_factory() as db:
        threads = list(
            db.scalars(
                select(AgentThread)
                .where(AgentThread.surface == "dm")
                .order_by(AgentThread.created_at)
            )
        )
        assert len(threads) == 2
        for thread, req_info in zip(threads, ("exception", "business_policy"), strict=True):
            thread.current_goal_key = open_goal(db, thread).goal_key
            res = broker.dispatch(
                db,
                clock,
                BrokerContext(ctx, account_id, thread.id, "dm", "customer"),
                name="owner.ask",
                version="v1",
                arguments={
                    "question": f"Policy for {req_info}?",
                    "required_info": req_info,
                    "visibility": "customer_reply",
                    "holding_response": False,
                },
            )
            assert res.ok, res

        questions = list(db.scalars(select(OwnerQuestion).order_by(OwnerQuestion.created_at.asc())))
        assert len(questions) == 2
        q1_id, q2_id = questions[0].id, questions[1].id

        link = ChannelLinkService.generate_link_code(db, clock, ctx, channel="telegram")
        ChannelLinkService.redeem_link_code(
            db,
            clock,
            channel="telegram",
            channel_user_id="78100",
            channel_chat_id="78100",
            raw_code=link[0],
            channel_username="owner_q",
        )
        db.commit()

    mock_tg = _MockTelegramHandler()
    client = TelegramClient(token="BOT_TEST", transport=httpx.MockTransport(mock_tg.handle))

    # 1. Unquoted short text while 2 questions are pending must NOT swallow either question
    with session_factory() as db:
        process_update(
            db,
            clock,
            {
                "update_id": 8001,
                "message": {
                    "message_id": 901,
                    "date": 1700000000,
                    "chat": {"id": 78100, "type": "private"},
                    "from": {"id": 78100, "is_bot": False, "first_name": "Owner"},
                    "text": "300 TL",
                },
            },
            client=client,
        )

    with session_factory() as db:
        q1 = db.get(OwnerQuestion, q1_id)
        q2 = db.get(OwnerQuestion, q2_id)
        assert q1 is not None and q1.state == "pending"
        assert q2 is not None and q2.state == "pending"
    assert any("Q-" in str(c["body"].get("text", "")) for c in mock_tg.calls)

    # 2. Replying specifically to Q-<q1> answers q1 and leaves q2 pending
    with session_factory() as db:
        process_update(
            db,
            clock,
            {
                "update_id": 8002,
                "message": {
                    "message_id": 902,
                    "date": 1700000010,
                    "chat": {"id": 78100, "type": "private"},
                    "from": {"id": 78100, "is_bot": False, "first_name": "Owner"},
                    "reply_to_message": {
                        "message_id": 500,
                        "date": 1700000000,
                        "chat": {"id": 78100, "type": "private"},
                        "text": f"Asistanınız Bilgi Bekliyor\nRef: Q-{str(q1_id)[:8]}",
                    },
                    "text": "Erken kayıt için 350 TL uygundur.",
                },
            },
            client=client,
        )

    with session_factory() as db:
        q1 = db.get(OwnerQuestion, q1_id)
        q2 = db.get(OwnerQuestion, q2_id)
        assert q1 is not None and q1.state == "answered"
        assert q2 is not None and q2.state == "pending"

    # 3. With 1 pending question remaining (q2), explicit owner command must NOT be swallowed
    with session_factory() as db:
        process_update(
            db,
            clock,
            {
                "update_id": 8003,
                "message": {
                    "message_id": 903,
                    "date": 1700000020,
                    "chat": {"id": 78100, "type": "private"},
                    "from": {"id": 78100, "is_bot": False, "first_name": "Owner"},
                    "text": "Bugün rapor özetini göster",
                },
            },
            client=client,
        )

    with session_factory() as db:
        q2 = db.get(OwnerQuestion, q2_id)
        assert q2 is not None and q2.state == "pending"


def test_serious9_telegram_pending_media_persists_across_sessions(
    session_factory: sessionmaker[Session], clock: FrozenClock
) -> None:
    """Pending Telegram media uploaded to worker 1 is retrieved cleanly by worker 2."""
    with session_factory() as db1:
        ws, users = workspace_with_members(db1, name="Multi Worker Gym")
        owner = users["owner"]
        set_tenant_context(db1, ws.id)
        asset = MediaAsset(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            storage_backend="local",
            storage_key=f"test/{uuid.uuid4().hex}.jpg",
            mime_type="image/jpeg",
            byte_size=1024,
            sha256="ab" * 32,
            width=800,
            height=600,
            status="ready",
        )
        db1.add(asset)
        db1.flush()

        set_pending_media(owner.id, asset.id, clock.now(), session=db1, workspace_id=ws.id)
        db1.commit()
        owner_id, ws_id, asset_id = owner.id, ws.id, asset.id

    # Worker 2 (fresh Session) retrieves and pops the persisted media reference
    with session_factory() as db2:
        set_tenant_context(db2, ws_id)
        popped = get_pending_media(owner_id, clock.now(), session=db2, workspace_id=ws_id)
        db2.commit()
        assert popped == asset_id

    # Subsequent lookup finds nothing
    with session_factory() as db3:
        set_tenant_context(db3, ws_id)
        assert get_pending_media(owner_id, clock.now(), session=db3, workspace_id=ws_id) is None


def test_serious11_discover_stuck_operations_uses_clock_and_avoids_starvation(
    session_factory: sessionmaker[Session], clock: FrozenClock
) -> None:
    """discover_stuck_operations ignores >= 100 outcome_unknown rows and respects clock cutoff."""
    with session_factory() as db:
        ws, _users = workspace_with_members(db, name="Stuck Discovery Gym")
        set_tenant_context(db, ws.id)
        social = SocialAccount(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            provider_kind="mock",
            external_account_id=uuid.uuid4().hex,
            username="stuck_disc",
            capabilities={"messaging": True},
            status="connected",
        )
        db.add(social)
        db.flush()

        old_time = clock.now() - timedelta(hours=2)
        # Seed 120 older outcome_unknown rows that used to starve real stuck operations
        for idx in range(120):
            db.add(
                Operation(
                    id=uuid.uuid4(),
                    workspace_id=ws.id,
                    operation_type="send_reply",
                    idempotency_key=f"unknown:{idx}:{uuid.uuid4().hex}",
                    subject_type="reply_draft",
                    subject_id=uuid.uuid4(),
                    social_account_id=social.id,
                    provider_kind="mock",
                    status="outcome_unknown",
                    is_simulated=True,
                    started_at=old_time,
                    created_at=old_time,
                )
            )

        stuck_op = Operation(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            operation_type="publish_content",
            idempotency_key=f"stuck:{uuid.uuid4().hex}",
            subject_type="content_item",
            subject_id=uuid.uuid4(),
            social_account_id=social.id,
            provider_kind="mock",
            status="in_progress",
            is_simulated=True,
            started_at=clock.now() - timedelta(minutes=20),
            created_at=clock.now() - timedelta(minutes=20),
        )
        fresh_op = Operation(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            operation_type="send_reply",
            idempotency_key=f"fresh:{uuid.uuid4().hex}",
            subject_type="reply_draft",
            subject_id=uuid.uuid4(),
            social_account_id=social.id,
            provider_kind="mock",
            status="in_progress",
            is_simulated=True,
            started_at=clock.now() - timedelta(minutes=5),
            created_at=clock.now() - timedelta(minutes=5),
        )
        db.add_all([stuck_op, fresh_op])
        db.commit()
        stuck_id = stuck_op.id

    with session_factory() as db:
        cutoff = clock.now() - timedelta(minutes=15)
        rows = db.execute(
            text(
                "SELECT id, workspace_id, subject_type, status "
                "FROM discover_stuck_operations(:cutoff, 100)"
            ),
            {"cutoff": cutoff},
        ).all()
        assert [r[0] for r in rows] == [stuck_id]
        assert rows[0][2] == "content_item"
        assert rows[0][3] == "in_progress"
