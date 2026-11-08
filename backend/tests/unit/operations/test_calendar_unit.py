"""Unit tests for Google Calendar OAuth, provider logic, and schema validation."""

import uuid
from datetime import UTC, date, datetime

import httpx
import pytest

from app.agent.calendar import (
    CalendarAvailabilityArgs,
    CalendarBookArgs,
    CalendarEvidence,
    CalendarModifyArgs,
)
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.integrations.calendar.base import CalendarEventSpec, CalendarRef
from app.integrations.calendar.errors import CalendarAuthError, CalendarRateLimited
from app.integrations.calendar.google import GoogleCalendarProvider
from app.integrations.calendar.oauth import (
    GOOGLE_CALENDAR_SCOPES,
    build_authorize_url,
    compute_capabilities,
)


def test_google_oauth_url_and_capabilities_mapping() -> None:
    settings = Settings(
        _env_file=None,
        google_client_id="my-client-id.apps.googleusercontent.com",
        google_client_secret="secret-123",
        google_redirect_uri="http://localhost:8000/api/v1/oauth/google-calendar/callback",
    )
    url = build_authorize_url(settings, "state_token_123")
    assert "client_id=my-client-id.apps.googleusercontent.com" in url
    assert "state=state_token_123" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url

    caps_rw = compute_capabilities(list(GOOGLE_CALENDAR_SCOPES))
    assert caps_rw == {
        "availability_read": True,
        "event_create": True,
        "event_update": True,
        "event_cancel": True,
    }

    caps_ro = compute_capabilities(["https://www.googleapis.com/auth/calendar.readonly"])
    assert caps_ro == {
        "availability_read": True,
        "event_create": False,
        "event_update": False,
        "event_cancel": False,
    }

    caps_none = compute_capabilities(["openid", "email"])
    assert caps_none == {
        "availability_read": False,
        "event_create": False,
        "event_update": False,
        "event_cancel": False,
    }


def test_google_calendar_provider_with_mock_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calendar/v3/freeBusy":
            return httpx.Response(
                200,
                json={
                    "calendars": {
                        "primary": {
                            "busy": [
                                {
                                    "start": "2026-11-09T12:00:00Z",
                                    "end": "2026-11-09T13:00:00Z",
                                }
                            ]
                        }
                    }
                },
            )
        if request.url.path == "/calendar/v3/calendars/primary/events":
            if request.method == "POST":
                return httpx.Response(
                    200,
                    json={
                        "id": "gcal_evt_1",
                        "status": "confirmed",
                        "summary": "Trial Session",
                        "start": {"dateTime": "2026-11-09T14:00:00Z"},
                        "end": {"dateTime": "2026-11-09T15:00:00Z"},
                        "htmlLink": "https://calendar.google.com/event?eid=1",
                    },
                )
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "id": "gcal_evt_1",
                                "status": "confirmed",
                                "summary": "Trial Session",
                                "start": {"dateTime": "2026-11-09T14:00:00Z"},
                                "end": {"dateTime": "2026-11-09T15:00:00Z"},
                            }
                        ]
                    },
                )
        if request.url.path == "/calendar/v3/calendars/primary/events/gcal_evt_1":
            if request.method == "PATCH":
                return httpx.Response(
                    200,
                    json={
                        "id": "gcal_evt_1",
                        "status": "confirmed",
                        "summary": "Rescheduled Session",
                        "start": {"dateTime": "2026-11-09T16:00:00Z"},
                        "end": {"dateTime": "2026-11-09T17:00:00Z"},
                    },
                )
            if request.method == "DELETE":
                return httpx.Response(204)
        return httpx.Response(404)

    clock = FrozenClock(datetime(2026, 11, 9, 8, 0, tzinfo=UTC))
    provider = GoogleCalendarProvider(
        clock,
        "client-id",
        "client-secret",
        transport=httpx.MockTransport(handler),
    )
    ref = CalendarRef(
        workspace_id=uuid.uuid4(),
        connection_id=uuid.uuid4(),
        calendar_id="primary",
        token_provider=lambda: "ya29.fake_token",
    )

    busy = provider.list_busy_intervals(
        ref,
        datetime(2026, 11, 9, 0, 0, tzinfo=UTC),
        datetime(2026, 11, 9, 23, 59, tzinfo=UTC),
    )
    assert len(busy) == 1
    assert busy[0].start_at == datetime(2026, 11, 9, 12, 0, tzinfo=UTC)

    spec = CalendarEventSpec(
        title="Trial Session",
        description="Notes",
        start_at=datetime(2026, 11, 9, 14, 0, tzinfo=UTC),
        end_at=datetime(2026, 11, 9, 15, 0, tzinfo=UTC),
        timezone="Europe/Istanbul",
        attendee_email="ada@example.com",
    )
    created = provider.create_event(ref, spec, "idem_1")
    assert created.external_event_id == "gcal_evt_1"
    assert created.status == "confirmed"

    found = provider.find_event_by_operation_key(ref, "idem_1")
    assert found is not None and found.external_event_id == "gcal_evt_1"

    updated = provider.update_event(ref, "gcal_evt_1", spec, "idem_2")
    assert updated.title == "Rescheduled Session"

    cancelled = provider.cancel_event(ref, "gcal_evt_1", "idem_3")
    assert cancelled.status == "cancelled"


