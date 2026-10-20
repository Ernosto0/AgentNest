"""``query.activity_summary`` answers from the daily report's numbers (plan H5, AC-E4)."""

from datetime import date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.integrations.instagram.models import SocialAccount
from app.reporting.periods import local_date_of
from tests.factories import create_workspace
from tests.helpers.reporting import Builder, at
from tests.integration.commands.conftest import CommandEnv

TODAY = date(2026, 1, 15)  # the fixture clock is 2026-01-15 12:00 UTC = 15:00 Istanbul
PARAMS_TO_METRICS = {
    "inbound_messages": "inbound_messages",
    "conversations": "conversations_with_inbound",
    "replies_sent": "replies_sent",
    "replies_auto": "replies_sent_auto",
    "replies_approved": "replies_sent_approved",
    "replies_by_owner": "replies_sent_by_owner",
    "escalations": "escalations",
    "attention_now": "attention_now",
}


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return at(day, hour, minute, tz="Europe/Istanbul")


def _builder(cmd: CommandEnv) -> Builder:
    """A builder on the workspace's one account (a workspace may have only one active)."""
    account = cmd.env.session.scalar(
        select(SocialAccount).where(SocialAccount.workspace_id == cmd.env.workspace.id)
    )
    return Builder(
        cmd.env.session, cmd.env.workspace, cmd.env.owner.user, simulated=True, account=account
    )


def _seed(cmd: CommandEnv) -> Builder:
    """Records on today and on each of the six days before it (n + 1 inbound messages on the
    day n days ago), plus replies of every kind today."""
    builder = _builder(cmd)
    for days_ago in range(0, 9):
        day = TODAY - timedelta(days=days_ago)
        conversation = builder.conversation(_at(day, 8, 0))
        last = None
        for n in range(days_ago + 1):
            last = builder.message(conversation, "inbound", _at(day, 6 + n))
        if days_ago == 0:
            assert last is not None
            builder.reply(conversation, last, _at(day, 9, 0), source="ai", decision="auto")
            builder.reply(
                conversation, last, _at(day, 9, 5), source="ai", decision="approval_required"
            )
            builder.reply(
                conversation, last, _at(day, 9, 10), source="owner", decision="approval_required"
            )
            builder.draft(
                conversation,
                last,
                source="ai",
                decision="human_required",
                status="needs_human",
                created_at=_at(day, 9, 15),
            )
    cmd.env.session.commit()
    return builder


def _report(cmd: CommandEnv, day: date) -> dict[str, Any]:
    response = cmd.env.call(
        cmd.env.owner, "GET", "/reports/daily", params={"date": day.isoformat()}
    )
    assert response.status_code == 200, response.text
    return {m["key"]: m["value"] for m in response.json()["metrics"]}


@pytest.fixture
def seeded(cmd: CommandEnv) -> CommandEnv:
    _seed(cmd)
    return cmd


def test_ac_e4_the_answer_equals_the_reports_number_at_the_same_instant(
    seeded: CommandEnv,
) -> None:
    cmd = seeded
    assert local_date_of(cmd.env.clock.now(), "Europe/Istanbul") == TODAY
    answer = cmd.run(cmd.env.owner, "Bugün kaç DM geldi?")

    assert answer["status"] == "completed"
    assert answer["result"]["message_key"] == "command.activity_summary"
    params = answer["result"]["params"]
    report = _report(cmd, TODAY)
    assert params["period"] == "today"
    assert params["inbound_messages"] == report["inbound_messages"] == 1
    for param, key in PARAMS_TO_METRICS.items():
        assert params[param] == report[key], param
    assert params["replies_sent"] == 3 and params["replies_auto"] == 1
    assert params["replies_approved"] == 1 and params["replies_by_owner"] == 1
    assert params["escalations"] == 1
    assert params["is_simulated"] is True  # INV-09: the answer says it covers simulated records
    assert answer["result"]["links"] == [{"target": "report", "date": TODAY.isoformat()}]


def test_the_answer_follows_the_report_as_records_arrive(seeded: CommandEnv) -> None:
    cmd = seeded
    first = cmd.run(cmd.env.owner, "Bugün kaç DM geldi?")["result"]["params"]["inbound_messages"]
    builder = _builder(cmd)
    builder.message(builder.conversation(_at(TODAY, 10, 0)), "inbound", _at(TODAY, 14, 0))
    cmd.env.session.commit()
    second = cmd.run(cmd.env.owner, "Bugün kaç DM geldi?")["result"]["params"]["inbound_messages"]
    assert second == first + 1 == _report(cmd, TODAY)["inbound_messages"]


