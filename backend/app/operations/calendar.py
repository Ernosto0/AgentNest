"""Calendar OAuth, connection lifecycle, availability computation, and operations ledger."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.agent.delegation import fence_action
from app.agent.models import AgentAction
from app.approvals.models import Approval
from app.audit import service as audit
from app.core.clock import Clock
from app.core.config import Settings, get_settings
from app.core.context import ActorRef, WorkspaceContext
from app.core.db import set_tenant_context
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.security import TokenKeyRing, account_token_aad, generate_token, hash_token
from app.identity import repository as identity_repo
from app.identity import service as identity_service
from app.identity.models import User, Workspace, WorkspaceMember
from app.identity.permissions import has_permission
from app.integrations.calendar import oauth, queries, registry
from app.integrations.calendar.base import (
    BusyInterval,
    CalendarEventInfo,
    CalendarEventSpec,
    CalendarRef,
)
from app.integrations.calendar.errors import (
    CalendarInvalidRequest,
    CalendarOutcomeUnknown,
    CalendarProviderError,
)
from app.integrations.calendar.models import (
    CalendarAppointment,
    CalendarConnection,
    CalendarOAuthState,
    SimCalendarEvent,
)
from app.integrations.instagram.transitions import apply_account_transition
from app.jobs.queue import enqueue
from app.jobs.registry import JobContext, job_handler
from app.knowledge.models import BusinessFact
from app.knowledge.values import WEEKDAYS, WeeklyHoursValue, time_to_minutes
from app.operations import conversation_deletion
from app.operations.accounts import lock_workspace
from app.operations.models import Operation
from app.operations.resolution import set_operation

MOCK_CALENDAR_CAPABILITIES = {
    "availability_read": True,
    "event_create": True,
    "event_update": True,
    "event_cancel": True,
}


@dataclass(frozen=True)
class CalendarCallbackOutcome:
    workspace_id: uuid.UUID
    error_code: str | None = None


@dataclass(frozen=True)
class AvailableSlot:
    start_at: datetime
    end_at: datetime
    local_date: str
    local_start_time: str
    local_end_time: str


@dataclass(frozen=True)
class AvailabilityResult:
    calendar_connected: bool
    timezone: str
    slot_duration_minutes: int
    hours_verified: bool
    requested_slot_available: bool | None
    available_slots: list[AvailableSlot]
    busy_intervals: list[BusyInterval]


class CalendarEffectPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: uuid.UUID


class ReconcileCalendarPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: uuid.UUID


def mock_calendar_allowed(settings: Settings, ctx: WorkspaceContext) -> bool:
    if "mock" not in settings.calendar_providers:
        return False
    if settings.app_env != "production":
        return True
    return ctx.is_demo and settings.allow_simulated_workspaces


def _context(session: Session, workspace_id: uuid.UUID, user_id: uuid.UUID) -> WorkspaceContext:
    session.scalar(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)
        .with_for_update()
    )
    found = identity_repo.get_membership(session, workspace_id, user_id)
    user = session.get(User, user_id)
    if found is None or found[1].status != "active" or user is None or not user.is_active:
        raise AppError("FORBIDDEN")
    member, workspace = found
    if not has_permission(member.role, "integrations.manage"):
        raise AppError("FORBIDDEN")
    return identity_service.workspace_context(workspace, ActorRef.user(user_id), member.role)


def transition_calendar_connection(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    connection: CalendarConnection,
    target: str,
    *,
    error_code: str | None = None,
    reauthorized: bool = False,
) -> CalendarConnection:
    previous = connection.status
    connection.status = apply_account_transition(previous, target, reauthorized=reauthorized)
    now = clock.now()
    if target == "connected":
        connection.connected_at = connection.connected_at or now
        connection.disconnected_at = None
        connection.degraded_until = None
        connection.last_error_code = None
        connection.consecutive_failures = 0
        connection.failure_window_started_at = None
    elif target == "disconnected":
        connection.disconnected_at = now
    if error_code is not None:
        connection.last_error_code = error_code
    session.flush()
    audit.record(
        session,
        ctx,
        f"calendar.{target}",
        "calendar_connection",
        connection.id,
        {
            "from": previous,
            "provider_kind": connection.provider_kind,
            "error_code": error_code,
        },
        is_simulated=connection.is_simulated,
        clock=clock,
    )
    return connection


def connect_mock_calendar(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    settings: Settings,
    *,
    account_email: str | None = None,
    calendar_summary: str | None = None,
    default_slot_duration_minutes: int = 30,
) -> CalendarConnection:
    if not mock_calendar_allowed(settings, ctx):
        raise AppError("FORBIDDEN", permission="integrations.mock")
    workspace = identity_repo.get_workspace(session, ctx)
    if workspace is None:
        raise AppError("NOT_FOUND")
    if queries.get_active_connection_for_workspace(session, ctx.workspace_id) is not None:
        raise AppError("CONFLICT_STATE", entity="calendar_connection", reason="connection_exists")
    email = account_email or f"{workspace.slug}@calendar.demo"
    conn = CalendarConnection(
        workspace_id=ctx.workspace_id,
        provider_kind="mock",
        external_account_id=f"mock-cal-{uuid.uuid4().hex[:12]}",
        account_email=email,
        calendar_id="primary",
        calendar_summary=calendar_summary or f"{workspace.name} Calendar",
        calendar_timezone=workspace.timezone,
        status="connected",
        capabilities=dict(MOCK_CALENDAR_CAPABILITIES),
        granted_scopes=[],
        default_slot_duration_minutes=default_slot_duration_minutes,
        connected_at=clock.now(),
    )
    try:
        with session.begin_nested():
            session.add(conn)
    except IntegrityError as exc:
        raise AppError(
            "CONFLICT_STATE", entity="calendar_connection", reason="connection_exists"
        ) from exc
    audit.record(
        session,
        ctx,
        "calendar.connected",
        "calendar_connection",
        conn.id,
        {"from": None, "provider_kind": "mock", "calendar_id": conn.calendar_id},
        is_simulated=True,
        clock=clock,
    )
    session.commit()
    return conn


def start_google_connect(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    settings: Settings,
    *,
    purpose: str = "connect",
    connection_id: uuid.UUID | None = None,
) -> str:
    if "google" not in settings.calendar_providers:
        raise AppError("FORBIDDEN")
    if ctx.actor.id is None or purpose not in ("connect", "reconnect"):
        raise AppError("VALIDATION_FAILED")
    user_id = uuid.UUID(ctx.actor.id)
    _context(session, ctx.workspace_id, user_id)
    if conversation_deletion.pending(session, ctx.workspace_id):
        raise AppError("CONFLICT_STATE")
    if purpose == "reconnect":
        conn = (
            queries.get_connection(session, ctx, connection_id, lock=True)
            if connection_id
            else None
        )
        if conn is None:
            raise AppError("NOT_FOUND")
        if conn.provider_kind != "google" or conn.status == "disconnected":
            raise AppError("CONFLICT_STATE")
    elif connection_id is not None:
        raise AppError("VALIDATION_FAILED")
    elif queries.get_active_connection_for_workspace(session, ctx.workspace_id) is not None:
        raise AppError("CONFLICT_STATE")
    raw = generate_token()
    session.add(
        CalendarOAuthState(
            workspace_id=ctx.workspace_id,
            user_id=user_id,
            state_hash=hash_token(raw),
            purpose=purpose,
            calendar_connection_id=connection_id,
            expires_at=clock.now() + timedelta(minutes=10),
            created_at=clock.now(),
        )
    )
    session.commit()
    return oauth.build_authorize_url(settings, raw)


def complete_google_callback(
    session_factory: Callable[[], Session],
    clock: Clock,
    settings: Settings,
    user_id: uuid.UUID,
    *,
    code: str | None,
    state: str | None,
    error: str | None,
) -> CalendarCallbackOutcome:
    if not state or len(state) > 512:
        raise AppError("OAUTH_STATE_INVALID")
    sh = hash_token(state)
    with session_factory() as session:
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            resolved = session.execute(
                text(
                    "SELECT id, workspace_id FROM public.resolve_calendar_oauth_state_by_hash(:sh)"
                ),
                {"sh": sh},
            ).first()
            if resolved is not None:
                set_tenant_context(session, resolved.workspace_id)
                row = session.get(CalendarOAuthState, resolved.id, with_for_update=True)
            else:
                row = None
        else:
            row = session.scalars(
                select(CalendarOAuthState)
                .where(CalendarOAuthState.state_hash == sh)
                .with_for_update()
            ).one_or_none()
        if (
            row is None
            or row.user_id != user_id
            or row.used_at is not None
            or row.invalidated_at is not None
            or row.expires_at <= clock.now()
        ):
            raise AppError("OAUTH_STATE_INVALID")
        row.used_at = clock.now()
        workspace_id = row.workspace_id
        state_id = row.id
        conn_id = row.calendar_connection_id
        purpose = row.purpose
        session.commit()
        try:
            _context(session, workspace_id, user_id)
            if "google" not in settings.calendar_providers:
                raise AppError("FORBIDDEN")
        except AppError as exc:
            return CalendarCallbackOutcome(workspace_id, exc.code)
    try:
        if error is not None or not code or len(code) > 4096:
            raise AppError("OAUTH_STATE_INVALID")
        exchanged = oauth.exchange_code_for_tokens(settings, code)
        with session_factory() as session:
            lock_workspace(session, workspace_id)
            ctx = _context(session, workspace_id, user_id)
            if conversation_deletion.pending(session, workspace_id):
                raise AppError("CONFLICT_STATE")
            current_state = session.get(CalendarOAuthState, state_id)
            if current_state is None or current_state.invalidated_at is not None:
                raise AppError("OAUTH_STATE_INVALID")
            active = queries.get_active_connection_for_workspace(session, workspace_id)
            if purpose == "reconnect":
                conn = (
                    queries.get_connection_in_workspace(session, workspace_id, conn_id, lock=True)
                    if conn_id
                    else None
                )
                if conn is None or conn.status == "disconnected" or conn.provider_kind != "google":
                    raise AppError("CONFLICT_STATE")
            else:
                if active is not None:
                    raise AppError("CONFLICT_STATE")
                conn = session.scalars(
                    select(CalendarConnection)
                    .where(
                        CalendarConnection.workspace_id == workspace_id,
                        CalendarConnection.provider_kind == "google",
                        CalendarConnection.external_account_id == exchanged.external_account_id,
                        CalendarConnection.status == "disconnected",
                    )
                    .order_by(CalendarConnection.created_at.desc(), CalendarConnection.id)
                    .limit(1)
                    .with_for_update()
                ).first()
                if conn is None:
                    conn = CalendarConnection(
                        id=new_id(),
                        workspace_id=workspace_id,
                        provider_kind="google",
                        external_account_id=exchanged.external_account_id,
                        status="connected",
                    )
                    session.add(conn)
            conn.account_email = exchanged.account_email
            conn.calendar_id = exchanged.calendar_id or "primary"
            conn.calendar_summary = exchanged.calendar_summary
            conn.calendar_timezone = exchanged.calendar_timezone
            conn.capabilities = oauth.compute_capabilities(exchanged.granted_scopes)
            conn.granted_scopes = exchanged.granted_scopes
            ring = TokenKeyRing(
                settings.token_encryption_keys.get_secret_value(),
                settings.token_encryption_active_key_id,
            )
            aad = account_token_aad(workspace_id, conn.id)
            conn.token_ciphertext, conn.token_key_id = ring.encrypt(exchanged.access_token, aad=aad)
            if exchanged.refresh_token:
                conn.refresh_token_ciphertext, _ = ring.encrypt(exchanged.refresh_token, aad=aad)
            conn.token_expires_at = clock.now() + timedelta(seconds=exchanged.expires_in_seconds)
            conn.token_refreshed_at = clock.now()
            if purpose == "reconnect" or conn.status == "disconnected":
                transition_calendar_connection(
                    session, clock, ctx, conn, "connected", reauthorized=True
                )
            else:
                conn.connected_at = clock.now()
                session.flush()
                audit.record(
                    session,
                    ctx,
                    "calendar.connected",
                    "calendar_connection",
                    conn.id,
                    {"from": None, "provider_kind": "google", "calendar_id": conn.calendar_id},
                    is_simulated=False,
                    clock=clock,
                )
            session.commit()
            return CalendarCallbackOutcome(workspace_id)
    except AppError as exc:
        return CalendarCallbackOutcome(workspace_id, exc.code)
    except CalendarProviderError as exc:
        return CalendarCallbackOutcome(workspace_id, exc.code)
    except IntegrityError:
        return CalendarCallbackOutcome(workspace_id, "CONFLICT_STATE")


def update_connection_settings(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    connection_id: uuid.UUID,
    *,
    default_slot_duration_minutes: int,
) -> CalendarConnection:
    conn = queries.get_connection(session, ctx, connection_id, lock=True)
    if conn is None or conn.status == "disconnected":
        raise AppError("NOT_FOUND")
    if not (15 <= default_slot_duration_minutes <= 240):
        raise AppError("VALIDATION_FAILED")
    conn.default_slot_duration_minutes = default_slot_duration_minutes
    conn.updated_at = clock.now()
    session.commit()
    return conn


def disconnect_calendar(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    connection_id: uuid.UUID,
) -> CalendarConnection:
    lock_workspace(session, ctx.workspace_id)
    conn = queries.get_connection(session, ctx, connection_id, lock=True)
    if conn is None:
        raise AppError("NOT_FOUND")
    if conn.status == "disconnected":
        return conn
    conn.token_ciphertext = None
    conn.refresh_token_ciphertext = None
    conn.token_key_id = None
    conn.token_expires_at = None
    session.execute(
        update(CalendarOAuthState)
        .where(
            CalendarOAuthState.workspace_id == ctx.workspace_id,
            CalendarOAuthState.used_at.is_(None),
            CalendarOAuthState.invalidated_at.is_(None),
        )
        .values(invalidated_at=clock.now())
    )
    transition_calendar_connection(session, clock, ctx, conn, "disconnected")
    session.commit()
    return conn


def _resolve_workspace_tz(tz_name: str | None) -> tuple[ZoneInfo, str]:
    name = tz_name or "Europe/Istanbul"
    try:
        return ZoneInfo(name), name
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC"), "UTC"


def _load_verified_hours(session: Session, workspace_id: uuid.UUID) -> WeeklyHoursValue | None:
    fact = session.scalars(
        select(BusinessFact)
        .where(
            BusinessFact.workspace_id == workspace_id,
            BusinessFact.category == "hours",
            BusinessFact.value_type == "weekly_hours",
            BusinessFact.status == "verified",
        )
        .order_by(BusinessFact.updated_at.desc())
        .limit(1)
    ).first()
    if fact is None:
        return None
    try:
        return WeeklyHoursValue.model_validate(fact.value)
    except Exception:
        return None


def _day_open_ranges(hours: WeeklyHoursValue | None, local_date: date) -> list[tuple[int, int]]:
    if hours is None:
        # Default fallback window 09:00-18:00 when no verified hours fact is configured
        return [(9 * 60, 18 * 60)]
    for exc in hours.exceptions:
        if exc.date == local_date:
            if exc.closed:
                return []
            return [(time_to_minutes(o), time_to_minutes(c)) for o, c in exc.ranges]
    day_key = WEEKDAYS[local_date.weekday()]
    day_ranges: list[tuple[str, str]] = getattr(hours, day_key, [])
    return [(time_to_minutes(o), time_to_minutes(c)) for o, c in day_ranges]


def check_availability(
    session_factory: Callable[[], Session],
    clock: Clock,
    settings: Settings,
    workspace_id: uuid.UUID,
    *,
    window_start: datetime,
    window_end: datetime,
    duration_minutes: int | None = None,
    requested_start_at: datetime | None = None,
    session: Session | None = None,
) -> AvailabilityResult:
    def _load_db_state(
        db: Session,
    ) -> tuple[
        ZoneInfo,
        str,
        CalendarConnection | None,
        WeeklyHoursValue | None,
        list[BusyInterval],
        list[BusyInterval] | None,
    ]:
        set_tenant_context(db, workspace_id)
        ws = db.get(Workspace, workspace_id)
        resolved_tz, resolved_tz_name = _resolve_workspace_tz(ws.timezone if ws else None)
        active_conn = queries.get_active_connection_for_workspace(db, workspace_id)
        verified_hours = _load_verified_hours(db, workspace_id)
        if active_conn is None or active_conn.status not in ("connected", "degraded"):
            return resolved_tz, resolved_tz_name, None, verified_hours, [], None
        appts = queries.list_appointments_in_window(db, workspace_id, window_start, window_end)
        local_busy = [
            BusyInterval(start_at=a.start_at.astimezone(UTC), end_at=a.end_at.astimezone(UTC))
            for a in appts
        ]
        sim_busy: list[BusyInterval] | None = None
        if active_conn.provider_kind == "mock":
            sim_rows = list(
                db.scalars(
                    select(SimCalendarEvent)
                    .where(
                        SimCalendarEvent.workspace_id == workspace_id,
                        SimCalendarEvent.calendar_connection_id == active_conn.id,
                        SimCalendarEvent.status == "confirmed",
                        SimCalendarEvent.start_at < window_end,
                        SimCalendarEvent.end_at > window_start,
                    )
                    .order_by(SimCalendarEvent.start_at.asc())
                )
            )
            sim_busy = [
                BusyInterval(start_at=r.start_at.astimezone(UTC), end_at=r.end_at.astimezone(UTC))
                for r in sim_rows
            ]
        return resolved_tz, resolved_tz_name, active_conn, verified_hours, local_busy, sim_busy

    if session is not None:
        tz, tz_name, conn, hours, appt_busy, mock_busy = _load_db_state(session)
    else:
        with session_factory() as db_sess:
            tz, tz_name, conn, hours, appt_busy, mock_busy = _load_db_state(db_sess)

    if conn is None:
        return AvailabilityResult(
            calendar_connected=False,
            timezone=tz_name,
            slot_duration_minutes=duration_minutes or 30,
            hours_verified=hours is not None,
            requested_slot_available=None,
            available_slots=[],
            busy_intervals=[],
        )

    slot_mins = duration_minutes or conn.default_slot_duration_minutes
    if mock_busy is not None:
        provider_busy = mock_busy
    else:
        ref = registry.calendar_ref(conn, settings)
        provider = registry.get_calendar_provider(
            conn.provider_kind, settings=settings, session_factory=session_factory, clock=clock
        )
        provider_busy = provider.list_busy_intervals(ref, window_start, window_end)
    all_busy = sorted(
        [*appt_busy, *provider_busy],
        key=lambda b: (b.start_at, b.end_at),
    )

    def _is_range_free(start_utc: datetime, end_utc: datetime) -> bool:
        if end_utc <= start_utc:
            return False
        local_s = start_utc.astimezone(tz)
        local_e = end_utc.astimezone(tz)
        if local_s.date() != local_e.date() and not (
            local_e.date() == local_s.date() + timedelta(days=1)
            and local_e.hour == 0
            and local_e.minute == 0
        ):
            return False
        s_mins = local_s.hour * 60 + local_s.minute
        e_mins = 1440 if local_e.date() > local_s.date() else local_e.hour * 60 + local_e.minute
        open_ranges = _day_open_ranges(hours, local_s.date())
        if not any(o <= s_mins and e_mins <= c for o, c in open_ranges):
            return False
        return not any(b.start_at < end_utc and b.end_at > start_utc for b in all_busy)

    now_utc = clock.now().astimezone(UTC)
    effective_start = max(window_start.astimezone(UTC), now_utc)
    effective_end = window_end.astimezone(UTC)

    slots: list[AvailableSlot] = []
    cur_date = effective_start.astimezone(tz).date()
    end_date = effective_end.astimezone(tz).date()
    step_mins = min(slot_mins, 30)

    while cur_date <= end_date and len(slots) < 48:
        for open_m, close_m in _day_open_ranges(hours, cur_date):
            m = open_m
            while m + slot_mins <= close_m and len(slots) < 48:
                sh, sm = divmod(m, 60)
                eh, em = divmod(m + slot_mins, 60)
                s_local = datetime.combine(cur_date, time(sh, sm), tzinfo=tz)
                e_local = (
                    datetime.combine(cur_date + timedelta(days=1), time(0, 0), tzinfo=tz)
                    if eh == 24
                    else datetime.combine(cur_date, time(eh, em), tzinfo=tz)
                )
                s_utc = s_local.astimezone(UTC)
                e_utc = e_local.astimezone(UTC)
                if (
                    s_utc >= effective_start
                    and e_utc <= effective_end
                    and _is_range_free(s_utc, e_utc)
                ):
                    slots.append(
                        AvailableSlot(
                            start_at=s_utc,
                            end_at=e_utc,
                            local_date=cur_date.isoformat(),
                            local_start_time=f"{sh:02d}:{sm:02d}",
                            local_end_time="24:00" if eh == 24 else f"{eh:02d}:{em:02d}",
                        )
                    )
                m += step_mins
        cur_date += timedelta(days=1)

    req_available: bool | None = None
    if requested_start_at is not None:
        req_s = requested_start_at.astimezone(UTC)
        req_e = req_s + timedelta(minutes=slot_mins)
        req_available = req_s >= now_utc and _is_range_free(req_s, req_e)

    return AvailabilityResult(
        calendar_connected=True,
        timezone=tz_name,
        slot_duration_minutes=slot_mins,
        hours_verified=hours is not None,
        requested_slot_available=req_available,
        available_slots=slots,
        busy_intervals=all_busy,
    )


def _terminal(db: Session, clock: Clock, action: AgentAction, status: str, code: str) -> None:
    action.status, action.outcome_code = status, code
    audit.record(
        db,
        None,
        "agent.action_transition",
        "agent_action",
        action.id,
        {"status": status, "code": code},
        workspace_id=action.workspace_id,
        clock=clock,
    )


def _wake(factory: sessionmaker[Session], clock: Clock, action_id: uuid.UUID) -> None:
    from app.agent.jobs import wake

    with factory() as db:
        action = db.get(AgentAction, action_id)
        if action is not None:
            wake(
                db,
                clock,
                action.workspace_id,
                action.thread_id,
                f"calendar-effect:{action.id}:{action.status}",
            )
            db.commit()


def _queue_reconcile(db: Session, clock: Clock, op: Operation) -> None:
    enqueue(
        db,
        "reconcile_calendar_effect",
        ReconcileCalendarPayload(operation_id=op.id),
        workspace_id=op.workspace_id,
        correlation_id=op.id,
        run_at=clock.now() + timedelta(seconds=2),
        dedup_key=f"reconcile_calendar_effect:{op.id}",
        clock=clock,
    )


@dataclass(frozen=True)
class _PreparedCalendarOp:
    operation_id: uuid.UUID
    operation_key: str
    operation_type: Literal[
        "calendar_create_event", "calendar_update_event", "calendar_cancel_event"
    ]
    provider_kind: str
    calendar_ref: CalendarRef
    spec: CalendarEventSpec | None
    external_event_id: str | None


def _prepare(
    db: Session, clock: Clock, settings: Settings, workspace_id: uuid.UUID, action_id: uuid.UUID
) -> _PreparedCalendarOp | None:
    set_tenant_context(db, workspace_id)
    candidate = db.scalar(
        select(AgentAction).where(
            AgentAction.id == action_id, AgentAction.workspace_id == workspace_id
        )
    )
    if candidate is None:
        return None
    from app.agent.repository import scoped_account

    scoped_account(db, workspace_id, candidate.social_account_id, lock=True)
    action = db.scalar(
        select(AgentAction)
        .where(AgentAction.id == action_id, AgentAction.workspace_id == workspace_id)
        .with_for_update()
    )
    if action is None or action.status not in {
        "queued",
        "authorized",
        "in_progress",
        "outcome_unknown",
    }:
        return None

    intent: dict[str, Any] = dict(action.content_intent or {})
    conn = queries.get_active_connection_for_workspace(db, workspace_id, lock=True)
    if conn is None or conn.status not in {"connected", "degraded"}:
        _terminal(db, clock, action, "cancelled", "CALENDAR_NOT_CONNECTED")
        return None

    op_type_map: dict[
        str, Literal["calendar_create_event", "calendar_update_event", "calendar_cancel_event"]
    ] = {
        "calendar.book": "calendar_create_event",
        "calendar.reschedule": "calendar_update_event",
        "calendar.cancel": "calendar_cancel_event",
    }
    op_type = op_type_map.get(action.action_type)
    if op_type is None:
        return None

    key = f"{op_type}:{action.id}"
    op = db.scalar(select(Operation).where(Operation.idempotency_key == key).with_for_update())
    if op is not None:
        action.operation_id = op.id
        if op.status in {"in_progress", "outcome_unknown"}:
            if op.status == "in_progress":
                set_operation(clock, op, "unknown", code="WORKER_INTERRUPTED")
                action.status = "outcome_unknown"
                _queue_reconcile(db, clock, op)
            return None
        if op.status in {"succeeded", "failed", "cancelled"}:
            action.status = op.status
            return None

    try:
        fence_action(
            db,
            clock,
            workspace_id,
            action.id,
            expected_action=action.action_type,
            payload_hash_value=action.payload_hash,
        )
        if action.policy_grant is None:
            approval = db.get(Approval, action.approval_id) if action.approval_id else None
            if (
                approval is None
                or approval.status != "approved"
                or approval.subject_type != "agent_action"
                or approval.subject_id != action.id
                or approval.subject_version != action.version
                or approval.payload_hash != action.payload_hash
                or (approval.execute_before is not None and clock.now() >= approval.execute_before)
            ):
                raise AppError("APPROVAL_STALE")
    except AppError:
        _terminal(db, clock, action, "cancelled", "APPROVAL_STALE")
        return None

    appt = (
        queries.get_appointment_in_workspace(db, workspace_id, action.payload_ref, lock=True)
        if action.payload_ref
        else None
    )

    spec: CalendarEventSpec | None = None
    ext_event_id: str | None = None

    if action.action_type == "calendar.book":
        start_at = datetime.fromisoformat(str(intent["start_at"]))
        end_at = datetime.fromisoformat(str(intent["end_at"]))
        tz_name = str(intent.get("timezone") or conn.calendar_timezone or "UTC")
        title = str(intent.get("title") or "Appointment")
        desc = intent.get("description")
        if appt is None:
            appt = CalendarAppointment(
                id=action.payload_ref or new_id(),
                workspace_id=workspace_id,
                calendar_connection_id=conn.id,
                conversation_id=(
                    uuid.UUID(str(intent["conversation_id"]))
                    if intent.get("conversation_id")
                    else None
                ),
                customer_identity_id=(
                    uuid.UUID(str(intent["customer_identity_id"]))
                    if intent.get("customer_identity_id")
                    else None
                ),
                title=title,
                description=desc,
                customer_name=intent.get("customer_name"),
                customer_contact=intent.get("customer_contact"),
                start_at=start_at,
                end_at=end_at,
                timezone=tz_name,
                status="scheduled",
                created_by_source=str(intent.get("created_by_source") or "customer"),
                is_simulated=conn.is_simulated,
                version=1,
            )
            db.add(appt)
            db.flush()
            action.payload_ref = appt.id
        spec = CalendarEventSpec(
            title=appt.title,
            description=appt.description,
            start_at=appt.start_at,
            end_at=appt.end_at,
            timezone=appt.timezone,
        )
    elif action.action_type == "calendar.reschedule":
        expected_version = int(intent.get("expected_version") or 1)
        if appt is None or appt.status != "scheduled" or appt.version != expected_version:
            _terminal(db, clock, action, "cancelled", "APPROVAL_STALE")
            return None
        start_at = datetime.fromisoformat(str(intent["new_start_at"]))
        end_at = datetime.fromisoformat(str(intent["new_end_at"]))
        spec = CalendarEventSpec(
            title=str(intent.get("title") or appt.title),
            description=intent.get("description", appt.description),
            start_at=start_at,
            end_at=end_at,
            timezone=appt.timezone,
        )
        ext_event_id = appt.external_event_id or f"sim_evt_{appt.id.hex[:16]}"
    elif action.action_type == "calendar.cancel":
        expected_version = int(intent.get("expected_version") or 1)
        if appt is None or appt.status != "scheduled" or appt.version != expected_version:
            _terminal(db, clock, action, "cancelled", "APPROVAL_STALE")
            return None
        ext_event_id = appt.external_event_id or f"sim_evt_{appt.id.hex[:16]}"

    if appt is None:
        return None

    if op is None:
        op = Operation(
            id=new_id(),
            workspace_id=workspace_id,
            operation_type=op_type,
            idempotency_key=key,
            subject_type="calendar_appointment",
            subject_id=appt.id,
            social_account_id=action.social_account_id,
            provider_kind=conn.provider_kind,
            status="pending",
            attempts=0,
            max_attempts=1,
            deadline_at=action.execute_before,
            is_simulated=conn.is_simulated,
            created_at=clock.now(),
        )
        db.add(op)
        db.flush()

    action.operation_id = op.id
    if action.policy_grant is None and action.approval_id:
        approval = db.get(Approval, action.approval_id)
        if approval is not None:
            if approval.operation_id is not None and approval.operation_id != op.id:
                _terminal(db, clock, action, "cancelled", "APPROVAL_STALE")
                return None
            approval.operation_id = op.id

    set_operation(clock, op, "start")
    op.attempts += 1
    op.started_at = clock.now()
    op.provider_ref = {
        "calendar_connection_id": str(conn.id),
        "appointment_id": str(appt.id),
        "external_event_id": ext_event_id,
    }
    action.status = "in_progress"
    return _PreparedCalendarOp(
        operation_id=op.id,
        operation_key=op.idempotency_key,
        operation_type=op_type,
        provider_kind=conn.provider_kind,
        calendar_ref=registry.calendar_ref(conn, settings),
        spec=spec,
        external_event_id=ext_event_id,
    )


def _finish(
    db: Session,
    clock: Clock,
    op: Operation,
    answer: CalendarEventInfo | None,
    error: Exception | None,
) -> None:
    set_tenant_context(db, op.workspace_id)
    action = db.scalar(
        select(AgentAction).where(AgentAction.operation_id == op.id).with_for_update()
    )
    if action is None or op.status not in {"in_progress", "outcome_unknown"}:
        return
    appt = (
        queries.get_appointment_in_workspace(db, op.workspace_id, op.subject_id, lock=True)
        if op.subject_id
        else None
    )
    intent: dict[str, Any] = dict(action.content_intent or {})
    if answer is not None:
        set_operation(clock, op, "succeed")
        op.result = {
            "external_event_id": answer.external_event_id,
            "status": answer.status,
            "start_at": answer.start_at.isoformat(),
            "end_at": answer.end_at.isoformat(),
        }
        action.status = "succeeded"
        audit_name = "calendar.appointment_booked"
        if appt is not None:
            appt.external_event_id = answer.external_event_id
            appt.updated_at = clock.now()
            if action.action_type == "calendar.reschedule":
                appt.start_at = answer.start_at
                appt.end_at = answer.end_at
                appt.version += 1
                audit_name = "calendar.appointment_rescheduled"
            elif action.action_type == "calendar.cancel":
                appt.status = "cancelled"
                appt.cancelled_at = clock.now()
                appt.cancellation_reason = str(intent.get("reason") or "") or None
                appt.version += 1
                audit_name = "calendar.appointment_cancelled"
            audit.record(
                db,
                None,
                audit_name,
                "calendar_appointment",
                appt.id,
                {
                    "action_id": str(action.id),
                    "external_event_id": answer.external_event_id,
                    "start_at": appt.start_at.isoformat(),
                    "end_at": appt.end_at.isoformat(),
                },
                workspace_id=op.workspace_id,
                is_simulated=op.is_simulated,
                clock=clock,
            )
    elif (
        isinstance(error, CalendarProviderError)
        and not isinstance(error, CalendarOutcomeUnknown)
        and op.status == "in_progress"
    ):
        code = error.request_code if isinstance(error, CalendarInvalidRequest) else error.code
        set_operation(clock, op, "fail", code=code)
        action.status, action.outcome_code = "failed", code
        if (
            appt is not None
            and action.action_type == "calendar.book"
            and not appt.external_event_id
        ):
            appt.status = "cancelled"
            appt.cancelled_at = clock.now()
    else:
        if op.status == "in_progress":
            set_operation(clock, op, "unknown", code="OUTCOME_UNKNOWN")
        action.status = "outcome_unknown"
        _queue_reconcile(db, clock, op)

    audit.record(
        db,
        None,
        "agent.action_transition",
        "agent_action",
        action.id,
        {"status": action.status, "operation_id": op.id, "action_type": action.action_type},
        workspace_id=action.workspace_id,
        is_simulated=op.is_simulated,
        clock=clock,
    )


def execute_calendar_action(
    factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
    workspace_id: uuid.UUID,
    action_id: uuid.UUID,
) -> None:
    with factory() as db:
        prepared = _prepare(db, clock, settings, workspace_id, action_id)
        db.commit()
    if prepared is None:
        _wake(factory, clock, action_id)
        return
    provider = registry.get_calendar_provider(
        prepared.provider_kind, settings=settings, session_factory=factory, clock=clock
    )
    answer: CalendarEventInfo | None = None
    error: Exception | None = None
    try:
        if prepared.operation_type == "calendar_create_event" and prepared.spec is not None:
            answer = provider.create_event(
                prepared.calendar_ref, prepared.spec, prepared.operation_key
            )
        elif (
            prepared.operation_type == "calendar_update_event"
            and prepared.spec is not None
            and prepared.external_event_id is not None
        ):
            answer = provider.update_event(
                prepared.calendar_ref,
                prepared.external_event_id,
                prepared.spec,
                prepared.operation_key,
            )
        elif (
            prepared.operation_type == "calendar_cancel_event"
            and prepared.external_event_id is not None
        ):
            answer = provider.cancel_event(
                prepared.calendar_ref, prepared.external_event_id, prepared.operation_key
            )
    except Exception as exc:
        error = exc

    with factory() as db:
        set_tenant_context(db, workspace_id)
        op = db.scalar(
            select(Operation)
            .where(Operation.id == prepared.operation_id, Operation.workspace_id == workspace_id)
            .with_for_update()
        )
        if op is not None:
            _finish(db, clock, op, answer, error)
        db.commit()
    _wake(factory, clock, action_id)


def reconcile_calendar_operation(
    factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
    workspace_id: uuid.UUID,
    operation_id: uuid.UUID,
) -> None:
    with factory() as db:
        set_tenant_context(db, workspace_id)
        op = db.scalar(
            select(Operation).where(
                Operation.id == operation_id, Operation.workspace_id == workspace_id
            )
        )
        if op is None or op.status != "outcome_unknown":
            return
        conn_id_str = (op.provider_ref or {}).get("calendar_connection_id")
        conn = (
            queries.get_connection_in_workspace(db, workspace_id, uuid.UUID(str(conn_id_str)))
            if conn_id_str
            else queries.get_active_connection_for_workspace(db, workspace_id)
        )
        if conn is None:
            return
        ref = registry.calendar_ref(conn, settings)
        provider_kind = conn.provider_kind
        key = op.idempotency_key

    provider = registry.get_calendar_provider(
        provider_kind, settings=settings, session_factory=factory, clock=clock
    )
    try:
        answer = provider.find_event_by_operation_key(ref, key)
    except Exception:
        return
    if answer is None:
        return
    with factory() as db:
        set_tenant_context(db, workspace_id)
        op = db.scalar(
            select(Operation)
            .where(Operation.id == operation_id, Operation.workspace_id == workspace_id)
            .with_for_update()
        )
        if op is not None and op.status == "outcome_unknown":
            _finish(db, clock, op, answer, None)
            action = db.scalar(select(AgentAction).where(AgentAction.operation_id == op.id))
            action_id = action.id if action else None
            db.commit()
            if action_id:
                _wake(factory, clock, action_id)


@job_handler("calendar_effect", CalendarEffectPayload, max_attempts=1)
def execute_calendar_job(job: JobContext) -> None:
    if isinstance(job.payload, CalendarEffectPayload) and job.workspace_id:
        execute_calendar_action(
            job.session_factory,
            job.clock,
            get_settings(),
            job.workspace_id,
            job.payload.action_id,
        )


@job_handler("reconcile_calendar_effect", ReconcileCalendarPayload, max_attempts=1)
def reconcile_calendar_job(job: JobContext) -> None:
    if isinstance(job.payload, ReconcileCalendarPayload) and job.workspace_id:
        reconcile_calendar_operation(
            job.session_factory,
            job.clock,
            get_settings(),
            job.workspace_id,
            job.payload.operation_id,
        )
