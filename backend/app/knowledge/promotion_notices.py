"""``promotion_expiry_notices``: tell the owners that a promotion ended (plan H18).

Once a day, per workspace, at 09:00 **local** time. A verified ``promotion.*`` fact is unusable
from the first local second after its ``valid_until`` day (both bounds are inclusive,
``knowledge/usability.py``). The run of local day ``L`` therefore announces the facts whose
``valid_until`` is ``L - 1``: they became unusable in the 24 hours before this run, and no other
run covers them, so each expiry is announced once. Nothing is changed in the data
(business-knowledge.md section 4); the notification only says "this promotion is over".

Like the daily report, the tick looks for a job with the day's key in any status, so a finished
(or dead) day is not enqueued again every minute.
"""

import uuid
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import ActorRef, WorkspaceContext
from app.identity import service as identity_service
from app.identity.models import Workspace
from app.jobs.models import Job
from app.jobs.queue import enqueue
from app.jobs.registry import JobContext, job_handler
from app.jobs.scheduler import register_periodic
from app.knowledge.models import BusinessFact
from app.notifications import service as notifications

PROMOTION_EXPIRED = "knowledge.promotion_expired"
NOTICE_HOUR_LOCAL = 9


class PromotionExpiryPayload(BaseModel):
    workspace_id: uuid.UUID
    local_date: date


def dedup_key(workspace_id: uuid.UUID, local_date: date) -> str:
    return f"promo_expiry:{workspace_id}:{local_date.isoformat()}"


def announce_expired(
    session: Session, clock: Clock, ctx: WorkspaceContext, local_date: date
) -> list[BusinessFact]:
    """Notify the ``knowledge.verify`` holders about every promotion that ended yesterday
    (local). Returns those facts. Runs in the caller's transaction and never commits."""
    expired = list(
        session.scalars(
            select(BusinessFact)
            .where(
                BusinessFact.workspace_id == ctx.workspace_id,
                BusinessFact.status == "verified",
                BusinessFact.key.like("promotion.%"),
                BusinessFact.valid_until == local_date - timedelta(days=1),
            )
            .order_by(BusinessFact.key)
        )
    )
    for fact in expired:
        notifications.notify_permission_holders(
            session,
            clock,
            ctx,
            permission="knowledge.verify",
            type=PROMOTION_EXPIRED,
            params={
                "fact_key": fact.key,
                "label": fact.label,
                "valid_until": str(fact.valid_until),  # the ISO date; the query matched it
            },
            subject_type="business_fact",
            subject_id=fact.id,
            dedup_key=f"promotion-expired:{fact.id}:{fact.valid_until}",
        )
    return expired


@job_handler("promotion_expiry_notices", PromotionExpiryPayload, max_attempts=1)
def promotion_expiry_notices(job: JobContext) -> None:
    payload = job.payload
    if not isinstance(payload, PromotionExpiryPayload):
        return
    with job.session_factory() as session:
        workspace = session.get(Workspace, payload.workspace_id)
        if workspace is None or workspace.status != "active":
            return  # gone or suspended meanwhile: nobody to tell
        ctx = identity_service.workspace_context(
            workspace, ActorRef.system("knowledge.promotions"), None
        )
        announce_expired(session, job.clock, ctx, payload.local_date)
        session.commit()


@register_periodic
def enqueue_promotion_expiry_notices(session: Session, clock: Clock) -> int:
    now = clock.now()
    rows = session.execute(
        select(Workspace.id, Workspace.timezone).where(Workspace.status == "active")
    ).all()
    enqueued = 0
    for workspace_id, timezone in rows:
        local_now = now.astimezone(ZoneInfo(timezone))
        if local_now.hour < NOTICE_HOUR_LOCAL:
            continue
        local_date = local_now.date()
        key = dedup_key(workspace_id, local_date)
        if session.scalar(select(exists().where(Job.dedup_key == key))):
            continue  # queued, running, done or dead: this day has had its job
        enqueue(
            session,
            "promotion_expiry_notices",
            PromotionExpiryPayload(workspace_id=workspace_id, local_date=local_date),
            workspace_id=workspace_id,
            correlation_id=None,
            dedup_key=key,
            clock=clock,
        )
        enqueued += 1
    return enqueued
