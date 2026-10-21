"""Publishing a scheduled content item (workflows.md section E step 6, ADR-011, INV-05/06/15).

The same pattern as ``send.py``: short transactions around calls that never run inside one.

* **T1** locks the item, runs the due-time checks, creates or finds the ledger row
  ``publish:{content_id}:v{version}``, marks it ``in_progress`` and the item ``publishing``, and
  **commits before the provider is called** (INV-15).
* The container is created, its id committed (**T2**), and polled until it is ``FINISHED``
  (every 10 s for up to 5 minutes, with the injected sleeper, the injected ``Clock`` and a
  heartbeat; **no transaction is open while it sleeps or polls**).
* ``publish_container`` is the one visible side effect; its outcome is recorded in **T3**.

An ambiguous outcome (a timeout after the request may have been accepted, any unexpected error
after the publish call) is never repeated blindly: the operation becomes ``outcome_unknown`` and
``reconcile_publish`` reads the container back. The container is the idempotency anchor: a
``PUBLISHED`` container is a success, a ``FINISHED`` one proves nothing was published, so
publishing again is safe (``outcome_unknown -> in_progress`` exists for publishing only).

The order of locks is always item, then operation, then account.
"""

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.approvals import repository as approvals_repo
from app.approvals import service as approvals
from app.audit import service as audit
from app.content import notifications as content_notifications
from app.content import transitions
from app.content.models import ContentItem, MediaAsset
from app.content.payload import PublishContentPayload, publish_job_key
from app.content.subject import bound_payload_hash
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.logging import get_logger
from app.identity.models import Workspace
from app.inbox.system import system_context
from app.integrations.instagram import queries
from app.integrations.instagram.base import (
    AccountRef,
    ContainerSpec,
    InstagramProvider,
    MediaInfo,
    PublishingQuota,
)
from app.integrations.instagram.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderInvalidRequest,
    ProviderOutcomeUnknown,
    ProviderPermissionError,
    ProviderRateLimited,
    ProviderTransientError,
)
from app.integrations.instagram.models import SocialAccount
from app.integrations.instagram.registry import get_provider
from app.integrations.storage.base import MediaStorageUnavailable
from app.integrations.storage.registry import get_media_storage
from app.jobs.queue import enqueue
from app.operations import health
from app.operations.models import Operation
from app.operations.payloads import ReconcilePublishPayload
from app.operations.resolution import set_operation

log = get_logger(__name__)

PUBLISH_MAX_ATTEMPTS = 5
# 1 / 5 / 15 / 30 minutes (state-machines.md section 6); a larger ``Retry-After`` overrides.
PUBLISH_BACKOFF = (60, 300, 900, 1800, 1800)
POLL_INTERVAL_SECONDS = 10
POLL_TIMEOUT = timedelta(minutes=5)
RECONCILE_DELAY = timedelta(minutes=1)  # first check, and between later ones
QUOTA_WINDOW = timedelta(hours=24)
QUOTA_FALLBACK_DELAY = timedelta(hours=1)  # when the oldest post is not known
MAX_CONTAINER_RECREATIONS = 2  # an expired container is replaced at most this often per run
# The lease a publishing job asks for: the polling budget plus the calls around it.
PUBLISH_LEASE_SECONDS = int(POLL_TIMEOUT.total_seconds()) + 120

ACTIONABLE = ("scheduled", "retry_scheduled")
# ``publish_container`` answers that mean "somebody may already have published this container":
# settled by reading the container, never by publishing again.
AMBIGUOUS_PUBLISH_CODES = frozenset(
    {"CONTAINER_PUBLISHED", "CONTAINER_NOT_READY", "CONTAINER_EXPIRED"}
)
ACCOUNT_UNAVAILABLE = transitions.PUBLISHING_HOLD_REASON

Kind = Literal["published", "skipped", "held", "failed", "retry", "rescheduled", "unknown"]


@dataclass(frozen=True)
class PublishOutcome:
    kind: Kind
    detail: str | None = None
    error_code: str | None = None
    retry_after_seconds: float | None = None  # ``retry``: the delay before the next attempt
    run_at: datetime | None = None  # ``rescheduled`` / ``unknown``: when to look again


@dataclass(frozen=True)
class _Prepared:
    """What the calls after T1 need, copied out of the locked rows."""

    workspace_id: uuid.UUID
    content_id: uuid.UUID
    operation_id: uuid.UUID
    account: AccountRef
    provider_kind: str
    content_type: str
    caption: str | None
    storage_key: str
    container_id: str | None


@dataclass(frozen=True)
class _Quota:
    used: int
    limit: int

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit


@dataclass
class _Env:
    """The injected collaborators of one execution."""

    session_factory: sessionmaker[Session]
    clock: Clock
    settings: Settings
    provider: InstagramProvider | None
    sleep: Callable[[float], None]
    heartbeat: Callable[[], None]
    # A retry decided inside ``reconcile_publish`` has no running ``publish_content`` job to
    # retry: it queues one (the job that decided it in ``execute_publish`` retries itself).
    requeue_on_retry: bool = False

    def provider_for(self, kind: str) -> InstagramProvider:
        return self.provider or get_provider(
            kind, settings=self.settings, session_factory=self.session_factory, clock=self.clock
        )


