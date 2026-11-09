"""Today counts, coverage and ingestion against migrated PostgreSQL."""

import uuid
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from app.comments.models import PublicComment, PublicMedia, PublicThread
from app.content.models import ContentItem
from app.core.errors import AppError
from app.insights import jobs, service
from app.insights.models import AccountInsightDaily
from app.integrations.instagram.models import SocialAccount
from app.jobs import run_due_jobs
from app.jobs.models import Job
from app.jobs.registry import JobContext
from app.jobs.scheduler import periodic_snapshot, register_periodic, scheduler_tick
from app.operations.models import Operation
from app.reporting.home import attention_counts
from tests.factories import (
    create_user,
    create_workspace,
    knowledge_ctx,
    login,
    workspace_with_members,
)


def world(db, clock):
    ws = create_workspace(db)
    user = create_user(db)
    account = SocialAccount(
        workspace_id=ws.id,
        platform="instagram",
        provider_kind="mock",
        external_account_id=str(uuid.uuid4()),
        username="today",
        status="connected",
        capabilities={},
        granted_scopes=[],
    )
    db.add(account)
    db.flush()
    return ws, user, account, knowledge_ctx(ws, user, "owner")


def public_comments(db, clock, ws, account, count):
    media = PublicMedia(
        workspace_id=ws.id,
        social_account_id=account.id,
        external_id=str(uuid.uuid4()),
        state="visible",
        updated_at=clock.now(),
        is_simulated=True,
    )
    db.add(media)
    db.flush()
    thread = PublicThread(
        workspace_id=ws.id,
        social_account_id=account.id,
        media_id=media.id,
        root_external_id=str(uuid.uuid4()),
    )
    db.add(thread)
    db.flush()
    rows = [
        PublicComment(
            workspace_id=ws.id,
            social_account_id=account.id,
            media_id=media.id,
            thread_id=thread.id,
            external_id=str(uuid.uuid4()),
            state="visible",
            updated_at=clock.now(),
            is_owner=False,
            is_simulated=True,
        )
        for _ in range(count)
    ]
    db.add_all(rows)
    db.flush()
    return rows


def test_exact_counts_exclude_answered_comments_without_list_caps(db_session, clock):
    db = db_session
    ws, user, account, ctx = world(db, clock)
    db.add_all(
        [
            ContentItem(
                workspace_id=ws.id,
                created_by_user_id=user.id,
                title=f"Draft {i}",
                status="draft",
                content_type="feed_image",
            )
            for i in range(61)
        ]
    )
    comments = public_comments(db, clock, ws, account, 35)
    target = comments[0]
    db.add(
        PublicComment(
            workspace_id=ws.id,
            social_account_id=account.id,
            media_id=target.media_id,
            thread_id=target.thread_id,
            parent_id=target.id,
            external_id="owner-answer",
            state="visible",
            updated_at=clock.now(),
            is_owner=True,
            is_simulated=True,
        )
    )
    for i, status in enumerate(("succeeded", "outcome_unknown", "pending", "failed"), 1):
        db.add(
            Operation(
                workspace_id=ws.id,
                social_account_id=account.id,
                operation_type="comment_reply",
                idempotency_key=str(uuid.uuid4()),
                subject_type="public_comment",
                subject_id=comments[i].id,
                provider_kind="mock",
                status=status,
            )
        )
    comments[5].state = "hidden"
    other_ws, _, other_account, _ = world(db, clock)
    public_comments(db, clock, other_ws, other_account, 9)
    db.flush()
    assert attention_counts(db, ctx) == {"drafts": 61, "unanswered_comments": 32}
    assert attention_counts(db, replace(ctx, role="staff"))["drafts"] is None
    account.status = "disconnected"
    db.flush()
    assert attention_counts(db, ctx)["unanswered_comments"] == 0


def test_attention_api_requires_workspace_membership(client, db_session):
    ws, users = workspace_with_members(db_session, roles=("owner", "manager", "staff"))
    foreign = create_workspace(db_session)
    for user in users.values():
        login(client, user)
        response = client.get(f"/api/v1/workspaces/{ws.id}/home/attention")
        assert response.status_code == 200
        assert response.json()["drafts"] == (None if user == users["staff"] else 0)
        assert client.get(f"/api/v1/workspaces/{foreign.id}/home/attention").status_code == 404


@pytest.mark.parametrize("range_days", [7, 28])
def test_partial_history_never_becomes_zero_totals_or_percentage(db_session, clock, range_days):
    ws, _, account, _ = world(db_session, clock)
    db_session.add(
        AccountInsightDaily(
            workspace_id=ws.id,
            social_account_id=account.id,
            local_date=clock.now().date(),
            metric="reach",
            value=10,
            fetched_at=clock.now(),
        )
    )
    db_session.flush()
    summary = service.get_summary(db_session, ws.id, account.id, range_days, clock)
    assert summary.status == "partial"
    assert summary.reach is None and summary.views is None and summary.interactions is None
    assert summary.reach_delta_pct is None
    assert summary.previous_days_covered == 0
    assert summary.sparkline[0].reach is None  # a gap, not a measured zero
    with pytest.raises(AppError):
        service.get_summary(db_session, uuid.uuid4(), account.id, clock=clock)


