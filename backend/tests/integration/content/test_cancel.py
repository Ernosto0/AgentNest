"""AC-D7: cancelling an item cancels its approval and its job (G1, workflows E step 7); a
waiting operation is cancelled through the ledger hook; ``publishing`` is a 409."""

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import select

from app.approvals.models import Approval
from app.audit.models import AuditLog
from app.content import hooks
from app.content.hooks import LedgerHooks
from app.content.models import ContentItem
from app.content.payload import publish_job_key
from app.jobs.models import Job
from tests.helpers.content import make_item, publish_job, request_approval, submittable_item
from tests.helpers.env import Env
from tests.integration.content.test_schedule import ITEMS, jobs_for, submit
from tests.integration.content.test_staff_submit import LATER, decide, staff_submit


def cancel(env: Env, item: ContentItem, role: str = "owner") -> Any:
    return env.call(getattr(env, role), "POST", f"{ITEMS}/{item.id}/cancel")


def audit_for(env: Env, item: ContentItem, action: str) -> list[AuditLog]:
    return list(
        env.session.scalars(
            select(AuditLog).where(AuditLog.resource_id == item.id, AuditLog.action == action)
        )
    )


@pytest.fixture
def cancelled_operations() -> Iterator[list[str]]:
    """A ledger hook that records the cancellations it is asked for."""
    reasons: list[str] = []

    def cancel_operation(session, clock, ctx, item, reason):  # type: ignore[no-untyped-def]
        reasons.append(f"{item.id}:{reason}")
        return True

    with hooks.hooks_snapshot(clear=True):
        hooks.register(
            LedgerHooks(operation_summary=lambda s, c, i: None, cancel_operation=cancel_operation)
        )
        yield reasons


def test_ac_d7_cancelling_a_scheduled_item_cancels_it_and_its_job(env: Env) -> None:
    item = submittable_item(env)
    scheduled = submit(env, item, self_approve=True)
    assert scheduled.status_code == 200
    (job,) = jobs_for(env, item)
    assert job.status == "queued"

    response = cancel(env, item)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    env.session.refresh(job)
    env.session.refresh(item)
    assert job.status == "cancelled" and job.dedup_key == publish_job_key(item.id, 1)
    assert item.status == "cancelled"
    assert len(audit_for(env, item, "content.cancelled")) == 1
    # The job is a no-op if it had been claimed anyway: nothing is "scheduled" any more.
    assert item.status not in ("scheduled", "retry_scheduled")


@pytest.mark.invariant("INV-16")
def test_a_cancelled_item_can_no_longer_be_edited_submitted_or_cancelled_again(env: Env) -> None:
    item = submittable_item(env)
    submit(env, item, self_approve=True)
    cancel(env, item)
    edit = env.call(
        env.owner, "PATCH", f"{ITEMS}/{item.id}", json={"expected_version": 1, "caption": "x"}
    )
    assert edit.status_code == 409 and edit.json()["code"] == "CONFLICT_STATE"
    assert submit(env, item, self_approve=True).status_code == 409
    again = cancel(env, item)
    assert again.status_code == 409
    assert again.json()["code"] == "CONFLICT_STATE"


def test_cancelling_an_item_that_waits_for_approval_cancels_the_pending_approval(env: Env) -> None:
    item, approval = staff_submit(env)
    response = cancel(env, item, "manager")
    assert response.status_code == 200
    env.session.refresh(approval)
    env.session.refresh(item)
    assert (item.status, approval.status, approval.cancel_reason) == (
        "cancelled",
        "cancelled",
        "SUBJECT_CANCELLED",
    )
    late = decide(env, env.owner, approval)
    assert late.status_code == 409 and late.json()["code"] == "APPROVAL_ALREADY_DECIDED"
    assert jobs_for(env, item) == []


def test_an_approved_approval_stays_approved_after_the_cancel(env: Env) -> None:
    """An approval never leaves ``approved`` (session 4); the executor refuses by the item's
    status, which is ``cancelled``."""
    item = submittable_item(env)
    submit(env, item, self_approve=True)
    approval = env.session.get(Approval, item.approval_id)
    assert approval is not None
    cancel(env, item)
    env.session.refresh(approval)
    env.session.refresh(item)
    assert (approval.status, item.status) == ("approved", "cancelled")


@pytest.mark.parametrize("status", ["draft", "on_hold", "retry_scheduled"])
def test_draft_hold_and_retry_can_be_cancelled(env: Env, status: str) -> None:
    item = make_item(env, status=status)
    job = publish_job(env, item) if status != "draft" else None
    response = cancel(env, item)
    assert response.status_code == 200
    env.session.refresh(item)
    assert item.status == "cancelled"
    if job is not None:
        env.session.refresh(job)
        assert job.status == "cancelled"


@pytest.mark.parametrize("status", ["publishing", "published", "failed", "rejected"])
def test_publishing_and_finished_items_cannot_be_cancelled(env: Env, status: str) -> None:
    item = make_item(env, status=status)
    job = publish_job(env, item)
    response = cancel(env, item)
    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT_STATE"
    env.session.refresh(item)
    env.session.refresh(job)
    assert item.status == status and job.status == "queued"  # nothing was touched


def test_cancel_reaches_a_waiting_operation_through_the_ledger_hook(
    env: Env, cancelled_operations: list[str]
) -> None:
    item = make_item(env, status="retry_scheduled")
    publish_job(env, item)
    assert cancel(env, item).status_code == 200
    assert cancelled_operations == [f"{item.id}:SUBJECT_CANCELLED"]


def test_a_conflict_does_not_reach_the_ledger(env: Env, cancelled_operations: list[str]) -> None:
    item = make_item(env, status="publishing")
    assert cancel(env, item).status_code == 409
    assert cancelled_operations == []


def test_an_item_with_a_pending_approval_in_draft_state_cancels_cleanly(env: Env) -> None:
    item = make_item(env, status="pending_approval", caption="Taslak")
    approval = request_approval(env, item)
    cancel(env, item)
    env.session.refresh(approval)
    assert approval.status == "cancelled"


def test_staff_cannot_cancel(env: Env) -> None:
    item = make_item(env)
    response = cancel(env, item, "staff")
    assert response.status_code == 403
    env.session.refresh(item)
    assert item.status == "draft"


def test_cancelling_leaves_other_items_jobs_alone(env: Env) -> None:
    first, second = submittable_item(env), submittable_item(env)
    submit(env, first, LATER, self_approve=True)
    submit(env, second, {"local_date": "2026-01-15", "local_time": "20:00"}, self_approve=True)
    cancel(env, first)
    statuses = {j.dedup_key: j.status for j in env.session.scalars(select(Job))}
    assert statuses[publish_job_key(first.id, 1)] == "cancelled"
    assert statuses[publish_job_key(second.id, 1)] == "queued"
