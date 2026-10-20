"""AC-F3, AC-F4 and G11: an unknown outcome is reconciled through the container, never repeated
blindly (INV-05, INV-06; ADR-011)."""

from datetime import timedelta
from typing import Any

import pytest

from app.jobs.queue import enqueue
from app.operations.payloads import ReconcileStuckPayload
from tests.helpers.publishing import Crash, Publishing


def run_stuck_check(pub: Publishing) -> None:
    """Enqueue and run ``reconcile_stuck_operations`` the way the scheduler does."""
    enqueue(
        pub.session,
        "reconcile_stuck_operations",
        ReconcileStuckPayload(),
        workspace_id=None,
        correlation_id=None,
        clock=pub.clock,
    )
    pub.session.commit()
    pub.process()


@pytest.mark.invariant("INV-06")
def test_ac_f3_a_timeout_after_the_publish_is_reconciled_to_published_without_a_second_post(
    pub: Publishing,
) -> None:
    item = pub.scheduled()
    pub.fail("publish", "timeout_after_success")

    assert pub.process() == 1  # the publish: the post went out, the answer was lost

    row = pub.reload(item)
    op = pub.operation(item)
    assert row.status == "publishing" and op is not None  # shown as "checking"
    assert (op.status, op.last_error_code) == ("outcome_unknown", "OUTCOME_UNKNOWN")
    assert len(pub.posts()) == 1  # the remote effect already happened
    (check,) = pub.jobs("reconcile_publish")
    assert check.run_at == pub.clock.now() + timedelta(minutes=1)
    assert len(pub.audits("operation.outcome_unknown")) == 1
    assert pub.process() == 0  # not due: no blind retry in between

    pub.clock.advance(minutes=1)
    assert pub.process() == 1  # reconciliation reads the container: PUBLISHED

    row = pub.reload(item)
    op = pub.operation(item)
    (post,) = pub.posts()  # still exactly one
    assert row.status == "published" and op is not None and op.status == "succeeded"
    assert row.external_media_id == post.media_id and row.external_permalink == post.permalink
    assert op.result["resolved_by"] == "reconcile" and op.attempts == 1  # never published twice
    assert [j.status for j in pub.jobs("reconcile_publish")] == ["succeeded"]
    assert len(pub.containers()) == 1
    assert pub.owner_note("content.published").severity == "info"
    assert len(pub.audits("operation.reconciled")) == 1


@pytest.mark.invariant("INV-06")
def test_reconciling_again_changes_nothing(pub: Publishing) -> None:
    item = pub.scheduled()
    pub.fail("publish", "timeout_after_success")
    pub.execute(item)
    op = pub.operation(item)
    assert op is not None
    assert pub.reconcile(op).kind == "published"
    for _ in range(2):
        assert pub.reconcile(op).detail == "resolved"
    assert len(pub.posts()) == 1


@pytest.mark.invariant("INV-06")
def test_ac_f4_a_worker_killed_between_container_and_publish_publishes_once_with_the_stored_id(
    make_pub: Any,
) -> None:
    pub: Publishing = make_pub(sim_container_delay_seconds=2)
    item = pub.scheduled()

    def kill() -> None:
        raise Crash

    pub.before["get_container_status"] = kill  # right after the container id was committed
    with pytest.raises(Crash):
        pub.execute(item)

    row = pub.reload(item)
    op = pub.operation(item)
    (container,) = pub.containers()
    assert row.status == "publishing" and op is not None and op.status == "in_progress"
    assert op.provider_ref["container_id"] == container.container_id  # committed before the crash
    assert pub.posts() == []

    # Running the job again does not start a second attempt: the first may still be alive.
    pub.calls.clear()
    assert pub.execute(item).detail == "not_due:publishing"
    assert "create_media_container" not in pub.calls and pub.posts() == []

    # The stuck sweep notices after 15 minutes and hands it to reconciliation (G11).
    pub.clock.advance(minutes=14)
    run_stuck_check(pub)
    assert pub.operation(item).status == "in_progress"  # type: ignore[union-attr]
    pub.clock.advance(minutes=2)
    run_stuck_check(pub)
    op = pub.operation(item)
    assert op is not None and op.status == "outcome_unknown"
    assert pub.process() == 0  # the check is due in a minute

    pub.clock.advance(minutes=1)
    assert pub.process() == 1  # the container is FINISHED: proven unpublished, published now

    row = pub.reload(item)
    op = pub.operation(item)
    (post,) = pub.posts()
    assert row.status == "published" and op is not None and op.status == "succeeded"
    assert post.container_id == container.container_id  # the stored id, no second container
    assert len(pub.containers()) == 1
    assert op.attempts == 2


