"""The operator's plan commands: show, set, reset and extend."""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.cli import main
from app.core.clock import SystemClock
from app.plans import service
from tests.factories import workspace_with_members

pytestmark = pytest.mark.commits


def make(factory: sessionmaker[Session]) -> tuple[uuid.UUID, str]:
    with factory() as session:
        workspace, _ = workspace_with_members(session, name="CLI Plans", slug="cli-plans")
        session.commit()
        return workspace.id, workspace.slug


def run(capsys: pytest.CaptureFixture[str], *args: str) -> dict[str, object]:
    capsys.readouterr()
    assert main(list(args)) == 0
    return json.loads(capsys.readouterr().out)  # type: ignore[no-any-return]


def test_plan_usage_shows_the_default(
    session_factory: sessionmaker[Session], capsys: pytest.CaptureFixture[str]
) -> None:
    _, slug = make(session_factory)
    out = run(capsys, "plan-usage", "--workspace", slug)
    assert (out["plan"], out["status"], out["quota"], out["used"], out["state"]) == (
        "growth",
        "trial",
        2500,
        0,
        "normal",
    )


def test_plan_set_changes_plan_override_and_status(
    session_factory: sessionmaker[Session], capsys: pytest.CaptureFixture[str]
) -> None:
    _, slug = make(session_factory)
    out = run(capsys, "plan-set", "--workspace", slug, "--plan", "starter", "--status", "active")
    assert (out["plan"], out["status"], out["quota"], out["quota_override"]) == (
        "starter",
        "active",
        500,
        None,
    )
    out = run(capsys, "plan-set", "--workspace", slug, "--plan", "pro", "--quota", "9000")
    assert (out["plan"], out["monthly_quota"], out["quota"], out["quota_override"]) == (
        "pro",
        7500,
        9000,
        9000,
    )
    assert out["status"] == "active"  # not touched
    out = run(capsys, "plan-set", "--workspace", slug, "--plan", "pro", "--clear-override")
    assert (out["quota"], out["quota_override"]) == (7500, None)
    # the change is stored, not just printed
    assert run(capsys, "plan-usage", "--workspace", slug)["plan"] == "pro"


def test_plan_set_resumes_a_paused_workspace(
    session_factory: sessionmaker[Session], capsys: pytest.CaptureFixture[str]
) -> None:
    workspace_id, slug = make(session_factory)
    run(capsys, "plan-set", "--workspace", slug, "--plan", "starter", "--quota", "10")
    with session_factory() as session:
        for i in range(11):
            service.consume(session, SystemClock(), workspace_id, f"d{i}")
        session.commit()
    assert run(capsys, "plan-usage", "--workspace", slug)["state"] == "paused"
    out = run(capsys, "plan-set", "--workspace", slug, "--plan", "growth", "--clear-override")
    assert (out["state"], out["used"]) == ("normal", 11)


def test_plan_reset_starts_a_fresh_period_with_the_warnings_armed(
    session_factory: sessionmaker[Session], capsys: pytest.CaptureFixture[str]
) -> None:
    workspace_id, slug = make(session_factory)
    run(capsys, "plan-set", "--workspace", slug, "--plan", "starter", "--quota", "10")
    with session_factory() as session:
        for i in range(9):
            service.consume(session, SystemClock(), workspace_id, f"d{i}")
        old_period = service.get_plan(session, SystemClock(), workspace_id).period_id
        session.commit()
    out = run(capsys, "plan-reset", "--workspace", slug)
    assert out["used"] == 0 and out["state"] == "normal"
    start = datetime.fromisoformat(str(out["period_start"]))
    assert abs(datetime.now(UTC) - start) < timedelta(minutes=5)
    with session_factory() as session:
        row = service.get_plan(session, SystemClock(), workspace_id)
        assert row.period_id != old_period
        assert not (row.warned_80 or row.warned_100 or row.warned_paused)


def test_plan_extend_moves_the_period_end_and_keeps_the_usage(
    session_factory: sessionmaker[Session], capsys: pytest.CaptureFixture[str]
) -> None:
    workspace_id, slug = make(session_factory)
    with session_factory() as session:
        service.consume(session, SystemClock(), workspace_id, "d0")
        session.commit()
    before = run(capsys, "plan-usage", "--workspace", slug)
    after = run(capsys, "plan-extend", "--workspace", slug, "--days", "10")
    gap = datetime.fromisoformat(str(after["period_end"])) - datetime.fromisoformat(
        str(before["period_end"])
    )
    assert gap == timedelta(days=10)
    assert after["used"] == 1


def test_bad_input_is_refused_and_changes_nothing(
    session_factory: sessionmaker[Session], capsys: pytest.CaptureFixture[str]
) -> None:
    _, slug = make(session_factory)
    assert main(["plan-usage", "--workspace", "no-such-workspace"]) == 1
    assert "workspace not found" in capsys.readouterr().err
    assert main(["plan-set", "--workspace", slug, "--plan", "starter", "--quota", "0"]) == 1
    assert main(["plan-extend", "--workspace", slug, "--days", "0"]) == 1
    capsys.readouterr()
    with pytest.raises(SystemExit):
        main(["plan-set", "--workspace", slug, "--plan", "enterprise"])
    assert run(capsys, "plan-usage", "--workspace", slug)["plan"] == "growth"
