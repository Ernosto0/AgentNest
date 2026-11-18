"""Offline Reel ledger publishing via poll_reel_container backoff jobs."""

from datetime import timedelta

import pytest
from sqlalchemy import delete, update

from app.integrations.instagram.errors import ProviderOutcomeUnknown
from app.integrations.instagram.models import SimContainer
from app.jobs.models import Job
from app.operations import publish
from app.operations.jobs import STUCK_AFTER


def _start_reel(pub, item):
    """Run execute_publish directly and mark the queued publish_content job consumed."""
    outcome = pub.execute(item)
    if outcome.kind != "retry":
        pub.session.execute(
            delete(Job).where(
                Job.workspace_id == pub.workspace.id,
                Job.job_type == "publish_content",
                Job.status == "queued",
            )
        )
        pub.session.commit()
    return outcome


def assert_reel_published(pub, item, *, containers=1):
    assert pub.reload(item).status == "published"
    op = pub.operation(item)
    assert op is not None and op.status == "succeeded"
    assert op.next_attempt_at is None
    assert "phase" not in op.provider_ref
    assert len(pub.posts()) == 1
    assert len(pub.containers()) == containers
    container = pub.containers()[-1]
    assert container.media_type == "REELS"
    assert (
        pub.provider.get_publishing_quota(publish.account_ref(pub.account, pub.settings)).used == 1
    )


def test_slow_processing_polls_at_exact_backoff_intervals_without_sleeping(make_pub, monkeypatch):
    pub = make_pub(sim_reel_processing_seconds=100)
    monkeypatch.setattr(publish, "get_provider", lambda *_, **__: pub.provider)
    cover = pub.media((1080, 1920))
    item = pub.reel(cover=cover, share_to_feed=False)
    t0 = pub.clock.now()

    outcome = _start_reel(pub, item)
    assert outcome.kind == "processing"
    assert outcome.run_at == t0 + timedelta(seconds=15)
    assert pub.sleeps == []
    assert pub.calls == ["get_publishing_quota", "create_media_container"]

    op = pub.operation(item)
    assert op is not None and op.status == "in_progress"
    assert op.next_attempt_at == t0 + timedelta(seconds=15)
    assert op.provider_ref["phase"] == "processing"
    assert op.provider_ref["polls"] == 0
    assert pub.reload(item).status == "publishing"

    # Poll 1 at +15 s -> IN_PROGRESS -> next check at +45 s (+30 s)
    pub.clock.advance(seconds=14)
    assert pub.process() == 0
    pub.clock.advance(seconds=1)
    assert pub.process() == 1
    op = pub.operation(item)
    assert op is not None and op.status == "in_progress"
    assert op.provider_ref["polls"] == 1
    assert op.next_attempt_at == t0 + timedelta(seconds=45)
    assert op.started_at == t0 + timedelta(seconds=15)

    # Poll 2 at +45 s -> IN_PROGRESS -> next check at +105 s (+60 s)
    pub.clock.advance(seconds=30)
    assert pub.process() == 1
    op = pub.operation(item)
    assert op is not None and op.provider_ref["polls"] == 2
    assert op.next_attempt_at == t0 + timedelta(seconds=105)
    assert op.started_at == t0 + timedelta(seconds=45)

    # Poll 3 at +105 s -> container finished (delay 100 s <= 105 s) -> publishes once
    pub.clock.advance(seconds=60)
    assert pub.process() == 1
    assert_reel_published(pub, item)
    assert pub.calls.count("publish_container") == 1
    assert pub.sleeps == []


def test_healthy_processing_survives_stuck_sweep_and_times_out_at_30_minutes(make_pub):
    pub = make_pub(sim_reel_processing_seconds=2000)
    item = pub.reel(thumb_offset_ms=2000)
    assert _start_reel(pub, item).kind == "processing"

    # Every poll interval is below STUCK_AFTER and refreshes started_at
    for step in (15, 30, 60, 60, 120, 120, 180, 180, 300):
        pub.clock.advance(seconds=step)
        assert pub.process() == 1
        op = pub.operation(item)
        assert op is not None and op.status == "in_progress"
        assert pub.clock.now() - op.started_at < STUCK_AFTER

    # Advance past REEL_PROCESSING_TIMEOUT (30 min from creation)
    while pub.reload(item).status == "publishing":
        op = pub.operation(item)
        assert op is not None and op.next_attempt_at is not None
        pub.advance_past(op.next_attempt_at)
        pub.process()

    assert pub.reload(item).status == "failed"
    assert pub.reload(item).last_error_code == "REEL_PROCESSING_TIMEOUT"
    assert pub.operation(item).status == "failed"
    assert pub.posts() == []


