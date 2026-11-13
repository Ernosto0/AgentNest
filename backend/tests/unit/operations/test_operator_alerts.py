"""Session 13 unit tests for Operator Monitoring and Alerts (P8-07, ADR-025 §4.3).

Covers:
- 8 canonical alert conditions:
  1. Dead background jobs (CRITICAL, 1h cooldown)
  2. Stale or failed backups (CRITICAL, 6h cooldown)
  3. Webhook signature failure bursts (WARNING, 1h cooldown)
  4. Connected accounts stuck in needs_reauth > 24h (WARNING, 24h cooldown)
  5. Agent dead wake/recovery jobs and stuck sessions > 30m (CRITICAL/WARNING, 1h cooldown)
  6. Unresolved operations in outcome_unknown > 30m (WARNING, 2h cooldown)
  7. Capability loss on connected account (WARNING, 6h cooldown)
  8. AI budget exhaustion and open circuit breakers (WARNING, 6h cooldown)
- Durable state tracking in operator_alert_states (deduplication & cooldown suppression).
- Re-alerting past cooldown window with incremented notification_count.
- Auto-resolution (firing -> resolved) and recovery notices.
- Alert email formatting, redaction, and secret protection (INV-08, INV-18).
- Alert delivery failure resilience and security.alert_delivery_failed audit logging.
- Background worker job handler evaluate_operator_alerts_job.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.agent.models import AgentSession
from app.ai.models import AgentRun
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.email import email_outbox
from app.identity.models import Workspace
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.jobs.registry import JobContext
from app.operations.jobs import evaluate_operator_alerts_job
from app.operations.models import Operation, OperatorAlertState
from app.operations.operator_alerts import (
    COOLDOWN_DEAD_JOBS,
    evaluate_operator_alerts,
)
from app.operations.payloads import EvaluateOperatorAlertsPayload
from app.operations.system_health import BackupHealth


@pytest.fixture(autouse=True)
def clean_outbox() -> None:
    email_outbox.clear()


def _make_settings(operator_email: str = "operator@example.com") -> Settings:
    return Settings(
        operator_alert_email=operator_email,
        product_name="AgentNest",
    )


def test_dead_jobs_trigger_critical_alert_and_email() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    clock = FrozenClock(now)
    settings = _make_settings()

    job_id = uuid.uuid4()
    dead_job = Job(
        id=job_id,
        job_type="send_reply",
        status="dead",
        payload={"reply_draft_id": str(uuid.uuid4())},
        attempts=6,
        max_attempts=6,
        last_error_code="PROVIDER_UNAVAILABLE",
        last_error_detail="Instagram API connection timeout after 5 retries",
        run_at=now - timedelta(minutes=10),
    )

    mock_session = MagicMock()
    # No existing alert state in DB
    mock_session.scalar.return_value = None
    # Dead jobs query
    mock_session.scalars.return_value.all.side_effect = [
        [dead_job],  # Job.status == 'dead'
        [],  # dead agent jobs
        [],  # active workspaces
        [],  # resolved states
    ]

    with (
        patch("app.operations.operator_alerts.backup_health") as mock_backup,
        patch("app.operations.operator_alerts.audit.record") as mock_audit,
    ):
        mock_backup.return_value = BackupHealth(
            last_backup_at=now - timedelta(hours=2),
            last_succeeded_at=now - timedelta(hours=2),
            last_backup_status="succeeded",
            stale_or_failed=False,
        )

        report = evaluate_operator_alerts(mock_session, clock, settings)

    assert report.active_candidates_count == 1
    assert report.new_alerts_fired == 1
    assert report.refired_alerts == 0
    assert report.resolved_alerts == 0
    assert report.suppressed_in_cooldown == 0
    assert report.delivery_failures == 0
    assert "dead_job:send_reply" in report.firing_keys

    # Email delivered to outbox
    messages = email_outbox.get_messages()
    assert len(messages) == 1
    msg = messages[0]
    assert msg.to_email == "operator@example.com"
    assert "[CRITICAL]" in msg.subject
    assert "Dead background job detected: send_reply" in msg.subject
    assert "PROVIDER_UNAVAILABLE" in msg.text_body

    # Audit event recorded
    mock_audit.assert_called_once()
    audit_args, audit_kwargs = mock_audit.call_args
    assert audit_args[2] == "security.operator_alert_fired"
    assert audit_args[3] == "operator_alert"
    assert audit_args[5]["alert_key"] == "dead_job:send_reply"
    assert audit_args[5]["severity"] == "critical"
    assert audit_args[5]["is_refire"] is False


def test_cooldown_suppresses_repeat_emails() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    clock = FrozenClock(now)
    settings = _make_settings()

    dead_job = Job(
        id=uuid.uuid4(),
        job_type="send_reply",
        status="dead",
        payload={},
        attempts=6,
        max_attempts=6,
        last_error_code="PROVIDER_UNAVAILABLE",
        run_at=now,
    )

    # Existing firing alert in cooldown
    existing_state = OperatorAlertState(
        id=uuid.uuid4(),
        alert_key="dead_job:send_reply",
        category="jobs",
        severity="critical",
        status="firing",
        first_triggered_at=now - timedelta(minutes=20),
        last_notified_at=now - timedelta(minutes=20),
        cooldown_until=now + timedelta(minutes=40),  # In cooldown for 40 more minutes
        notification_count=1,
        summary="Dead job send_reply",
        details={},
    )

    mock_session = MagicMock()
    mock_session.scalar.side_effect = [0, existing_state]
    mock_session.scalars.return_value.all.side_effect = [
        [dead_job],
        [],
        [],
        [],
    ]

    with (
        patch("app.operations.operator_alerts.backup_health") as mock_backup,
        patch("app.operations.operator_alerts.audit.record") as mock_audit,
    ):
        mock_backup.return_value = BackupHealth(
            last_backup_at=now,
            last_succeeded_at=now,
            last_backup_status="succeeded",
            stale_or_failed=False,
        )

        report = evaluate_operator_alerts(mock_session, clock, settings)

    assert report.active_candidates_count == 1
    assert report.new_alerts_fired == 0
    assert report.suppressed_in_cooldown == 1
    assert len(email_outbox.get_messages()) == 0
    mock_audit.assert_not_called()


def test_cooldown_expiration_triggers_refire_email() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    clock = FrozenClock(now)
    settings = _make_settings()

    dead_job = Job(
        id=uuid.uuid4(),
        job_type="send_reply",
        status="dead",
        payload={},
        attempts=6,
        max_attempts=6,
        last_error_code="PROVIDER_UNAVAILABLE",
        run_at=now,
    )

    # Existing firing alert whose cooldown has EXPIRED
    existing_state = OperatorAlertState(
        id=uuid.uuid4(),
        alert_key="dead_job:send_reply",
        category="jobs",
        severity="critical",
        status="firing",
        first_triggered_at=now - timedelta(hours=2),
        last_notified_at=now - timedelta(hours=2),
        cooldown_until=now - timedelta(minutes=1),  # Cooldown passed!
        notification_count=1,
        summary="Dead job send_reply",
        details={},
    )

    mock_session = MagicMock()
    mock_session.scalar.side_effect = [0, existing_state]
    mock_session.scalars.return_value.all.side_effect = [
        [dead_job],
        [],
        [],
        [],
    ]

    with (
        patch("app.operations.operator_alerts.backup_health") as mock_backup,
        patch("app.operations.operator_alerts.audit.record") as mock_audit,
    ):
        mock_backup.return_value = BackupHealth(
            last_backup_at=now,
            last_succeeded_at=now,
            last_backup_status="succeeded",
            stale_or_failed=False,
        )

        report = evaluate_operator_alerts(mock_session, clock, settings)

    assert report.active_candidates_count == 1
    assert report.refired_alerts == 1
    assert report.suppressed_in_cooldown == 0
    assert existing_state.notification_count == 2
    assert existing_state.last_notified_at == now
    assert existing_state.cooldown_until == now + COOLDOWN_DEAD_JOBS

    # Verify email was sent
    assert len(email_outbox.get_messages()) == 1

    # Verify audit event emitted with is_refire=True
    mock_audit.assert_called_once()
    audit_args = mock_audit.call_args[0]
    assert audit_args[5]["is_refire"] is True
    assert audit_args[5]["notification_count"] == 2


def test_resolved_alert_transitions_and_sends_recovery_notice() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    clock = FrozenClock(now)
    settings = _make_settings()

    # Prior firing alert in DB
    existing_state = OperatorAlertState(
        id=uuid.uuid4(),
        alert_key="dead_job:send_reply",
        category="jobs",
        severity="critical",
        status="firing",
        first_triggered_at=now - timedelta(hours=1),
        last_notified_at=now - timedelta(hours=1),
        cooldown_until=now + timedelta(minutes=30),
        notification_count=1,
        summary="Dead background job detected: send_reply",
        details={"job_type": "send_reply"},
    )

    mock_session = MagicMock()
    mock_session.scalar.return_value = 0
    # All condition collectors return empty (problem resolved!)
    mock_session.scalars.return_value.all.side_effect = [
        [],  # dead jobs: empty!
        [],  # dead agent jobs: empty!
        [],  # active workspaces: empty!
        [existing_state],  # Currently firing states to resolve
    ]

    with (
        patch("app.operations.operator_alerts.backup_health") as mock_backup,
        patch("app.operations.operator_alerts.audit.record") as mock_audit,
    ):
        mock_backup.return_value = BackupHealth(
            last_backup_at=now,
            last_succeeded_at=now,
            last_backup_status="succeeded",
            stale_or_failed=False,
        )

        report = evaluate_operator_alerts(mock_session, clock, settings)

    assert report.active_candidates_count == 0
    assert report.resolved_alerts == 1
    assert "dead_job:send_reply" in report.resolved_keys

    # State updated to resolved
    assert existing_state.status == "resolved"
    assert existing_state.resolved_at == now
    assert existing_state.cooldown_until is None

    # Recovery email was sent
    messages = email_outbox.get_messages()
    assert len(messages) == 1
    assert "[RESOLVED]" in messages[0].subject
    assert "Resolved: Dead background job detected: send_reply" in messages[0].subject

    # Audit event recorded
    mock_audit.assert_called_once()
    audit_args = mock_audit.call_args[0]
    assert audit_args[2] == "security.operator_alert_resolved"


def test_backup_failure_alert_detected() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    clock = FrozenClock(now)
    settings = _make_settings()

    mock_session = MagicMock()
    mock_session.scalar.return_value = None
    mock_session.scalars.return_value.all.side_effect = [
        [],  # dead jobs
        [],  # dead agent jobs
        [],  # active workspaces
        [],  # resolved states
    ]

    with (
        patch("app.operations.operator_alerts.backup_health") as mock_backup,
        patch("app.operations.operator_alerts.audit.record"),
    ):
        mock_backup.return_value = BackupHealth(
            last_backup_at=now - timedelta(hours=30),
            last_succeeded_at=now - timedelta(hours=30),
            last_backup_status="failed",
            last_error_code="BACKUP_ENCRYPTION_FAILED",
            stale_or_failed=True,
        )

        report = evaluate_operator_alerts(mock_session, clock, settings)

    assert "backup:stale_or_failed" in report.firing_keys
    msg = email_outbox.get_messages()[0]
    assert "Database backup failed (BACKUP_ENCRYPTION_FAILED)" in msg.subject
    assert "[CRITICAL]" in msg.subject


def test_webhook_signature_burst_alert_detected() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    clock = FrozenClock(now)
    settings = _make_settings()

    mock_session = MagicMock()
    mock_session.scalar.side_effect = [
        15,  # Signature invalid count >= 10
        None,  # State lookup for operator_alert_states
    ]
    mock_session.scalars.return_value.all.side_effect = [
        [],  # dead jobs
        [],  # dead agent jobs
        [],  # active workspaces
        [],  # resolved states
    ]

    with (
        patch("app.operations.operator_alerts.backup_health") as mock_backup,
        patch("app.operations.operator_alerts.audit.record"),
    ):
        mock_backup.return_value = BackupHealth(
            last_backup_at=now,
            last_succeeded_at=now,
            last_backup_status="succeeded",
            stale_or_failed=False,
        )

        report = evaluate_operator_alerts(mock_session, clock, settings)

    assert "webhook:signature_failure_burst" in report.firing_keys
    msg = email_outbox.get_messages()[0]
    assert "[WARNING]" in msg.subject
    assert "Webhook signature failure burst detected" in msg.subject


def test_account_stuck_in_needs_reauth_alert() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    clock = FrozenClock(now)
    settings = _make_settings()

    ws_id = uuid.uuid4()
    acct_id = uuid.uuid4()
    ws = Workspace(id=ws_id, name="Test WS", slug="test-ws", status="active")
    account = SocialAccount(
        id=acct_id,
        workspace_id=ws_id,
        platform="instagram",
        provider_kind="meta",
        external_account_id="ig_123",
        username="acme_coffee",
        status="needs_reauth",
        last_error_code="TOKEN_REVOKED",
        updated_at=now - timedelta(hours=26),  # Stuck for 26 hours (> 24h)
    )

    mock_session = MagicMock()
    mock_session.scalar.return_value = None
    mock_session.scalars.return_value.all.side_effect = [
        [],  # dead jobs
        [],  # dead agent jobs
        [ws],  # active workspaces
        [account],  # stuck accounts query
        [],  # stuck sessions
        [],  # unresolved ops
        [],  # capability missing
        [],  # budget runs
        [],  # degraded accounts
        [],  # resolved states
    ]

    with (
        patch("app.operations.operator_alerts.backup_health") as mock_backup,
        patch("app.operations.operator_alerts.audit.record"),
    ):
        mock_backup.return_value = BackupHealth(
            last_backup_at=now,
            last_succeeded_at=now,
            last_backup_status="succeeded",
            stale_or_failed=False,
        )

        report = evaluate_operator_alerts(mock_session, clock, settings)

    assert f"account_needs_reauth:{acct_id}" in report.firing_keys
    msg = email_outbox.get_messages()[0]
    assert "[WARNING]" in msg.subject
    assert "@acme_coffee stuck in needs_reauth > 24 hours" in msg.subject


def test_agent_stuck_session_alert() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    clock = FrozenClock(now)
    settings = _make_settings()

    ws_id = uuid.uuid4()
    session_id = uuid.uuid4()
    ws = Workspace(id=ws_id, name="Test WS", slug="test-ws", status="active")
    agent_session = AgentSession(
        id=session_id,
        workspace_id=ws_id,
        thread_id=uuid.uuid4(),
        goal_key="inbox_triage",
        initiating_event_cursor=1,
        status="in_progress",
        updated_at=now - timedelta(minutes=45),  # Stuck 45m (> 30m)
    )

    mock_session = MagicMock()
    mock_session.scalar.return_value = None
    mock_session.scalars.return_value.all.side_effect = [
        [],  # dead jobs
        [],  # dead agent jobs
        [ws],  # active workspaces
        [],  # stuck accounts
        [agent_session],  # stuck sessions query
        [],  # unresolved ops
        [],  # capability missing
        [],  # budget runs
        [],  # degraded accounts
        [],  # resolved states
    ]

    with (
        patch("app.operations.operator_alerts.backup_health") as mock_backup,
        patch("app.operations.operator_alerts.audit.record"),
    ):
        mock_backup.return_value = BackupHealth(
            last_backup_at=now,
            last_succeeded_at=now,
            last_backup_status="succeeded",
            stale_or_failed=False,
        )

        report = evaluate_operator_alerts(mock_session, clock, settings)

    assert f"agent_health:stuck_session:{session_id}" in report.firing_keys
    msg = email_outbox.get_messages()[0]
    assert "stuck > 30 minutes in state 'in_progress'" in msg.subject


def test_unresolved_operation_alert() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    clock = FrozenClock(now)
    settings = _make_settings()

    ws_id = uuid.uuid4()
    op_id = uuid.uuid4()
    ws = Workspace(id=ws_id, name="Test WS", slug="test-ws", status="active")
    op = Operation(
        id=op_id,
        workspace_id=ws_id,
        social_account_id=uuid.uuid4(),
        subject_type="reply_draft",
        subject_id=uuid.uuid4(),
        operation_type="send_reply",
        provider_kind="meta",
        idempotency_key="send_reply:op1",
        status="outcome_unknown",
        created_at=now - timedelta(minutes=40),  # > 30m
    )

    mock_session = MagicMock()
    mock_session.scalar.return_value = None
    mock_session.scalars.return_value.all.side_effect = [
        [],  # dead jobs
        [],  # dead agent jobs
        [ws],  # active workspaces
        [],  # stuck accounts
        [],  # stuck sessions
        [op],  # unresolved ops query
        [],  # capability missing
        [],  # budget runs
        [],  # degraded accounts
        [],  # resolved states
    ]

    with (
        patch("app.operations.operator_alerts.backup_health") as mock_backup,
        patch("app.operations.operator_alerts.audit.record"),
    ):
        mock_backup.return_value = BackupHealth(
            last_backup_at=now,
            last_succeeded_at=now,
            last_backup_status="succeeded",
            stale_or_failed=False,
        )

        report = evaluate_operator_alerts(mock_session, clock, settings)

    assert f"unresolved_operation:{op_id}" in report.firing_keys
    msg = email_outbox.get_messages()[0]
    assert "Unresolved send_reply operation stuck in outcome_unknown > 30 minutes" in msg.subject


def test_capability_loss_alert() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    clock = FrozenClock(now)
    settings = _make_settings()

    ws_id = uuid.uuid4()
    acct_id = uuid.uuid4()
    ws = Workspace(id=ws_id, name="Test WS", slug="test-ws", status="active")
    account = SocialAccount(
        id=acct_id,
        workspace_id=ws_id,
        platform="instagram",
        provider_kind="meta",
        external_account_id="ig_123",
        username="boutique_shop",
        status="connected",
        last_error_code="CAPABILITY_MISSING",
    )

    mock_session = MagicMock()
    mock_session.scalar.return_value = None
    mock_session.scalars.return_value.all.side_effect = [
        [],  # dead jobs
        [],  # dead agent jobs
        [ws],  # active workspaces
        [],  # stuck accounts
        [],  # stuck sessions
        [],  # unresolved ops
        [account],  # capability loss query
        [],  # budget runs
        [],  # degraded accounts
        [],  # resolved states
    ]

    with (
        patch("app.operations.operator_alerts.backup_health") as mock_backup,
        patch("app.operations.operator_alerts.audit.record"),
    ):
        mock_backup.return_value = BackupHealth(
            last_backup_at=now,
            last_succeeded_at=now,
            last_backup_status="succeeded",
            stale_or_failed=False,
        )

        report = evaluate_operator_alerts(mock_session, clock, settings)

    assert f"capability_loss:{acct_id}" in report.firing_keys
    msg = email_outbox.get_messages()[0]
    assert "@boutique_shop lost required capability (CAPABILITY_MISSING)" in msg.subject


def test_ai_budget_exhaustion_alert() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    clock = FrozenClock(now)
    settings = _make_settings()

    ws_id = uuid.uuid4()
    ws = Workspace(id=ws_id, name="Test WS", slug="test-ws", status="active")
    run = AgentRun(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        task="draft_reply",
        status="failed",
        error_code="LLM_BUDGET_EXCEEDED",
        created_at=now - timedelta(hours=1),
    )

    mock_session = MagicMock()
    mock_session.scalar.return_value = None
    mock_session.scalars.return_value.all.side_effect = [
        [],  # dead jobs
        [],  # dead agent jobs
        [ws],  # active workspaces
        [],  # stuck accounts
        [],  # stuck sessions
        [],  # unresolved ops
        [],  # capability missing
        [run],  # budget runs query
        [],  # degraded accounts
        [],  # resolved states
    ]

    with (
        patch("app.operations.operator_alerts.backup_health") as mock_backup,
        patch("app.operations.operator_alerts.audit.record"),
    ):
        mock_backup.return_value = BackupHealth(
            last_backup_at=now,
            last_succeeded_at=now,
            last_backup_status="succeeded",
            stale_or_failed=False,
        )

        report = evaluate_operator_alerts(mock_session, clock, settings)

    assert f"ai_budget_exhausted:workspace:{ws_id}" in report.firing_keys
    msg = email_outbox.get_messages()[0]
    assert "Workspace daily AI budget exhausted" in msg.subject


def test_alert_delivery_failure_visibility() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    clock = FrozenClock(now)
    settings = _make_settings()

    dead_job = Job(
        id=uuid.uuid4(),
        job_type="send_reply",
        status="dead",
        payload={},
        attempts=6,
        max_attempts=6,
        run_at=now,
    )

    mock_session = MagicMock()
    mock_session.scalar.return_value = None
    mock_session.scalars.return_value.all.side_effect = [
        [dead_job],
        [],
        [],
        [],
    ]

    with (
        patch("app.operations.operator_alerts.backup_health") as mock_backup,
        patch("app.operations.operator_alerts.send_operator_alert_email") as mock_send,
        patch("app.operations.operator_alerts.audit.record") as mock_audit,
    ):
        mock_backup.return_value = BackupHealth(
            last_backup_at=now,
            last_succeeded_at=now,
            last_backup_status="succeeded",
            stale_or_failed=False,
        )
        mock_send.side_effect = OSError("SMTP server connection refused")

        report = evaluate_operator_alerts(mock_session, clock, settings)

    # State still persisted in DB despite email failure
    assert report.active_candidates_count == 1
    assert report.new_alerts_fired == 1
    assert report.delivery_failures == 1
    mock_session.add.assert_called_once()

    # Delivery failure recorded in audit log
    mock_audit.assert_called_once()
    audit_args = mock_audit.call_args[0]
    assert audit_args[2] == "security.alert_delivery_failed"
    assert "SMTP server connection refused" in audit_args[5]["error"]


def test_job_handler_evaluate_operator_alerts() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    clock = FrozenClock(now)

    mock_session = MagicMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__enter__.return_value = mock_session

    job_ctx = JobContext(
        job_id=uuid.uuid4(),
        job_type="evaluate_operator_alerts",
        workspace_id=None,
        correlation_id=None,
        payload=EvaluateOperatorAlertsPayload(auto_resolve=True),
        attempt=1,
        max_attempts=1,
        session_factory=mock_factory,
        clock=clock,
        _heartbeat=lambda: None,
    )

    with patch("app.operations.operator_alerts.evaluate_operator_alerts") as mock_eval:
        evaluate_operator_alerts_job(job_ctx)

    mock_eval.assert_called_once()
    mock_session.commit.assert_called_once()


def test_evaluate_alerts_cli_main_clean(capsys: pytest.CaptureFixture[str]) -> None:
    import sys
    from pathlib import Path

    root_dir = str(Path(__file__).resolve().parents[4])
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)

    from scripts.evaluate_alerts import main as cli_main

    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    mock_session = MagicMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__enter__.return_value = mock_session
    mock_session.scalars.return_value.all.return_value = []

    mock_report = MagicMock(
        evaluated_at=now,
        active_candidates_count=0,
        new_alerts_fired=0,
        refired_alerts=0,
        resolved_alerts=0,
        suppressed_in_cooldown=0,
        delivery_failures=0,
        resolved_keys=[],
    )

    with (
        patch("sys.argv", ["evaluate_alerts.py", "--json"]),
        patch("scripts.evaluate_alerts.get_session_factory", return_value=mock_factory),
        patch("scripts.evaluate_alerts.evaluate_operator_alerts", return_value=mock_report),
    ):
        exit_code = cli_main()

    assert exit_code == 0
    captured = capsys.readouterr()
    assert '"active_candidates_count": 0' in captured.out


def _dead(job_type: str, workspace_id: uuid.UUID | None, now: datetime) -> Job:
    return Job(
        id=uuid.uuid4(),
        job_type=job_type,
        status="dead",
        payload={},
        attempts=6,
        max_attempts=6,
        last_error_code="PROVIDER_UNAVAILABLE",
        run_at=now,
        workspace_id=workspace_id,
    )


def test_an_aggregated_dead_job_alert_belongs_to_a_workspace_only_when_all_its_jobs_do() -> None:
    """A per-type alert counts dead jobs of every tenant; stamping it with one sample job's
    workspace put a platform-wide condition into that tenant's Activity feed (INV-01)."""
    from app.operations.operator_alerts import _collect_dead_jobs

    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    ws_a, ws_b = uuid.uuid4(), uuid.uuid4()
    session = MagicMock()
    session.scalars.return_value.all.return_value = [
        _dead("send_reply", ws_a, now),
        _dead("send_reply", ws_b, now),
        _dead("publish_content", ws_a, now),
        _dead("publish_content", ws_a, now),
        _dead("retention_cleanup", None, now),
    ]
    by_key = {c.alert_key: c for c in _collect_dead_jobs(session)}
    assert by_key["dead_job:send_reply"].workspace_id is None  # two tenants: system-level
    assert by_key["dead_job:publish_content"].workspace_id == ws_a  # one tenant: theirs
    assert by_key["dead_job:retention_cleanup"].workspace_id is None