def _skip(detail: str) -> PublishOutcome:
    return PublishOutcome("skipped", detail=detail)


def capability_for(content_type: str) -> str:
    """``feed_image`` needs ``publish_feed_image``; ``story_image``, ``publish_story_image``."""
    return f"publish_{content_type}"


# --- entry points ---------------------------------------------------------------------------------


def execute_publish(
    session_factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
    workspace_id: uuid.UUID,
    content_id: uuid.UUID,
    version: int,
    *,
    provider: InstagramProvider | None = None,
    sleep: Callable[[float], None] = time.sleep,
    heartbeat: Callable[[], None] | None = None,
) -> PublishOutcome:
    """Publish ``version`` of the item once. Safe to call again: the ledger, the item's status
    and the container decide what, if anything, still has to happen."""
    env = _Env(session_factory, clock, settings, provider, sleep, heartbeat or (lambda: None))
    quota = _read_quota(env, workspace_id, content_id, version)  # no transaction is open
    with session_factory() as session:  # [T1]
        prepared = _begin(session, env, workspace_id, content_id, version, quota)
        session.commit()
    if isinstance(prepared, PublishOutcome):
        return prepared
    return _drive(env, prepared)


def reconcile_publish(
    session_factory: sessionmaker[Session],
    clock: Clock,
    settings: Settings,
    workspace_id: uuid.UUID,
    operation_id: uuid.UUID,
    *,
    provider: InstagramProvider | None = None,
    sleep: Callable[[float], None] = time.sleep,
    heartbeat: Callable[[], None] | None = None,
) -> PublishOutcome:
    """One reconciliation check of an ``outcome_unknown`` publish: read the container back.

    ``PUBLISHED`` is a success; ``FINISHED`` or ``EXPIRED`` proves nothing was published, so the
    publish continues (with the same or a new container); ``IN_PROGRESS`` or an unreadable
    container is looked at again later; ``ERROR`` and the deadline end it. Never a blind retry.
    """
    env = _Env(
        session_factory,
        clock,
        settings,
        provider,
        sleep,
        heartbeat or (lambda: None),
        requeue_on_retry=True,
    )
    with session_factory() as session:
        op = _operation_by_id(session, workspace_id, operation_id)
        if op is None or op.operation_type != "publish_content" or op.status != "outcome_unknown":
            return _skip("resolved")
        account = queries.get_account_in_workspace(session, workspace_id, op.social_account_id)
        if account is None:
            return _skip("account_missing")
        ref = AccountRef(account.id, workspace_id, account.external_account_id)
        kind = account.provider_kind
        container_id = op.provider_ref.get("container_id")

    status_code: str | None = None
    media_id: str | None = None
    media: MediaInfo | None = None
    if container_id:
        reader = env.provider_for(kind)
        try:  # no transaction is open here
            status = reader.get_container_status(ref, str(container_id))
            status_code, media_id = status.status_code, status.media_id
        except ProviderError:
            pass  # a failed read and an unreadable container are treated alike: ask again later
        if status_code == "PUBLISHED":
            media = _fetch_media(reader, ref, media_id)

    with session_factory() as session:
        concluded = _conclude(
            session,
            env,
            workspace_id,
            operation_id,
            bool(container_id),
            status_code,
            media_id,
            media,
        )
        session.commit()
    if isinstance(concluded, PublishOutcome):
        return concluded
    return _drive(env, concluded)


def abandon_publish(
    session: Session,
    clock: Clock,
    workspace_id: uuid.UUID,
    content_id: uuid.UUID,
    version: int,
    code: str,
) -> None:
    """The ``publish_content`` job is dead (``on_dead``): make sure the item does not stay
    ``scheduled`` for ever. An attempt that may have reached the provider is left to
    reconciliation; everything else becomes ``failed``. No commit."""
    ctx = system_context(session, workspace_id, "operations.publish")
    item = _item(session, workspace_id, content_id, lock=True)
    if ctx is None or item is None or item.version != version:
        return
    if item.status not in (*ACTIONABLE, "publishing"):
        return
    op = _operation_by_key(session, publish_job_key(content_id, version))
    if (
        item.status == "publishing"
        and op is not None
        and op.status
        in (
            "in_progress",
            "outcome_unknown",
        )
    ):
        if op.status == "in_progress":  # the worker may have died mid-call: find out, never repeat
            mark_unknown(session, clock, ctx, item, op)
        return
    if item.status == "scheduled":
        transitions.apply(
            session, clock, ctx, item, "start"
        )  # the table has no scheduled -> failed
    if op is not None and op.status in ("pending", "retry_wait"):
        set_operation(clock, op, "cancel" if op.status == "pending" else "fail", code=code)
    transitions.apply(session, clock, ctx, item, "fail", reason=code)
    content_notifications.notify(
        session, clock, ctx, item, content_notifications.FAILED, reason=code
    )


