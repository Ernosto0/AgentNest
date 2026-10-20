"""A harness for the publish executor tests (P5-06).

It schedules real content items through the service (the same path the API uses), runs the
executor against the simulated Instagram, and checks the invariants that every publish test
must check: how many posts the simulator really holds (INV-06), and that **no transaction is
open while the executor sleeps or calls the provider** (a session factory that remembers every
session it handed out).
"""

import io
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.audit.models import AuditLog
from app.content import service
from app.content.models import ContentItem, MediaAsset
from app.content.service import ScheduleRequest
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.identity.models import User, Workspace
from app.integrations.instagram.base import InstagramProvider
from app.integrations.instagram.models import (
    SimContainer,
    SimFailureRule,
    SimPublishedMedia,
    SocialAccount,
)
from app.integrations.instagram.registry import get_provider
from app.integrations.storage.base import build_key
from app.integrations.storage.local import LocalMediaStorage
from app.jobs.models import Job
from app.jobs.testing import run_due_jobs
from app.notifications.models import Notification
from app.operations import publish
from app.operations.models import Operation
from tests.factories import knowledge_ctx

MOCK_CAPABILITIES = {"messaging": True, "publish_feed_image": True, "publish_story_image": True}
TRACKED = frozenset(
    {
        "get_publishing_quota",
        "create_media_container",
        "get_container_status",
        "publish_container",
        "get_media",
    }
)


class Crash(BaseException):  # noqa: N818  (it stands for a killed process, not for an error)
    """A worker that dies: not an ``Exception``, so nothing in the executor can catch it."""


class GuardedFactory:
    """A session factory that remembers its sessions, so a test can ask whether any of them has
    a transaction open (a provider call or a sleep in one would hold a lock for its duration)."""

    def __init__(self, inner: sessionmaker[Session]) -> None:
        self._inner = inner
        self.sessions: list[Session] = []

    def __call__(self) -> Session:
        session = self._inner()
        self.sessions.append(session)
        return session

    def open_transactions(self) -> int:
        return sum(1 for s in self.sessions if s.in_transaction())


class GuardedProvider:
    """Wraps the provider: records every call and asserts that no transaction is open when the
    executor makes it. ``before`` hooks run first (to simulate a crash, or a cancel)."""

    def __init__(
        self,
        inner: InstagramProvider,
        factory: GuardedFactory,
        calls: list[str],
        before: dict[str, Callable[[], None]],
    ) -> None:
        self._inner = inner
        self._factory = factory
        self._calls = calls
        self._before = before

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._inner, name)
        if name not in TRACKED:
            return target

        def call(*args: Any, **kwargs: Any) -> Any:
            assert self._factory.open_transactions() == 0, f"a transaction was open during {name}"
            self._calls.append(name)
            hook = self._before.pop(name, None)
            if hook is not None:
                hook()
            return target(*args, **kwargs)

        return call


