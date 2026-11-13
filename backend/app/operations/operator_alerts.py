"""Operator alerting engine, deduplication and cooldowns (P8-07, ADR-025 §4.3).

Evaluates the 8 canonical operational conditions:
1. Dead jobs (jobs.status == 'dead', immediate per-job-type key, 1h cooldown, CRITICAL)
2. Backup failure / stale backup heartbeat (> 26h staleness, 6h cooldown, CRITICAL)
3. Webhook signature failure burst (>= 10 failures in 1h, 1h cooldown, WARNING)
4. Connected account stuck in needs_reauth > 24 hours (24h cooldown, WARNING)
5. Account-agent dead wake/recovery jobs or stuck sessions (> 30m, 1h cooldown, CRITICAL/WARNING)
6. Unresolved operations (status == 'outcome_unknown' > 30m, 2h cooldown, WARNING)
7. Capability loss (status connected/degraded with CAPABILITY_MISSING, 6h cooldown, WARNING)
8. AI budget exhaustion / circuit open (budget exhausted or circuit degraded, 6h cooldown, WARNING)

Maintains durable state in ``operator_alert_states``:
- Suppresses notification spam during cooldown periods.
- Re-alerts when an active condition persists past cooldown.
- Automatically transitions resolved alerts (firing -> resolved) and sends recovery notifications.
- Visible in CLI, worker jobs, database state, and audit logs even if email delivery fails.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.models import ACTIVE_RUN_STATES, AgentSession
from app.ai.models import AgentRun
from app.ai.runner import BUDGET_EXCEEDED
from app.audit import service as audit
from app.audit.models import AuditLog
from app.core.clock import Clock
from app.core.config import Settings
from app.core.db import clear_tenant_context, set_tenant_context
from app.core.email import send_operator_alert_email
from app.core.logging import get_logger
from app.identity.models import Workspace
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.operations.models import Operation, OperatorAlertState
from app.operations.system_health import backup_health

_log = get_logger("app.operations.operator_alerts")

# Canonical Cooldown Durations (ADR-025 §4.3)
COOLDOWN_DEAD_JOBS = timedelta(hours=1)
COOLDOWN_BACKUP = timedelta(hours=6)
COOLDOWN_SIGNATURE_BURST = timedelta(hours=1)
COOLDOWN_STUCK_REAUTH = timedelta(hours=24)
COOLDOWN_AGENT_HEALTH = timedelta(hours=1)
COOLDOWN_UNRESOLVED_OPERATIONS = timedelta(hours=2)
COOLDOWN_CAPABILITY_LOSS = timedelta(hours=6)
COOLDOWN_AI_BUDGET = timedelta(hours=6)

# Thresholds
SIGNATURE_BURST_THRESHOLD = 10
SIGNATURE_BURST_WINDOW = timedelta(hours=1)
STUCK_REAUTH_THRESHOLD = timedelta(hours=24)
STUCK_SESSION_THRESHOLD = timedelta(minutes=30)
UNRESOLVED_OPERATION_THRESHOLD = timedelta(minutes=30)
AGENT_CRITICAL_JOB_TYPES = ("agent_wake", "agent_continue", "agent_wake_due", "agent_recover")


@dataclass(frozen=True)
class AlertCandidate:
    """An alert condition currently detected in the system."""

    alert_key: str
    category: str
    severity: Literal["critical", "warning", "info"]
    summary: str
    details: dict[str, Any]
    cooldown: timedelta
    workspace_id: uuid.UUID | None = None


class OperatorAlertEvaluationReport(BaseModel):
    """Result of an operator alert evaluation cycle."""

    evaluated_at: datetime
    active_candidates_count: int
    new_alerts_fired: int
    refired_alerts: int
    resolved_alerts: int
    suppressed_in_cooldown: int
    delivery_failures: int
    firing_keys: list[str]
    resolved_keys: list[str]


def _sole_workspace(jobs: list[Job]) -> uuid.UUID | None:
    """The workspace of an aggregated dead-job alert: only when every job belongs to it.

    A per-job-type alert counts dead jobs across all workspaces. Attributing it to the
    workspace of one sample job would put a platform-wide condition (and other tenants' counts)
    into that tenant's Activity feed (INV-01), so a mixed or workspace-less set is system-level.
    """
    workspaces = {j.workspace_id for j in jobs}
    if len(workspaces) == 1:
        (only,) = workspaces
        return only
    return None


def _collect_dead_jobs(session: Session) -> list[AlertCandidate]:
    """1. Dead background jobs (immediate per-job-type key, 1h cooldown, CRITICAL)."""
    dead_jobs = session.scalars(
        select(Job).where(Job.status == "dead").order_by(Job.job_type, Job.run_at.desc())
    ).all()

    if not dead_jobs:
        return []

    # Group by job type
    by_type: dict[str, list[Job]] = {}
    for j in dead_jobs:
        by_type.setdefault(j.job_type, []).append(j)

    candidates: list[AlertCandidate] = []
    for j_type, jobs in by_type.items():
        sample = jobs[0]
        # Agent-specific dead jobs are handled under agent health
        if j_type in AGENT_CRITICAL_JOB_TYPES:
            continue

        candidates.append(
            AlertCandidate(
                alert_key=f"dead_job:{j_type}",
                category="jobs",
                severity="critical",
                summary=f"Dead background job detected: {j_type} ({len(jobs)} dead)",
                details={
                    "job_type": j_type,
                    "dead_count": len(jobs),
                    "sample_job_id": str(sample.id),
                    "workspace_id": str(sample.workspace_id) if sample.workspace_id else None,
                    "attempts": sample.attempts,
                    "last_error_code": sample.last_error_code,
                    "last_error": sample.last_error_detail,
                },
                cooldown=COOLDOWN_DEAD_JOBS,
                workspace_id=_sole_workspace(jobs),
            )
        )
    return candidates


def _collect_backup_failure(
    session: Session, clock: Clock, settings: Settings
) -> list[AlertCandidate]:
    """2. Backup failure / stale backup heartbeat (> 26h staleness, 6h cooldown, CRITICAL)."""
    health = backup_health(session, clock=clock, settings=settings)
    if not health.stale_or_failed:
        return []

    summary = (
        f"Database backup failed ({health.last_error_code or 'FAILURE'})"
        if health.last_backup_status == "failed"
        else "Database backup is stale or missing (> 26 hours since last verified backup)"
    )

    details = {
        "last_backup_status": health.last_backup_status,
        "age_seconds": health.age_seconds,
        "last_backup_id": health.last_backup_id,
        "last_error_code": health.last_error_code,
        "last_succeeded_at": (
            health.last_succeeded_at.isoformat() if health.last_succeeded_at else None
        ),
        "last_backup_at": (health.last_backup_at.isoformat() if health.last_backup_at else None),
    }

    return [
        AlertCandidate(
            alert_key="backup:stale_or_failed",
            category="backup",
            severity="critical",
            summary=summary,
            details=details,
            cooldown=COOLDOWN_BACKUP,
            workspace_id=None,
        )
    ]


def _collect_signature_failure_bursts(session: Session, now: datetime) -> list[AlertCandidate]:
    """3. Webhook signature failure burst (>= 10 in 1 hour, 1h cooldown, WARNING)."""
    since = now - SIGNATURE_BURST_WINDOW
    raw_count = session.scalar(
        select(func.count()).where(
            AuditLog.action == "webhook.signature_invalid",
            AuditLog.workspace_id.is_(None),
            AuditLog.occurred_at >= since,
        )
    )
    try:
        count = int(raw_count or 0)
    except (TypeError, ValueError):
        count = 0

    if count >= SIGNATURE_BURST_THRESHOLD:
        return [
            AlertCandidate(
                alert_key="webhook:signature_failure_burst",
                category="security",
                severity="warning",
                summary=(
                    f"Webhook signature failure burst detected "
                    f"({count} invalid signatures in 1 hour)"
                ),
                details={
                    "burst_count": count,
                    "window_minutes": int(SIGNATURE_BURST_WINDOW.total_seconds() / 60),
                    "threshold": SIGNATURE_BURST_THRESHOLD,
                },
                cooldown=COOLDOWN_SIGNATURE_BURST,
                workspace_id=None,
            )
        ]
    return []


def _collect_tenant_alerts(
    session: Session, workspace: Workspace, now: datetime
) -> list[AlertCandidate]:
    """Collect tenant-scoped alerts under active tenant RLS context."""
    candidates: list[AlertCandidate] = []
    ws_id = workspace.id

    # 4. Connected account stuck in needs_reauth > 24 hours (24h cooldown, WARNING)
    reauth_cutoff = now - STUCK_REAUTH_THRESHOLD
    stuck_accounts = session.scalars(
        select(SocialAccount).where(
            SocialAccount.workspace_id == ws_id,
            SocialAccount.status == "needs_reauth",
            SocialAccount.updated_at <= reauth_cutoff,
        )
    ).all()
    for acct in stuck_accounts:
        candidates.append(
            AlertCandidate(
                alert_key=f"account_needs_reauth:{acct.id}",
                category="accounts",
                severity="warning",
                summary=(
                    f"Connected Instagram account @{acct.username or str(acct.id)} "
                    f"stuck in needs_reauth > 24 hours"
                ),
                details={
                    "social_account_id": str(acct.id),
                    "username": acct.username,
                    "workspace_id": str(ws_id),
                    "last_error_code": acct.last_error_code,
                    "stuck_since": acct.updated_at.isoformat(),
                },
                cooldown=COOLDOWN_STUCK_REAUTH,
                workspace_id=ws_id,
            )
        )

    # 5. Agent health: dead wake/recovery jobs or stuck sessions (> 30m, 1h cooldown)
    stuck_session_cutoff = now - STUCK_SESSION_THRESHOLD
    stuck_sessions = session.scalars(
        select(AgentSession).where(
            AgentSession.workspace_id == ws_id,
            AgentSession.status.in_(ACTIVE_RUN_STATES),
            AgentSession.updated_at <= stuck_session_cutoff,
        )
    ).all()
    for s in stuck_sessions:
        candidates.append(
            AlertCandidate(
                alert_key=f"agent_health:stuck_session:{s.id}",
                category="agent",
                severity="warning",
                summary=f"Account agent session {s.id} stuck > 30 minutes in state '{s.status}'",
                details={
                    "session_id": str(s.id),
                    "thread_id": str(s.thread_id),
                    "workspace_id": str(ws_id),
                    "status": s.status,
                    "stuck_minutes": int((now - s.updated_at).total_seconds() / 60),
                },
                cooldown=COOLDOWN_AGENT_HEALTH,
                workspace_id=ws_id,
            )
        )

    # 6. Unresolved operations (status == 'outcome_unknown' > 30m, 2h cooldown, WARNING)
    unresolved_cutoff = now - UNRESOLVED_OPERATION_THRESHOLD
    unresolved_ops = session.scalars(
        select(Operation).where(
            Operation.workspace_id == ws_id,
            Operation.status == "outcome_unknown",
            Operation.created_at <= unresolved_cutoff,
        )
    ).all()
    for op in unresolved_ops:
        candidates.append(
            AlertCandidate(
                alert_key=f"unresolved_operation:{op.id}",
                category="operations",
                severity="warning",
                summary=(
                    f"Unresolved {op.operation_type} operation "
                    f"stuck in outcome_unknown > 30 minutes"
                ),
                details={
                    "operation_id": str(op.id),
                    "operation_type": op.operation_type,
                    "social_account_id": str(op.social_account_id),
                    "workspace_id": str(ws_id),
                    "idempotency_key": op.idempotency_key,
                    "age_minutes": int((now - op.created_at).total_seconds() / 60),
                },
                cooldown=COOLDOWN_UNRESOLVED_OPERATIONS,
                workspace_id=ws_id,
            )
        )

    # 7. Capability loss (status connected/degraded with CAPABILITY_MISSING, 6h cooldown, WARNING)
    cap_accounts = session.scalars(
        select(SocialAccount).where(
            SocialAccount.workspace_id == ws_id,
            SocialAccount.status.in_(("connected", "degraded")),
            SocialAccount.last_error_code == "CAPABILITY_MISSING",
        )
    ).all()
    for acct in cap_accounts:
        candidates.append(
            AlertCandidate(
                alert_key=f"capability_loss:{acct.id}",
                category="accounts",
                severity="warning",
                summary=(
                    f"Account @{acct.username or str(acct.id)} lost "
                    f"required capability (CAPABILITY_MISSING)"
                ),
                details={
                    "social_account_id": str(acct.id),
                    "username": acct.username,
                    "workspace_id": str(ws_id),
                    "last_error_code": acct.last_error_code,
                },
                cooldown=COOLDOWN_CAPABILITY_LOSS,
                workspace_id=ws_id,
            )
        )

    # 8. AI budget exhaustion / circuit open (6h cooldown, WARNING)
    budget_runs = session.scalars(
        select(AgentRun).where(
            AgentRun.workspace_id == ws_id,
            AgentRun.error_code == BUDGET_EXCEEDED,
            AgentRun.created_at >= now - timedelta(hours=24),
        )
    ).all()
    if budget_runs:
        candidates.append(
            AlertCandidate(
                alert_key=f"ai_budget_exhausted:workspace:{ws_id}",
                category="agent",
                severity="warning",
                summary=(
                    f"Workspace daily AI budget exhausted ({len(budget_runs)} runs exceeded limit)"
                ),
                details={"workspace_id": str(ws_id), "exceeded_runs_24h": len(budget_runs)},
                cooldown=COOLDOWN_AI_BUDGET,
                workspace_id=ws_id,
            )
        )

    degraded_accounts = session.scalars(
        select(SocialAccount).where(
            SocialAccount.workspace_id == ws_id,
            SocialAccount.status == "degraded",
            SocialAccount.degraded_until.is_not(None),
            SocialAccount.degraded_until > now,
        )
    ).all()
    for acct in degraded_accounts:
        candidates.append(
            AlertCandidate(
                alert_key=f"circuit_open:account:{acct.id}",
                category="accounts",
                severity="warning",
                summary=(
                    f"Circuit open for account @{acct.username or str(acct.id)}: "
                    f"degraded until "
                    f"{acct.degraded_until.isoformat() if acct.degraded_until else 'cooldown'}"
                ),
                details={
                    "social_account_id": str(acct.id),
                    "username": acct.username,
                    "workspace_id": str(ws_id),
                    "degraded_until": (
                        acct.degraded_until.isoformat() if acct.degraded_until else None
                    ),
                    "last_error_code": acct.last_error_code,
                },
                cooldown=COOLDOWN_AI_BUDGET,
                workspace_id=ws_id,
            )
        )

    return candidates


def collect_active_alert_candidates(
    session: Session, clock: Clock, settings: Settings
) -> list[AlertCandidate]:
    """Collect all currently detected alert candidates across system and workspaces."""
    now = clock.now().astimezone(UTC)
    candidates: list[AlertCandidate] = []

    # 1. System-wide collectors (Category B tables)
    clear_tenant_context(session)
    candidates.extend(_collect_dead_jobs(session))
    candidates.extend(_collect_backup_failure(session, clock, settings))
    candidates.extend(_collect_signature_failure_bursts(session, now))

    # Agent dead jobs (system-wide Job table)
    dead_agent_jobs = session.scalars(
        select(Job).where(Job.status == "dead", Job.job_type.in_(AGENT_CRITICAL_JOB_TYPES))
    ).all()
    by_agent_type: dict[str, list[Job]] = {}
    for j in dead_agent_jobs:
        by_agent_type.setdefault(j.job_type, []).append(j)
    for j_type, jobs in by_agent_type.items():
        sample = jobs[0]
        candidates.append(
            AlertCandidate(
                alert_key=f"agent_health:dead_job:{j_type}",
                category="agent",
                severity="critical",
                summary=f"Account agent execution/recovery job dead: {j_type} ({len(jobs)} dead)",
                details={
                    "job_type": j_type,
                    "count": len(jobs),
                    "sample_job_id": str(sample.id),
                    "last_error_code": sample.last_error_code,
                    "last_error": sample.last_error_detail,
                },
                cooldown=COOLDOWN_AGENT_HEALTH,
                workspace_id=_sole_workspace(jobs),
            )
        )

    # 2. Workspace-scoped collectors (Category C tables under RLS)
    workspaces = session.scalars(
        select(Workspace).where(Workspace.status.in_(("active", "deleting")))
    ).all()
    for ws in workspaces:
        set_tenant_context(session, ws.id)
        candidates.extend(_collect_tenant_alerts(session, ws, now))

    # Clear tenant context back to global
    clear_tenant_context(session)
    return candidates


def evaluate_operator_alerts(
    session: Session,
    clock: Clock,
    settings: Settings,
    *,
    auto_resolve: bool = True,
    operator_email: str | None = None,
) -> OperatorAlertEvaluationReport:
    """Evaluate alert conditions, update durable deduplication states, and send notifications.

    Durable deduplication contract (ADR-025 §4.3):
    - Suppresses repeat emails while ``now < cooldown_until``.
    - Increments ``notification_count`` and sends re-alert when persistent past cooldown.
    - Transitions active alerts to ``resolved`` and sends recovery notice when cleared.
    """
    now = clock.now().astimezone(UTC)
    recipient = (
        operator_email if operator_email is not None else settings.operator_alert_email.strip()
    )

    candidates = collect_active_alert_candidates(session, clock, settings)
    active_keys = {c.alert_key for c in candidates}

    new_fired = 0
    refired = 0
    resolved = 0
    suppressed = 0
    delivery_failures = 0
    firing_keys: list[str] = []
    resolved_keys: list[str] = []

    # 1. Process active candidates
    for cand in candidates:
        firing_keys.append(cand.alert_key)
        state = session.scalar(
            select(OperatorAlertState).where(OperatorAlertState.alert_key == cand.alert_key)
        )

        should_send = False
        is_refire = False

        if state is None:
            # Case A: Brand new alert
            state = OperatorAlertState(
                id=uuid.uuid4(),
                alert_key=cand.alert_key,
                category=cand.category,
                severity=cand.severity,
                status="firing",
                workspace_id=cand.workspace_id,
                summary=cand.summary,
                details=cand.details,
                first_triggered_at=now,
                last_notified_at=now,
                cooldown_until=now + cand.cooldown,
                notification_count=1,
            )
            session.add(state)
            should_send = True
            new_fired += 1
        elif state.status == "resolved":
            # Case B: Re-fired after being resolved
            state.status = "firing"
            state.resolved_at = None
            state.first_triggered_at = now
            state.last_notified_at = now
            state.cooldown_until = now + cand.cooldown
            state.notification_count = 1
            state.summary = cand.summary
            state.details = cand.details
            state.severity = cand.severity
            state.workspace_id = cand.workspace_id
            should_send = True
            new_fired += 1
        else:
            # Case C: Currently firing
            state.summary = cand.summary
            state.details = cand.details
            # An aggregate alert follows its condition (see _sole_workspace), so the recovery
            # notice is attributed where the latest notification was.
            state.workspace_id = cand.workspace_id
            if state.cooldown_until is None or now >= state.cooldown_until:
                # Cooldown expired: re-notify operator
                state.last_notified_at = now
                state.cooldown_until = now + cand.cooldown
                state.notification_count += 1
                should_send = True
                is_refire = True
                refired += 1
            else:
                # In cooldown: suppress email
                suppressed += 1

        if should_send:
            try:
                if recipient:
                    send_operator_alert_email(
                        settings,
                        to_email=recipient,
                        alert_key=cand.alert_key,
                        category=cand.category,
                        severity=cand.severity,
                        summary=cand.summary,
                        details=cand.details,
                        is_recovery=False,
                    )
                audit.record(
                    session,
                    None,
                    "security.operator_alert_fired",
                    "operator_alert",
                    state.id,
                    {
                        "alert_key": cand.alert_key,
                        "category": cand.category,
                        "severity": cand.severity,
                        "summary": cand.summary,
                        "is_refire": is_refire,
                        "notification_count": state.notification_count,
                    },
                    clock=clock,
                    workspace_id=cand.workspace_id,
                )
                _log.warning(
                    "operator_alert_notified",
                    alert_key=cand.alert_key,
                    severity=cand.severity,
                    refire=is_refire,
                )
            except Exception as exc:
                delivery_failures += 1
                _log.error(
                    "operator_alert_delivery_failed",
                    alert_key=cand.alert_key,
                    error=str(exc),
                )
                audit.record(
                    session,
                    None,
                    "security.alert_delivery_failed",
                    "operator_alert",
                    state.id,
                    {"alert_key": cand.alert_key, "error": str(exc)},
                    clock=clock,
                    workspace_id=cand.workspace_id,
                )

    # 2. Process resolved alerts (firing -> resolved)
    if auto_resolve:
        stmt = select(OperatorAlertState).where(OperatorAlertState.status == "firing")
        if active_keys:
            stmt = stmt.where(OperatorAlertState.alert_key.not_in(active_keys))
        currently_firing_states = session.scalars(stmt).all()

        for st in currently_firing_states:
            resolved_keys.append(st.alert_key)
            st.status = "resolved"
            st.resolved_at = now
            st.cooldown_until = None
            resolved += 1

            try:
                if recipient:
                    send_operator_alert_email(
                        settings,
                        to_email=recipient,
                        alert_key=st.alert_key,
                        category=st.category,
                        severity=st.severity,
                        summary=f"Resolved: {st.summary}",
                        details=st.details,
                        is_recovery=True,
                    )
                audit.record(
                    session,
                    None,
                    "security.operator_alert_resolved",
                    "operator_alert",
                    st.id,
                    {
                        "alert_key": st.alert_key,
                        "category": st.category,
                        "severity": st.severity,
                        "summary": st.summary,
                    },
                    clock=clock,
                    workspace_id=st.workspace_id,
                )
                _log.info("operator_alert_resolved", alert_key=st.alert_key)
            except Exception as exc:
                delivery_failures += 1
                _log.error(
                    "operator_recovery_delivery_failed",
                    alert_key=st.alert_key,
                    error=str(exc),
                )
                audit.record(
                    session,
                    None,
                    "security.alert_delivery_failed",
                    "operator_alert",
                    st.id,
                    {"alert_key": st.alert_key, "error": str(exc)},
                    clock=clock,
                    workspace_id=st.workspace_id,
                )

    session.flush()

    return OperatorAlertEvaluationReport(
        evaluated_at=now,
        active_candidates_count=len(candidates),
        new_alerts_fired=new_fired,
        refired_alerts=refired,
        resolved_alerts=resolved,
        suppressed_in_cooldown=suppressed,
        delivery_failures=delivery_failures,
        firing_keys=firing_keys,
        resolved_keys=resolved_keys,
    )
