"""System health for the owner and the manager (observability.md section 6, plan H13).

Everything is counted from tables, scoped to one workspace, except the signature-failure count:
those audit rows have no workspace (a forged request cannot be attributed), so the number is
system-wide and labelled as such. Only counts, codes, ids and times are returned: no payload,
no message text, no error detail.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.ai.models import AgentRun
from app.ai.runner import BUDGET_EXCEEDED, BUDGET_WINDOW
from app.audit import service as audit
from app.audit.models import AuditLog
from app.core.clock import Clock
from app.core.config import REPO_ROOT, Settings, get_settings
from app.core.context import WorkspaceContext
from app.inbox.models import InboundEvent
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.operations.models import Operation

WINDOW = timedelta(hours=24)
BACKUP_STALE_THRESHOLD = timedelta(hours=26)
LATEST_FAILURES = 5
FAILED_OPERATION_STATUSES = ("failed", "outcome_unknown")
BACKUP_AUDIT_ACTIONS = ("system.backup_succeeded", "system.backup_failed")


class BackupHealth(BaseModel):
    """System-wide backup heartbeat & staleness status (ADR-025 §4.3, P8-02 / P8-07)."""

    last_backup_at: datetime | None
    last_succeeded_at: datetime | None = None
    last_backup_status: Literal["succeeded", "failed", "missing"]
    last_backup_id: str | None = None
    last_error_code: str | None = None
    last_archive_key: str | None = None
    last_size_bytes: int | None = None
    age_seconds: int | None = None
    stale_or_failed: bool

    @property
    def last_success_at(self) -> datetime | None:
        return self.last_succeeded_at

    @property
    def last_error(self) -> str | None:
        return self.last_error_code


class AccountHealth(BaseModel):
    id: uuid.UUID
    username: str | None
    status: str
    last_error_code: str | None
    connection_expires_at: datetime | None
    degraded_until: datetime | None
    is_simulated: bool


class OperationCount(BaseModel):
    type: str
    status: str
    count: int


class OperationFailure(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    last_error_code: str | None
    occurred_at: datetime
    is_simulated: bool


class OperationsHealth(BaseModel):
    counts: list[OperationCount]
    latest_failures: list[OperationFailure]


class JobsHealth(BaseModel):
    queued: int
    oldest_queued_age_seconds: int | None
    dead_24h: int


class WebhooksHealth(BaseModel):
    received_24h: int
    ignored_24h: int
    failed_24h: int
    # System-wide: a request with a bad signature belongs to no workspace.
    signature_failures_24h_system_wide: int


class AiRunCount(BaseModel):
    task: str
    status: str
    count: int


class AiHealth(BaseModel):
    runs: list[AiRunCount]
    total: int
    failed: int
    failure_rate: float
    input_units: int
    output_units: int
    estimated_cost_usd: float | None
    budget_used: int
    budget_limit: int


class SystemHealthOut(BaseModel):
    generated_at: datetime
    window_hours: int
    accounts: list[AccountHealth]
    operations: OperationsHealth
    jobs: JobsHealth
    webhooks: WebhooksHealth
    ai: AiHealth


def _accounts(session: Session, ctx: WorkspaceContext) -> list[AccountHealth]:
    rows = session.scalars(
        select(SocialAccount)
        .where(SocialAccount.workspace_id == ctx.workspace_id)
        .order_by(SocialAccount.created_at, SocialAccount.id)
    )
    return [
        AccountHealth(
            id=a.id,
            username=a.username,
            status=a.status,
            last_error_code=a.last_error_code,
            connection_expires_at=a.token_expires_at,
            degraded_until=a.degraded_until,
            is_simulated=a.is_simulated,
        )
        for a in rows
    ]


def _operations(session: Session, ctx: WorkspaceContext, since: datetime) -> OperationsHealth:
    stamp = func.coalesce(Operation.completed_at, Operation.created_at)
    counts = session.execute(
        select(Operation.operation_type, Operation.status, func.count())
        .where(Operation.workspace_id == ctx.workspace_id, Operation.created_at >= since)
        .group_by(Operation.operation_type, Operation.status)
        .order_by(Operation.operation_type, Operation.status)
    ).all()
    failures = session.execute(
        select(Operation, stamp)
        .where(
            Operation.workspace_id == ctx.workspace_id,
            Operation.status.in_(FAILED_OPERATION_STATUSES),
            stamp >= since,
        )
        .order_by(stamp.desc(), Operation.id)
        .limit(LATEST_FAILURES)
    ).all()
    return OperationsHealth(
        counts=[OperationCount(type=t, status=s, count=n) for t, s, n in counts],
        latest_failures=[
            OperationFailure(
                id=op.id,
                type=op.operation_type,
                status=op.status,
                last_error_code=op.last_error_code,
                occurred_at=at,
                is_simulated=op.is_simulated,
            )
            for op, at in failures
        ],
    )


def _jobs(session: Session, ctx: WorkspaceContext, now: datetime, since: datetime) -> JobsHealth:
    queued, oldest = session.execute(
        select(func.count(), func.min(Job.run_at)).where(
            Job.workspace_id == ctx.workspace_id, Job.status == "queued"
        )
    ).one()
    dead = session.scalar(
        select(func.count()).where(
            Job.workspace_id == ctx.workspace_id,
            Job.status == "dead",
            func.coalesce(Job.finished_at, Job.updated_at) >= since,
        )
    )
    age = max(0, int((now - oldest).total_seconds())) if oldest is not None else None
    return JobsHealth(queued=int(queued), oldest_queued_age_seconds=age, dead_24h=int(dead or 0))


def _webhooks(session: Session, ctx: WorkspaceContext, since: datetime) -> WebhooksHealth:
    def events(status: str | None = None) -> int:
        stmt = select(func.count()).where(
            InboundEvent.workspace_id == ctx.workspace_id, InboundEvent.received_at >= since
        )
        if status is not None:
            stmt = stmt.where(InboundEvent.status == status)
        return int(session.scalar(stmt) or 0)

    signature = session.scalar(
        select(func.count()).where(
            AuditLog.action == "webhook.signature_invalid",
            AuditLog.workspace_id.is_(None),
            AuditLog.occurred_at >= since,
        )
    )
    return WebhooksHealth(
        received_24h=events(),
        ignored_24h=events("ignored"),
        failed_24h=events("failed"),
        signature_failures_24h_system_wide=int(signature or 0),
    )


def estimate_cost(
    price_table: str, model: str | None, input_units: int, output_units: int
) -> float | None:
    """USD from ``LLM_PRICE_TABLE`` (per million tokens); ``None`` for an unpriced model."""
    if not price_table or model is None:
        return None
    try:
        price = json.loads(price_table).get(model)
        if not price:
            return None
        return input_units / 1_000_000 * float(
            price["input_per_mtok"]
        ) + output_units / 1_000_000 * float(price["output_per_mtok"])
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def _ai(
    session: Session, ctx: WorkspaceContext, settings: Settings, now: datetime, since: datetime
) -> AiHealth:
    runs = session.execute(
        select(AgentRun.task, AgentRun.status, func.count())
        .where(AgentRun.workspace_id == ctx.workspace_id, AgentRun.created_at >= since)
        .group_by(AgentRun.task, AgentRun.status)
        .order_by(AgentRun.task, AgentRun.status)
    ).all()
    total = sum(n for _, _, n in runs)
    failed = sum(n for _, status, n in runs if status == "failed")

    by_model = session.execute(
        select(
            AgentRun.model,
            func.coalesce(func.sum(AgentRun.input_tokens), 0),
            func.coalesce(func.sum(AgentRun.output_tokens), 0),
        )
        .where(AgentRun.workspace_id == ctx.workspace_id, AgentRun.created_at >= since)
        .group_by(AgentRun.model)
    ).all()
    usage = [(m, int(i or 0), int(o or 0)) for m, i, o in by_model]
    input_units = sum(i for _, i, _ in usage)
    output_units = sum(o for _, _, o in usage)
    costs = [estimate_cost(settings.llm_price_table, m, i, o) for m, i, o in usage]
    priced = [c for c in costs if c is not None]
    used = session.scalar(
        select(func.count()).where(
            AgentRun.workspace_id == ctx.workspace_id,
            AgentRun.created_at >= now - BUDGET_WINDOW,
            AgentRun.status != "queued",
            or_(AgentRun.error_code.is_(None), AgentRun.error_code != BUDGET_EXCEEDED),
        )
    )
    return AiHealth(
        runs=[AiRunCount(task=t, status=s, count=n) for t, s, n in runs],
        total=total,
        failed=failed,
        failure_rate=round(failed / total, 4) if total else 0.0,
        input_units=input_units,
        output_units=output_units,
        estimated_cost_usd=round(sum(priced), 6) if priced else None,
        budget_used=int(used or 0),
        budget_limit=settings.llm_max_calls_per_workspace_per_day,
    )


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def resolve_backup_status_path(
    settings: Settings | None = None, *, status_path: Path | None = None
) -> Path:
    if status_path is not None:
        return status_path
    resolved = settings or get_settings()
    candidate = Path(resolved.backup_status_file)
    return candidate if candidate.is_absolute() else (REPO_ROOT / candidate)


def record_backup_audit(
    session: Session,
    clock: Clock,
    *,
    status: Literal["succeeded", "failed"] | None = None,
    succeeded: bool | None = None,
    backup_id: str = "",
    archive_key: str | None = None,
    size_bytes: int | None = None,
    archive_size_bytes: int | None = None,
    sha256: str | None = None,
    archive_sha256: str | None = None,
    alembic_revision: str | None = None,
    pruned_count: int = 0,
    error_code: str | None = None,
    error_message: str | None = None,
) -> AuditLog:
    """Record a system-level backup outcome in ``audit_logs`` (content-free metadata; INV-12)."""
    if status is not None:
        resolved_status: Literal["succeeded", "failed"] = status
    elif succeeded is not None:
        resolved_status = "succeeded" if succeeded else "failed"
    else:
        resolved_status = "succeeded"

    action = "system.backup_succeeded" if resolved_status == "succeeded" else "system.backup_failed"
    metadata: dict[str, Any] = {
        "backup_id": backup_id,
        "status": resolved_status,
        "pruned_count": int(pruned_count),
    }
    if archive_key:
        metadata["archive_key"] = archive_key
    effective_size = size_bytes if size_bytes is not None else archive_size_bytes
    if effective_size is not None:
        metadata["size_bytes"] = int(effective_size)
    effective_sha = sha256 or archive_sha256
    if effective_sha:
        metadata["sha256"] = effective_sha
    if alembic_revision:
        metadata["alembic_revision"] = alembic_revision
    effective_err = error_code or error_message
    if effective_err:
        metadata["error_code"] = effective_err
        metadata["error"] = effective_err
    return audit.record(
        session,
        None,
        action,
        "backup",
        None,
        metadata,
        clock=clock,
    )


def backup_health(
    session_or_now: Session | Clock | datetime | None = None,
    clock: Clock | None = None,
    settings: Settings | None = None,
    *,
    status_path: Path | None = None,
    status_file: Path | None = None,
) -> BackupHealth:
    """Evaluate backup health and the >26h staleness / failure threshold (ADR-025 §4.3).

    Combines the durable host/container status file (``.backup-status.json``) and system-level
    ``audit_logs`` entries (``system.backup_succeeded`` / ``system.backup_failed``) so operator
    alerts in Session 13 can detect both explicit backup failures and silent cron/timer stops.
    """
    session: Session | None = None
    if isinstance(session_or_now, datetime):
        now = (
            session_or_now.astimezone(UTC)
            if session_or_now.tzinfo is not None
            else session_or_now.replace(tzinfo=UTC)
        )
    elif isinstance(session_or_now, Session):
        session = session_or_now
        now = clock.now().astimezone(UTC) if clock is not None else datetime.now(UTC)
    elif session_or_now is not None and hasattr(session_or_now, "now"):
        now = session_or_now.now().astimezone(UTC)
    elif clock is not None:
        now = clock.now().astimezone(UTC)
    else:
        now = datetime.now(UTC)

    path = resolve_backup_status_path(settings, status_path=status_path or status_file)

    file_attempt_at: datetime | None = None
    file_succeeded_at: datetime | None = None
    file_status: Literal["succeeded", "failed"] | None = None
    file_backup_id: str | None = None
    file_error_code: str | None = None
    file_archive_key: str | None = None
    file_size_bytes: int | None = None

    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                status_val = (
                    str(raw.get("last_backup_status") or raw.get("status") or "").strip().lower()
                )
                if status_val in ("succeeded", "failed"):
                    file_status = "succeeded" if status_val == "succeeded" else "failed"
                file_attempt_at = _parse_iso_datetime(
                    raw.get("last_attempt_at") or raw.get("last_backup_at")
                )
                file_succeeded_at = _parse_iso_datetime(
                    raw.get("last_succeeded_at")
                    or raw.get("last_success_at")
                    or (raw.get("last_backup_at") if file_status == "succeeded" else None)
                )
                if raw.get("last_backup_id") or raw.get("backup_id"):
                    file_backup_id = str(raw.get("last_backup_id") or raw.get("backup_id"))
                if raw.get("last_error_code") or raw.get("last_error"):
                    file_error_code = str(raw.get("last_error_code") or raw.get("last_error"))
                if raw.get("last_archive_key") or raw.get("archive_key"):
                    file_archive_key = str(raw.get("last_archive_key") or raw.get("archive_key"))
                size_raw = (
                    raw.get("last_archive_size_bytes")
                    if raw.get("last_archive_size_bytes") is not None
                    else raw.get("ciphertext_size_bytes")
                )
                if size_raw is not None:
                    file_size_bytes = int(size_raw)
        except (OSError, ValueError, TypeError):
            file_status = "failed"
            file_error_code = "BACKUP_STATUS_CORRUPT"

    db_attempt_at: datetime | None = None
    db_succeeded_at: datetime | None = None
    db_status: Literal["succeeded", "failed"] | None = None
    db_backup_id: str | None = None
    db_error_code: str | None = None
    db_archive_key: str | None = None
    db_size_bytes: int | None = None

    if session is not None:
        latest_audit = session.scalars(
            select(AuditLog)
            .where(
                AuditLog.workspace_id.is_(None),
                AuditLog.action.in_(BACKUP_AUDIT_ACTIONS),
            )
            .order_by(AuditLog.occurred_at.desc(), AuditLog.created_at.desc())
            .limit(1)
        ).first()
        if latest_audit is not None:
            db_attempt_at = latest_audit.occurred_at.astimezone(UTC)
            db_status = (
                "succeeded" if latest_audit.action == "system.backup_succeeded" else "failed"
            )
            meta = latest_audit.metadata_ or {}
            if meta.get("backup_id"):
                db_backup_id = str(meta["backup_id"])
            if meta.get("error_code") or meta.get("error"):
                db_error_code = str(meta.get("error_code") or meta.get("error"))
            if meta.get("archive_key"):
                db_archive_key = str(meta["archive_key"])
            if meta.get("size_bytes") is not None:
                db_size_bytes = int(meta["size_bytes"])

        latest_success = session.scalars(
            select(AuditLog)
            .where(
                AuditLog.workspace_id.is_(None),
                AuditLog.action == "system.backup_succeeded",
            )
            .order_by(AuditLog.occurred_at.desc(), AuditLog.created_at.desc())
            .limit(1)
        ).first()
        if latest_success is not None:
            db_succeeded_at = latest_success.occurred_at.astimezone(UTC)

    # Pick the newer attempt signal between status file and DB audit log.
    use_db = db_status is not None and (
        file_status is None
        or (
            db_attempt_at is not None
            and (file_attempt_at is None or db_attempt_at > file_attempt_at)
        )
    )
    if use_db and db_status is not None:
        last_status: Literal["succeeded", "failed", "missing"] = db_status
        last_backup_at = db_attempt_at
        last_backup_id = db_backup_id
        last_error_code = db_error_code
        last_archive_key = db_archive_key
        last_size_bytes = db_size_bytes
    elif file_status is not None:
        last_status = file_status
        last_backup_at = file_attempt_at
        last_backup_id = file_backup_id
        last_error_code = file_error_code
        last_archive_key = file_archive_key
        last_size_bytes = file_size_bytes
    else:
        return BackupHealth(
            last_backup_at=None,
            last_succeeded_at=None,
            last_backup_status="missing",
            last_backup_id=None,
            last_error_code=None,
            last_archive_key=None,
            last_size_bytes=None,
            age_seconds=None,
            stale_or_failed=True,
        )

    candidates = [ts for ts in (file_succeeded_at, db_succeeded_at) if ts is not None]
    last_succeeded_at = max(candidates) if candidates else None
    age_seconds = (
        max(0, int((now - last_succeeded_at).total_seconds()))
        if last_succeeded_at is not None
        else None
    )
    is_stale = last_succeeded_at is None or (now - last_succeeded_at) > BACKUP_STALE_THRESHOLD
    stale_or_failed = last_status != "succeeded" or is_stale

    return BackupHealth(
        last_backup_at=last_backup_at,
        last_succeeded_at=last_succeeded_at,
        last_backup_status=last_status,
        last_backup_id=last_backup_id,
        last_error_code=last_error_code,
        last_archive_key=last_archive_key,
        last_size_bytes=last_size_bytes,
        age_seconds=age_seconds,
        stale_or_failed=stale_or_failed,
    )


def build(
    session: Session, clock: Clock, settings: Settings, ctx: WorkspaceContext
) -> SystemHealthOut:
    now = clock.now()
    since = now - WINDOW
    return SystemHealthOut(
        generated_at=now,
        window_hours=int(WINDOW.total_seconds() // 3600),
        accounts=_accounts(session, ctx),
        operations=_operations(session, ctx, since),
        jobs=_jobs(session, ctx, now, since),
        webhooks=_webhooks(session, ctx, since),
        ai=_ai(session, ctx, settings, now, since),
    )
