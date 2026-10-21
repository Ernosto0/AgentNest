"""P6-07 (H16): yesterday's seeded history."""

from typing import Any

import pytest
from sqlalchemy import func, select, text

from app.audit.models import AuditLog
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.db import Base
from app.demo.seed import seed
from app.identity.models import Workspace
from app.jobs.models import Job
from app.jobs.testing import run_due_jobs
from app.reporting.models import DailyReport
from tests.helpers.demo import (
    STUDIOS,
    YESTERDAY_REPORT,
    SessionFactory,
    stored_report,
    tenant_tables,
    workspace_ids,
    yesterday_of,
)

pytestmark = pytest.mark.commits


@pytest.mark.parametrize("slug", STUDIOS)
def test_yesterdays_report_is_exact(seeded: SessionFactory, clock: FrozenClock, slug: str) -> None:
    ids = workspace_ids(seeded)
    with seeded() as session:
        timezone = session.get(Workspace, ids[slug]).timezone  # type: ignore[union-attr]
    report = stored_report(seeded, ids[slug])

    assert report.local_date == yesterday_of(clock, timezone)
    assert report.has_simulated_data is True
    values = {key: entry["value"] for key, entry in report.metrics.items()}
    for key, expected in YESTERDAY_REPORT.items():
        assert values[key] == expected, key
    # Derived: one draft is left waiting for approval, and the complaint waits for a person.
    assert values["pending_approvals_now"] == 1
    assert values["unanswered_open_now"] == 2
    assert values["attention_now"] == 2
    assert values["content_on_hold_now"] == 0
    assert values["content_scheduled_next_24h"] == 0
    assert values["median_first_response_minutes"] is not None
    assert 0 < values["median_first_response_minutes"] < 5


def test_other_workspace_gets_no_history(seeded: SessionFactory) -> None:
    ids = workspace_ids(seeded)
    with seeded() as session:
        reports = session.scalar(
            select(func.count())
            .select_from(DailyReport)
            .where(DailyReport.workspace_id == ids["other-workspace"])
        )
    assert reports == 0


def test_every_history_row_is_simulated(seeded: SessionFactory) -> None:
    """INV-09: no tenant row is a real-looking one, whatever table it sits in."""
    ids = workspace_ids(seeded)
    studio_ids = [ids[s] for s in STUDIOS]
    with seeded() as session:
        for table in tenant_tables():
            if "is_simulated" not in table.c or table.name == "audit_logs":
                continue
            real = session.scalar(
                select(func.count())
                .select_from(table)
                .where(table.c.workspace_id.in_(studio_ids), table.c.is_simulated.is_(False))
            )
            assert real == 0, table.name
        # Audit: the history's own entries (everything but the seed's setup) are simulated.
        history_prefixes = (
            "message.",
            "reply",
            "approval.",
            "content.",
            "media.",
            "operation.",
            "report.",
            "conversation.",
        )
        entries = session.scalars(
            select(AuditLog).where(AuditLog.workspace_id.in_(studio_ids))
        ).all()
    history = [e for e in entries if e.action.startswith(history_prefixes)]
    assert history, "the history writes audit entries"
    # Phase 5 behaviour, not changed here: a draft and its upload are not tied to an account
    # yet, so their audit entries are not simulated until submit. Nothing else may be.
    not_simulated = {e.action for e in history if not e.is_simulated}
    assert not_simulated <= {"content.created", "media.uploaded"}


def test_history_leaves_no_queued_jobs_and_all_ledger_rows_settled(seeded: SessionFactory) -> None:
    with seeded() as session:
        open_jobs = session.scalars(select(Job).where(Job.status.in_(("queued", "running")))).all()
        statuses = {r[0] for r in session.execute(text("select distinct status from operations"))}
    assert [j.job_type for j in open_jobs] == []
    assert statuses == {"succeeded", "failed"}  # 4 sends + 1 publish ok; 1 publish failed


def test_seed_twice_adds_the_history_once(
    seeded: SessionFactory, clock: FrozenClock, seed_settings: Settings
) -> None:
    def counts() -> dict[str, int]:
        with seeded() as session:
            return {
                t.name: session.scalar(select(func.count()).select_from(t)) or 0
                for t in Base.metadata.sorted_tables
                if t.name not in ("sessions",)
            }

    before = counts()
    seed(seeded, clock, seed_settings)
    seed(seeded, clock, seed_settings)
    assert counts() == before
    assert before["conversations"] == 12
    assert before["daily_reports"] == 2


def test_nothing_of_the_history_is_visible_to_a_worker_until_it_is_complete(
    session_factory: SessionFactory,
    clock: FrozenClock,
    seed_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A running worker uses the real clock: it must never see the history's jobs or their
    (to a real clock, expired) leases. Everything is committed at once, when the day is done."""
    seen: list[int] = []
    real_run_due_jobs = run_due_jobs

    def observing_run_due_jobs(*args: Any, **kwargs: Any) -> int:
        with session_factory() as other:  # another connection, like a worker's
            seen.append(other.scalar(select(func.count()).select_from(Job)) or 0)
        return real_run_due_jobs(*args, **kwargs)

    monkeypatch.setattr("app.demo.history_seed.run_due_jobs", observing_run_due_jobs)
    seed(session_factory, clock, seed_settings)

    zeros = [n for n in seen if n == 0]
    visible = {n for n in seen if n > 0}
    # The first studio is built without a single job being visible; the second one is built
    # while only the first one's (finished) jobs are, and none of its own.
    assert len(zeros) >= 10
    assert seen[: len(zeros)] == zeros
    assert len(visible) == 1
    with session_factory() as session:
        unfinished = session.scalar(
            select(func.count()).select_from(Job).where(Job.status != "succeeded")
        )
    assert unfinished == 0