def abandon_reconcile(
    session: Session, clock: Clock, workspace_id: uuid.UUID, operation_id: uuid.UUID
) -> None:
    """The ``reconcile_publish`` job is dead: nothing could confirm the publish. Reported as
    ``OUTCOME_UNCONFIRMED`` and never repeated. No commit."""
    ctx = system_context(session, workspace_id, "operations.reconcile")
    op = _operation_by_id(session, workspace_id, operation_id)
    if ctx is None or op is None:
        return
    item = _item(session, workspace_id, op.subject_id, lock=True)
    op = _operation_by_id(session, workspace_id, operation_id, lock=True)
    if op is None or op.status != "outcome_unknown":
        return
    set_operation(clock, op, "fail", code="OUTCOME_UNCONFIRMED")
    if item is not None and item.status == "publishing":
        transitions.apply(session, clock, ctx, item, "fail", reason="OUTCOME_UNCONFIRMED")
        content_notifications.notify(
            session, clock, ctx, item, content_notifications.FAILED, reason="OUTCOME_UNCONFIRMED"
        )


# --- reads ----------------------------------------------------------------------------------------


def _item(
    session: Session, workspace_id: uuid.UUID, content_id: uuid.UUID, *, lock: bool = False
) -> ContentItem | None:
    statement = select(ContentItem).where(
        ContentItem.workspace_id == workspace_id, ContentItem.id == content_id
    )
    return session.scalars(statement.with_for_update() if lock else statement).one_or_none()


def _operation_by_key(session: Session, key: str, *, lock: bool = True) -> Operation | None:
    statement = select(Operation).where(Operation.idempotency_key == key)
    return session.scalars(statement.with_for_update() if lock else statement).one_or_none()


def _operation_by_id(
    session: Session, workspace_id: uuid.UUID, operation_id: uuid.UUID, *, lock: bool = False
) -> Operation | None:
    statement = select(Operation).where(
        Operation.workspace_id == workspace_id, Operation.id == operation_id
    )
    return session.scalars(statement.with_for_update() if lock else statement).one_or_none()


def _read_quota(
    env: _Env, workspace_id: uuid.UUID, content_id: uuid.UUID, version: int
) -> _Quota | None:
    """The provider's publishing quota (plan.md G8), read **before** T1 and with no transaction
    open. ``None`` when nothing is due or the read failed: the provider enforces its limit at
    publish time anyway (a rate-limited answer is retried like any other)."""
    with env.session_factory() as session:
        item = _item(session, workspace_id, content_id)
        if (
            item is None
            or item.version != version
            or item.status not in ACTIONABLE
            or item.social_account_id is None
        ):
            return None
        account = queries.get_account_in_workspace(session, workspace_id, item.social_account_id)
        if account is None or account.status != "connected":
            return None  # T1 holds the item
        ref = AccountRef(account.id, workspace_id, account.external_account_id)
        kind = account.provider_kind
    try:  # the session is closed: no transaction is open during the provider call
        reading: PublishingQuota = env.provider_for(kind).get_publishing_quota(ref)
    except ProviderError:
        log.warning("publish_quota_unavailable", content_id=str(content_id))
        return None
    return _Quota(reading.used, reading.limit)


def _fetch_media(
    provider: InstagramProvider, ref: AccountRef, media_id: str | None
) -> MediaInfo | None:
    """The permalink of a published post, best effort (a read: no transaction is open)."""
    if media_id is None:
        return None
    try:
        return provider.get_media(ref, media_id)
    except ProviderError:
        log.warning("publish_media_lookup_failed")
        return None


# --- T1 -------------------------------------------------------------------------------------------