def test_published_during_poll_finishes_without_second_publish(pub, monkeypatch):
    monkeypatch.setattr(publish, "get_provider", lambda *_, **__: pub.provider)
    item = pub.reel()
    assert _start_reel(pub, item).kind == "processing"
    op = pub.operation(item)
    assert op is not None
    # Simulate container already published remotely before poll runs
    container = pub.containers()[0]
    pub.provider.publish_container(
        publish.account_ref(pub.account, pub.settings), container.container_id
    )
    calls_before = pub.calls.count("publish_container")

    pub.advance_past(op.next_attempt_at)
    assert pub.process() == 1
    assert pub.calls.count("publish_container") == calls_before
    assert_reel_published(pub, item)


@pytest.mark.parametrize("subcode", [2207026, None])
def test_non_retryable_processing_error_fails_with_subcode_and_never_publishes(
    make_pub, subcode, monkeypatch
):
    pub = make_pub(sim_reel_processing_seconds=10)
    monkeypatch.setattr(publish, "get_provider", lambda *_, **__: pub.provider)
    item = pub.reel()
    pub.fail("create_reel_container", "processing_error", delay_s=10, error_subcode=subcode)
    assert _start_reel(pub, item).kind == "processing"
    op = pub.operation(item)
    assert op is not None
    pub.advance_past(op.next_attempt_at)
    assert pub.process() == 1

    assert pub.reload(item).status == "failed"
    assert pub.reload(item).last_error_code == "MEDIA_REJECTED"
    op = pub.operation(item)
    assert op is not None and op.status == "failed"
    assert op.last_error_detail == (
        f"SUBCODE_{subcode}" if subcode is not None else "simulated media processing error"
    )
    assert pub.posts() == []
    assert pub.calls.count("publish_container") == 0
    assert pub.owner_note("content.failed") is not None


@pytest.mark.parametrize("subcode", [2207003, 2207032, 2207053])
def test_retryable_subcodes_recreate_container_up_to_cap(make_pub, subcode):
    pub = make_pub(sim_reel_processing_seconds=10)
    item = pub.reel()
    pub.fail("create_reel_container", "processing_error", delay_s=10, error_subcode=subcode)
    pub.fail("create_reel_container", "processing_error", delay_s=10, error_subcode=subcode)
    assert _start_reel(pub, item).kind == "processing"

    for _ in range(3):
        op = pub.operation(item)
        assert op is not None and op.next_attempt_at is not None
        pub.advance_past(op.next_attempt_at)
        pub.process()

    assert_reel_published(pub, item, containers=3)
    assert pub.operation(item).provider_ref["recreations"] == 2

    # 3rd recreation exceeds cap -> fails PROVIDER_UNAVAILABLE
    item2 = pub.reel()
    for _ in range(3):
        pub.fail("create_reel_container", "processing_error", delay_s=10, error_subcode=subcode)
    assert _start_reel(pub, item2).kind == "processing"
    for _ in range(4):
        op2 = pub.operation(item2)
        if op2 is None or op2.status != "in_progress":
            break
        pub.advance_past(op2.next_attempt_at)
        pub.process()
    assert pub.reload(item2).status == "failed"
    assert pub.reload(item2).last_error_code == "PROVIDER_UNAVAILABLE"


def test_expired_container_recreates_once(make_pub):
    pub = make_pub(sim_reel_processing_seconds=10)
    item = pub.reel()
    assert _start_reel(pub, item).kind == "processing"
    pub.session.execute(
        update(SimContainer)
        .where(SimContainer.workspace_id == pub.workspace.id)
        .values(expires_at=pub.clock.now() + timedelta(seconds=5))
    )
    pub.session.commit()
    pub.clock.advance(seconds=15)
    assert pub.process() == 1
    assert pub.reload(item).status == "publishing"
    assert len(pub.containers()) == 2
    op = pub.operation(item)
    assert op is not None and op.next_attempt_at is not None
    pub.advance_past(op.next_attempt_at)
    assert pub.process() == 1
    assert_reel_published(pub, item, containers=2)


def test_read_failures_reschedule_without_attempt_and_hand_over_after_five(make_pub):
    pub = make_pub(sim_reel_processing_seconds=10)
    item = pub.reel()
    assert _start_reel(pub, item).kind == "processing"
    pub.fail("container_status", "rate_limited", retry_after=90, remaining=4)
    op = pub.operation(item)
    assert op is not None
    attempts_before = op.attempts

    for _ in range(4):
        pub.advance_past(pub.operation(item).next_attempt_at)
        assert pub.process() == 1
    op = pub.operation(item)
    assert op is not None and op.status == "in_progress"
    assert op.attempts == attempts_before
    assert op.provider_ref["read_failures"] == 4

    # 5th read failure hands over through _record_error(..., "status")
    pub.fail("container_status", "transient", remaining=1)
    pub.advance_past(op.next_attempt_at)
    assert pub.process() == 1
    assert pub.reload(item).status == "retry_scheduled"
    op = pub.operation(item)
    assert op is not None and op.status == "retry_wait"

    pub.advance_past(op.next_attempt_at)
    assert pub.process() == 1
    assert_reel_published(pub, item)