class Publishing:
    def __init__(
        self,
        session: Session,
        factory: sessionmaker[Session],
        clock: FrozenClock,
        settings: Settings,
        workspace: Workspace,
        owner: User,
        *,
        staff: User | None = None,
    ) -> None:
        self.session = session
        self.clock = clock
        self.settings = settings
        self.workspace = workspace
        self.owner = owner
        self.factory = GuardedFactory(factory)
        self.ctx: WorkspaceContext = knowledge_ctx(workspace, owner, "owner")
        self.storage = LocalMediaStorage(settings.media_root, clock)
        self.calls: list[str] = []
        self.before: dict[str, Callable[[], None]] = {}
        self.sleeps: list[float] = []
        self.account = SocialAccount(
            workspace_id=workspace.id,
            platform="instagram",
            provider_kind="mock",
            external_account_id=f"mock-{workspace.id.hex[:10]}",
            username="golkent.demo",
            status="connected",
            capabilities=dict(MOCK_CAPABILITIES),
            connected_at=clock.now(),
        )
        session.add(self.account)
        session.commit()
        self.provider: InstagramProvider = GuardedProvider(  # type: ignore[assignment]
            get_provider("mock", settings=settings, session_factory=self.factory, clock=clock),
            self.factory,
            self.calls,
            self.before,
        )

    # --- building items ---------------------------------------------------------------------

    def media(self, size: tuple[int, int] = (1080, 1350)) -> MediaAsset:
        out = io.BytesIO()
        Image.new("RGB", size, "navy").save(out, "JPEG")
        key = build_key(self.workspace.id, uuid.uuid4(), self.clock.now())
        self.storage.put(key, io.BytesIO(out.getvalue()), "image/jpeg")
        asset = MediaAsset(
            workspace_id=self.workspace.id,
            storage_backend="local",
            storage_key=key,
            mime_type="image/jpeg",
            byte_size=len(out.getvalue()),
            width=size[0],
            height=size[1],
            sha256="b" * 64,
            status="ready",
            created_by_user_id=self.owner.id,
        )
        self.session.add(asset)
        self.session.commit()
        return asset

    def draft(self, content_type: str = "feed_image", caption: str | None = None) -> ContentItem:
        asset = self.media((1080, 1920) if content_type == "story_image" else (1080, 1350))
        now = self.clock.now()
        item = ContentItem(
            workspace_id=self.workspace.id,
            content_type=content_type,
            status="draft",
            version=1,
            title="Haftalık paylaşım",
            caption=None if content_type == "story_image" else (caption or "Cuma günü görüşürüz"),
            overlay_text_suggestions=[],
            media_asset_id=asset.id,
            validation={"passed": True, "issues": [], "stale": False},
            created_by_user_id=self.owner.id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(item)
        self.session.commit()
        return item

    def schedule(
        self,
        item: ContentItem,
        when: ScheduleRequest | None = None,
    ) -> ContentItem:
        """Submit with self-approval (the owner), by default for "now". The submit-time quota
        forecast is not what these tests exercise, so it never gets in the way."""
        service.submit(
            self.session,
            self.clock,
            self.settings.model_copy(update={"publish_daily_limit": 1000}),
            self.ctx,
            item.id,
            schedule=when or ScheduleRequest(publish_now=True),
            self_approve=True,
            expected_version=item.version,
        )
        return self.reload(item)

    def scheduled(self, content_type: str = "feed_image", **kwargs: Any) -> ContentItem:
        return self.schedule(self.draft(content_type), **kwargs)

    # --- running ----------------------------------------------------------------------------

    def sleeper(self, seconds: float) -> None:
        assert self.factory.open_transactions() == 0, "a transaction was open during sleep"
        self.sleeps.append(seconds)
        self.clock.advance(seconds=seconds)

    def execute(
        self, item: ContentItem, *, version: int | None = None, heartbeats: list[int] | None = None
    ) -> publish.PublishOutcome:
        def heartbeat() -> None:
            assert self.factory.open_transactions() == 0, "a transaction was open at a heartbeat"
            if heartbeats is not None:
                heartbeats.append(1)

        return publish.execute_publish(
            self.factory,  # type: ignore[arg-type]
            self.clock,
            self.settings,
            self.workspace.id,
            item.id,
            version if version is not None else item.version,
            provider=self.provider,
            sleep=self.sleeper,
            heartbeat=heartbeat,
        )

    def reconcile(self, operation: Operation) -> publish.PublishOutcome:
        return publish.reconcile_publish(
            self.factory,  # type: ignore[arg-type]
            self.clock,
            self.settings,
            self.workspace.id,
            operation.id,
            provider=self.provider,
            sleep=self.sleeper,
        )

    def process(self) -> int:
        """Run what is due the way the worker would (the job handlers read ``get_settings``,
        which the ``pub`` fixture points at this harness's settings)."""
        return run_due_jobs(self.clock, session_factory=self.factory)  # type: ignore[arg-type]

    # --- the simulator ------------------------------------------------------------------------

    def fail(
        self,
        operation: str,
        mode: str,
        *,
        remaining: int | None = 1,
        retry_after: int | None = None,
    ) -> None:
        self.session.add(
            SimFailureRule(
                workspace_id=self.workspace.id,
                social_account_id=self.account.id,
                operation=operation,
                mode=mode,
                remaining=remaining,
                retry_after_s=retry_after,
            )
        )
        self.session.commit()

    def posts(self) -> list[SimPublishedMedia]:
        """What the simulated Instagram really holds: INV-06 counts these."""
        self.session.expire_all()
        return list(
            self.session.scalars(select(SimPublishedMedia).order_by(SimPublishedMedia.published_at))
        )

    def containers(self) -> list[SimContainer]:
        self.session.expire_all()
        return list(self.session.scalars(select(SimContainer).order_by(SimContainer.created_at)))

    # --- reading state ------------------------------------------------------------------------

    def reload(self, item: ContentItem) -> ContentItem:
        self.session.expire_all()
        fresh = self.session.get(ContentItem, item.id)
        assert fresh is not None
        return fresh

    def operation(self, item: ContentItem, version: int | None = None) -> Operation | None:
        self.session.expire_all()
        return self.session.scalars(
            select(Operation).where(
                Operation.idempotency_key == f"publish:{item.id}:v{version or item.version}"
            )
        ).one_or_none()

    def jobs(self, job_type: str) -> list[Job]:
        self.session.expire_all()
        return list(
            self.session.scalars(
                select(Job).where(Job.job_type == job_type).order_by(Job.created_at, Job.id)
            )
        )

    def notifications(self, kind: str) -> list[Notification]:
        self.session.expire_all()
        return list(self.session.scalars(select(Notification).where(Notification.type == kind)))

    def owner_note(self, kind: str) -> Notification:
        """The one notification of ``kind`` the owner got (every approver gets one)."""
        (note,) = [n for n in self.notifications(kind) if n.recipient_user_id == self.owner.id]
        return note

    def audits(self, action: str) -> list[AuditLog]:
        self.session.expire_all()
        return list(self.session.scalars(select(AuditLog).where(AuditLog.action == action)))

    def account_now(self) -> SocialAccount:
        self.session.expire_all()
        account = self.session.get(SocialAccount, self.account.id)
        assert account is not None
        return account

    def at(self, hour: int, minute: int = 0) -> datetime:
        return datetime(2026, 1, 15, hour, minute, tzinfo=UTC)

    def advance_to(self, when: datetime) -> None:
        self.clock.advance(when - self.clock.now())

    def advance_past(self, run_at: datetime | None) -> None:
        assert run_at is not None
        self.clock.advance(max(run_at - self.clock.now(), timedelta()))
