"""The Calendar provider contract (ADR-010).

One protocol, two implementations: ``MockCalendarProvider`` (a stateful simulator backed by
``sim_calendar_events``) and ``GoogleCalendarProvider`` (real Google Calendar API v3).
Only ``operations`` may call the side-effecting methods (``create_event``, ``update_event``,
``cancel_event``, ``refresh_token``) and reconciliation reads (INV-15).
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

CalendarProviderKind = Literal["mock", "google"]


@dataclass(frozen=True)
class CalendarRef:
    """What an adapter needs to act for one connected calendar."""

    connection_id: uuid.UUID
    workspace_id: uuid.UUID
    calendar_id: str
    token_provider: Callable[[], str] | None = field(default=None, repr=False, compare=False)
    refresh_token_provider: Callable[[], str] | None = field(
        default=None, repr=False, compare=False
    )


@dataclass(frozen=True)
class BusyInterval:
    """A busy time range returned by FreeBusy or event query (UTC)."""

    start_at: datetime
    end_at: datetime


@dataclass(frozen=True)
class CalendarEventSpec:
    """Specification for creating or updating a calendar event."""

    title: str
    description: str | None
    start_at: datetime
    end_at: datetime
    timezone: str
    attendee_email: str | None = None


@dataclass(frozen=True)
class CalendarEventInfo:
    """Normalized representation of a calendar event on the provider."""

    external_event_id: str
    title: str
    description: str | None
    start_at: datetime
    end_at: datetime
    status: Literal["confirmed", "cancelled"]
    html_link: str | None = None


@dataclass(frozen=True)
class CalendarProfile:
    """Metadata about the connected calendar."""

    calendar_id: str
    account_email: str | None
    calendar_summary: str | None
    calendar_timezone: str | None


@dataclass(frozen=True)
class CalendarTokenInfo:
    """Refreshed access token and expiry."""

    expires_at: datetime | None
    access_token: str | None = field(default=None, repr=False)


class CalendarProvider(Protocol):
    kind: CalendarProviderKind

    def get_calendar_profile(self, calendar: CalendarRef) -> CalendarProfile: ...

    def list_busy_intervals(
        self, calendar: CalendarRef, window_start: datetime, window_end: datetime
    ) -> list[BusyInterval]: ...

    def list_events(
        self, calendar: CalendarRef, window_start: datetime, window_end: datetime
    ) -> list[CalendarEventInfo]: ...

    def find_event_by_operation_key(
        self, calendar: CalendarRef, operation_key: str
    ) -> CalendarEventInfo | None: ...

    # --- side effects: operations only (INV-15) ---
    def create_event(
        self, calendar: CalendarRef, spec: CalendarEventSpec, operation_key: str
    ) -> CalendarEventInfo: ...

    def update_event(
        self,
        calendar: CalendarRef,
        external_event_id: str,
        spec: CalendarEventSpec,
        operation_key: str,
    ) -> CalendarEventInfo: ...

    def cancel_event(
        self, calendar: CalendarRef, external_event_id: str, operation_key: str
    ) -> CalendarEventInfo: ...

    def refresh_token(self, calendar: CalendarRef) -> CalendarTokenInfo: ...
