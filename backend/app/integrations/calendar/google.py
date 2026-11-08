"""Google Calendar API v3 adapter (ADR-010, INV-05, INV-10)."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import quote

import httpx

from app.core.clock import Clock
from app.integrations.calendar.base import (
    BusyInterval,
    CalendarEventInfo,
    CalendarEventSpec,
    CalendarProfile,
    CalendarProviderKind,
    CalendarRef,
    CalendarTokenInfo,
)
from app.integrations.calendar.errors import (
    CalendarAuthError,
    CalendarInvalidRequest,
    CalendarOutcomeUnknown,
    CalendarPermissionError,
    CalendarRateLimited,
    CalendarTransientError,
)

GOOGLE_CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
GOOGLE_OAUTH_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105
IDEMPOTENCY_PROP = "agentnest_idempotency_key"


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _format_iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_event_item(item: dict[str, Any]) -> CalendarEventInfo | None:
    event_id = str(item.get("id") or "").strip()
    if not event_id:
        return None
    raw_status = str(item.get("status") or "confirmed")
    status: Literal["confirmed", "cancelled"] = (
        "cancelled" if raw_status == "cancelled" else "confirmed"
    )
    start_obj = item.get("start") or {}
    end_obj = item.get("end") or {}
    start_str = start_obj.get("dateTime") or start_obj.get("date")
    end_str = end_obj.get("dateTime") or end_obj.get("date")
    if not start_str or not end_str:
        return None
    try:
        if "T" in str(start_str):
            start_at = _parse_iso(str(start_str))
            end_at = _parse_iso(str(end_str))
        else:
            start_at = datetime.fromisoformat(f"{start_str}T00:00:00+00:00")
            end_at = datetime.fromisoformat(f"{end_str}T00:00:00+00:00")
    except ValueError:
        return None
    return CalendarEventInfo(
        external_event_id=event_id,
        title=str(item.get("summary") or "Busy"),
        description=item.get("description"),
        start_at=start_at,
        end_at=end_at,
        status=status,
        html_link=item.get("htmlLink"),
    )


class GoogleCalendarProvider:
    kind: CalendarProviderKind = "google"

    def __init__(
        self,
        clock: Clock,
        client_id: str,
        client_secret: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._clock = clock
        self._client_id = client_id
        self._client_secret = client_secret
        self._transport = transport

    def _client(self) -> httpx.Client:
        for name in ("httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.WARNING)
        return httpx.Client(
            transport=self._transport,
            timeout=15.0,
            follow_redirects=False,
            trust_env=False,
        )

    def _token(self, calendar: CalendarRef) -> str:
        if calendar.token_provider is None:
            raise CalendarAuthError("TOKEN_UNAVAILABLE")
        return calendar.token_provider()

    def _headers(self, calendar: CalendarRef) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token(calendar)}"}

    def get_calendar_profile(self, calendar: CalendarRef) -> CalendarProfile:
        cal_id = quote(calendar.calendar_id, safe="")
        try:
            with self._client() as client:
                resp = client.get(
                    f"{GOOGLE_CALENDAR_API_BASE}/calendars/{cal_id}",
                    headers=self._headers(calendar),
                )
        except httpx.HTTPError:
            raise CalendarTransientError("PROVIDER_UNAVAILABLE") from None
        self._raise_for_status(resp, is_mutation=False)
        body = resp.json()
        return CalendarProfile(
            calendar_id=str(body.get("id") or calendar.calendar_id),
            account_email=body.get("id"),
            calendar_summary=body.get("summary"),
            calendar_timezone=body.get("timeZone"),
        )

    def list_busy_intervals(
        self, calendar: CalendarRef, window_start: datetime, window_end: datetime
    ) -> list[BusyInterval]:
        try:
            with self._client() as client:
                resp = client.post(
                    f"{GOOGLE_CALENDAR_API_BASE}/freeBusy",
                    headers=self._headers(calendar),
                    json={
                        "timeMin": _format_iso(window_start),
                        "timeMax": _format_iso(window_end),
                        "items": [{"id": calendar.calendar_id}],
                    },
                )
        except httpx.HTTPError:
            raise CalendarTransientError("PROVIDER_UNAVAILABLE") from None
        self._raise_for_status(resp, is_mutation=False)
        body = resp.json()
        calendars: dict[str, Any] = body.get("calendars") or {}
        cal_data: dict[str, Any] = calendars.get(calendar.calendar_id) or next(
            iter(calendars.values()), {}
        )
        busy_list = cal_data.get("busy") or []
        intervals: list[BusyInterval] = []
        for entry in busy_list:
            start_s = entry.get("start")
            end_s = entry.get("end")
            if start_s and end_s:
                intervals.append(
                    BusyInterval(start_at=_parse_iso(start_s), end_at=_parse_iso(end_s))
                )
        return intervals

    def list_events(
        self, calendar: CalendarRef, window_start: datetime, window_end: datetime
    ) -> list[CalendarEventInfo]:
        cal_id = quote(calendar.calendar_id, safe="")
        try:
            with self._client() as client:
                resp = client.get(
                    f"{GOOGLE_CALENDAR_API_BASE}/calendars/{cal_id}/events",
                    headers=self._headers(calendar),
                    params={
                        "timeMin": _format_iso(window_start),
                        "timeMax": _format_iso(window_end),
                        "singleEvents": "true",
                        "orderBy": "startTime",
                        "maxResults": "250",
                    },
                )
        except httpx.HTTPError:
            raise CalendarTransientError("PROVIDER_UNAVAILABLE") from None
        self._raise_for_status(resp, is_mutation=False)
        items = resp.json().get("items") or []
        result: list[CalendarEventInfo] = []
        for item in items:
            parsed = _parse_event_item(item)
            if parsed is not None and parsed.status == "confirmed":
                result.append(parsed)
        return result

    def find_event_by_operation_key(
        self, calendar: CalendarRef, operation_key: str
    ) -> CalendarEventInfo | None:
        cal_id = quote(calendar.calendar_id, safe="")
        try:
            with self._client() as client:
                resp = client.get(
                    f"{GOOGLE_CALENDAR_API_BASE}/calendars/{cal_id}/events",
                    headers=self._headers(calendar),
                    params={
                        "privateExtendedProperty": f"{IDEMPOTENCY_PROP}={operation_key}",
                        "showDeleted": "true",
                        "maxResults": "5",
                    },
                )
        except httpx.HTTPError:
            raise CalendarTransientError("PROVIDER_UNAVAILABLE") from None
        self._raise_for_status(resp, is_mutation=False)
        items = resp.json().get("items") or []
        for item in items:
            parsed = _parse_event_item(item)
            if parsed is not None:
                return parsed
        return None

    def create_event(
        self, calendar: CalendarRef, spec: CalendarEventSpec, operation_key: str
    ) -> CalendarEventInfo:
        cal_id = quote(calendar.calendar_id, safe="")
        payload: dict[str, Any] = {
            "summary": spec.title,
            "description": spec.description or "",
            "start": {"dateTime": _format_iso(spec.start_at), "timeZone": spec.timezone},
            "end": {"dateTime": _format_iso(spec.end_at), "timeZone": spec.timezone},
            "extendedProperties": {"private": {IDEMPOTENCY_PROP: operation_key}},
        }
        if spec.attendee_email:
            payload["attendees"] = [{"email": spec.attendee_email}]
        try:
            with self._client() as client:
                resp = client.post(
                    f"{GOOGLE_CALENDAR_API_BASE}/calendars/{cal_id}/events",
                    headers=self._headers(calendar),
                    json=payload,
                )
        except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.RemoteProtocolError):
            raise CalendarOutcomeUnknown("OUTCOME_UNKNOWN") from None
        except httpx.HTTPError:
            raise CalendarTransientError("PROVIDER_UNAVAILABLE") from None
        self._raise_for_status(resp, is_mutation=True)
        parsed = _parse_event_item(resp.json())
        if parsed is None:
            raise CalendarOutcomeUnknown("OUTCOME_UNKNOWN")
        return parsed

    def update_event(
        self,
        calendar: CalendarRef,
        external_event_id: str,
        spec: CalendarEventSpec,
        operation_key: str,
    ) -> CalendarEventInfo:
        cal_id = quote(calendar.calendar_id, safe="")
        evt_id = quote(external_event_id, safe="")
        payload: dict[str, Any] = {
            "summary": spec.title,
            "description": spec.description or "",
            "start": {"dateTime": _format_iso(spec.start_at), "timeZone": spec.timezone},
            "end": {"dateTime": _format_iso(spec.end_at), "timeZone": spec.timezone},
            "extendedProperties": {"private": {IDEMPOTENCY_PROP: operation_key}},
        }
        try:
            with self._client() as client:
                resp = client.patch(
                    f"{GOOGLE_CALENDAR_API_BASE}/calendars/{cal_id}/events/{evt_id}",
                    headers=self._headers(calendar),
                    json=payload,
                )
        except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.RemoteProtocolError):
            raise CalendarOutcomeUnknown("OUTCOME_UNKNOWN") from None
        except httpx.HTTPError:
            raise CalendarTransientError("PROVIDER_UNAVAILABLE") from None
        self._raise_for_status(resp, is_mutation=True)
        parsed = _parse_event_item(resp.json())
        if parsed is None:
            raise CalendarOutcomeUnknown("OUTCOME_UNKNOWN")
        return parsed

    def cancel_event(
        self, calendar: CalendarRef, external_event_id: str, operation_key: str
    ) -> CalendarEventInfo:
        cal_id = quote(calendar.calendar_id, safe="")
        evt_id = quote(external_event_id, safe="")
        now = self._clock.now()
        try:
            with self._client() as client:
                resp = client.delete(
                    f"{GOOGLE_CALENDAR_API_BASE}/calendars/{cal_id}/events/{evt_id}",
                    headers=self._headers(calendar),
                )
        except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.RemoteProtocolError):
            raise CalendarOutcomeUnknown("OUTCOME_UNKNOWN") from None
        except httpx.HTTPError:
            raise CalendarTransientError("PROVIDER_UNAVAILABLE") from None
        if resp.status_code in (200, 204, 404, 410):
            return CalendarEventInfo(
                external_event_id=external_event_id,
                title="Cancelled",
                description=None,
                start_at=now,
                end_at=now + timedelta(minutes=30),
                status="cancelled",
            )
        self._raise_for_status(resp, is_mutation=True)
        return CalendarEventInfo(
            external_event_id=external_event_id,
            title="Cancelled",
            description=None,
            start_at=now,
            end_at=now + timedelta(minutes=30),
            status="cancelled",
        )

    def refresh_token(self, calendar: CalendarRef) -> CalendarTokenInfo:
        if calendar.refresh_token_provider is None:
            raise CalendarAuthError("REFRESH_TOKEN_UNAVAILABLE")
        refresh_tok = calendar.refresh_token_provider()
        try:
            with self._client() as client:
                resp = client.post(
                    GOOGLE_OAUTH_ENDPOINT,
                    data={
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_tok,
                    },
                )
        except httpx.HTTPError:
            raise CalendarTransientError("PROVIDER_UNAVAILABLE") from None
        if resp.status_code in (400, 401):
            raise CalendarAuthError("ACCOUNT_NEEDS_REAUTH")
        self._raise_for_status(resp, is_mutation=False)
        body = resp.json()
        access_token = str(body.get("access_token") or "").strip()
        expires_in = int(body.get("expires_in") or 3600)
        if not access_token:
            raise CalendarTransientError("PROVIDER_UNAVAILABLE")
        return CalendarTokenInfo(
            expires_at=self._clock.now() + timedelta(seconds=expires_in),
            access_token=access_token,
        )

    def _raise_for_status(self, response: httpx.Response, *, is_mutation: bool) -> None:
        code = response.status_code
        if 200 <= code < 300:
            return
        if code == 401:
            raise CalendarAuthError("ACCOUNT_NEEDS_REAUTH")
        if code == 403:
            raise CalendarPermissionError("CAPABILITY_MISSING")
        if code == 429:
            retry_after = response.headers.get("Retry-After")
            secs = int(retry_after) if retry_after and retry_after.isdigit() else None
            raise CalendarRateLimited(retry_after_s=secs, detail="PROVIDER_RATE_LIMITED")
        if 400 <= code < 500:
            raise CalendarInvalidRequest("PROVIDER_REJECTED")
        if is_mutation:
            raise CalendarOutcomeUnknown("OUTCOME_UNKNOWN")
        raise CalendarTransientError("PROVIDER_UNAVAILABLE")
