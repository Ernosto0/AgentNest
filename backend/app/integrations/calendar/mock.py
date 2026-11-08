"""Stateful simulator for Calendar (ADR-010, INV-09, INV-14).

Backed by ``sim_calendar_events`` so offline tests and demo workspaces run the exact same
availability, booking, rescheduling, cancellation, and reconciliation code paths without
external credentials.
"""

import hashlib
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.db import set_tenant_context
from app.integrations.calendar.base import (
    BusyInterval,
    CalendarEventInfo,
    CalendarEventSpec,
    CalendarProfile,
    CalendarProviderKind,
    CalendarRef,
    CalendarTokenInfo,
)
from app.integrations.calendar.errors import CalendarInvalidRequest
from app.integrations.calendar.models import CalendarConnection, SimCalendarEvent


def _event_id_from_key(operation_key: str) -> str:
    digest = hashlib.sha256(operation_key.encode("utf-8")).hexdigest()[:16]
    return f"sim_evt_{digest}"


def _to_info(row: SimCalendarEvent) -> CalendarEventInfo:
    status: Literal["confirmed", "cancelled"] = (
        "cancelled" if row.status == "cancelled" else "confirmed"
    )
    return CalendarEventInfo(
        external_event_id=row.external_event_id,
        title=row.title,
        description=row.description,
        start_at=row.start_at,
        end_at=row.end_at,
        status=status,
    )


class MockCalendarProvider:
    kind: CalendarProviderKind = "mock"

    def __init__(self, session_factory: Callable[[], Session], clock: Clock) -> None:
        self._session_factory = session_factory
        self._clock = clock

    def get_calendar_profile(self, calendar: CalendarRef) -> CalendarProfile:
        with self._session_factory() as session:
            set_tenant_context(session, calendar.workspace_id)
            conn = session.get(CalendarConnection, calendar.connection_id)
            return CalendarProfile(
                calendar_id=calendar.calendar_id,
                account_email=conn.account_email if conn else "demo@calendar.local",
                calendar_summary=conn.calendar_summary if conn else "Demo Calendar",
                calendar_timezone=conn.calendar_timezone if conn else "UTC",
            )

    def list_busy_intervals(
        self, calendar: CalendarRef, window_start: datetime, window_end: datetime
    ) -> list[BusyInterval]:
        events = self.list_events(calendar, window_start, window_end)
        return [
            BusyInterval(start_at=e.start_at, end_at=e.end_at)
            for e in events
            if e.status == "confirmed"
        ]

    def list_events(
        self, calendar: CalendarRef, window_start: datetime, window_end: datetime
    ) -> list[CalendarEventInfo]:
        with self._session_factory() as session:
            set_tenant_context(session, calendar.workspace_id)
            stmt = (
                select(SimCalendarEvent)
                .where(
                    SimCalendarEvent.workspace_id == calendar.workspace_id,
                    SimCalendarEvent.calendar_connection_id == calendar.connection_id,
                    SimCalendarEvent.status == "confirmed",
                    SimCalendarEvent.start_at < window_end,
                    SimCalendarEvent.end_at > window_start,
                )
                .order_by(SimCalendarEvent.start_at.asc())
            )
            return [_to_info(row) for row in session.scalars(stmt)]

    def find_event_by_operation_key(
        self, calendar: CalendarRef, operation_key: str
    ) -> CalendarEventInfo | None:
        with self._session_factory() as session:
            set_tenant_context(session, calendar.workspace_id)
            stmt = select(SimCalendarEvent).where(
                SimCalendarEvent.workspace_id == calendar.workspace_id,
                SimCalendarEvent.calendar_connection_id == calendar.connection_id,
                SimCalendarEvent.operation_key == operation_key,
            )
            row = session.scalars(stmt).one_or_none()
            return _to_info(row) if row is not None else None

    def create_event(
        self, calendar: CalendarRef, spec: CalendarEventSpec, operation_key: str
    ) -> CalendarEventInfo:
        if spec.end_at <= spec.start_at:
            raise CalendarInvalidRequest("INVALID_TIME_RANGE", "end_at must be after start_at")
        with self._session_factory() as session:
            set_tenant_context(session, calendar.workspace_id)
            existing = session.scalars(
                select(SimCalendarEvent).where(
                    SimCalendarEvent.workspace_id == calendar.workspace_id,
                    SimCalendarEvent.calendar_connection_id == calendar.connection_id,
                    SimCalendarEvent.operation_key == operation_key,
                )
            ).one_or_none()
            if existing is not None:
                return _to_info(existing)
            row = SimCalendarEvent(
                workspace_id=calendar.workspace_id,
                calendar_connection_id=calendar.connection_id,
                external_event_id=_event_id_from_key(operation_key),
                operation_key=operation_key,
                title=spec.title,
                description=spec.description,
                start_at=spec.start_at,
                end_at=spec.end_at,
                status="confirmed",
            )
            session.add(row)
            session.flush()
            info = _to_info(row)
            session.commit()
            return info

    def update_event(
        self,
        calendar: CalendarRef,
        external_event_id: str,
        spec: CalendarEventSpec,
        operation_key: str,
    ) -> CalendarEventInfo:
        if spec.end_at <= spec.start_at:
            raise CalendarInvalidRequest("INVALID_TIME_RANGE", "end_at must be after start_at")
        with self._session_factory() as session:
            set_tenant_context(session, calendar.workspace_id)
            row = session.scalars(
                select(SimCalendarEvent)
                .where(
                    SimCalendarEvent.workspace_id == calendar.workspace_id,
                    SimCalendarEvent.calendar_connection_id == calendar.connection_id,
                    SimCalendarEvent.external_event_id == external_event_id,
                )
                .with_for_update()
            ).one_or_none()
            if row is None:
                row = SimCalendarEvent(
                    workspace_id=calendar.workspace_id,
                    calendar_connection_id=calendar.connection_id,
                    external_event_id=external_event_id,
                    operation_key=operation_key,
                    title=spec.title,
                    description=spec.description,
                    start_at=spec.start_at,
                    end_at=spec.end_at,
                    status="confirmed",
                )
                session.add(row)
            else:
                row.title = spec.title
                row.description = spec.description
                row.start_at = spec.start_at
                row.end_at = spec.end_at
                row.operation_key = operation_key
                row.status = "confirmed"
            session.flush()
            info = _to_info(row)
            session.commit()
            return info

    def cancel_event(
        self, calendar: CalendarRef, external_event_id: str, operation_key: str
    ) -> CalendarEventInfo:
        with self._session_factory() as session:
            set_tenant_context(session, calendar.workspace_id)
            row = session.scalars(
                select(SimCalendarEvent)
                .where(
                    SimCalendarEvent.workspace_id == calendar.workspace_id,
                    SimCalendarEvent.calendar_connection_id == calendar.connection_id,
                    SimCalendarEvent.external_event_id == external_event_id,
                )
                .with_for_update()
            ).one_or_none()
            if row is None:
                now = self._clock.now()
                return CalendarEventInfo(
                    external_event_id=external_event_id,
                    title="Cancelled",
                    description=None,
                    start_at=now,
                    end_at=now + timedelta(minutes=30),
                    status="cancelled",
                )
            row.status = "cancelled"
            row.operation_key = operation_key
            session.flush()
            info = _to_info(row)
            session.commit()
            return info

    def refresh_token(self, calendar: CalendarRef) -> CalendarTokenInfo:
        return CalendarTokenInfo(expires_at=None, access_token=None)
