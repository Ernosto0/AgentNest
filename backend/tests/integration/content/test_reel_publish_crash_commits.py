"""Crash safety and concurrent poll idempotency on real commits for Reels."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import delete

from app.jobs.models import Job
from app.operations import publish
from app.operations.jobs import poll_reel_container
from app.operations.payloads import PollReelContainerPayload
from tests.helpers.publishing import Crash
from tests.integration.content.test_publish_crash_commits import fresh_state, pub, sweep

__all__ = ["pub"]
pytestmark = [pytest.mark.commits, pytest.mark.invariant("INV-06")]


def test_crash_after_create_before_t2_creates_fresh_container_on_reconcile(
    pub, session_factory, monkeypatch
):
    item = pub.reel()
    monkeypatch.setattr(
        publish, "_store_reel_processing", lambda *_, **__: (_ for _ in ()).throw(Crash())
    )
    with pytest.raises(Crash):
        pub.execute(item)
    row, op, containers, posts = fresh_state(session_factory, item.id)
    assert op is not None and op.status == "in_progress"
    assert op.provider_ref == {}
    assert len(containers) == 1 and len(posts) == 0

    monkeypatch.undo()
    pub.clock.advance(minutes=16)
    sweep(pub)
    pub.clock.advance(minutes=1)
    assert pub.reconcile(pub.operation(item)).kind == "processing"
    pub.advance_past(pub.operation(item).next_attempt_at)
    pub.process()
    row, op, containers, posts = fresh_state(session_factory, item.id)
    assert row.status == "published" and op is not None and op.status == "succeeded"
    assert len(posts) == 1 and len(containers) == 2


def test_crash_after_t2_and_after_publish_both_settle_once(pub, session_factory, monkeypatch):
    # 1. Crash immediately after T2: container and poll job are both durable
    item = pub.reel()
    pub.execute(item)
    row, op, containers, posts = fresh_state(session_factory, item.id)
    assert op is not None and op.status == "in_progress"
    assert op.provider_ref["phase"] == "processing"
    assert len(pub.jobs("poll_reel_container")) == 1
    assert len(posts) == 0

    # New worker advances and crashes right after publish_container before _finish commits
    monkeypatch.setattr(publish, "_finish", lambda *_, **__: (_ for _ in ()).throw(Crash()))
    pub.advance_past(op.next_attempt_at)
    with pytest.raises(Crash):
        pub.poll_reel(op)
    _, op_mid, _, posts_mid = fresh_state(session_factory, item.id)
    assert len(posts_mid) == 1 and op_mid is not None and op_mid.status == "in_progress"

    # Stuck sweep moves to outcome_unknown; a late poll is a no-op; reconcile reads PUBLISHED
    monkeypatch.undo()
    pub.session.execute(
        delete(Job).where(
            Job.workspace_id == pub.workspace.id,
            Job.job_type.in_(("publish_content", "poll_reel_container")),
            Job.status == "queued",
        )
    )
    pub.session.commit()
    pub.clock.advance(minutes=16)
    sweep(pub)
    _, fenced_op, _, _ = fresh_state(session_factory, item.id)
    assert fenced_op is not None and fenced_op.status == "outcome_unknown"
    assert pub.poll_reel(fenced_op).kind == "skipped"
    pub.clock.advance(minutes=1)
    assert pub.reconcile(fenced_op).kind == "published"
    row, op_done, containers_done, posts_done = fresh_state(session_factory, item.id)
    assert row.status == "published" and op_done is not None and op_done.status == "succeeded"
    assert len(posts_done) == 1 and len(containers_done) == 1
    assert poll_reel_container is not None and PollReelContainerPayload is not None


def test_two_concurrent_polls_publish_at_most_once(pub, session_factory):
    item = pub.reel()
    assert pub.execute(item).kind == "processing"
    op = pub.operation(item)
    assert op is not None
    pub.clock.advance(seconds=15)

    def run_once():
        return publish.poll_reel(
            session_factory,
            pub.clock,
            pub.settings,
            pub.workspace.id,
            op.id,
        ).kind

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(run_once)
        f2 = pool.submit(run_once)
        outcomes = {f1.result(), f2.result()}

    assert "published" in outcomes
    row, op_after, _, posts = fresh_state(session_factory, item.id)
    assert row.status == "published" and op_after is not None and op_after.status == "succeeded"
    assert len(posts) == 1
