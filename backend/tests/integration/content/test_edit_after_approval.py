"""AC-D6: editing an item after it was submitted or approved returns it to ``draft`` and takes
the old version out of play (INV-16): the approval can no longer authorise anything and the
queued publish job of the old version is cancelled."""

from collections.abc import Iterator

import pytest
from sqlalchemy import select

from app.approvals import callbacks
from app.approvals import service as approvals_service
from app.approvals.models import Approval
from app.audit.models import AuditLog
from app.content import hooks
from app.content.hooks import NO_LEDGER
from app.content.models import ContentItem
from app.content.payload import publish_job_key
from app.core.errors import AppError
from app.jobs.models import Job
from tests.helpers.content import make_item as make
from tests.helpers.content import publish_job, request_approval
from tests.helpers.env import Env

ITEMS = "/content-items"


@pytest.fixture(autouse=True)
def content_subject() -> Iterator[None]:
    """The approval subject of content (registered by P5-04): it reports the item's version, so
    a decision can be taken. Its decided-callback does nothing; the test sets the status."""
    with callbacks.callbacks_snapshot(clear=True):
        callbacks.register(
            "content_item",
            lambda session, clock, ctx, approval: None,
            current_version=lambda session, ctx, item_id: (
                None if (item := session.get(ContentItem, item_id)) is None else item.version
            ),
            status_of=lambda session, ctx, item_id: None,
        )
        yield


def edit(env: Env, item: ContentItem, **body: object):  # type: ignore[no-untyped-def]
    return env.call(
        env.owner, "PATCH", f"{ITEMS}/{item.id}", json={"expected_version": item.version, **body}
    )


def approved_and_scheduled(env: Env) -> tuple[ContentItem, Approval, Job]:
    """What a submit would leave behind: a scheduled item, its approved approval and its job."""
    item = make(env, status="pending_approval", caption="Cuma günü görüşürüz")
    approval = request_approval(env, item)
    approvals_service.decide(
        env.session,
        env.clock,
        env.ctx(env.owner),
        approval.id,
        decision="approve",
        payload_hash=approval.payload_hash,
    )
    item.status = "scheduled"  # the subject callback (P5-04) does this; set up directly here
    job = publish_job(env, item)
    env.session.flush()
    return item, approval, job


@pytest.mark.invariant("INV-16")
def test_editing_a_scheduled_item_returns_it_to_draft_and_voids_the_approval(env: Env) -> None:
    item, approval, job = approved_and_scheduled(env)
    assert (item.status, approval.status, job.status) == ("scheduled", "approved", "queued")

    response = edit(env, item, caption="Cumartesi günü görüşürüz")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["version"]) == ("draft", 2)
    assert body["scheduled_at"] is None

    # The job of the old version will never run ...
    env.session.refresh(job)
    assert job.status == "cancelled"
    assert job.dedup_key == publish_job_key(item.id, 1)
    # ... and the approval, bound to version 1, authorises nothing for version 2.
    with pytest.raises(AppError) as error:
        approvals_service.assert_executable(
            env.session, env.clock, env.ctx(env.owner), approval.id, item.version
        )
    assert error.value.code == "APPROVAL_STALE"
    assert (
        body["approval"]["subject_version"],
        body["approval"]["status"],
    ) == (1, "approved")  # the staff view shows it was bound to the old version


@pytest.mark.invariant("INV-16")
def test_editing_an_item_that_waits_for_approval_cancels_its_pending_approval(env: Env) -> None:
    item = make(env, status="pending_approval", caption="Taslak")
    approval = request_approval(env, item)

    response = edit(env, item, caption="Yeni taslak")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "draft"
    env.session.refresh(approval)
    assert (approval.status, approval.cancel_reason) == ("cancelled", "SUBJECT_EDITED")
    assert response.json()["approval"]["status"] == "cancelled"
    # Nobody can approve it any more.
    with pytest.raises(AppError) as error:
        approvals_service.decide(
            env.session,
            env.clock,
            env.ctx(env.owner),
            approval.id,
            decision="approve",
            payload_hash=approval.payload_hash,
        )
    assert error.value.code == "APPROVAL_ALREADY_DECIDED"
    actions = [
        a.action
        for a in env.session.scalars(select(AuditLog).where(AuditLog.resource_id == item.id))
    ]
    assert "content.updated" in actions
    assert "approval.cancelled" in [
        a.action
        for a in env.session.scalars(select(AuditLog).where(AuditLog.resource_id == approval.id))
    ]


