"""AC-E3 across state changes, regeneration, source retention and tenant boundaries."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from statistics import median
from threading import Barrier

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.approvals.models import Approval
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.errors import AppError
from app.inbox.models import Conversation, InboundEvent, Message, ReplyDraft
from app.reporting import drilldown, service
from app.reporting.definitions import KEYS
from app.reporting.models import DailyReport, ReportItem, ReportSourceGap
from app.retention.cleanup import run_retention
from tests.factories import create_user, create_workspace, knowledge_ctx
from tests.helpers.reporting import DAY, EXPECTED, Builder, at, build_day
from tests.integration.reporting.conftest import ReportEnv


@pytest.mark.commits
def test_concurrent_first_reads_capture_exactly_one_generation(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        scenario = build_day(session)
        session.commit()
    barrier = Barrier(2)

    def read() -> uuid.UUID | None:
        with session_factory() as session:
            barrier.wait(timeout=10)
            report = service.get_report(session, FrozenClock(scenario.now), scenario.ctx, DAY)
            session.commit()
            return report.snapshot_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: read(), range(2)))
    assert ids[0] == ids[1] and ids[0] is not None
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(DailyReport)) == 1


def test_median_uses_original_durations_before_rounding(db_session: Session) -> None:
    workspace = create_workspace(db_session)
    user = create_user(db_session)
    builder = Builder(db_session, workspace, user)
    for hour, seconds in [(9, 62.4), (10, 63)]:
        conversation = builder.conversation(at(DAY, hour))
        builder.message(conversation, "inbound", at(DAY, hour))
        builder.message(conversation, "outbound", at(DAY, hour) + timedelta(seconds=seconds))
    db_session.commit()
    ctx = knowledge_ctx(workspace, user, "owner")
    clock = FrozenClock(at(DAY + timedelta(days=1), 0))
    report = service.get_report(db_session, clock, ctx, DAY)
    items = drilldown.metric_items(
        db_session, clock, ctx, DAY, "median_first_response_minutes", locale="en"
    )
    measures = sorted(i.measure for i in items.items if i.measure is not None)
    assert measures == [1.04, 1.05]
    assert round(median(measures), 1) == report.value("median_first_response_minutes") == 1.0


def _items(env: ReportEnv, key: str, snapshot_id: uuid.UUID | None = None) -> drilldown.Drilldown:
    return drilldown.metric_items(
        env.env.session,
        env.clock,
        env.scenario.ctx,
        DAY,
        key,
        locale="en",
        limit=200,
        snapshot_id=snapshot_id,
    )


def test_all_historical_memberships_and_measurements_survive_state_changes(
    report_env: ReportEnv,
) -> None:
    env = report_env
    before = {key: _items(env, key) for key in KEYS}
    session = env.env.session
    session.execute(
        update(Conversation)
        .where(Conversation.workspace_id == env.scenario.ctx.workspace_id)
        .values(attention="none", last_outbound_at=env.clock.now())
    )
    session.execute(
        update(Approval)
        .where(Approval.workspace_id == env.scenario.ctx.workspace_id)
        .values(status="approved")
    )
    session.execute(
        update(Message)
        .where(
            Message.workspace_id == env.scenario.ctx.workspace_id, Message.direction == "inbound"
        )
        .values(is_deleted=True)
    )
    env.builder().approval("reply.send", "pending")
    session.commit()
    env.clock.advance(hours=2)

    for key in KEYS:
        after = _items(env, key)
        assert after == before[key], key
        assert after.value == EXPECTED[key]
        if key == "median_first_response_minutes":
            assert (
                round(median(i.measure for i in after.items if i.measure is not None), 1)
                == after.value
            )
        else:
            assert len(after.items) == after.value


def test_links_and_cursors_remain_on_the_original_generation_after_regeneration(
    report_env: ReportEnv,
) -> None:
    env = report_env
    response = env.env.call(env.env.owner, "GET", "/reports/daily", params={"date": str(DAY)})
    original = response.json()
    metric = next(m for m in original["metrics"] if m["key"] == "inbound_messages")
    first = env.env.owner.client.get(metric["link"]["api"] + "&limit=2").json()
    expected_ids = {str(i.id) for i in _items(env, "inbound_messages").items}
    builder = env.builder()
    builder.message(builder.conversation(at(DAY, 23)), "inbound", at(DAY, 23, 1))
    env.env.session.commit()
    # Same clock instant: revision order must still select the new generation.
    newer = env.env.call(
        env.env.owner, "POST", "/reports/daily/generate", json={"date": str(DAY)}
    ).json()
    assert newer["snapshot_id"] != original["snapshot_id"]
    latest = env.env.call(env.env.owner, "GET", "/reports/daily", params={"date": str(DAY)}).json()
    assert latest["snapshot_id"] == newer["snapshot_id"]

    ids = [i["id"] for i in first["items"]]
    cursor = first["next_cursor"]
    while cursor:
        page = env.env.call(
            env.env.owner,
            "GET",
            f"/reports/daily/{DAY}/metrics/inbound_messages",
            params={"cursor": cursor, "limit": 2},
        )
        assert page.status_code == 200, page.text
        body = page.json()
        assert body["snapshot_id"] == original["snapshot_id"]
        assert body["value"] == EXPECTED["inbound_messages"]
        ids.extend(i["id"] for i in body["items"])
        cursor = body["next_cursor"]
    assert len(ids) == len(set(ids)) == len(expected_ids)
    assert set(ids) == expected_ids
    old_report = env.env.call(
        env.env.owner,
        "GET",
        "/reports/daily",
        params={
            "date": str(DAY),
            "snapshot_id": original["snapshot_id"],
        },
    )
    assert old_report.json() == original
    mismatch = env.env.call(
        env.env.owner,
        "GET",
        f"/reports/daily/{DAY}/metrics/inbound_messages",
        params={
            "cursor": first["next_cursor"],
            "snapshot_id": newer["snapshot_id"],
        },
    )
    assert mismatch.status_code == 422
    wrong_metric = env.env.call(
        env.env.owner,
        "GET",
        f"/reports/daily/{DAY}/metrics/replies_sent",
        params={
            "cursor": first["next_cursor"],
        },
    )
    assert wrong_metric.status_code == 422


def test_snapshots_remain_explainable_after_deletion_and_privacy_redaction(
    report_env: ReportEnv,
    settings: Settings,
) -> None:
    env = report_env
    session = env.env.session
    session.execute(update(Message).values(text="private customer text"))
    session.execute(update(ReplyDraft).values(text="private reply", template="private template"))
    session.execute(update(InboundEvent).values(payload={"secret": "private webhook"}))
    session.commit()
    report = service.get_report(session, env.clock, env.scenario.ctx, DAY)
    before = {key: _items(env, key) for key in KEYS}
    session.commit()
    counts = run_retention(env.factory, settings, env.clock.now() + timedelta(days=366))
    session.expire_all()
    assert (
        counts.webhook_rows_deleted > 0 and counts.messages_nulled > 0 and counts.drafts_nulled > 0
    )
    assert session.scalar(select(func.count()).select_from(InboundEvent)) == 0
    for key in KEYS:
        assert _items(env, key, report.snapshot_id) == before[key], key
    # Evidence contains only routing IDs, timestamps, flags, measurements and group keys.
    assert set(ReportItem.__table__.columns.keys()) == {
        "id",
        "workspace_id",
        "report_id",
        "metric_key",
        "subject_type",
        "subject_id",
        "occurred_at",
        "is_simulated",
        "link_id",
        "measure",
        "group_key",
    }
    assert session.scalar(select(func.count()).select_from(ReportSourceGap)) > 0
    before_count = session.scalar(select(func.count()).select_from(DailyReport))
    response = env.env.call(
        env.env.owner, "POST", "/reports/daily/generate", json={"date": str(DAY)}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "REPORT_SOURCES_RETAINED_OUT"
    assert response.json()["params"] == {"metrics": ["integration_errors"]}
    assert session.scalar(select(func.count()).select_from(DailyReport)) == before_count
    assert service.get_report(session, env.clock, env.scenario.ctx, DAY).metrics == report.metrics


def test_retention_gap_uses_failure_time_and_preserves_other_days_and_workspaces(
    report_env: ReportEnv,
    settings: Settings,
) -> None:
    env = report_env
    session = env.env.session
    other = build_day(session)
    # Received long ago but failed yesterday: the reporting timestamp is processed_at.
    event = env.builder().inbound_event("failed", at(DAY - timedelta(days=100), 12))
    event.processed_at = at(DAY - timedelta(days=1), 12)
    session.commit()
    run_retention(env.factory, settings, env.clock.now())
    session.expire_all()
    with pytest.raises(AppError, match="REPORT_SOURCES_RETAINED_OUT"):
        service.generate_daily_report(
            session, env.clock, env.scenario.ctx, DAY - timedelta(days=1), scheduled=False
        )
    # These periods lost no contributing failures.
    assert (
        service.generate_daily_report(
            session, env.clock, env.scenario.ctx, DAY, scheduled=False
        ).value("integration_errors")
        == 18
    )
    assert (
        service.generate_daily_report(session, env.clock, other.ctx, DAY, scheduled=False).value(
            "integration_errors"
        )
        == 18
    )


def test_foreign_or_wrong_day_snapshots_and_cursors_are_refused(report_env: ReportEnv) -> None:
    env = report_env
    other = build_day(env.env.session)
    foreign = service.generate_daily_report(
        env.env.session, env.clock, other.ctx, DAY, scheduled=False
    )
    env.env.session.commit()
    for path in ("/reports/daily", f"/reports/daily/{DAY}/metrics/inbound_messages"):
        response = env.env.call(
            env.env.owner,
            "GET",
            path,
            params={"date": str(DAY), "snapshot_id": str(foreign.snapshot_id)},
        )
        assert response.status_code == 404
    own = _items(env, "inbound_messages")
    assert {i.id for i in own.items}.isdisjoint(
        {
            i.id
            for i in drilldown.metric_items(
                env.env.session,
                env.clock,
                other.ctx,
                DAY,
                "inbound_messages",
                locale="en",
                limit=200,
            ).items
        }
    )
    wrong_day = env.env.call(
        env.env.owner,
        "GET",
        "/reports/daily",
        params={
            "date": str(DAY - timedelta(days=1)),
            "snapshot_id": str(own.snapshot_id),
        },
    )
    assert wrong_day.status_code == 404
    page = drilldown.metric_items(
        env.env.session, env.clock, other.ctx, DAY, "inbound_messages", locale="en", limit=1
    )
    with pytest.raises(AppError, match="VALIDATION_FAILED"):
        drilldown.metric_items(
            env.env.session,
            env.clock,
            env.scenario.ctx,
            DAY,
            "inbound_messages",
            locale="en",
            cursor=page.next_cursor,
        )
    # Composite FK also prevents evidence being attached to another tenant's generation.
    savepoint = env.env.session.begin_nested()
    env.env.session.add(
        ReportItem(
            workspace_id=env.scenario.ctx.workspace_id,
            report_id=foreign.snapshot_id,
            metric_key="inbound_messages",
            subject_type="message",
            subject_id=uuid.uuid4(),
            link_id=uuid.uuid4(),
            is_simulated=True,
        )
    )
    with pytest.raises(IntegrityError):
        env.env.session.flush()
    savepoint.rollback()


def test_legacy_report_values_are_preserved_without_fabricating_membership(
    report_env: ReportEnv,
) -> None:
    env = report_env
    row = DailyReport(
        workspace_id=env.scenario.ctx.workspace_id,
        local_date=DAY,
        timezone=env.scenario.ctx.timezone,
        period_start=env.scenario.start,
        period_end=env.scenario.end,
        metrics={"inbound_messages": {"value": 999}},
        definitions_version="1",
        generated_at=env.clock.now(),
    )
    env.env.session.add(row)
    env.env.session.commit()
    report = env.env.call(env.env.owner, "GET", "/reports/daily", params={"date": str(DAY)}).json()
    assert report["metrics"][0]["value"] == 999
    assert report["evidence_complete"] is False
    missing = env.env.owner.client.get(report["metrics"][0]["link"]["api"])
    assert missing.status_code == 409
    assert missing.json()["code"] == "REPORT_EVIDENCE_UNAVAILABLE"
    regenerated = service.generate_daily_report(
        env.env.session, env.clock, env.scenario.ctx, DAY, scheduled=False
    )
    assert regenerated.evidence_complete and regenerated.value("inbound_messages") == 15
    assert env.env.session.get(DailyReport, row.id).metrics == {"inbound_messages": {"value": 999}}
