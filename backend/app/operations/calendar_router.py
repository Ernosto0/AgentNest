"""Calendar connection and appointments router (/api/v1/workspaces/{workspace_id}/calendar)."""

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_clock, require_membership
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.integrations.calendar import queries
from app.integrations.calendar.models import CalendarAppointment, CalendarConnection
from app.operations import calendar as calendar_service

router = APIRouter(prefix="/workspaces/{workspace_id}/calendar", tags=["integrations"])


class AuthorizeUrlOut(BaseModel):
    authorize_url: str


class CalendarConnectionOut(BaseModel):
    id: uuid.UUID
    provider_kind: str
    external_account_id: str
    account_email: str | None
    calendar_id: str
    calendar_summary: str | None
    calendar_timezone: str | None
    status: str
    capabilities: dict[str, Any]
    default_slot_duration_minutes: int
    last_error_code: str | None
    is_simulated: bool
    connected_at: datetime | None
    disconnected_at: datetime | None
    created_at: datetime


class CalendarConnectionListOut(BaseModel):
    items: list[CalendarConnectionOut]


class ConnectMockCalendarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_email: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None
    ) = None
    calendar_summary: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None
    ) = None
    default_slot_duration_minutes: int = Field(default=30, ge=15, le=240)


class UpdateCalendarSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_slot_duration_minutes: int = Field(ge=15, le=240)


class CalendarAppointmentOut(BaseModel):
    id: uuid.UUID
    calendar_connection_id: uuid.UUID
    conversation_id: uuid.UUID | None
    customer_identity_id: uuid.UUID | None
    external_event_id: str | None
    title: str
    description: str | None
    customer_name: str | None
    customer_contact: str | None
    start_at: datetime
    end_at: datetime
    timezone: str
    status: str
    created_by_source: str
    is_simulated: bool
    version: int
    cancelled_at: datetime | None
    cancellation_reason: str | None
    created_at: datetime


class CalendarAppointmentListOut(BaseModel):
    items: list[CalendarAppointmentOut]


def _to_connection_out(conn: CalendarConnection) -> CalendarConnectionOut:
    return CalendarConnectionOut(
        id=conn.id,
        provider_kind=conn.provider_kind,
        external_account_id=conn.external_account_id,
        account_email=conn.account_email,
        calendar_id=conn.calendar_id,
        calendar_summary=conn.calendar_summary,
        calendar_timezone=conn.calendar_timezone,
        status=conn.status,
        capabilities=conn.capabilities,
        default_slot_duration_minutes=conn.default_slot_duration_minutes,
        last_error_code=conn.last_error_code,
        is_simulated=conn.is_simulated,
        connected_at=conn.connected_at,
        disconnected_at=conn.disconnected_at,
        created_at=conn.created_at,
    )


def _to_appointment_out(appt: CalendarAppointment) -> CalendarAppointmentOut:
    return CalendarAppointmentOut(
        id=appt.id,
        calendar_connection_id=appt.calendar_connection_id,
        conversation_id=appt.conversation_id,
        customer_identity_id=appt.customer_identity_id,
        external_event_id=appt.external_event_id,
        title=appt.title,
        description=appt.description,
        customer_name=appt.customer_name,
        customer_contact=appt.customer_contact,
        start_at=appt.start_at,
        end_at=appt.end_at,
        timezone=appt.timezone,
        status=appt.status,
        created_by_source=appt.created_by_source,
        is_simulated=appt.is_simulated,
        version=appt.version,
        cancelled_at=appt.cancelled_at,
        cancellation_reason=appt.cancellation_reason,
        created_at=appt.created_at,
    )


@router.get("", response_model=CalendarConnectionListOut)
def list_calendar_connections(
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
) -> CalendarConnectionListOut:
    return CalendarConnectionListOut(
        items=[_to_connection_out(c) for c in queries.list_connections(db, ctx)]
    )


@router.post("/connect/google", response_model=AuthorizeUrlOut)
def connect_google(
    ctx: WorkspaceContext = Depends(require_membership("integrations.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> AuthorizeUrlOut:
    url = calendar_service.start_google_connect(db, clock, ctx, settings)
    return AuthorizeUrlOut(authorize_url=url)


@router.post("/connect-mock", response_model=CalendarConnectionOut, status_code=201)
def connect_mock(
    payload: ConnectMockCalendarIn,
    ctx: WorkspaceContext = Depends(require_membership("integrations.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> CalendarConnectionOut:
    conn = calendar_service.connect_mock_calendar(
        db,
        clock,
        ctx,
        settings,
        account_email=payload.account_email,
        calendar_summary=payload.calendar_summary,
        default_slot_duration_minutes=payload.default_slot_duration_minutes,
    )
    return _to_connection_out(conn)


@router.post("/{connection_id}/reconnect/google", response_model=AuthorizeUrlOut)
def reconnect_google(
    connection_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("integrations.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> AuthorizeUrlOut:
    url = calendar_service.start_google_connect(
        db, clock, ctx, settings, purpose="reconnect", connection_id=connection_id
    )
    return AuthorizeUrlOut(authorize_url=url)


@router.patch("/{connection_id}", response_model=CalendarConnectionOut)
def update_calendar_connection(
    connection_id: uuid.UUID,
    payload: UpdateCalendarSettingsIn,
    ctx: WorkspaceContext = Depends(require_membership("integrations.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> CalendarConnectionOut:
    conn = calendar_service.update_connection_settings(
        db,
        clock,
        ctx,
        connection_id,
        default_slot_duration_minutes=payload.default_slot_duration_minutes,
    )
    return _to_connection_out(conn)


@router.post("/{connection_id}/disconnect", response_model=CalendarConnectionOut)
def disconnect_calendar_connection(
    connection_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("integrations.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> CalendarConnectionOut:
    conn = calendar_service.disconnect_calendar(db, clock, ctx, connection_id)
    return _to_connection_out(conn)


@router.get("/appointments", response_model=CalendarAppointmentListOut)
def list_appointments(
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    include_cancelled: bool = Query(default=False),
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> CalendarAppointmentListOut:
    w_start = start_at or (clock.now() - timedelta(days=1))
    w_end = end_at or (clock.now() + timedelta(days=30))
    rows = queries.list_appointments_in_window(
        db,
        ctx.workspace_id,
        w_start,
        w_end,
        include_cancelled=include_cancelled,
    )
    return CalendarAppointmentListOut(items=[_to_appointment_out(r) for r in rows])