def _begin(
    session: Session,
    env: _Env,
    workspace_id: uuid.UUID,
    content_id: uuid.UUID,
    version: int,
    quota: _Quota | None,
) -> _Prepared | PublishOutcome:
    clock = env.clock
    now = clock.now()
    ctx = system_context(session, workspace_id, "operations.publish")
    item = _item(session, workspace_id, content_id, lock=True)
    if item is None or ctx is None:
        return _skip("item_missing")
    workspace = session.get(Workspace, workspace_id)
    if workspace is None or workspace.status != "active":
        return _skip("workspace_inactive")

    op = _operation_by_key(session, publish_job_key(content_id, version))
    if item.version == version and op is not None and op.status == "succeeded":
        if item.status in (*ACTIONABLE, "publishing"):  # the effect happened, the item lags
            account = queries.get_account_in_workspace(
                session, workspace_id, op.social_account_id, lock=True
            )
            if account is not None:
                if item.status != "publishing":
                    transitions.apply(session, clock, ctx, item, "start")
                _record_published(
                    session, clock, ctx, item, op, account,
                    media_id=_text(op.result.get("media_id")),
                    permalink=_text(op.result.get("permalink")),
                    published_at=op.completed_at or now, via="repair",
                )  # fmt: skip
                return PublishOutcome("published", detail="repaired")
        return _skip(f"already_published:{item.status}")
    if item.version != version or item.status not in ACTIONABLE:
        # Edited, cancelled, held or already running: nothing to do, and an operation that was
        # only waiting for this run is released.
        if op is not None and op.status in ("pending", "retry_wait"):
            set_operation(clock, op, "cancel")
        return _skip(f"not_due:{item.status}")
    if op is not None and op.status in ("in_progress", "outcome_unknown", "failed", "cancelled"):
        return _skip(f"operation_{op.status}")

    approval = (
        approvals_repo.get_approval(session, ctx, item.approval_id, lock=True)
        if item.approval_id is not None
        else None
    )
    if approval is None:
        return _refuse(session, clock, ctx, item, op, "APPROVAL_STALE")
    deadline = approval.execute_before
    if deadline is not None and now >= deadline:
        return _refuse(session, clock, ctx, item, op, "PUBLISH_DEADLINE_PASSED")
    try:
        approvals.assert_executable(session, clock, ctx, approval.id, item.version)
    except AppError as exc:
        return _refuse(session, clock, ctx, item, op, exc.code)
    if bound_payload_hash(session, item) != approval.payload_hash:
        return _refuse(session, clock, ctx, item, op, "APPROVAL_STALE")

    account = (
        queries.get_account_in_workspace(session, workspace_id, item.social_account_id, lock=True)
        if item.social_account_id is not None
        else None
    )
    capability = capability_for(item.content_type)
    if (
        account is None
        or account.status != "connected"
        or account.capabilities.get(capability) is not True
    ):
        return _hold(session, clock, ctx, item, op)
    asset = session.scalars(
        select(MediaAsset).where(
            MediaAsset.workspace_id == workspace_id, MediaAsset.id == item.media_asset_id
        )
    ).one_or_none()
    if asset is None or asset.status != "ready":
        return _refuse(session, clock, ctx, item, op, "MEDIA_REJECTED")

    if quota is not None and quota.exhausted:
        retry_at = _quota_retry_at(session, item, account, quota, now)
        if deadline is not None and retry_at >= deadline:
            return _refuse(session, clock, ctx, item, op, "PUBLISH_DEADLINE_PASSED")
        op = op or _create_operation(session, clock, item, account, deadline)
        set_operation(clock, op, "start")  # pending / retry_wait -> in_progress -> retry_wait
        set_operation(clock, op, "retry", code="PUBLISH_QUOTA_EXHAUSTED")
        op.next_attempt_at = retry_at  # nothing was tried: the attempt counter is untouched
        transitions.apply(session, clock, ctx, item, "start")
        transitions.apply(session, clock, ctx, item, "retry", reason="PUBLISH_QUOTA_EXHAUSTED")
        return PublishOutcome("rescheduled", error_code="PUBLISH_QUOTA_EXHAUSTED", run_at=retry_at)

    op = op or _create_operation(session, clock, item, account, deadline)
    approvals.assert_executable(
        session, clock, ctx, approval.id, item.version, operation_id=op.id
    )  # the approval is consumed by this operation; retries of it stay covered
    set_operation(clock, op, "start")
    op.attempts += 1
    op.started_at = now  # each attempt: the "stuck" sweep measures from the latest start
    op.next_attempt_at = None
    transitions.apply(session, clock, ctx, item, "start")
    return _prepared(item, op, account, asset)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _prepared(
    item: ContentItem, op: Operation, account: SocialAccount, asset: MediaAsset
) -> _Prepared:
    container_id = op.provider_ref.get("container_id")
    return _Prepared(
        workspace_id=item.workspace_id,
        content_id=item.id,
        operation_id=op.id,
        account=AccountRef(account.id, item.workspace_id, account.external_account_id),
        provider_kind=account.provider_kind,
        content_type=item.content_type,
        caption=item.caption,
        storage_key=asset.storage_key,
        container_id=str(container_id) if container_id else None,
    )


