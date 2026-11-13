"""Bounded per-account ingestion jobs; scheduler callbacks only enqueue IDs."""

import uuid
from datetime import date, timedelta

from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.content.models import ContentItem
from app.core.clock import Clock
from app.core.config import get_settings
from app.core.errors import RetryableError
from app.insights import service
from app.insights.models import AccountInsightDaily
from app.integrations.instagram.errors import ProviderRateLimited, ProviderTransientError
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.jobs.queue import enqueue
from app.jobs.registry import JobContext, job_handler
from app.jobs.scheduler import register_periodic


class InsightsPayload(BaseModel):
    account_id: uuid.UUID
    content_item_id: uuid.UUID | None = None


def _eligible(account: SocialAccount | None) -> bool:
    return bool(
        account
        and account.status == "connected"
        and account.provider_kind in get_settings().instagram_providers
        and (
            account.provider_kind == "mock"
            or "instagram_business_manage_insights" in (account.granted_scopes or [])
        )
    )


def _enqueue_once(
    session: Session,
    clock: Clock,
    account: SocialAccount,
    kind: str,
    period: str,
    content_item_id: uuid.UUID | None = None,
) -> int:
    key = f"{kind}:{account.id}:{content_item_id or 'account'}:{period}"
    # Include terminal jobs: active-only dedup would repeat work every minute.
    if session.scalar(select(exists().where(Job.dedup_key == key))):
        return 0
    enqueue(
        session,
        kind,
        InsightsPayload(account_id=account.id, content_item_id=content_item_id),
        workspace_id=account.workspace_id,
        correlation_id=None,
        dedup_key=key,
        clock=clock,
    )
    return 1


def _accounts(session: Session) -> list[SocialAccount]:
    return [
        a
        for a in session.scalars(select(SocialAccount).where(SocialAccount.status == "connected"))
        if _eligible(a)
    ]


@register_periodic
def sync_account_insights_daily(session: Session, clock: Clock) -> int:
    if not get_settings().insights_enabled:
        return 0
    return sum(
        _enqueue_once(session, clock, a, "insights_daily", clock.now().date().isoformat())
        for a in _accounts(session)
    )


@register_periodic
def sync_audience_weekly(session: Session, clock: Clock) -> int:
    if not get_settings().insights_enabled:
        return 0
    today = clock.now().date()
    week = (today - timedelta(days=today.weekday())).isoformat()
    return sum(
        _enqueue_once(session, clock, a, "insights_audience", week) for a in _accounts(session)
    )


@register_periodic
def capture_stories_insights(session: Session, clock: Clock) -> int:
    if not get_settings().insights_enabled:
        return 0
    now = clock.now()
    stories = session.scalars(
        select(ContentItem).where(
            ContentItem.content_type == "story_image",
            ContentItem.status == "published",
            ContentItem.published_at >= now - timedelta(hours=24),
            ContentItem.published_at <= now,
            ContentItem.external_media_id.is_not(None),
        )
    )
    count = 0
    for story in stories:
        account = session.get(SocialAccount, story.social_account_id)
        if (
            _eligible(account)
            and account is not None
            and account.workspace_id == story.workspace_id
        ):
            count += _enqueue_once(
                session, clock, account, "insights_story", now.strftime("%Y-%m-%dT%H"), story.id
            )
    return count


def _run(job: JobContext, kind: str) -> None:
    settings = get_settings()
    if not settings.insights_enabled or not isinstance(job.payload, InsightsPayload):
        return
    payload = job.payload
    days: list[date] = []
    with job.session_factory() as db:
        account = db.scalar(
            select(SocialAccount).where(
                SocialAccount.id == payload.account_id,
                SocialAccount.workspace_id == job.workspace_id,
            )
        )
        if not _eligible(account) or account is None:
            return
        if kind == "daily":
            start = job.clock.now().date() - timedelta(days=55)
            rows = db.execute(
                select(AccountInsightDaily.local_date, AccountInsightDaily.metric).where(
                    AccountInsightDaily.workspace_id == account.workspace_id,
                    AccountInsightDaily.social_account_id == account.id,
                    AccountInsightDaily.local_date >= start,
                )
            ).all()
            coverage: dict[date, set[str]] = {}
            for day, metric in rows:
                coverage.setdefault(day, set()).add(metric)
            for i in range(56):
                day = start + timedelta(days=i)
                if i >= 54 or not {"reach", "views", "total_interactions"} <= coverage.get(
                    day, set()
                ):
                    days.append(day)
        story = None
        if kind == "story":
            story = db.scalar(
                select(ContentItem).where(
                    ContentItem.id == payload.content_item_id,
                    ContentItem.workspace_id == account.workspace_id,
                    ContentItem.social_account_id == account.id,
                    ContentItem.status == "published",
                    ContentItem.content_type == "story_image",
                    ContentItem.published_at >= job.clock.now() - timedelta(hours=24),
                    ContentItem.external_media_id.is_not(None),
                )
            )
            if story is None:
                return
            db.expunge(story)
        db.expunge(account)
    # Close the read transaction before provider I/O. Ingestion fetches before
    # writing; only the handler commits the subsequent write transaction.
    try:
        with job.session_factory() as db:
            db.rollback()  # tenant factories may start a transaction while binding context
            if kind == "daily":
                service.sync_account_daily(
                    db, job.clock, settings, account, days=days, heartbeat=job.heartbeat
                )
            elif kind == "audience":
                service.sync_account_audience(db, job.clock, settings, account)
            elif story is not None and story.external_media_id and story.published_at:
                service.capture_media_snapshot(
                    db,
                    job.clock,
                    settings,
                    account,
                    ig_media_id=story.external_media_id,
                    media_kind="story_image",
                    content_item_id=story.id,
                    is_final=job.clock.now() - story.published_at >= timedelta(hours=22),
                )
            db.commit()
    except (ProviderRateLimited, ProviderTransientError) as error:
        raise RetryableError("PROVIDER_UNAVAILABLE") from error


@job_handler("insights_daily", InsightsPayload, max_attempts=3, timeout=120)
def ingest_daily(job: JobContext) -> None:
    _run(job, "daily")


@job_handler("insights_audience", InsightsPayload, max_attempts=3)
def ingest_audience(job: JobContext) -> None:
    _run(job, "audience")


@job_handler("insights_story", InsightsPayload, max_attempts=3)
def ingest_story(job: JobContext) -> None:
    _run(job, "story")
