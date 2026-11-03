"""Delivery policy engine & quiet hours evaluator (ADR-012, Phase 9 Session 03).

Determines whether a notification should be pushed immediately to an external owner channel
(such as Telegram), held/skipped due to quiet hours, or restricted to in-app web viewing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.clock import Clock
from app.integrations.channels.base import ChannelRecipient
from app.notifications.models import Notification

# Routing matrix categories
IMMEDIATE_TYPES: frozenset[str] = frozenset(
    {
        "approval.requested",
        "approval.expired",
        "owner_question.created",
        "owner_question.requested",
        "owner_question.window_closed",
        "system.integration_error",
        "account.needs_reauth",
    }
)

QUIET_HOURS_TYPES: frozenset[str] = frozenset(
    {
        "report.daily_ready",
        "content.scheduled",
        "content.on_hold",
        "content.failed",
        "conversation.needs_human",
        "reply.failed",
        "account.degraded",
        "account.permission_missing",
        "knowledge.promotion_expired",
    }
)

ROUTINE_INFO_TYPES: frozenset[str] = frozenset(
    {
        "content.published",
        "knowledge.fact_changed",
        "account.recovered",
        "member.joined",
        "owner_question.expired",
    }
)

DEFAULT_QUIET_START = time(22, 0)
DEFAULT_QUIET_END = time(8, 0)
EXPIRY_BYPASS_THRESHOLD_SECONDS = 2 * 3600  # 2 hours


@dataclass(frozen=True)
class DeliveryDecision:
    """Decision made by the delivery policy engine."""

    should_deliver: bool
    channel: str
    status: str  # 'pending', 'skipped_quiet_hours', 'web_only', 'dismissed'
    reason: str
    is_quiet_hours: bool = False
    bypassed_quiet_hours: bool = False


def resolve_timezone(tz_name: str | None) -> ZoneInfo:
    """Resolve a timezone identifier safely, defaulting to UTC on missing or invalid names."""
    if not tz_name or not tz_name.strip():
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(tz_name.strip())
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return ZoneInfo("UTC")


def is_in_quiet_hours(
    dt: datetime,
    tz_name: str | None = None,
    start_time: time = DEFAULT_QUIET_START,
    end_time: time = DEFAULT_QUIET_END,
) -> bool:
    """Check if the given datetime falls within the recipient's local quiet hours window.

    By default: 22:00 to 08:00 (spans across midnight).
    - 21:59:59 -> False
    - 22:00:00 -> True
    - 07:59:59 -> True
    - 08:00:00 -> False
    """
    tz = resolve_timezone(tz_name)
    if dt.tzinfo is None:
        local_dt = dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
    else:
        local_dt = dt.astimezone(tz)

    local_time = local_dt.time()

    if start_time > end_time:
        # Crosses midnight (e.g. 22:00 to 08:00)
        return local_time >= start_time or local_time < end_time
    else:
        # Same-day window (e.g. 13:00 to 15:00)
        return start_time <= local_time < end_time


def _parse_datetime(val: Any) -> datetime | None:
    """Parse various datetime representations into a timezone-aware UTC datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=ZoneInfo("UTC"))
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val, tz=ZoneInfo("UTC"))
    if isinstance(val, str):
        try:
            parsed = datetime.fromisoformat(val.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=ZoneInfo("UTC"))
        except (ValueError, TypeError):
            return None
    return None


def should_bypass_quiet_hours(
    notification: Notification,
    clock: Clock,
) -> tuple[bool, str]:
    """Check whether a notification qualifies for quiet-hours bypass.

    Returns:
        (bypassed: bool, reason: str)
    """
    # 1. Critical severity always bypasses quiet hours
    if notification.severity == "critical":
        return True, "critical_severity"

    # 2. Critical types (e.g. account reauth, integration error) bypass quiet hours
    if notification.type in {"system.integration_error", "account.needs_reauth"}:
        return True, "critical_type"

    # 3. Approval request with window expiry < 2 hours bypasses quiet hours
    if notification.type == "approval.requested":
        raw_expires_at = (notification.params or {}).get("expires_at")
        expires_at = _parse_datetime(raw_expires_at)
        if expires_at is not None:
            time_until_expiry = (expires_at - clock.now()).total_seconds()
            if time_until_expiry < EXPIRY_BYPASS_THRESHOLD_SECONDS:
                return True, "approval_expiring_soon"

    return False, ""


def evaluate_delivery_policy(
    notification: Notification,
    recipient: ChannelRecipient,
    clock: Clock,
    channel: str = "telegram",
    quiet_start: time = DEFAULT_QUIET_START,
    quiet_end: time = DEFAULT_QUIET_END,
) -> DeliveryDecision:
    """Evaluate whether and how to dispatch a notification to the specified channel.

    Rules:
    1. Web channel notifications are in-app and always deliver immediately.
    2. Routine info notifications are web-only by default (not pushed to external channels).
    3. Critical notifications bypass quiet hours and push immediately.
    4. Time-sensitive approval requests (< 2h to expiry) bypass quiet hours and push immediately.
    5. Non-critical notifications during quiet hours are marked 'skipped_quiet_hours'.
    6. Non-quiet notifications in IMMEDIATE_TYPES or QUIET_HOURS_TYPES are pushed ('pending').
    """
    if channel == "web":
        return DeliveryDecision(
            should_deliver=True,
            channel="web",
            status="pending",
            reason="web_immediate",
        )

    # 1. Check if routine info / web-only
    is_routine_info = notification.type in ROUTINE_INFO_TYPES or (
        notification.severity == "info"
        and notification.type not in IMMEDIATE_TYPES
        and notification.type not in QUIET_HOURS_TYPES
    )
    if is_routine_info and notification.severity != "critical":
        return DeliveryDecision(
            should_deliver=False,
            channel=channel,
            status="web_only",
            reason="routine_info_web_only",
        )

    # 2. Quiet hours evaluation
    in_quiet = is_in_quiet_hours(
        clock.now(),
        tz_name=recipient.timezone,
        start_time=quiet_start,
        end_time=quiet_end,
    )

    bypassed, bypass_reason = should_bypass_quiet_hours(notification, clock)

    if in_quiet:
        if bypassed:
            return DeliveryDecision(
                should_deliver=True,
                channel=channel,
                status="pending",
                reason=f"quiet_hours_bypassed:{bypass_reason}",
                is_quiet_hours=True,
                bypassed_quiet_hours=True,
            )
        else:
            return DeliveryDecision(
                should_deliver=False,
                channel=channel,
                status="skipped_quiet_hours",
                reason="quiet_hours_active",
                is_quiet_hours=True,
                bypassed_quiet_hours=False,
            )

    # 3. Outside quiet hours
    reason = "immediate_route" if notification.type in IMMEDIATE_TYPES else "normal_delivery"
    return DeliveryDecision(
        should_deliver=True,
        channel=channel,
        status="pending",
        reason=reason,
        is_quiet_hours=False,
        bypassed_quiet_hours=False,
    )
