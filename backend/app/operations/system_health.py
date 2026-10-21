"""System health for the owner and the manager (observability.md section 6, plan H13).

Everything is counted from tables, scoped to one workspace, except the signature-failure count:
those audit rows have no workspace (a forged request cannot be attributed), so the number is
system-wide and labelled as such. Only counts, codes, ids and times are returned: no payload,
no message text, no error detail.
"""

import json
import uuid
from datetime import datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.ai.models import AgentRun
from app.ai.runner import BUDGET_EXCEEDED, BUDGET_WINDOW
from app.audit.models import AuditLog
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.inbox.models import InboundEvent
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.operations.models import Operation

WINDOW = timedelta(hours=24)
LATEST_FAILURES = 5
FAILED_OPERATION_STATUSES = ("failed", "outcome_unknown")


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