def test_ingestion_leaves_scheduler_transaction_open(db_session, clock, settings):
    _, _, account, _ = world(db_session, clock)
    with db_session.begin_nested():
        service.sync_account_daily(db_session, clock, settings, account)
        assert db_session.execute(text("SELECT 1")).scalar() == 1
        assert db_session.in_nested_transaction()


@pytest.mark.commits
def test_scheduler_enqueues_once_per_period_without_provider_io(
    session_factory, clock, monkeypatch
):
    with session_factory() as db:
        _, _, account, _ = world(db, clock)
        account_id = account.id
        db.commit()
    monkeypatch.setattr(service, "sync_account_daily", lambda *a, **k: pytest.fail("scheduler I/O"))
    monkeypatch.setattr(
        service, "sync_account_audience", lambda *a, **k: pytest.fail("scheduler I/O")
    )
    with periodic_snapshot(clear=True):
        register_periodic(jobs.sync_account_insights_daily)
        register_periodic(jobs.sync_audience_weekly)
        assert scheduler_tick(session_factory, clock) == 2
        with session_factory() as db:
            for job in db.scalars(select(Job)):
                job.status = "succeeded"
            db.commit()
        clock.advance(minutes=1)
        assert scheduler_tick(session_factory, clock) == 0
        clock.advance(days=1)
        assert scheduler_tick(session_factory, clock) == 1
        with session_factory() as db:
            assert db.scalar(select(func.count()).select_from(Job)) == 3
            assert all(j.payload["account_id"] == str(account_id) for j in db.scalars(select(Job)))


@pytest.mark.commits
def test_worker_backfills_both_periods_and_refreshes_only_recent_days(session_factory, clock):
    with session_factory() as db:
        ws, _, account, _ = world(db, clock)
        ws_id, account_id = ws.id, account.id
        db.commit()
    beats = []
    ctx = JobContext(
        job_id=uuid.uuid4(),
        job_type="insights_daily",
        workspace_id=ws_id,
        correlation_id=None,
        payload=jobs.InsightsPayload(account_id=account_id),
        attempt=1,
        max_attempts=3,
        session_factory=session_factory,
        clock=clock,
        _heartbeat=lambda: beats.append(1),
    )
    jobs.ingest_daily(ctx)
    assert len(beats) == 56
    with session_factory() as db:
        summary = service.get_summary(db, ws_id, account_id, 28, clock)
        assert summary.status == "ok"
        assert summary.current_days_covered == summary.previous_days_covered == 28
        assert summary.reach is not None and summary.reach_delta_pct is not None
    beats.clear()
    jobs.ingest_daily(ctx)
    assert len(beats) == 2


@pytest.mark.commits
def test_verified_agent_reply_removes_attention_but_queued_reply_does_not(session_factory, clock):
    from app.operations.public_comments import execute
    from tests.integration.agent.test_public_actions import propose, ready

    world, broker_ctx, target = ready(session_factory, clock, "reply")
    action = propose(session_factory, clock, broker_ctx, target, "reply")
    with session_factory() as db:
        assert attention_counts(db, world[0])["unanswered_comments"] == 1
    execute(session_factory, clock, world[3], world[0].workspace_id, uuid.UUID(action["action_id"]))
    with session_factory() as db:
        assert attention_counts(db, world[0])["unanswered_comments"] == 0


@pytest.mark.commits
def test_actual_worker_uses_external_story_id_and_no_open_transaction_during_collection(
    session_factory,
    clock,
    monkeypatch,
):
    with session_factory() as db:
        ws, user, account, _ = world(db, clock)
        story = ContentItem(
            workspace_id=ws.id,
            social_account_id=account.id,
            created_by_user_id=user.id,
            title="Published story",
            content_type="story_image",
            status="published",
            published_at=clock.now() - timedelta(hours=23),
            external_media_id="instagram-story-123",
        )
        db.add(story)
        db.commit()
        assert jobs.capture_stories_insights(db, clock) == 1
        assert jobs.sync_account_insights_daily(db, clock) == 1
        db.commit()

    seen = []
    original = service.get_provider

    def provider_spy(*args, **kwargs):
        provider = original(*args, **kwargs)
        original_daily = provider.get_account_insights
        original_media = provider.get_media_insights

        def daily(*args, **kw):
            assert not kwargs["session_factory"]().in_transaction()
            return original_daily(*args, **kw)

        def media(ref, media_id, media_kind):
            assert not kwargs["session_factory"]().in_transaction()
            seen.append(media_id)
            return original_media(ref, media_id, media_kind)

        provider.get_account_insights = daily
        provider.get_media_insights = media
        return provider

    monkeypatch.setattr(service, "get_provider", provider_spy)
    assert run_due_jobs(clock, session_factory=session_factory) == 2
    with session_factory() as db:
        assert all(job.status == "succeeded" for job in db.scalars(select(Job)))
    assert seen == ["instagram-story-123"]