def test_yesterday_is_the_whole_previous_local_day(seeded: CommandEnv) -> None:
    cmd = seeded
    yesterday = TODAY - timedelta(days=1)
    answer = cmd.run(cmd.env.owner, "Dün ne oldu?")
    params = answer["result"]["params"]
    assert params["period"] == "yesterday"
    assert params["inbound_messages"] == 2  # n + 1 messages on the day n days ago
    report = _report(cmd, yesterday)
    for param, key in PARAMS_TO_METRICS.items():
        if key not in ("attention_now",):  # a snapshot: as of the moment, not of the day
            assert params[param] == report[key], param
    assert answer["result"]["links"] == [{"target": "report", "date": yesterday.isoformat()}]


def test_the_last_seven_days_are_the_sum_of_seven_local_days(seeded: CommandEnv) -> None:
    cmd = seeded
    answer = cmd.run(cmd.env.owner, "Son 7 gün")
    params = answer["result"]["params"]
    assert answer["result"]["message_key"] == "command.activity_summary"
    assert params["period"] == "last_7_days"
    days = [TODAY - timedelta(days=n) for n in range(7)]
    reports = [_report(cmd, day) for day in days]
    assert (
        params["inbound_messages"]
        == sum(r["inbound_messages"] for r in reports)
        == 1 + 2 + 3 + 4 + 5 + 6 + 7
    )
    assert params["replies_sent"] == sum(r["replies_sent"] for r in reports) == 3
    # The two older days (8 and 9 messages) are outside the window.
    assert answer["result"]["links"] == [{"target": "report", "date": TODAY.isoformat()}]


@pytest.mark.parametrize(
    ("text", "period"),
    [
        ("How many DMs did we get today?", "today"),
        ("what happened yesterday", "yesterday"),
        ("summary of the last 7 days", "last_7_days"),
        ("Son 7 gün", "last_7_days"),
        ("Bugün kaç mesaj geldi", "today"),
        ("Dün ne oldu?", "yesterday"),
        ("bugün neler oldu", "today"),
    ],
)
def test_the_grammar_reads_the_period(seeded: CommandEnv, text: str, period: str) -> None:
    command = seeded.run(seeded.env.owner, text)
    assert command["status"] == "completed", command
    assert command["result"]["message_key"] == "command.activity_summary"
    assert command["result"]["params"]["period"] == period


def test_a_day_boundary_in_the_workspace_timezone_decides_yesterday(seeded: CommandEnv) -> None:
    """A message at 23:59 local on the previous day is yesterday's; 00:00 local is today's, even
    though both are on the same UTC date (INV-19)."""
    cmd = seeded
    builder = _builder(cmd)
    conversation = builder.conversation(_at(TODAY - timedelta(days=1), 22, 0))
    builder.message(conversation, "inbound", _at(TODAY - timedelta(days=1), 23, 59))
    builder.message(conversation, "inbound", _at(TODAY, 0, 0))
    cmd.env.session.commit()
    today = cmd.run(cmd.env.owner, "Bugün kaç DM geldi?")["result"]["params"]["inbound_messages"]
    yesterday = cmd.run(cmd.env.owner, "Dün ne oldu?")["result"]["params"]["inbound_messages"]
    assert today == 2 and yesterday == 3
    assert today == _report(cmd, TODAY)["inbound_messages"]


def test_the_answer_for_another_workspace_is_never_mixed_in(seeded: CommandEnv) -> None:
    cmd = seeded
    other = create_workspace(cmd.env.session, name="Other", slug="other")
    foreign = Builder(cmd.env.session, other, cmd.env.owner.user)
    for _ in range(5):
        foreign.message(foreign.conversation(_at(TODAY, 8, 0)), "inbound", _at(TODAY, 9, 0))
    cmd.env.session.commit()
    answer = cmd.run(cmd.env.owner, "Bugün kaç DM geldi?")
    assert answer["result"]["params"]["inbound_messages"] == 1


def test_a_workspace_without_messages_answers_zero_not_an_error(cmd: CommandEnv) -> None:
    answer = cmd.run(cmd.env.owner, "Bugün kaç DM geldi?")
    params = answer["result"]["params"]
    assert answer["status"] == "completed"
    assert params["inbound_messages"] == 0 and params["replies_sent"] == 0
    assert params["is_simulated"] is False
