"""Unit tests for owner channel abstraction, delivery policy engine, quiet hours, and jobs.

(ADR-012 / ADR-014 / Phase 9 Session 03)
Covers:
- WebChannel implementation and OwnerChannel protocol conformance.
- Channel registry lazy loading, dynamic registration, and error handling.
- Quiet hours boundary conditions (21:59 vs 22:00 vs 22:01, 07:59 vs 08:00 vs 08:01, midnight).
- Quiet hours across timezones: UTC, Europe/Istanbul (+3), America/New_York, fallback.
- Critical severity bypass of quiet hours.
- Urgent approval expiry (< 2 hours) bypass vs non-urgent (>= 2 hours) skipped.
- Notification routing matrix (immediate, quiet-hours-subject, web-only).
- Web channel immediate delivery bypass.
- Durable delivery job lifecycle: claim, deliver outside transaction, record outcome, handle errors.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import FrozenClock
from app.core.db import set_tenant_context
from app.identity.models import ChannelLink
from app.integrations.channels.base import (
    ChannelRecipient,
    DeliveryResult,
    OwnerChannel,
    WebChannel,
)
from app.integrations.channels.registry import (
    get_channel,
    list_registered_channels,
    register_channel,
    reset_channel_registry,
)
from app.jobs.models import Job
from app.jobs.registry import JobContext
from app.notifications.delivery_policy import (
    evaluate_delivery_policy,
    is_in_quiet_hours,
    resolve_timezone,
)
from app.notifications.jobs import (
    DeliverChannelNotificationPayload,
    deliver_channel_notification,
    dispatch_channel_notification,
)
from app.notifications.models import Notification, NotificationDelivery
from tests.factories import workspace_with_members


class MockChannel:
    """Mock OwnerChannel for testing delivery dispatch."""

    def __init__(
        self, name: str = "mock", succeed: bool = True, error_msg: str | None = None
    ) -> None:
        self.name = name
        self.succeed = succeed
        self.error_msg = error_msg
        self.delivered_calls: list[tuple[uuid.UUID, ChannelRecipient]] = []

    def deliver_notification(
        self,
        session: Session,
        clock: Any,
        delivery: NotificationDelivery,
        recipient: ChannelRecipient,
    ) -> DeliveryResult:
        self.delivered_calls.append((delivery.id, recipient))
        if self.succeed:
            return DeliveryResult(
                success=True,
                status="delivered",
                delivered_at=clock.now(),
                metadata={"mock": True},
            )
        return DeliveryResult(
            success=False,
            status="failed",
            error_message=self.error_msg or "mock failure",
        )

    def render_command_result(
        self,
        session: Session,
        clock: Any,
        command: Any,
        recipient: ChannelRecipient,
    ) -> None:
        return None


# ---------------------------------------------------------------------------
# 1. Base Protocol & WebChannel Tests
# ---------------------------------------------------------------------------


def test_web_channel_protocol_conformance() -> None:
    web = WebChannel()
    assert isinstance(web, OwnerChannel)
    assert web.name == "web"

    clock = FrozenClock(datetime(2026, 11, 4, 12, 0, tzinfo=UTC))
    recipient = ChannelRecipient(
        user_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        channel="web",
    )
    delivery = NotificationDelivery(
        id=uuid.uuid4(),
        workspace_id=recipient.workspace_id,
        notification_id=uuid.uuid4(),
        recipient_user_id=recipient.user_id,
        channel="web",
        status="pending",
    )

    result = web.deliver_notification(MagicMock(), clock, delivery, recipient)
    assert result.success is True
    assert result.status == "delivered"
    assert result.delivered_at == clock.now()
    assert result.metadata.get("in_app") is True

    # Web render command is a clean no-op
    assert web.render_command_result(MagicMock(), clock, None, recipient) is None


# ---------------------------------------------------------------------------
# 2. Channel Registry Tests
# ---------------------------------------------------------------------------


def test_channel_registry_operations() -> None:
    reset_channel_registry()

    assert "web" in list_registered_channels()
    web = get_channel("web")
    assert isinstance(web, WebChannel)

    mock = MockChannel(name="telegram")
    register_channel("telegram", mock)
    assert get_channel("telegram") is mock

    with pytest.raises(KeyError, match="Unknown owner channel: 'unknown'"):
        get_channel("unknown")

    reset_channel_registry()
    assert "telegram" not in list_registered_channels()


# ---------------------------------------------------------------------------
# 3. Quiet Hours Boundary & Overnight Window Tests
# ---------------------------------------------------------------------------


def test_quiet_hours_boundary_conditions_utc() -> None:
    # 21:59:59 is still awake
    dt_awake_evening = datetime(2026, 11, 4, 21, 59, 59, tzinfo=UTC)
    assert is_in_quiet_hours(dt_awake_evening, tz_name="UTC") is False

    # 22:00:00 starts quiet hours
    dt_quiet_start = datetime(2026, 11, 4, 22, 0, 0, tzinfo=UTC)
    assert is_in_quiet_hours(dt_quiet_start, tz_name="UTC") is True

    # 22:01:00 is quiet
    dt_quiet_night = datetime(2026, 11, 4, 22, 1, 0, tzinfo=UTC)
    assert is_in_quiet_hours(dt_quiet_night, tz_name="UTC") is True

    # 23:59:59 is quiet
    dt_before_midnight = datetime(2026, 11, 4, 23, 59, 59, tzinfo=UTC)
    assert is_in_quiet_hours(dt_before_midnight, tz_name="UTC") is True

    # 00:00:00 (midnight) is quiet
    dt_midnight = datetime(2026, 11, 5, 0, 0, 0, tzinfo=UTC)
    assert is_in_quiet_hours(dt_midnight, tz_name="UTC") is True

    # 04:30:00 is quiet
    dt_early_morning = datetime(2026, 11, 5, 4, 30, 0, tzinfo=UTC)
    assert is_in_quiet_hours(dt_early_morning, tz_name="UTC") is True

    # 07:59:59 is quiet
    dt_before_morning = datetime(2026, 11, 5, 7, 59, 59, tzinfo=UTC)
    assert is_in_quiet_hours(dt_before_morning, tz_name="UTC") is True

    # 08:00:00 morning boundary ends quiet hours
    dt_morning_end = datetime(2026, 11, 5, 8, 0, 0, tzinfo=UTC)
    assert is_in_quiet_hours(dt_morning_end, tz_name="UTC") is False

    # 08:00:01 is awake
    dt_morning_awake = datetime(2026, 11, 5, 8, 0, 1, tzinfo=UTC)
    assert is_in_quiet_hours(dt_morning_awake, tz_name="UTC") is False

    # 14:00:00 afternoon is awake
    dt_afternoon = datetime(2026, 11, 5, 14, 0, 0, tzinfo=UTC)
    assert is_in_quiet_hours(dt_afternoon, tz_name="UTC") is False


# ---------------------------------------------------------------------------
# 4. Quiet Hours Across Timezones
# ---------------------------------------------------------------------------


def test_quiet_hours_across_timezones() -> None:
    # Europe/Istanbul is UTC+3 (no DST)
    # 19:00 UTC = 22:00 in Istanbul -> quiet hours start
    dt_istanbul_start = datetime(2026, 11, 4, 19, 0, 0, tzinfo=UTC)
    assert is_in_quiet_hours(dt_istanbul_start, tz_name="Europe/Istanbul") is True

    # 18:59:59 UTC = 21:59:59 in Istanbul -> awake
    dt_istanbul_awake = datetime(2026, 11, 4, 18, 59, 59, tzinfo=UTC)
    assert is_in_quiet_hours(dt_istanbul_awake, tz_name="Europe/Istanbul") is False

    # 04:59:59 UTC = 07:59:59 in Istanbul -> quiet
    dt_istanbul_morning = datetime(2026, 11, 5, 4, 59, 59, tzinfo=UTC)
    assert is_in_quiet_hours(dt_istanbul_morning, tz_name="Europe/Istanbul") is True

    # 05:00:00 UTC = 08:00:00 in Istanbul -> awake
    dt_istanbul_woken = datetime(2026, 11, 5, 5, 0, 0, tzinfo=UTC)
    assert is_in_quiet_hours(dt_istanbul_woken, tz_name="Europe/Istanbul") is False

    # America/New_York in standard time (EST is UTC-5)
    # In January: 03:00 UTC = 22:00 in New York -> quiet hours start
    dt_ny_start = datetime(2026, 1, 15, 3, 0, 0, tzinfo=UTC)
    assert is_in_quiet_hours(dt_ny_start, tz_name="America/New_York") is True

    # 02:59:59 UTC = 21:59:59 in New York -> awake
    dt_ny_awake = datetime(2026, 1, 15, 2, 59, 59, tzinfo=UTC)
    assert is_in_quiet_hours(dt_ny_awake, tz_name="America/New_York") is False

    # 13:00:00 UTC = 08:00:00 in New York -> awake
    dt_ny_woken = datetime(2026, 1, 15, 13, 0, 0, tzinfo=UTC)
    assert is_in_quiet_hours(dt_ny_woken, tz_name="America/New_York") is False

    # Invalid / empty timezone safely defaults to UTC
    assert resolve_timezone(None).key == "UTC"
    assert resolve_timezone("").key == "UTC"
    assert resolve_timezone("Nonexistent/Invalid_Timezone").key == "UTC"
    assert is_in_quiet_hours(dt_istanbul_start, tz_name="Nonexistent/Invalid_Timezone") is False


def test_custom_same_day_quiet_window() -> None:
    # Test a custom daytime window e.g. 13:00 to 15:00 (start < end)
    custom_start = time(13, 0)
    custom_end = time(15, 0)

    before = datetime(2026, 11, 4, 12, 59, 59, tzinfo=UTC)
    assert is_in_quiet_hours(before, "UTC", custom_start, custom_end) is False

    inside = datetime(2026, 11, 4, 13, 30, 0, tzinfo=UTC)
    assert is_in_quiet_hours(inside, "UTC", custom_start, custom_end) is True

    after = datetime(2026, 11, 4, 15, 0, 0, tzinfo=UTC)
    assert is_in_quiet_hours(after, "UTC", custom_start, custom_end) is False


# ---------------------------------------------------------------------------
# 5. Critical Severity & Urgent Expiry Bypass Tests
# ---------------------------------------------------------------------------


def test_critical_severity_bypasses_quiet_hours() -> None:
    # 02:00 UTC (quiet hours)
    clock = FrozenClock(datetime(2026, 11, 4, 2, 0, 0, tzinfo=UTC))
    recipient = ChannelRecipient(
        user_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        channel="telegram",
        timezone="UTC",
    )

    notif = Notification(
        id=uuid.uuid4(),
        workspace_id=recipient.workspace_id,
        recipient_user_id=recipient.user_id,
        type="account.needs_reauth",
        severity="critical",
        params={},
    )

    decision = evaluate_delivery_policy(notif, recipient, clock, channel="telegram")
    assert decision.should_deliver is True
    assert decision.status == "pending"
    assert decision.is_quiet_hours is True
    assert decision.bypassed_quiet_hours is True
    assert "critical" in decision.reason


def test_urgent_approval_expiry_bypasses_quiet_hours() -> None:
    # 03:00 UTC (quiet hours)
    now = datetime(2026, 11, 4, 3, 0, 0, tzinfo=UTC)
    clock = FrozenClock(now)
    recipient = ChannelRecipient(
        user_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        channel="telegram",
        timezone="UTC",
    )

    # Urgent approval: expires in 45 minutes (< 2 hours)
    urgent_expiry = now + timedelta(minutes=45)
    urgent_notif = Notification(
        id=uuid.uuid4(),
        workspace_id=recipient.workspace_id,
        recipient_user_id=recipient.user_id,
        type="approval.requested",
        severity="attention",
        params={"expires_at": urgent_expiry.isoformat()},
    )

    decision = evaluate_delivery_policy(urgent_notif, recipient, clock, channel="telegram")
    assert decision.should_deliver is True
    assert decision.status == "pending"
    assert decision.is_quiet_hours is True
    assert decision.bypassed_quiet_hours is True
    assert "approval_expiring_soon" in decision.reason

    # Non-urgent approval: expires in 5 hours (>= 2 hours) -> skipped during quiet hours
    leisure_expiry = now + timedelta(hours=5)
    leisure_notif = Notification(
        id=uuid.uuid4(),
        workspace_id=recipient.workspace_id,
        recipient_user_id=recipient.user_id,
        type="approval.requested",
        severity="attention",
        params={"expires_at": leisure_expiry.isoformat()},
    )

    decision_leisure = evaluate_delivery_policy(leisure_notif, recipient, clock, channel="telegram")
    assert decision_leisure.should_deliver is False
    assert decision_leisure.status == "skipped_quiet_hours"
    assert decision_leisure.is_quiet_hours is True
    assert decision_leisure.bypassed_quiet_hours is False


# ---------------------------------------------------------------------------
# 6. Notification Routing Matrix Tests
# ---------------------------------------------------------------------------


def test_routing_matrix_evaluations() -> None:
    # 14:00 UTC (daytime, awake)
    day_clock = FrozenClock(datetime(2026, 11, 4, 14, 0, 0, tzinfo=UTC))
    recipient = ChannelRecipient(
        user_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        channel="telegram",
        timezone="UTC",
    )

    # 1. Immediate types pushed outside quiet hours
    for notif_type in ["approval.requested", "approval.expired", "owner_question.created"]:
        n = Notification(
            id=uuid.uuid4(),
            workspace_id=recipient.workspace_id,
            recipient_user_id=recipient.user_id,
            type=notif_type,
            severity="attention"
            if "requested" in notif_type or "created" in notif_type
            else "info",
            params={},
        )
        d = evaluate_delivery_policy(n, recipient, day_clock, channel="telegram")
        assert d.should_deliver is True
        assert d.status == "pending"
        assert d.is_quiet_hours is False

    # 2. Quiet-hours-subject items pushed outside quiet hours, skipped during quiet hours
    report_notif = Notification(
        id=uuid.uuid4(),
        workspace_id=recipient.workspace_id,
        recipient_user_id=recipient.user_id,
        type="report.daily_ready",
        severity="info",
        params={},
    )
    d_day = evaluate_delivery_policy(report_notif, recipient, day_clock, channel="telegram")
    assert d_day.should_deliver is True
    assert d_day.status == "pending"

    night_clock = FrozenClock(datetime(2026, 11, 4, 23, 0, 0, tzinfo=UTC))
    d_night = evaluate_delivery_policy(report_notif, recipient, night_clock, channel="telegram")
    assert d_night.should_deliver is False
    assert d_night.status == "skipped_quiet_hours"
    assert d_night.is_quiet_hours is True

    # 3. Routine info notifications are web-only
    for routine_type in ["content.published", "knowledge.fact_changed", "member.joined"]:
        routine_notif = Notification(
            id=uuid.uuid4(),
            workspace_id=recipient.workspace_id,
            recipient_user_id=recipient.user_id,
            type=routine_type,
            severity="info",
            params={},
        )
        d_routine = evaluate_delivery_policy(
            routine_notif, recipient, day_clock, channel="telegram"
        )
        assert d_routine.should_deliver is False
        assert d_routine.status == "web_only"
        assert d_routine.reason == "routine_info_web_only"

    # 4. Web channel always delivers immediately
    d_web = evaluate_delivery_policy(routine_notif, recipient, night_clock, channel="web")
    assert d_web.should_deliver is True
    assert d_web.status == "pending"
    assert d_web.channel == "web"


# ---------------------------------------------------------------------------
# 7. Durable Delivery Job Execution & DB Lifecycle Tests
# ---------------------------------------------------------------------------


def test_dispatch_and_deliver_channel_notification_success(
    db_session: Session,
) -> None:
    ws, users = workspace_with_members(db_session, name="Delivery Test WS")
    owner = users["owner"]
    set_tenant_context(db_session, ws.id)

    clock = FrozenClock(datetime(2026, 11, 4, 14, 0, 0, tzinfo=UTC))

    # Link telegram channel
    link = ChannelLink(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        user_id=owner.id,
        channel="telegram",
        channel_user_id="tg_12345",
        channel_chat_id="chat_67890",
        channel_username="owner_bot",
        status="active",
        linked_at=clock.now(),
    )
    db_session.add(link)
    db_session.flush()

    # Create notification
    notif = Notification(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        recipient_user_id=owner.id,
        type="approval.requested",
        severity="attention",
        params={"summary": "Approve price update"},
        created_at=clock.now(),
        updated_at=clock.now(),
    )
    db_session.add(notif)
    db_session.flush()

    recipient = ChannelRecipient(
        user_id=owner.id,
        workspace_id=ws.id,
        channel="telegram",
        channel_user_id=link.channel_user_id,
        channel_chat_id=link.channel_chat_id,
        timezone="UTC",
    )

    # Register mock telegram channel
    reset_channel_registry()
    mock_channel = MockChannel(name="telegram", succeed=True)
    register_channel("telegram", mock_channel)

    # Dispatch channel notification
    delivery = dispatch_channel_notification(
        db_session,
        clock,
        workspace_id=ws.id,
        notification=notif,
        recipient=recipient,
        channel="telegram",
        channel_link_id=link.id,
    )
    db_session.commit()

    assert delivery.status == "pending"
    assert delivery.attempt_count == 0

    # Verify job enqueued
    job_row = db_session.scalar(
        select(Job).where(
            Job.job_type == "deliver_channel_notification",
            Job.workspace_id == ws.id,
        )
    )
    assert job_row is not None
    assert job_row.payload["delivery_id"] == str(delivery.id)

    # Run deliver_channel_notification worker
    session_factory = sessionmaker(bind=db_session.get_bind())
    job_ctx = JobContext(
        job_id=job_row.id,
        job_type="deliver_channel_notification",
        workspace_id=ws.id,
        correlation_id=None,
        payload=DeliverChannelNotificationPayload(delivery_id=delivery.id),
        attempt=1,
        max_attempts=3,
        session_factory=session_factory,
        clock=clock,
        _heartbeat=lambda: None,
    )

    deliver_channel_notification(job_ctx)

    db_session.expire_all()
    # Verify delivery record updated to delivered
    updated_delivery = db_session.get(NotificationDelivery, delivery.id)
    assert updated_delivery is not None
    assert updated_delivery.status == "delivered"
    assert updated_delivery.attempt_count == 1
    assert updated_delivery.sent_at == clock.now()
    assert updated_delivery.last_error is None
    assert len(mock_channel.delivered_calls) == 1
    assert mock_channel.delivered_calls[0][0] == delivery.id


def test_deliver_channel_notification_failure_records_error(
    db_session: Session,
) -> None:
    ws, users = workspace_with_members(db_session, name="Delivery Fail WS")
    owner = users["owner"]
    set_tenant_context(db_session, ws.id)

    clock = FrozenClock(datetime(2026, 11, 4, 14, 0, 0, tzinfo=UTC))

    notif = Notification(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        recipient_user_id=owner.id,
        type="approval.requested",
        severity="attention",
        params={},
        created_at=clock.now(),
        updated_at=clock.now(),
    )
    db_session.add(notif)
    db_session.flush()

    delivery = NotificationDelivery(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        notification_id=notif.id,
        recipient_user_id=owner.id,
        channel="telegram",
        status="pending",
        attempt_count=0,
    )
    db_session.add(delivery)
    db_session.commit()

    reset_channel_registry()
    mock_channel = MockChannel(
        name="telegram", succeed=False, error_msg="Telegram API 403 Forbidden"
    )
    register_channel("telegram", mock_channel)

    session_factory = sessionmaker(bind=db_session.get_bind())
    job_ctx = JobContext(
        job_id=uuid.uuid4(),
        job_type="deliver_channel_notification",
        workspace_id=ws.id,
        correlation_id=None,
        payload=DeliverChannelNotificationPayload(delivery_id=delivery.id),
        attempt=1,
        max_attempts=3,
        session_factory=session_factory,
        clock=clock,
        _heartbeat=lambda: None,
    )

    with pytest.raises(RuntimeError, match="Telegram API 403 Forbidden"):
        deliver_channel_notification(job_ctx)

    db_session.expire_all()
    updated_delivery = db_session.get(NotificationDelivery, delivery.id)
    assert updated_delivery is not None
    assert updated_delivery.status == "failed"
    assert updated_delivery.attempt_count == 1
    assert "Telegram API 403 Forbidden" in (updated_delivery.last_error or "")


def test_dispatch_channel_notification_skipped_during_quiet_hours(
    db_session: Session,
) -> None:
    ws, users = workspace_with_members(db_session, name="Quiet Hours WS")
    owner = users["owner"]
    set_tenant_context(db_session, ws.id)

    # 23:00 UTC (quiet hours)
    clock = FrozenClock(datetime(2026, 11, 4, 23, 0, 0, tzinfo=UTC))

    notif = Notification(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        recipient_user_id=owner.id,
        type="report.daily_ready",
        severity="info",
        params={},
        created_at=clock.now(),
        updated_at=clock.now(),
    )
    db_session.add(notif)
    db_session.flush()

    recipient = ChannelRecipient(
        user_id=owner.id,
        workspace_id=ws.id,
        channel="telegram",
        timezone="UTC",
    )

    delivery = dispatch_channel_notification(
        db_session,
        clock,
        workspace_id=ws.id,
        notification=notif,
        recipient=recipient,
        channel="telegram",
    )
    db_session.commit()

    assert delivery.status == "skipped_quiet_hours"

    # Verify no delivery job enqueued for skipped quiet hours
    job_row = db_session.scalar(
        select(Job).where(
            Job.job_type == "deliver_channel_notification",
            Job.workspace_id == ws.id,
        )
    )
    assert job_row is None