def test_auth_error_on_poll_holds_item_and_rerun_while_processing_skips(make_pub):
    pub = make_pub(sim_reel_processing_seconds=10)
    item = pub.reel()
    assert _start_reel(pub, item).kind == "processing"
    assert pub.execute(item).kind == "skipped"

    pub.fail("container_status", "auth_revoked")
    op = pub.operation(item)
    assert op is not None
    pub.advance_past(op.next_attempt_at)
    assert pub.process() == 1
    assert pub.reload(item).status == "on_hold"
    assert pub.account_now().status == "needs_reauth"


def test_ambiguous_publish_and_lost_create_and_deadline_and_quota(make_pub, monkeypatch):
    pub = make_pub(sim_reel_processing_seconds=10)
    monkeypatch.setattr(publish, "get_provider", lambda *_, **__: pub.provider)
    # 1. Lost create answer retries safely
    item1 = pub.reel()
    pub.fail("create_reel_container", "timeout_after_success")
    assert pub.execute(item1).kind == "retry"
    assert pub.posts() == []
    pub.advance_past(pub.operation(item1).next_attempt_at)
    assert pub.process() == 1
    assert pub.reload(item1).status == "publishing"
    pub.advance_past(pub.operation(item1).next_attempt_at)
    assert pub.process() == 1
    assert_reel_published(pub, item1, containers=2)

    # 2. Ambiguous publish reconciles without second publish
    item2 = pub.reel()
    assert _start_reel(pub, item2).kind == "processing"
    pub.fail("publish", "timeout_after_success")
    pub.advance_past(pub.operation(item2).next_attempt_at)
    assert pub.process() == 1
    op2 = pub.operation(item2)
    assert op2 is not None and op2.status == "outcome_unknown"
    pub.clock.advance(minutes=1, seconds=1)
    assert pub.process() == 1
    assert pub.reload(item2).status == "published"
    assert len(pub.posts()) == 2
    assert pub.calls.count("publish_container") == 2

    # 3. Deadline passed while processing fails safely
    pub.set_max_delay(2)
    item3 = pub.reel()
    assert _start_reel(pub, item3).kind == "processing"
    op3 = pub.operation(item3)
    assert op3 is not None and op3.deadline_at is not None
    pub.advance_to(op3.deadline_at + timedelta(seconds=1))
    assert pub.process() == 1
    assert pub.reload(item3).status == "failed"
    assert pub.reload(item3).last_error_code == "PUBLISH_DEADLINE_PASSED"

    # 4. Poll executed twice sequentially yields one post
    item4 = pub.reel()
    assert _start_reel(pub, item4).kind == "processing"
    op4 = pub.operation(item4)
    assert op4 is not None
    pub.clock.advance(seconds=15)
    assert pub.poll_reel(op4).kind == "published"
    assert pub.poll_reel(op4).kind == "skipped"
    assert len(pub.posts()) == 3
    assert ProviderOutcomeUnknown is not None


def test_reconcile_reel_retryable_error_increments_recreations_and_enforces_cap(
    make_pub, monkeypatch
):
    pub = make_pub(sim_reel_processing_seconds=10)
    monkeypatch.setattr(publish, "get_provider", lambda *_, **__: pub.provider)
    item = pub.reel()
    pub.fail(
        "create_reel_container",
        "processing_error",
        error_subcode=2207032,
        remaining=3,
    )
    assert _start_reel(pub, item).kind == "processing"
    op = pub.operation(item)
    assert op is not None

    # Move operation to outcome_unknown (as after restore or stuck-worker sweep) twice;
    # each reconcile recreates the container and increments recreations (1, then 2).
    for expected_recreations in (1, 2):
        pub.clock.advance(seconds=10)
        op = pub.operation(item)
        assert op is not None
        op.status = "outcome_unknown"
        pub.session.flush()
        assert pub.poll_reel(op).kind == "skipped"
        outcome = pub.reconcile(op)
        assert outcome.kind == "processing"
        op_after = pub.operation(item)
        assert op_after is not None and op_after.status == "in_progress"
        assert op_after.provider_ref["recreations"] == expected_recreations

    # Third reconcile encounters a 3rd retryable error and hits MAX_CONTAINER_RECREATIONS (2).
    pub.clock.advance(seconds=10)
    op = pub.operation(item)
    assert op is not None
    op.status = "outcome_unknown"
    pub.session.flush()
    outcome = pub.reconcile(op)
    assert outcome.kind == "failed"
    assert outcome.error_code == "PROVIDER_UNAVAILABLE"
    assert pub.reload(item).status == "failed"
    assert pub.reload(item).last_error_code == "PROVIDER_UNAVAILABLE"