def test_google_calendar_error_mapping() -> None:
    def auth_fail(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid Credentials"}})

    def rate_limit(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "30"}, json={"error": {}})

    clock = FrozenClock(datetime(2026, 11, 9, 8, 0, tzinfo=UTC))
    ref = CalendarRef(
        workspace_id=uuid.uuid4(),
        connection_id=uuid.uuid4(),
        calendar_id="primary",
        token_provider=lambda: "bad_token",
    )

    p_auth = GoogleCalendarProvider(
        clock,
        "client-id",
        "client-secret",
        transport=httpx.MockTransport(auth_fail),
    )
    with pytest.raises(CalendarAuthError):
        p_auth.list_busy_intervals(
            ref,
            datetime(2026, 11, 9, 0, 0, tzinfo=UTC),
            datetime(2026, 11, 9, 1, 0, tzinfo=UTC),
        )

    p_rate = GoogleCalendarProvider(
        clock,
        "client-id",
        "client-secret",
        transport=httpx.MockTransport(rate_limit),
    )
    with pytest.raises(CalendarRateLimited) as exc_info:
        p_rate.list_busy_intervals(
            ref,
            datetime(2026, 11, 9, 0, 0, tzinfo=UTC),
            datetime(2026, 11, 9, 1, 0, tzinfo=UTC),
        )
    assert exc_info.value.retry_after_s == 30.0


def test_calendar_agent_tool_arg_schemas() -> None:
    avail = CalendarAvailabilityArgs.model_validate(
        {"local_date": "2026-11-09", "local_time": "12:00", "duration_minutes": 60}
    )
    assert avail.local_date == date(2026, 11, 9)
    assert avail.local_time == "12:00"

    book = CalendarBookArgs.model_validate(
        {
            "local_date": "2026-11-09",
            "local_time": "12:00",
            "duration_minutes": 60,
            "title": "Pilates Session",
            "customer_name": "Ada",
        }
    )
    assert book.title == "Pilates Session"

    mod = CalendarModifyArgs.model_validate(
        {
            "appointment_id": str(uuid.uuid4()),
            "expected_version": 1,
            "operation": "reschedule",
            "new_local_date": "2026-11-10",
            "new_local_time": "14:00",
        }
    )
    assert mod.operation == "reschedule"

    ev = CalendarEvidence.model_validate(
        {
            "kind": "booked",
            "appointment_id": str(uuid.uuid4()),
            "appointment_version": 1,
        }
    )
    assert ev.kind == "booked"
