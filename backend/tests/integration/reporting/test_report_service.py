"""The report service (workflows.md section F, plan H3): live today, stored past days,
regeneration, the audit entry, the notification and INV-08."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.ai import runtime
from app.audit.models import AuditLog
from app.core.errors import AppError
from app.notifications.models import Notification
from app.reporting import service
from app.reporting.models import DailyReport
from tests.helpers.reporting import DAY, EXPECTED, TIMEZONE, at
from tests.integration.reporting.conftest import ReportEnv


def _rows(env: ReportEnv) -> int:
    return env.env.session.scalar(select(func.count()).select_from(DailyReport)) or 0


def _audits(env: ReportEnv) -> int:
    return (
        env.env.session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "report.generated")
        )
        or 0
    )


def _notifications(env: ReportEnv) -> list[Notification]:
    return list(
        env.env.session.scalars(
            select(Notification).where(Notification.type == "report.daily_ready")
        )
    )


def _inbound(env: ReportEnv, hour: int = 9, minute: int = 59) -> None:
    builder = env.builder()
    conversation = builder.conversation(at(DAY, 9, 0))
    builder.message(conversation, "inbound", at(DAY, hour, minute))
    env.env.session.commit()


def test_a_past_day_is_computed_and_stored_once_then_re_read(report_env: ReportEnv) -> None:
    env = report_env
    ctx = env.scenario.ctx
    assert _rows(env) == 0

    first = service.get_report(env.env.session, env.clock, ctx, DAY)
    env.env.session.commit()
    assert first.stored and not first.is_partial
    for key, expected in EXPECTED.items():
        assert first.value(key) == expected, key
    assert _rows(env) == 1 and _audits(env) == 1

    _inbound(env)  # a record the stored report does not know about
    again = service.get_report(env.env.session, env.clock, ctx, DAY)
    assert again.value("inbound_messages") == EXPECTED["inbound_messages"]  # re-read, not redone
    assert again.generated_at == first.generated_at
    assert _rows(env) == 1 and _audits(env) == 1


def test_generate_preserves_the_previous_generation(report_env: ReportEnv) -> None:
    env = report_env
    ctx = env.scenario.ctx
    first = service.generate_daily_report(env.env.session, env.clock, ctx, DAY, scheduled=False)
    _inbound(env)
    env.clock.advance(minutes=5)

    regenerated = service.generate_daily_report(
        env.env.session, env.clock, ctx, DAY, scheduled=False
    )
    env.env.session.commit()

    assert regenerated.value("inbound_messages") == EXPECTED["inbound_messages"] + 1
    assert regenerated.generated_at == env.clock.now()
    assert _rows(env) == 2
    assert regenerated.snapshot_id != first.snapshot_id
    original = env.env.session.get(DailyReport, first.snapshot_id)
    assert original is not None and original.metrics == first.metrics
    stored = service.stored_report(env.env.session, ctx, DAY)
    assert stored is not None and stored.revision == 2
    assert stored.metrics["inbound_messages"]["value"] == EXPECTED["inbound_messages"] + 1
    assert _audits(env) == 2
    # The stored copy is what a later read returns.
    reread = service.get_report(env.env.session, env.clock, ctx, DAY)
    assert reread.value("inbound_messages") == EXPECTED["inbound_messages"] + 1


def test_today_is_live_and_never_stored_by_a_read(report_env: ReportEnv) -> None:
    env = report_env
    ctx = env.scenario.ctx
    today = DAY + timedelta(days=1)
    env.clock.advance(hours=10)  # 10:00 local on the next day

    first = service.get_report(env.env.session, env.clock, ctx, today)
    assert first.value("inbound_messages") == 0 and first.is_partial and not first.stored
    assert first.period_end == env.clock.now()

    builder = env.builder()
    conversation = builder.conversation(at(today, 9, 0))
    builder.message(conversation, "inbound", at(today, 9, 30))
    env.env.session.commit()
    second = service.get_report(env.env.session, env.clock, ctx, today)
    assert second.value("inbound_messages") == 1  # live: sees the new record
    assert _rows(env) == 0 and _audits(env) == 0  # nothing was stored


def test_a_stored_partial_report_of_today_is_marked_partial(report_env: ReportEnv) -> None:
    env = report_env
    env.clock.advance(hours=20)  # 20:00 local on the next day
    today = DAY + timedelta(days=1)
    report = service.generate_daily_report(
        env.env.session, env.clock, env.scenario.ctx, today, scheduled=False
    )
    assert report.is_partial and report.period_end == env.clock.now()
    row = env.env.session.scalars(select(DailyReport)).one()
    assert row.period_end == env.clock.now()
    env.clock.advance(days=1)  # it is a past day now, and the stored row says it was partial
    reread = service.get_report(env.env.session, env.clock, env.scenario.ctx, today)
    assert reread.is_partial and reread.stored


def test_a_future_day_is_refused(report_env: ReportEnv) -> None:
    env = report_env
    tomorrow = DAY + timedelta(days=2)  # the clock stands at the start of DAY + 1
    for call in (
        lambda: service.get_report(env.env.session, env.clock, env.scenario.ctx, tomorrow),
        lambda: service.generate_daily_report(
            env.env.session, env.clock, env.scenario.ctx, tomorrow, scheduled=False
        ),
    ):
        with pytest.raises(AppError) as raised:
            call()
        assert raised.value.code == "VALIDATION_FAILED"
    assert _rows(env) == 0


def test_the_audit_entry_has_no_text_and_follows_the_report(report_env: ReportEnv) -> None:
    env = report_env
    service.generate_daily_report(
        env.env.session, env.clock, env.scenario.ctx, DAY, scheduled=False
    )
    entry = env.env.session.scalars(
        select(AuditLog).where(AuditLog.action == "report.generated")
    ).one()
    assert entry.workspace_id == env.env.workspace.id
    assert entry.resource_type == "daily_report"
    assert entry.metadata_ == {
        "local_date": DAY.isoformat(),
        "scheduled": False,
        "definitions_version": "1",
        "is_partial": False,
    }
    assert entry.is_simulated is True  # the scripted day is simulated (INV-09)
    report = env.env.session.scalars(select(DailyReport)).one()
    assert entry.resource_id == report.id


def test_only_a_scheduled_run_announces_the_report_and_it_does_so_once(
    report_env: ReportEnv,
) -> None:
    env = report_env
    ctx = env.scenario.ctx
    service.generate_daily_report(env.env.session, env.clock, ctx, DAY, scheduled=False)
    assert _notifications(env) == []  # an on-demand run is silent

    service.generate_daily_report(env.env.session, env.clock, ctx, DAY, scheduled=True)
    recipients = {n.recipient_user_id for n in _notifications(env)}
    # reports.view: the owner and the manager, not staff.
    assert recipients == {env.env.owner.user.id, env.env.manager.user.id}
    sample = _notifications(env)[0]
    assert sample.severity == "info" and sample.is_simulated is True
    assert sample.params == {"local_date": DAY.isoformat()}
    assert sample.dedup_key == f"report:{DAY.isoformat()}"
    assert sample.subject_type == "daily_report"

    service.generate_daily_report(env.env.session, env.clock, ctx, DAY, scheduled=True)
    assert len(_notifications(env)) == 2  # an unread duplicate is not created (dedup)

    for notification in _notifications(env):
        notification.read_at = env.clock.now()
    env.env.session.commit()
    service.generate_daily_report(env.env.session, env.clock, ctx, DAY, scheduled=True)
    assert len(_notifications(env)) == 4  # once read, the next run may announce again


def test_inv_08_the_report_path_makes_no_model_call(report_env: ReportEnv) -> None:
    env = report_env
    provider = runtime.get_provider()
    calls_before = len(provider.calls)  # type: ignore[attr-defined]
    ctx = env.scenario.ctx

    service.get_report(env.env.session, env.clock, ctx, DAY)
    service.generate_daily_report(env.env.session, env.clock, ctx, DAY, scheduled=True)
    for role in (env.env.owner, env.env.manager, env.env.staff):
        env.env.call(role, "GET", "/reports/daily", params={"date": DAY.isoformat()})
        env.env.call(role, "GET", f"/reports/daily/{DAY.isoformat()}/metrics/inbound_messages")
    env.env.call(env.env.owner, "POST", "/reports/daily/generate", json={"date": DAY.isoformat()})
    assert len(provider.calls) == calls_before  # type: ignore[attr-defined]


def test_the_day_is_the_workspace_local_day(report_env: ReportEnv) -> None:
    env = report_env
    report = service.generate_daily_report(
        env.env.session, env.clock, env.scenario.ctx, DAY, scheduled=False
    )
    assert report.timezone == TIMEZONE
    assert (report.period_start, report.period_end) == (env.scenario.start, env.scenario.end)
