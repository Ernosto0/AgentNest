"""Tables owned by the Calendar integration.

``calendar_connections`` stores the workspace's connected calendar (Google or mock).
``calendar_appointments`` stores booked appointments with optimistic concurrency (``version``)
and customer identity scoping (INV-03).
``sim_calendar_events`` backs ``MockCalendarProvider`` for offline dev/test/demo (INV-09, INV-14).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin, WorkspaceScopedMixin

CALENDAR_PROVIDER_KINDS = ("mock", "google")
CALENDAR_CONNECTION_STATUSES = ("connected", "needs_reauth", "degraded", "disconnected")
APPOINTMENT_STATUSES = ("scheduled", "cancelled", "completed")
APPOINTMENT_SOURCES = ("customer", "owner", "owner_task")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class CalendarConnection(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    __tablename__ = "calendar_connections"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        CheckConstraint(_in("provider_kind", CALENDAR_PROVIDER_KINDS), name="provider_kind"),
        CheckConstraint(_in("status", CALENDAR_CONNECTION_STATUSES), name="status"),
        CheckConstraint("consecutive_failures >= 0", name="consecutive_failures"),
        CheckConstraint(
            "default_slot_duration_minutes >= 15 AND default_slot_duration_minutes <= 240",
            name="slot_duration_range",
        ),
        # Only a real (Google) connection holds tokens; the mock never has one (INV-10).
        CheckConstraint(
            "provider_kind = 'google' OR "
            "(token_ciphertext IS NULL AND refresh_token_ciphertext IS NULL)",
            name="mock_no_token",
        ),
        Index(
            "uq_calendar_connections_active_workspace",
            "workspace_id",
            unique=True,
            postgresql_where=text("status <> 'disconnected'"),
        ),
    )

    provider_kind: Mapped[str] = mapped_column(Text, nullable=False)
    external_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    account_email: Mapped[str | None] = mapped_column(Text)
    calendar_id: Mapped[str] = mapped_column(Text, nullable=False, server_default="primary")
    calendar_summary: Mapped[str | None] = mapped_column(Text)
    calendar_timezone: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="connected")
    capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    granted_scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    default_slot_duration_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("30")
    )
    token_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    refresh_token_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    token_key_id: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    degraded_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(Text)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_simulated(self) -> bool:
        """INV-09: derived from the provider kind and copied to every row the connection yields."""
        return self.provider_kind == "mock"


class CalendarOAuthState(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    """Hashed, user-bound single-use OAuth state for Google Calendar."""

    __tablename__ = "calendar_oauth_states"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("state_hash"),
        ForeignKeyConstraint(
            ["workspace_id", "calendar_connection_id"],
            ["calendar_connections.workspace_id", "calendar_connections.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("purpose IN ('connect', 'reconnect')", name="purpose"),
        CheckConstraint(
            "(purpose = 'connect' AND calendar_connection_id IS NULL) OR "
            "(purpose = 'reconnect' AND calendar_connection_id IS NOT NULL)",
            name="purpose_connection",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    state_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    calendar_connection_id: Mapped[uuid.UUID | None] = mapped_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CalendarAppointment(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    """A workspace appointment synced with the connected calendar."""

    __tablename__ = "calendar_appointments"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "calendar_connection_id"],
            ["calendar_connections.workspace_id", "calendar_connections.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "customer_identity_id"],
            ["customer_identities.workspace_id", "customer_identities.id"],
            ondelete="SET NULL",
        ),
        CheckConstraint(_in("status", APPOINTMENT_STATUSES), name="status"),
        CheckConstraint(_in("created_by_source", APPOINTMENT_SOURCES), name="created_by_source"),
        CheckConstraint("end_at > start_at", name="valid_interval"),
        CheckConstraint("version >= 1", name="positive_version"),
        Index(
            "ix_calendar_appointments_workspace_window",
            "workspace_id",
            "status",
            "start_at",
            "end_at",
        ),
        Index(
            "ix_calendar_appointments_customer",
            "workspace_id",
            "customer_identity_id",
            "start_at",
        ),
    )

    calendar_connection_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column()
    customer_identity_id: Mapped[uuid.UUID | None] = mapped_column()
    external_event_id: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    customer_name: Mapped[str | None] = mapped_column(Text)
    customer_contact: Mapped[str | None] = mapped_column(Text)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="scheduled")
    created_by_source: Mapped[str] = mapped_column(Text, nullable=False)
    is_simulated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(Text)


class SimCalendarEvent(UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, Base):
    """Simulated provider event for ``MockCalendarProvider`` (INV-09, INV-14)."""

    __tablename__ = "sim_calendar_events"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "calendar_connection_id"],
            ["calendar_connections.workspace_id", "calendar_connections.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("calendar_connection_id", "external_event_id"),
        UniqueConstraint("calendar_connection_id", "operation_key"),
        CheckConstraint("status IN ('confirmed', 'cancelled')", name="status"),
        CheckConstraint("end_at > start_at", name="valid_interval"),
        Index(
            "ix_sim_calendar_events_window",
            "calendar_connection_id",
            "status",
            "start_at",
            "end_at",
        ),
    )

    calendar_connection_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    external_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    operation_key: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="confirmed")