@pytest.mark.invariant("INV-06")
def test_a_worker_killed_after_the_publish_is_reconciled_to_published_not_published_again(
    pub: Publishing,
) -> None:
    item = pub.scheduled()

    def kill() -> None:
        raise Crash

    pub.before["get_media"] = kill  # the post is out; T3 never ran
    with pytest.raises(Crash):
        pub.execute(item)
    assert len(pub.posts()) == 1
    assert pub.reload(item).status == "publishing"

    pub.clock.advance(minutes=16)
    run_stuck_check(pub)
    pub.clock.advance(minutes=1)
    pub.process()

    row = pub.reload(item)
    (post,) = pub.posts()
    assert row.status == "published" and row.external_media_id == post.media_id
    assert row.external_permalink == post.permalink  # fetched through the container's media id
    assert len(pub.containers()) == 1


def test_a_container_that_is_still_processing_is_checked_again_until_it_is_ready(
    make_pub: Any,
) -> None:
    pub: Publishing = make_pub(sim_container_delay_seconds=1800)
    item = pub.scheduled()
    assert pub.execute(item).kind == "unknown"  # the polling budget (5 min) ran out

    pub.clock.advance(minutes=1)
    outcome = pub.reconcile(pub.operation(item))  # type: ignore[arg-type]
    assert outcome.kind == "rescheduled" and outcome.run_at == pub.clock.now() + timedelta(
        minutes=1
    )
    assert pub.posts() == []

    pub.advance_to(pub.clock.now() + timedelta(minutes=30))
    outcome = pub.reconcile(pub.operation(item))  # type: ignore[arg-type]
    assert outcome.kind == "published"  # FINISHED: published in the same run
    assert len(pub.posts()) == 1 and len(pub.containers()) == 1


def test_the_reconcile_job_looks_again_on_the_same_row(make_pub: Any) -> None:
    pub: Publishing = make_pub(sim_container_delay_seconds=1800)
    item = pub.scheduled()
    pub.execute(item)
    pub.clock.advance(minutes=1)
    pub.process()  # (the publish job, queued by the schedule, finds the item publishing)
    (check,) = pub.jobs("reconcile_publish")
    assert check.status == "queued" and check.attempts == 0  # RescheduleJob spends no attempt
    assert check.run_at == pub.clock.now() + timedelta(minutes=1)
    assert pub.posts() == []


def test_an_error_status_found_by_reconciliation_fails_the_item_as_media_rejected(
    make_pub: Any,
) -> None:
    pub: Publishing = make_pub(sim_container_delay_seconds=1800)
    item = pub.scheduled()
    pub.execute(item)
    pub.fail("container_status", "invalid_media")
    pub.clock.advance(minutes=1)
    outcome = pub.reconcile(pub.operation(item))  # type: ignore[arg-type]
    assert (outcome.kind, outcome.error_code) == ("failed", "MEDIA_REJECTED")
    assert pub.reload(item).status == "failed" and pub.posts() == []
    assert pub.owner_note("content.failed").params["reason"] == "MEDIA_REJECTED"


def test_a_container_that_never_finishes_ends_at_the_deadline(make_pub: Any) -> None:
    pub: Publishing = make_pub(sim_container_delay_seconds=86_400)
    item = pub.scheduled()
    pub.execute(item)
    pub.clock.advance(minutes=361)
    outcome = pub.reconcile(pub.operation(item))  # type: ignore[arg-type]
    assert (outcome.kind, outcome.error_code) == ("failed", "PUBLISH_DEADLINE_PASSED")
    assert pub.reload(item).status == "failed" and pub.posts() == []


def test_an_unreadable_container_past_the_deadline_is_reported_as_unconfirmed(
    pub: Publishing,
) -> None:
    item = pub.scheduled()
    pub.fail("publish", "timeout_after_success")
    pub.execute(item)
    pub.fail("container_status", "transient", remaining=None)
    pub.clock.advance(minutes=1)
    assert pub.reconcile(pub.operation(item)).kind == "rescheduled"  # type: ignore[arg-type]
    pub.clock.advance(minutes=400)
    outcome = pub.reconcile(pub.operation(item))  # type: ignore[arg-type]
    assert (outcome.kind, outcome.error_code) == ("failed", "OUTCOME_UNCONFIRMED")
    assert pub.reload(item).last_error_code == "OUTCOME_UNCONFIRMED"
    assert len(pub.posts()) == 1  # it is out; we only could not confirm it, and never repeat it


def test_the_stuck_sweep_leaves_a_finished_publish_alone(pub: Publishing) -> None:
    """G11: only an operation that is still in_progress is touched."""
    item = pub.scheduled()
    pub.execute(item)  # succeeded: not stuck
    pub.clock.advance(hours=1)
    run_stuck_check(pub)
    assert pub.reload(item).status == "published" and len(pub.posts()) == 1