def _create_operation(
    session: Session,
    clock: Clock,
    item: ContentItem,
    account: SocialAccount,
    deadline: datetime | None,
) -> Operation:
    """The ledger row of this version (``ON CONFLICT DO NOTHING``, then ``FOR UPDATE``)."""
    key = publish_job_key(item.id, item.version)
    session.execute(
        pg_insert(Operation)
        .values(
            id=new_id(),
            workspace_id=item.workspace_id,
            operation_type="publish_content",
            idempotency_key=key,
            subject_type="content_item",
            subject_id=item.id,
            social_account_id=account.id,
            provider_kind=account.provider_kind,
            status="pending",
            attempts=0,
            max_attempts=PUBLISH_MAX_ATTEMPTS,
            deadline_at=deadline,
            is_simulated=account.is_simulated,
            created_at=clock.now(),
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
    )
    return session.scalars(
        select(Operation).where(Operation.idempotency_key == key).with_for_update()
    ).one()


def _quota_retry_at(
    session: Session, item: ContentItem, account: SocialAccount, quota: _Quota, now: datetime
) -> datetime:
    """When the quota has room again (plan.md G8): the instant the oldest post that has to leave
    the window does, 24 h after it was published. ``PublishingQuota`` carries no timestamps, so
    the times come from the account's published items; if they do not cover the count, an hour
    from now."""
    published = [
        t
        for t in session.scalars(
            select(ContentItem.published_at)
            .where(
                ContentItem.workspace_id == item.workspace_id,
                ContentItem.social_account_id == account.id,
                ContentItem.status == "published",
                ContentItem.published_at > now - QUOTA_WINDOW,
            )
            .order_by(ContentItem.published_at)
        )
        if t is not None
    ]
    leaving = quota.used - quota.limit + 1  # how many posts must leave before there is room
    if 0 < leaving <= len(published):
        return max(published[leaving - 1] + QUOTA_WINDOW, now + timedelta(seconds=1))
    return now + QUOTA_FALLBACK_DELAY


# --- due-time outcomes without a provider call ---------------------------------------------------


def _release_waiting_operation(clock: Clock, op: Operation | None, code: str) -> None:
    if op is None:
        return
    if op.status == "pending":
        set_operation(clock, op, "cancel")
    elif op.status == "retry_wait":
        set_operation(clock, op, "fail", code=code)


def _refuse(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    item: ContentItem,
    op: Operation | None,
    code: str,
) -> PublishOutcome:
    """The item cannot go out and never will (overdue, approval no longer valid, media gone):
    ``failed``. The table has no ``scheduled -> failed`` or ``retry_scheduled -> publishing ->``
    shortcut, so the item takes ``start`` first inside the same transaction."""
    _release_waiting_operation(clock, op, code)
    transitions.apply(session, clock, ctx, item, "start")
    transitions.apply(session, clock, ctx, item, "fail", reason=code)
    content_notifications.notify(
        session, clock, ctx, item, content_notifications.FAILED, reason=code
    )
    return PublishOutcome("failed", error_code=code)


def _hold(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    item: ContentItem,
    op: Operation | None,
) -> PublishOutcome:
    """The account is not usable at the due time: ``on_hold (ACCOUNT_UNAVAILABLE)``. The owner
    re-approves, because the schedule may have passed (workflows.md section G.2)."""
    if op is not None and op.status in ("pending", "retry_wait"):
        set_operation(clock, op, "cancel")
    transitions.apply(session, clock, ctx, item, "hold", reason=ACCOUNT_UNAVAILABLE)
    content_notifications.notify(
        session, clock, ctx, item, content_notifications.ON_HOLD, reason=ACCOUNT_UNAVAILABLE
    )
    return PublishOutcome("held", error_code=ACCOUNT_UNAVAILABLE)


# --- the calls ------------------------------------------------------------------------------------


def _drive(env: _Env, prepared: _Prepared) -> PublishOutcome:
    """Everything after T1: container, polling, publish, outcome. No transaction is open
    during any provider call or sleep."""
    provider = env.provider_for(prepared.provider_kind)
    container_id = prepared.container_id
    recreated = 0
    while True:
        if container_id is None:
            try:
                container_id = _create_container(env, provider, prepared)
            except Exception as exc:
                return _record_error(env, prepared, exc, "create")
            _store_container(env, prepared, container_id)  # [T2]

        polled = _poll(env, provider, prepared, container_id)
        if isinstance(polled, PublishOutcome):
            return polled
        if polled.state == "published":  # already published: only the record is missing
            return _finish(env, provider, prepared, polled.media_id)
        if polled.state == "expired":
            recreated += 1
            if recreated > MAX_CONTAINER_RECREATIONS:
                return _record_error(
                    env, prepared, ProviderTransientError("the container keeps expiring"), "status"
                )
            _store_container(env, prepared, None)  # forget it: step 2 creates a new one
            container_id = None
            continue

        try:  # FINISHED: the one visible side effect
            media_id = provider.publish_container(prepared.account, container_id)
        except Exception as exc:
            return _record_error(env, prepared, exc, "publish")
        return _finish(env, provider, prepared, media_id)


def _create_container(env: _Env, provider: InstagramProvider, prepared: _Prepared) -> str:
    try:
        storage = get_media_storage(env.settings, env.clock)
    except MediaStorageUnavailable as exc:
        raise ProviderInvalidRequest("MEDIA_REJECTED", "media storage unavailable") from exc
    url = storage.public_fetch_url(prepared.storage_key, env.settings.media_public_url_ttl_seconds)
    story = prepared.content_type == "story_image"
    spec = ContainerSpec("STORIES" if story else "IMAGE", url, None if story else prepared.caption)
    return provider.create_media_container(prepared.account, spec)


@dataclass(frozen=True)
class _Polled:
    state: Literal["finished", "published", "expired"]
    media_id: str | None = None  # only with ``published``


def _poll(
    env: _Env, provider: InstagramProvider, prepared: _Prepared, container_id: str
) -> _Polled | PublishOutcome:
    """Wait for the container (plan.md G9): every 10 s for up to 5 minutes, the elapsed time
    taken from the ``Clock``, the sleeper injected, a heartbeat after each wait. Returns what
    the container became, or the outcome of an error or of the timeout."""
    started = env.clock.now()
    while True:
        try:
            status = provider.get_container_status(prepared.account, container_id)
        except Exception as exc:
            return _record_error(env, prepared, exc, "status")
        code = status.status_code
        if code == "FINISHED":
            return _Polled("finished")
        if code == "PUBLISHED":
            return _Polled("published", status.media_id)
        if code == "EXPIRED":
            return _Polled("expired")
        if code == "ERROR":
            return _fail_now(env, prepared, "MEDIA_REJECTED", status.error_detail)
        if env.clock.now() - started >= POLL_TIMEOUT:  # still IN_PROGRESS
            return _poll_timeout(env, prepared)
        env.sleep(POLL_INTERVAL_SECONDS)
        env.heartbeat()


# --- T2 / T3 and the error records ----------------------------------------------------------------


def _locked(
    session: Session, prepared: _Prepared
) -> tuple[WorkspaceContext, ContentItem, Operation, SocialAccount]:
    """Item, operation, account (in that order) of a run after T1, locked."""
    ctx = system_context(session, prepared.workspace_id, "operations.publish")
    item = _item(session, prepared.workspace_id, prepared.content_id, lock=True)
    op = _operation_by_id(session, prepared.workspace_id, prepared.operation_id, lock=True)
    account = queries.get_account_in_workspace(
        session, prepared.workspace_id, prepared.account.social_account_id, lock=True
    )
    if ctx is None or item is None or op is None or account is None:
        raise RuntimeError("the records of a publish vanished between T1 and the outcome")
    return ctx, item, op, account


def _store_container(env: _Env, prepared: _Prepared, container_id: str | None) -> None:
    """[T2] Commit the container id (or forget it), so a re-run uses the stored one."""
    with env.session_factory() as session:
        op = _operation_by_id(session, prepared.workspace_id, prepared.operation_id, lock=True)
        if op is None:
            raise RuntimeError("the operation of a publish vanished")
        reference = {k: v for k, v in op.provider_ref.items() if k != "container_id"}
        if container_id is not None:
            reference["container_id"] = container_id
        op.provider_ref = reference
        session.commit()


def _finish(
    env: _Env, provider: InstagramProvider, prepared: _Prepared, media_id: str | None
) -> PublishOutcome:
    media = _fetch_media(provider, prepared.account, media_id)  # a read, outside the transaction
    with env.session_factory() as session:  # [T3]
        ctx, item, op, account = _locked(session, prepared)
        if op.status == "succeeded":
            return PublishOutcome("published", detail="already_recorded")
        if op.status not in ("in_progress", "outcome_unknown"):
            return _skip(f"operation_{op.status}")
        _record_published(
            session, env.clock, ctx, item, op, account,
            media_id=media_id,
            permalink=media.permalink if media else None,
            published_at=(media.timestamp if media and media.timestamp else env.clock.now()),
            via="publish",
        )  # fmt: skip
        session.commit()
    return PublishOutcome("published")


def _record_published(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    item: ContentItem,
    op: Operation,
    account: SocialAccount,
    *,
    media_id: str | None,
    permalink: str | None,
    published_at: datetime,
    via: str,
) -> None:
    """The post is out: the operation succeeded, the item is ``published`` (immutable from now
    on, INV-17), the approvers are told, the account's failure counter is reset."""
    if op.status != "succeeded":  # a repair finds it done already
        set_operation(clock, op, "succeed")
        op.result = {"media_id": media_id, "permalink": permalink, "resolved_by": via}
    transitions.apply(
        session, clock, ctx, item, "succeed",
        published_at=published_at, external_media_id=media_id, external_permalink=permalink,
    )  # fmt: skip
    health.record_success(account)
    content_notifications.notify(session, clock, ctx, item, content_notifications.PUBLISHED)
    if via == "reconcile":
        audit.record(
            session,
            ctx,
            "operation.reconciled",
            "operation",
            op.id,
            {"content_id": item.id, "outcome": "succeeded"},
            is_simulated=op.is_simulated,
            clock=clock,
        )


def mark_unknown(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    item: ContentItem,
    op: Operation,
) -> PublishOutcome:
    """The outcome is not known: never publish again to find out. The item stays ``publishing``
    (the UI shows "checking" from the operation) and ``reconcile_publish`` reads the container."""
    now = clock.now()
    set_operation(clock, op, "unknown", code="OUTCOME_UNKNOWN")
    run_at = now + RECONCILE_DELAY
    enqueue(
        session,
        "reconcile_publish",
        ReconcilePublishPayload(operation_id=op.id),
        workspace_id=op.workspace_id,
        correlation_id=op.correlation_id,
        run_at=run_at,
        dedup_key=f"reconcile_publish:{op.id}",
        clock=clock,
    )
    audit.record(
        session,
        ctx,
        "operation.outcome_unknown",
        "operation",
        op.id,
        {"content_id": item.id, "version": item.version},
        is_simulated=op.is_simulated,
        clock=clock,
    )
    return PublishOutcome("unknown", error_code="OUTCOME_UNKNOWN", run_at=run_at)


def _poll_timeout(env: _Env, prepared: _Prepared) -> PublishOutcome:
    """The container is still processing after the polling budget: hand over to reconciliation."""
    with env.session_factory() as session:
        ctx, item, op, _ = _locked(session, prepared)
        outcome = (
            mark_unknown(session, env.clock, ctx, item, op)
            if op.status == "in_progress"
            else _skip(f"operation_{op.status}")
        )
        session.commit()
    return outcome


def _fail_now(env: _Env, prepared: _Prepared, code: str, detail: str | None) -> PublishOutcome:
    with env.session_factory() as session:
        ctx, item, op, _ = _locked(session, prepared)
        outcome = _fail(session, env.clock, ctx, item, op, code, detail)
        session.commit()
    return outcome


def _fail(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    item: ContentItem,
    op: Operation,
    code: str,
    detail: str | None = None,
) -> PublishOutcome:
    if op.status != "in_progress" and op.status != "outcome_unknown":
        return _skip(f"operation_{op.status}")
    set_operation(clock, op, "fail", code=code)
    op.last_error_detail = detail
    transitions.apply(session, clock, ctx, item, "fail", reason=code)
    content_notifications.notify(
        session, clock, ctx, item, content_notifications.FAILED, reason=code
    )
    return PublishOutcome("failed", error_code=code)


def _record_error(
    env: _Env, prepared: _Prepared, error: Exception, phase: Literal["create", "status", "publish"]
) -> PublishOutcome:
    """Map a provider error to the ledger and the item (workflows.md section G.1)."""
    with env.session_factory() as session:
        ctx, item, op, account = _locked(session, prepared)
        if op.status != "in_progress":
            return _skip(f"operation_{op.status}")
        outcome = _map_error(session, env, ctx, item, op, account, error, phase)
        session.commit()
    return outcome


def _map_error(
    session: Session,
    env: _Env,
    ctx: WorkspaceContext,
    item: ContentItem,
    op: Operation,
    account: SocialAccount,
    error: Exception,
    phase: Literal["create", "status", "publish"],
) -> PublishOutcome:
    clock = env.clock
    now = clock.now()
    if phase == "publish" and (
        isinstance(error, ProviderOutcomeUnknown)
        or (
            isinstance(error, ProviderInvalidRequest)
            and error.request_code in AMBIGUOUS_PUBLISH_CODES
        )
        or not isinstance(error, ProviderError)
    ):
        # The request may have been accepted (or anything unexpected happened after it): find
        # out, never publish again blindly.
        if not isinstance(error, ProviderError):
            log.error(
                "publish_unexpected_error", error=type(error).__name__, operation_id=str(op.id)
            )
        return mark_unknown(session, clock, ctx, item, op)

    if isinstance(error, ProviderInvalidRequest):
        code = "MEDIA_REJECTED" if error.request_code == "MEDIA_REJECTED" else "PROVIDER_REJECTED"
        return _fail(session, clock, ctx, item, op, code, error.request_code)

    if isinstance(error, ProviderPermissionError):
        health.handle_permission_error(
            session, clock, ctx, account, capability_for(item.content_type)
        )
        return _fail(session, clock, ctx, item, op, "CAPABILITY_MISSING")

    if isinstance(error, ProviderAuthError):
        # Not published, and not a content problem: the item waits for the owner (G1).
        health.handle_auth_error(session, clock, ctx, account)
        set_operation(clock, op, "fail", code="ACCOUNT_NEEDS_REAUTH")
        transitions.apply(session, clock, ctx, item, "hold", reason=ACCOUNT_UNAVAILABLE)
        content_notifications.notify(
            session, clock, ctx, item, content_notifications.ON_HOLD, reason=ACCOUNT_UNAVAILABLE
        )
        return PublishOutcome("held", error_code="ACCOUNT_NEEDS_REAUTH")

    # Transient, rate limited, or an unclassified failure before anything visible happened
    # (creating a container and reading its status have no visible effect, so even an
    # ``OutcomeUnknown`` there is only a failed attempt).
    retry_after = 0.0
    if isinstance(error, ProviderRateLimited):
        code = error.code  # not a health failure
        retry_after = float(error.retry_after_s or 0)
    else:
        if not isinstance(error, ProviderError):
            log.error(
                "publish_unexpected_error", error=type(error).__name__, operation_id=str(op.id)
            )
        code = error.code if isinstance(error, ProviderTransientError) else "PROVIDER_UNAVAILABLE"
        health.record_transient_failure(account, code)
    backoff = PUBLISH_BACKOFF[min(max(op.attempts, 1), len(PUBLISH_BACKOFF)) - 1]
    delay = max(float(backoff), retry_after)
    out_of_time = op.deadline_at is not None and now + timedelta(seconds=delay) >= op.deadline_at
    if op.attempts >= op.max_attempts or out_of_time:
        return _fail(session, clock, ctx, item, op, code)
    set_operation(clock, op, "retry", code=code)
    op.next_attempt_at = now + timedelta(seconds=delay)
    transitions.apply(session, clock, ctx, item, "retry", reason=code)
    if env.requeue_on_retry:
        enqueue(
            session,
            "publish_content",
            PublishContentPayload(content_id=item.id, version=item.version),
            workspace_id=item.workspace_id,
            correlation_id=op.correlation_id,
            run_at=op.next_attempt_at,
            dedup_key=publish_job_key(item.id, item.version),
            clock=clock,
        )
    return PublishOutcome("retry", error_code=code, retry_after_seconds=delay)


# --- reconciliation -------------------------------------------------------------------------


def _conclude(
    session: Session,
    env: _Env,
    workspace_id: uuid.UUID,
    operation_id: uuid.UUID,
    had_container: bool,
    status_code: str | None,
    media_id: str | None,
    media: MediaInfo | None,
) -> _Prepared | PublishOutcome:
    clock = env.clock
    now = clock.now()
    ctx = system_context(session, workspace_id, "operations.reconcile")
    op_row = _operation_by_id(session, workspace_id, operation_id)
    item = _item(session, workspace_id, op_row.subject_id, lock=True) if op_row else None
    op = _operation_by_id(session, workspace_id, operation_id, lock=True)
    if ctx is None or op is None or item is None:
        return _skip("resolved")
    if op.status != "outcome_unknown":
        return _skip("resolved")  # somebody else got there first
    account = queries.get_account_in_workspace(
        session, workspace_id, op.social_account_id, lock=True
    )
    if account is None:
        return _skip("account_missing")

    if status_code == "PUBLISHED":  # the post is out, whatever the deadline says
        _record_published(
            session, clock, ctx, item, op, account,
            media_id=media_id,
            permalink=media.permalink if media else None,
            published_at=(media.timestamp if media and media.timestamp else now),
            via="reconcile",
        )  # fmt: skip
        return PublishOutcome("published", detail="reconciled")

    deadline = op.deadline_at
    past_deadline = deadline is not None and now >= deadline

    def finish(code: str) -> PublishOutcome:
        set_operation(clock, op, "fail", code=code)
        if item.status == "publishing":
            transitions.apply(session, clock, ctx, item, "fail", reason=code)
            content_notifications.notify(
                session, clock, ctx, item, content_notifications.FAILED, reason=code
            )
        audit.record(
            session,
            ctx,
            "operation.reconciled",
            "operation",
            op.id,
            {"content_id": item.id, "outcome": "failed", "code": code},
            is_simulated=op.is_simulated,
            clock=clock,
        )
        return PublishOutcome("failed", error_code=code)

    def later() -> PublishOutcome:
        return PublishOutcome("rescheduled", run_at=now + RECONCILE_DELAY)

    if had_container and status_code is None:  # unreadable: the post may exist
        return finish("OUTCOME_UNCONFIRMED") if past_deadline else later()
    if status_code == "ERROR":
        return finish("MEDIA_REJECTED")
    if past_deadline:  # proven not published, and too late to do it now
        return finish("PUBLISH_DEADLINE_PASSED")
    if status_code == "IN_PROGRESS":
        return later()

    # FINISHED (proven unpublished), EXPIRED (never published, needs a new container) or no
    # container at all (nothing was ever created): publishing again is safe.
    if op.attempts >= op.max_attempts:
        return finish("PROVIDER_UNAVAILABLE")
    if status_code != "FINISHED":
        op.provider_ref = {k: v for k, v in op.provider_ref.items() if k != "container_id"}
    asset = session.scalars(
        select(MediaAsset).where(
            MediaAsset.workspace_id == workspace_id, MediaAsset.id == item.media_asset_id
        )
    ).one_or_none()
    if asset is None or asset.status != "ready":
        return finish("MEDIA_REJECTED")
    set_operation(clock, op, "start")  # outcome_unknown -> in_progress: publishing only
    op.attempts += 1
    op.started_at = now
    op.next_attempt_at = None
    audit.record(
        session,
        ctx,
        "operation.reconciled",
        "operation",
        op.id,
        {"content_id": item.id, "outcome": "retry", "container": status_code or "none"},
        is_simulated=op.is_simulated,
        clock=clock,
    )
    return _prepared(item, op, account, asset)