def test_an_on_hold_item_that_is_edited_keeps_no_job_and_no_hold(env: Env) -> None:
    item = make(env, status="on_hold", caption="Eski", hold_reason="FACT_CHANGED")
    job = publish_job(env, item)

    response = edit(env, item, caption="Yeni")

    assert (response.json()["status"], response.json()["hold_reason"]) == ("draft", None)
    env.session.refresh(job)
    assert job.status == "cancelled"


def test_only_the_job_of_the_edited_version_is_cancelled(env: Env) -> None:
    item, _approval, job = approved_and_scheduled(env)
    other = make(env, status="scheduled", caption="Başka bir gönderi")
    other_job = publish_job(env, other)

    assert edit(env, item, caption="Yeni").status_code == 200

    env.session.refresh(job)
    env.session.refresh(other_job)
    assert (job.status, other_job.status) == ("cancelled", "queued")


def test_a_running_publish_job_is_left_to_re_check_the_state(env: Env) -> None:
    """A job that is already running is not touched: it re-checks status and version itself."""
    item, _approval, job = approved_and_scheduled(env)
    job.status = "running"
    env.session.flush()

    assert edit(env, item, caption="Yeni").status_code == 200

    env.session.refresh(job)
    assert job.status == "running"


def test_a_title_only_edit_leaves_the_approval_and_the_job_alone(env: Env) -> None:
    item, approval, job = approved_and_scheduled(env)

    body = edit(env, item, title="Yeni iç başlık").json()

    assert (body["status"], body["version"]) == ("scheduled", 1)
    env.session.refresh(approval)
    env.session.refresh(job)
    assert (approval.status, job.status) == ("approved", "queued")


def test_a_failed_edit_leaves_the_approval_and_the_job_alone(env: Env) -> None:
    """A stale version is refused before anything is cancelled."""
    item, approval, job = approved_and_scheduled(env)
    response = env.call(
        env.owner,
        "PATCH",
        f"{ITEMS}/{item.id}",
        json={"expected_version": 7, "caption": "Yeni"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "VERSION_CONFLICT"
    env.session.refresh(approval)
    env.session.refresh(job)
    env.session.refresh(item)
    assert (item.status, approval.status, job.status) == ("scheduled", "approved", "queued")


# --- the ledger hook (skeleton) -------------------------------------------------------------


def test_without_a_registered_ledger_the_item_has_no_operation(env: Env) -> None:
    item = make(env, status="scheduled")
    with hooks.hooks_snapshot(clear=True):  # the operations module registers its hooks at startup
        assert hooks.get() is NO_LEDGER
        assert env.call(env.owner, "GET", f"{ITEMS}/{item.id}").json()["operation"] is None


def test_a_registered_ledger_hook_supplies_the_operation_summary(env: Env) -> None:
    item = make(env, status="retry_scheduled")
    startup = hooks.get()
    summary = hooks.OperationSummary(
        status="retry_wait", attempts=2, next_attempt_at=env.clock.now(), last_error_code="X"
    )
    with hooks.hooks_snapshot(clear=True):
        hooks.register(
            hooks.LedgerHooks(
                operation_summary=lambda session, ctx, it: summary if it.id == item.id else None,
                cancel_operation=NO_LEDGER.cancel_operation,
            )
        )
        with pytest.raises(ValueError, match="already registered"):
            hooks.register(NO_LEDGER)
        body = env.call(env.owner, "GET", f"{ITEMS}/{item.id}").json()
    assert body["operation"]["status"] == "retry_wait"
    assert body["operation"]["attempts"] == 2
    assert hooks.get() is startup  # restored
