"""AC-F1, AC-F2: retryable provider errors retry the same job row with backoff (plan.md G10)."""

from datetime import timedelta

import pytest

from tests.helpers.env import Env
from tests.helpers.publishing import Publishing

ITEMS = "/content-items"


@pytest.mark.invariant("INV-06")
def test_ac_f1_transient_twice_retries_with_backoff_and_publishes_once_on_the_third_attempt(
    pub: Publishing, env: Env
) -> None:
    item = pub.scheduled()
    pub.fail("publish", "transient", remaining=2)

    assert pub.process() == 1  # attempt 1
    row = pub.reload(item)
    op = pub.operation(item)
    assert op is not None and row.status == "retry_scheduled"
    assert (op.status, op.attempts, op.last_error_code) == ("retry_wait", 1, "PROVIDER_UNAVAILABLE")
    assert op.next_attempt_at == pub.clock.now() + timedelta(minutes=1)
    (job,) = pub.jobs("publish_content")
    assert (job.status, job.run_at, job.attempts) == ("queued", op.next_attempt_at, 1)
    assert pub.process() == 0  # not due yet
    assert pub.posts() == []

    pub.clock.advance(minutes=1)
    assert pub.process() == 1  # attempt 2
    op = pub.operation(item)
    assert op is not None and (op.status, op.attempts) == ("retry_wait", 2)
    assert op.next_attempt_at == pub.clock.now() + timedelta(minutes=5)
    assert pub.reload(item).status == "retry_scheduled" and pub.posts() == []

    pub.clock.advance(minutes=5)
    assert pub.process() == 1  # attempt 3
    item = pub.reload(item)
    op = pub.operation(item)
    assert item.status == "published" and op is not None
    assert (op.status, op.attempts) == ("succeeded", 3)
    assert len(pub.posts()) == 1  # exactly one publication
    assert len(pub.containers()) == 1  # the container made on attempt 1 was reused
    assert [j.status for j in pub.jobs("publish_content")] == ["succeeded"]  # the same row
    assert pub.account_now().consecutive_failures == 0  # a success resets the counter
    assert len(pub.audits("content.retry_scheduled")) == 2
    assert pub.notifications("content.failed") == []
    assert len(pub.notifications("content.published")) >= 1


def test_the_retry_is_visible_in_the_api_with_its_next_attempt_time(
    pub: Publishing, env: Env
) -> None:
    item = pub.scheduled()
    pub.fail("create_container", "transient")
    pub.process()
    pub.session.expire_all()
    body = env.call(env.owner, "GET", f"{ITEMS}/{item.id}").json()
    assert body["status"] == "retry_scheduled"
    assert body["operation"]["status"] == "retry_wait"
    assert body["operation"]["next_attempt_at"] is not None
    assert pub.containers() == [] and pub.posts() == []


@pytest.mark.invariant("INV-06")
def test_ac_f2_transient_always_ends_failed_after_the_attempts_and_notifies(
    pub: Publishing,
) -> None:
    item = pub.scheduled()
    pub.fail("publish", "transient", remaining=None)

    backoffs = [1, 5, 15, 30]
    for minutes in backoffs:
        assert pub.process() == 1
        assert pub.reload(item).status == "retry_scheduled"
        pub.clock.advance(minutes=minutes)
    assert pub.process() == 1  # attempt 5

    item = pub.reload(item)
    op = pub.operation(item)
    assert item.status == "failed" and item.last_error_code == "PROVIDER_UNAVAILABLE"
    assert op is not None and (op.status, op.attempts) == ("failed", 5)
    assert op.last_error_code == "PROVIDER_UNAVAILABLE"
    assert pub.owner_note("content.failed").params["reason"] == "PROVIDER_UNAVAILABLE"
    assert pub.posts() == []
    assert [j.status for j in pub.jobs("publish_content")] == ["succeeded"]
    assert pub.account_now().consecutive_failures == 5


def test_a_retry_after_beyond_the_deadline_fails_at_once(pub: Publishing) -> None:
    item = pub.scheduled()
    pub.fail("publish", "rate_limited", retry_after=25 * 3600)  # the deadline is 24 h away
    outcome = pub.execute(item)
    assert (outcome.kind, outcome.error_code) == ("failed", "PROVIDER_RATE_LIMITED")
    row = pub.reload(item)
    assert row.status == "failed" and pub.posts() == []
    assert pub.account_now().consecutive_failures == 0  # a rate limit is not a health failure


def test_a_larger_retry_after_wins_over_the_backoff(pub: Publishing) -> None:
    item = pub.scheduled()
    pub.fail("publish", "rate_limited", retry_after=600)
    outcome = pub.execute(item)
    assert (outcome.kind, outcome.retry_after_seconds) == ("retry", 600.0)


@pytest.mark.invariant("INV-06")
def test_a_container_that_expired_between_attempts_is_replaced(pub: Publishing) -> None:
    item = pub.scheduled()
    pub.fail("publish", "transient")
    pub.execute(item)
    (first,) = pub.containers()
    first.expires_at = pub.clock.now() - timedelta(seconds=1)  # the provider let it expire
    pub.session.commit()
    pub.clock.advance(minutes=1)

    assert pub.process() == 1

    assert pub.reload(item).status == "published"
    containers = pub.containers()
    assert len(containers) == 2  # the old one was never published, a new one was made
    (post,) = pub.posts()
    assert post.container_id == containers[1].container_id != first.container_id
    op = pub.operation(item)
    assert op is not None and op.provider_ref["container_id"] == post.container_id


def test_cancelling_while_a_retry_is_waiting_cancels_the_operation_and_the_job(
    pub: Publishing, env: Env
) -> None:
    item = pub.scheduled()
    pub.fail("publish", "transient")
    pub.process()
    pub.session.expire_all()

    response = env.call(env.owner, "POST", f"{ITEMS}/{item.id}/cancel")

    assert response.status_code == 200, response.text
    op = pub.operation(item)
    assert op is not None and op.status == "cancelled"
    assert [j.status for j in pub.jobs("publish_content")] == ["cancelled"]
    pub.clock.advance(hours=1)
    assert pub.process() == 0
    assert pub.reload(item).status == "cancelled" and pub.posts() == []
    # And a job that was already running when the cancel came does nothing either.
    assert pub.execute(item).detail == "not_due:cancelled"
    assert pub.posts() == []
