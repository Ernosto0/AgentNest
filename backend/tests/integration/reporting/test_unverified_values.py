"""D-01: "replies sent" and "unverified values sent" in the daily report.

The second number is read from the claim-validator result stored with each sent reply's draft. It
is never a constant, so these tests build replies whose stored results differ and check that the
number follows them, that the drill-down lists exactly those replies, and that simulated data is
flagged like every other metric.
"""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.reporting import service
from app.reporting.metrics import compute_metrics
from app.reporting.summary import build_summary
from tests.factories import create_user, create_workspace, knowledge_ctx
from tests.helpers.reporting import DAY, TIMEZONE, UNVERIFIED_AI, UNVERIFIED_OWNER, Builder, at
from tests.integration.reporting.conftest import ReportEnv

CLEAN: dict[str, Any] = {"passed": True, "issues": [], "rendered": []}
OWN_MATCHES_VERIFIED: dict[str, Any] = {
    "passed": False,
    "issues": [{"code": "MONEY", "span": [0, 5], "text": "6.000", "matches_verified": True}],
    "rendered": [],
}
TOO_LONG_ONLY: dict[str, Any] = {
    "passed": False,
    "issues": [{"code": "TOO_LONG", "span": [0, 5], "text": ""}],
    "rendered": [],
}
RENDER_ERROR_ONLY: dict[str, Any] = {
    "passed": False,
    "issues": [{"code": "FACT_NOT_FOUND", "span": None, "text": "pricing.x"}],
    "rendered": [],
}


@pytest.fixture
def day(db_session: Session):  # type: ignore[no-untyped-def]
    workspace = create_workspace(db_session, timezone=TIMEZONE)
    user = create_user(db_session)
    builder = Builder(db_session, workspace, user, simulated=False)
    conversation = builder.conversation(at(DAY, 9))
    first = builder.message(conversation, "inbound", at(DAY, 9, 1))
    ctx = knowledge_ctx(workspace)
    return builder, conversation, first, ctx


def _metrics(session: Session, ctx):  # type: ignore[no-untyped-def]
    start, end = at(DAY, 0), at(DAY, 23, 59, 59)
    return compute_metrics(session, ctx, start, end, end)


def _reply(builder: Builder, conversation, first, minute: int, **kwargs):  # type: ignore[no-untyped-def]
    return builder.reply(conversation, first, at(DAY, 10, minute), **kwargs)


def test_a_day_without_replies_reports_zero_unverified(db_session: Session, day) -> None:
    _, _, _, ctx = day
    metrics = _metrics(db_session, ctx)
    assert metrics.value("replies_sent") == 0
    assert metrics.value("unverified_values_sent") == 0


def test_clean_replies_are_sent_and_none_is_unverified(db_session: Session, day) -> None:
    builder, conversation, first, ctx = day
    for minute in range(3):
        _reply(builder, conversation, first, minute, source="ai", decision="auto", validation=CLEAN)
    metrics = _metrics(db_session, ctx)
    assert metrics.value("replies_sent") == 3
    assert metrics.value("unverified_values_sent") == 0


def test_the_number_follows_the_stored_validator_results(db_session: Session, day) -> None:
    builder, conversation, first, ctx = day
    _reply(builder, conversation, first, 0, source="ai", decision="auto", validation=CLEAN)
    assert _metrics(db_session, ctx).value("unverified_values_sent") == 0

    _reply(
        builder, conversation, first, 1, source="owner", decision="approval_required",
        validation=UNVERIFIED_OWNER,
    )  # fmt: skip
    assert _metrics(db_session, ctx).value("unverified_values_sent") == 1

    _reply(
        builder, conversation, first, 2, source="ai", decision="approval_required",
        validation=UNVERIFIED_AI,
    )  # fmt: skip
    metrics = _metrics(db_session, ctx)
    assert metrics.value("unverified_values_sent") == 2
    assert metrics.value("replies_sent") == 3


def test_a_reply_with_two_unverified_values_counts_once(db_session: Session, day) -> None:
    builder, conversation, first, ctx = day
    two = {
        "passed": False,
        "issues": [*UNVERIFIED_AI["issues"], *UNVERIFIED_OWNER["issues"]],
        "rendered": [],
    }
    _reply(
        builder,
        conversation,
        first,
        0,
        source="owner",
        decision="approval_required",
        validation=two,
    )
    assert _metrics(db_session, ctx).value("unverified_values_sent") == 1


def test_a_person_s_value_that_equals_a_verified_one_is_not_unverified(
    db_session: Session, day
) -> None:
    builder, conversation, first, ctx = day
    _reply(
        builder, conversation, first, 0, source="owner", decision="approval_required",
        validation=OWN_MATCHES_VERIFIED,
    )  # fmt: skip
    assert _metrics(db_session, ctx).value("unverified_values_sent") == 0


def test_a_length_or_render_problem_is_not_an_unverified_value(db_session: Session, day) -> None:
    builder, conversation, first, ctx = day
    for minute, validation in enumerate((TOO_LONG_ONLY, RENDER_ERROR_ONLY)):
        _reply(
            builder, conversation, first, minute, source="owner", decision="approval_required",
            validation=validation,
        )  # fmt: skip
    assert _metrics(db_session, ctx).value("unverified_values_sent") == 0


