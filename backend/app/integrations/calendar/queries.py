"""Read-only calendar connection and appointment lookups."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import WorkspaceContext
from app.integrations.calendar.models import CalendarAppointment, CalendarConnection


def get_connection(
    session: Session, ctx: WorkspaceContext, connection_id: uuid.UUID, *, lock: bool = False
) -> CalendarConnection | None:
    stmt = select(CalendarConnection).where(
        CalendarConnection.workspace_id == ctx.workspace_id,
        CalendarConnection.id == connection_id,
    )
    return session.scalars(stmt.with_for_update() if lock else stmt).one_or_none()


def get_connection_in_workspace(
    session: Session, workspace_id: uuid.UUID, connection_id: uuid.UUID, *, lock: bool = False
) -> CalendarConnection | None:
    stmt = select(CalendarConnection).where(
        CalendarConnection.workspace_id == workspace_id,
        CalendarConnection.id == connection_id,
    )
    return session.scalars(stmt.with_for_update() if lock else stmt).one_or_none()


def get_active_connection_for_workspace(
    session: Session, workspace_id: uuid.UUID, *, lock: bool = False
) -> CalendarConnection | None:
    stmt = select(CalendarConnection).where(
        CalendarConnection.workspace_id == workspace_id,
        CalendarConnection.status != "disconnected",
    )
    return session.scalars(stmt.with_for_update() if lock else stmt).one_or_none()


def list_connections(session: Session, ctx: WorkspaceContext) -> list[CalendarConnection]:
    stmt = (
        select(CalendarConnection)
        .where(CalendarConnection.workspace_id == ctx.workspace_id)
        .order_by(CalendarConnection.created_at.desc(), CalendarConnection.id)
    )
    return list(session.scalars(stmt))


def has_connected_calendar(session: Session, workspace_id: uuid.UUID) -> bool:
    stmt = select(CalendarConnection.id).where(
        CalendarConnection.workspace_id == workspace_id,
        CalendarConnection.status.in_(("connected", "degraded")),
    )
    return session.scalars(stmt).first() is not None


def get_appointment_in_workspace(
    session: Session,
    workspace_id: uuid.UUID,
    appointment_id: uuid.UUID,
    *,
    lock: bool = False,
) -> CalendarAppointment | None:
    stmt = select(CalendarAppointment).where(
        CalendarAppointment.workspace_id == workspace_id,
        CalendarAppointment.id == appointment_id,
    )
    return session.scalars(stmt.with_for_update() if lock else stmt).one_or_none()


def list_appointments_in_window(
    session: Session,
    workspace_id: uuid.UUID,
    window_start: datetime,
    window_end: datetime,
    *,
    customer_identity_id: uuid.UUID | None = None,
    include_cancelled: bool = False,
) -> list[CalendarAppointment]:
    stmt = select(CalendarAppointment).where(
        CalendarAppointment.workspace_id == workspace_id,
        CalendarAppointment.start_at < window_end,
        CalendarAppointment.end_at > window_start,
    )
    if not include_cancelled:
        stmt = stmt.where(CalendarAppointment.status == "scheduled")
    if customer_identity_id is not None:
        stmt = stmt.where(CalendarAppointment.customer_identity_id == customer_identity_id)
    stmt = stmt.order_by(CalendarAppointment.start_at.asc(), CalendarAppointment.id)
    return list(session.scalars(stmt))
