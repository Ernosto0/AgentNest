"""Demo history (H16): one day of yesterday's activity for each studio, through the real paths.

The history is what makes the seeded daily report meaningful: six inbound customer messages per
studio, four answered (approved and sent through the ledger), one handed to a person (a
complaint, ``human_required``), one left waiting for approval, one feed post published and one
feed post failed (``invalid_media``). Everything runs through the real code paths with a
``FrozenClock`` at yesterday's local times, so the audit trail, the operations ledger and the
simulator rows are exactly as consistent as real activity (INV-05/06/12, INV-09).

It is idempotent: a studio that already has a conversation is left alone, so ``seed`` can run
again without duplicating history. Afterwards no non-periodic job is left queued.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.approvals import service as approvals_service
from app.approvals.models import Approval
from app.content import media as content_media
from app.content import service as content_service
from app.content.service import ScheduleRequest
from app.core.clock import Clock, FrozenClock
from app.core.config import Settings
from app.core.context import ActorRef
from app.demo import simulator
from app.identity import service as identity_service
from app.identity.models import User, Workspace, WorkspaceMember
from app.inbox.models import Conversation, Message, ReplyDraft
from app.integrations.instagram.models import SimFailureRule
from app.integrations.storage.registry import get_media_storage
from app.jobs.testing import run_due_jobs
from app.operations import publish
from app.reporting import service as reporting_service
from app.reporting.periods import day_bounds, local_date_of

SEED_ACTOR = ActorRef.system("seed")

STUDIOS = ("golkent-fitness", "harbor-cafe")

FEED_SAMPLE = Path(__file__).parent / "media" / "feed-sample.jpg"

# One day per studio: (customer alias, message text, outcome). ``approve`` answers and sends,
# ``leave`` produces a draft that waits for approval, ``escalate`` is a complaint for a person.
STUDIO_HISTORY: dict[str, tuple[tuple[str, str, str], ...]] = {
    "golkent-fitness": (
        ("Ayşe", "Aylık üyelik ne kadar?", "approve"),
        ("Mehmet", "Çalışma saatleriniz nedir?", "approve"),
        ("Can", "Deneme seansı ücretsiz mi?", "approve"),
        ("Sarah", "How much is the monthly membership?", "approve"),
        ("Zeynep", "Adresiniz nerede?", "leave"),
        ("Burak", "Bu bir rezalet, çok memnuniyetsizim.", "escalate"),
    ),
    "harbor-cafe": (
        ("Emma", "How much is the brunch combo?", "approve"),
        ("Liam", "What are your opening hours?", "approve"),
        ("Olivia", "Do you have any morning promotions?", "approve"),
        ("Noah", "Where are you located?", "approve"),
        ("Mia", "Can we book a table for 8 people?", "leave"),
        ("Ethan", "This is terrible, I am very unhappy with the service.", "escalate"),
    ),
}

# (caption, fail) per studio: one post goes out, the next one fails on an invalid image.
STUDIO_POSTS: dict[str, tuple[str, str]] = {
    "golkent-fitness": ("Yeni haftaya hazırız!", "Bugün harika bir gün!"),
    "harbor-cafe": ("Fresh morning croissants just out of the oven!", "See you for coffee today!"),
}

STEP = timedelta(minutes=30)
HISTORY_START = time(17, 0)  # local time of the first customer message


def _owner(session: Session, workspace_id: uuid.UUID) -> User:
    row = (
        session.execute(
            select(User)
            .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
            .where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.role == "owner")
        )
        .scalars()
        .first()
    )
    if row is None:
        raise RuntimeError(f"workspace {workspace_id} has no owner")
    return row


def _has_conversations(session_factory: sessionmaker[Session], workspace_id: uuid.UUID) -> bool:
    with session_factory() as session:
        return (
            session.scalar(
                select(Conversation.id).where(Conversation.workspace_id == workspace_id).limit(1)
            )
            is not None
        )


def _deliver_and_draft(
    factory: sessionmaker[Session],
    clock: FrozenClock,
    settings: Settings,
    workspace_id: uuid.UUID,
    alias: str,
    text: str,
) -> None:
    """A customer message through the simulator, then the ingest and drafting jobs."""
    simulator.simulate_customer_message(
        factory, clock, settings, workspace_id, customer_alias=alias, text=text
    )
    run_due_jobs(clock, session_factory=factory)  # process_inbound_event
    clock.advance(seconds=settings.reply_debounce_seconds + 1)
    run_due_jobs(clock, session_factory=factory)  # draft_reply


def _approve_open_draft(
    factory: sessionmaker[Session],
    clock: FrozenClock,
    workspace_id: uuid.UUID,
    owner: User,
    alias: str,
) -> None:
    """Approve the pending draft of ``alias`` and let the send job run (real approval path)."""
    with factory() as session:
        workspace = session.get(Workspace, workspace_id)
        if workspace is None:
            raise RuntimeError(f"workspace {workspace_id} is missing")
        ctx = identity_service.workspace_context(workspace, ActorRef.user(owner.id), "owner")
        conversation = session.scalars(
            select(Conversation).where(
                Conversation.workspace_id == workspace_id,
                Conversation.customer_external_id == simulator.customer_id_for(alias),
            )
        ).one()
        draft = session.scalars(
            select(ReplyDraft).where(
                ReplyDraft.conversation_id == conversation.id,
                ReplyDraft.status == "pending_approval",
            )
        ).one()
        approval = session.get(Approval, draft.approval_id)
        if approval is None:
            raise RuntimeError(f"draft {draft.id} has no approval")
        approval_id = approval.id
        payload_hash = approval.payload_hash
    with factory() as session:
        approvals_service.decide(
            session,
            clock,
            ctx,
            approval_id,
            decision="approve",
            payload_hash=payload_hash,
        )
    run_due_jobs(clock, session_factory=factory)  # send_reply


def _publish_post(
    factory: sessionmaker[Session],
    clock: FrozenClock,
    settings: Settings,
    workspace: Workspace,
    owner: User,
    caption: str,
    *,
    fail: bool,
) -> None:
    """One feed post through the real upload, draft, submit and publish-executor paths."""
    ctx = identity_service.workspace_context(workspace, ActorRef.user(owner.id), "owner")
    storage = get_media_storage(settings, clock)
    with factory() as session:
        with FEED_SAMPLE.open("rb") as handle:
            asset = content_media.ingest(
                session, clock, settings, storage, ctx, handle, "feed-sample.jpg", "image/jpeg"
            )
        item, _ = content_service.create_draft(
            session,
            clock,
            ctx,
            content_type="feed_image",
            title="Haftalık paylaşım" if workspace.default_locale == "tr" else "Weekly post",
            caption=caption,
            media_asset_id=asset.id,
        )
        item = content_service.submit(
            session,
            clock,
            settings,
            ctx,
            item.id,
            schedule=ScheduleRequest(publish_now=True),
            self_approve=True,
            expected_version=item.version,
        )
        item_id = item.id
        version = item.version
        account_id = item.social_account_id

    if fail:
        with factory() as session:
            session.add(
                SimFailureRule(
                    workspace_id=workspace.id,
                    social_account_id=account_id,
                    operation="create_container",
                    mode="invalid_media",
                    remaining=1,
                    retry_after_s=None,
                )
            )
            session.commit()

    def _sleeper(seconds: float) -> None:
        clock.advance(seconds=seconds)

    publish.execute_publish(
        factory,
        clock,
        settings,
        workspace.id,
        item_id,
        version,
        sleep=_sleeper,
        heartbeat=lambda: None,
    )


def _backdate_conversations(session: Session, workspace_id: uuid.UUID) -> None:
    """``conversations.created_at`` is stamped by the database (``now()``), not by the injected
    clock, so the frozen-clock history would read "created today". Set it to the first message,
    which is what it would have been had the conversations really started yesterday."""
    first_message = (
        select(func.min(Message.provider_timestamp))
        .where(Message.conversation_id == Conversation.id)
        .scalar_subquery()
    )
    session.execute(
        update(Conversation)
        .where(Conversation.workspace_id == workspace_id)
        .values(created_at=first_message)
    )
    session.commit()


@contextmanager
def _one_transaction(factory: sessionmaker[Session]) -> Iterator[sessionmaker[Session]]:
    """Sessions that share one outer transaction, committed only when the history is complete.

    The history runs jobs with a frozen clock in the past. Committed, those jobs (and their
    leases, which a real clock sees as expired) would be visible to a running worker, which
    would claim them with the real clock and corrupt the history. Inside one transaction the
    worker sees nothing until the whole day exists and no job is left queued. If the factory is
    already bound to a connection (a test), the caller owns the transaction.
    """
    bind = factory.kw.get("bind")
    if not isinstance(bind, Engine):
        yield factory
        return
    with bind.connect() as connection:
        outer = connection.begin()
        try:
            yield sessionmaker(
                bind=connection,
                expire_on_commit=False,
                autoflush=False,
                join_transaction_mode="create_savepoint",
            )
        except BaseException:
            outer.rollback()
            raise
        outer.commit()


def _seed_workspace_history(
    factory: sessionmaker[Session],
    settings: Settings,
    workspace: Workspace,
    now: datetime,
) -> None:
    with _one_transaction(factory) as shared:
        _build_history(shared, settings, workspace, now)


def _build_history(
    factory: sessionmaker[Session],
    settings: Settings,
    workspace: Workspace,
    now: datetime,
) -> None:
    tz = workspace.timezone
    today = local_date_of(now, tz)
    yesterday = today - timedelta(days=1)
    _, end = day_bounds(yesterday, tz)
    # Evening, so the draft left waiting for approval is still valid when the demo starts
    # (approvals live 24 h from creation).
    start = datetime.combine(yesterday, HISTORY_START, tzinfo=ZoneInfo(tz)).astimezone(UTC)
    clock = FrozenClock(start)

    with factory() as session:
        owner = _owner(session, workspace.id)

    for alias, text, outcome in STUDIO_HISTORY[workspace.slug]:
        _deliver_and_draft(factory, clock, settings, workspace.id, alias, text)
        if outcome == "approve":
            _approve_open_draft(factory, clock, workspace.id, owner, alias)
        clock.advance(STEP)

    published_caption, failed_caption = STUDIO_POSTS[workspace.slug]
    for caption, fail in ((published_caption, False), (failed_caption, True)):
        _publish_post(factory, clock, settings, workspace, owner, caption, fail=fail)
        clock.advance(STEP)

    # Flush what is still due: the sends' echo webhooks and the queued publish jobs (both
    # no-ops now that the items are settled), leaving no non-periodic job behind.
    clock.advance(end - clock.now())
    run_due_jobs(clock, session_factory=factory)

    with factory() as session:
        _backdate_conversations(session, workspace.id)
        ctx = identity_service.workspace_context(workspace, SEED_ACTOR, None)
        reporting_service.generate_daily_report(session, clock, ctx, yesterday, scheduled=False)
        session.commit()


def seed_history(
    session_factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
    slugs: Collection[str] | None = None,
) -> None:
    """Seed yesterday's history for every demo studio that has no conversations yet (only
    among ``slugs`` when given)."""
    # The CLI process (``seed``) has not loaded the job handlers the API and the worker load at
    # startup; the history enqueues and runs jobs, and ``enqueue`` refuses unknown job types.
    from app.handlers import load_handlers

    load_handlers()
    now = clock.now()
    with session_factory() as session:
        workspaces = [
            session.scalars(
                select(Workspace).where(Workspace.slug == slug, Workspace.status == "active")
            ).one_or_none()
            for slug in STUDIOS
            if slugs is None or slug in slugs
        ]
    for workspace in workspaces:
        if workspace is None or _has_conversations(session_factory, workspace.id):
            continue
        _seed_workspace_history(session_factory, settings, workspace, now)