def test_an_assistant_reply_sent_although_its_validation_failed_is_counted(
    db_session: Session, day
) -> None:
    builder, conversation, first, ctx = day
    failed = {"passed": False, "issues": [], "rendered": []}
    _reply(
        builder,
        conversation,
        first,
        0,
        source="approved_answer",
        decision="auto",
        validation=failed,
    )
    assert _metrics(db_session, ctx).value("unverified_values_sent") == 1


def test_a_reply_with_no_stored_result_is_in_replies_sent_only(db_session: Session, day) -> None:
    """No draft, an erased validation or a server-written agent reply cannot be judged."""
    builder, conversation, first, ctx = day
    builder.message(conversation, "outbound", at(DAY, 10, 0))  # no draft
    _reply(builder, conversation, first, 1, source="ai", decision="auto", validation={})
    metrics = _metrics(db_session, ctx)
    assert metrics.value("replies_sent") == 2
    assert metrics.value("unverified_values_sent") == 0


def test_replies_outside_the_day_and_unsent_drafts_do_not_count(db_session: Session, day) -> None:
    builder, conversation, first, ctx = day
    builder.reply(
        conversation, first, at(DAY - timedelta(days=1), 10), source="owner",
        decision="approval_required", validation=UNVERIFIED_OWNER,
    )  # fmt: skip
    builder.draft(
        conversation, first, source="owner", decision="approval_required", status="failed",
        created_at=at(DAY, 10), validation=UNVERIFIED_OWNER,
    )  # fmt: skip
    assert _metrics(db_session, ctx).value("unverified_values_sent") == 0


def test_a_simulated_reply_is_flagged_like_every_other_metric(db_session: Session) -> None:
    workspace = create_workspace(db_session, timezone=TIMEZONE)
    builder = Builder(db_session, workspace, create_user(db_session), simulated=True)
    conversation = builder.conversation(at(DAY, 9))
    first = builder.message(conversation, "inbound", at(DAY, 9, 1))
    _reply(
        builder,
        conversation,
        first,
        0,
        source="owner",
        decision="approval_required",
        validation=UNVERIFIED_OWNER,
    )
    metric = _metrics(db_session, knowledge_ctx(workspace)).by_key["unverified_values_sent"]
    assert metric.value == 1 and metric.has_simulated_data is True


def test_the_report_summary_counts_it_and_leaves_the_guarantee_to_the_metrics(
    db_session: Session, day
) -> None:
    builder, conversation, first, ctx = day
    _reply(
        builder,
        conversation,
        first,
        0,
        source="owner",
        decision="approval_required",
        validation=UNVERIFIED_OWNER,
    )
    metrics = _metrics(db_session, ctx)
    summary = build_summary(
        {m.key: m.as_dict() for m in metrics.metrics},
        ["replies_sent", "unverified_values_sent"],
        "en",
    )
    assert "Replies that contained unverified values: 1" in summary.text


def test_the_daily_summary_for_telegram_carries_both_numbers(
    db_session: Session, clock: FrozenClock
) -> None:
    workspace = create_workspace(db_session, timezone=TIMEZONE)
    ctx = knowledge_ctx(workspace)
    builder = Builder(db_session, workspace, create_user(db_session), simulated=False)
    now = clock.now()
    conversation = builder.conversation(now - timedelta(minutes=30))
    first = builder.message(conversation, "inbound", now - timedelta(minutes=25))
    builder.reply(
        conversation,
        first,
        now - timedelta(minutes=20),
        source="ai",
        decision="auto",
        validation=CLEAN,
    )
    before = service.get_daily_summary(db_session, clock, ctx)
    assert before["replies_sent"] == 1 and before["unverified_values_sent"] == 0

    builder.reply(
        conversation, first, now - timedelta(minutes=10), source="owner",
        decision="approval_required", validation=UNVERIFIED_OWNER,
    )  # fmt: skip
    after = service.get_daily_summary(db_session, clock, ctx)
    assert after["replies_sent"] == 2 and after["unverified_values_sent"] == 1


def test_the_guarantee_report_lines_are_shown_even_at_zero(report_env: ReportEnv) -> None:
    """The API serves both numbers with a drill-down link; the scripted day has 19 replies with
    a stored unverified value and the drill-down lists exactly those."""
    env = report_env
    body = env.env.call(
        env.env.owner, "GET", "/reports/daily", params={"date": DAY.isoformat()}
    ).json()
    by_key = {m["key"]: m for m in body["metrics"]}
    assert by_key["replies_sent"]["value"] == 40
    assert by_key["unverified_values_sent"]["value"] == 19
    assert (
        f"/more/reports/{DAY.isoformat()}/unverified_values_sent"
        in (by_key["unverified_values_sent"]["link"]["route"])
    )
    drill = env.env.call(
        env.env.owner,
        "GET",
        f"/reports/daily/{DAY.isoformat()}/metrics/unverified_values_sent",
        params={"limit": 100},
    ).json()
    assert drill["value"] == 19 and len(drill["items"]) == 19
    assert all(i["kind"] == "message" and i["link"] for i in drill["items"])
    staff = env.env.call(
        env.env.staff, "GET", "/reports/daily", params={"date": DAY.isoformat()}
    ).json()
    assert "unverified_values_sent" in {m["key"] for m in staff["metrics"]}  # an inbox metric
