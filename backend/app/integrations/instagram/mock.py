"""``MockInstagramProvider``: a stateful simulator behind the real provider contract (ADR-010).

State lives in the database (``sim_*`` tables) so it survives restarts and is shared by the API
and the worker. It models the documented behaviour: the 24 h customer-service window (derived
from the simulated inbound messages), the 1000-byte text limit, one stored message per
accepted send, and scripted failures. Time comes from the injected clock.

Publishing (Phase 5): ``create_media_container`` reads the JPEG back through the injected
``MediaStorage`` (plan G3), ``sim_containers`` carries the container lifecycle and
``sim_published_media`` is the evidence of what was published (``unique(container_id)``).
"""

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.integrations.instagram import webhook_format
from app.integrations.instagram.base import (
    AccountProfile,
    AccountRef,
    ContainerSpec,
    ContainerStatus,
    MediaInfo,
    NormalizedInboundEvent,
    OutboundMessageInfo,
    ProviderKind,
    PublishingQuota,
    SendResult,
    TokenInfo,
)
from app.integrations.instagram.errors import (
    ProviderAuthError,
    ProviderInvalidRequest,
    ProviderOutcomeUnknown,
    ProviderPermissionError,
    ProviderRateLimited,
    ProviderTransientError,
    ProviderWindowClosed,
)
from app.integrations.instagram.models import (
    SimContainer,
    SimFailureRule,
    SimInboundMessage,
    SimPublishedMedia,
    SimSentMessage,
    SocialAccount,
)
from app.integrations.storage.base import MediaStorage, StorageObjectNotFound
from app.integrations.storage.local import parse_local_url

MESSAGING_WINDOW = timedelta(hours=24)
MAX_TEXT_BYTES = 1000
DEFAULT_RETRY_AFTER_S = 30
CONTAINER_LIFETIME = timedelta(hours=24)
QUOTA_WINDOW = timedelta(hours=24)
DEFAULT_CONTAINER_DELAY_S = 2
DEFAULT_DAILY_PUBLISH_LIMIT = 50
JPEG_MAGIC = b"\xff\xd8\xff"
PERMALINK_BASE = "https://instagram.example/sim"

SessionFactory = Callable[[], Session]


class MockInstagramProvider:
    kind: ProviderKind = "mock"

    def __init__(
        self,
        session_factory: SessionFactory,
        clock: Clock,
        app_secret: str,
        *,
        storage: MediaStorage | None = None,
        container_delay_s: int = DEFAULT_CONTAINER_DELAY_S,
        daily_publish_limit: int = DEFAULT_DAILY_PUBLISH_LIMIT,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._codec = webhook_format.WebhookCodec(app_secret)
        self._storage = storage
        self._container_delay = timedelta(seconds=container_delay_s)
        self._daily_publish_limit = daily_publish_limit

    # --- webhooks -----------------------------------------------------------------------------

    def verify_signature(self, raw_body: bytes, signature_header: str | None) -> bool:
        return self._codec.verify_signature(raw_body, signature_header)

    def parse_webhook(self, payload: dict[str, Any]) -> list[NormalizedInboundEvent]:
        return self._codec.parse_webhook(payload)

    # --- simulator support (not part of the provider protocol) --------------------------------

    def record_simulated_inbound(
        self, account: AccountRef, sender_id: str, mid: str, received_at: datetime
    ) -> None:
        """Remember that the simulator delivered a customer message, which opens the window."""
        with self._session_factory() as session:
            session.add(
                SimInboundMessage(
                    workspace_id=account.workspace_id,
                    social_account_id=account.social_account_id,
                    sender_id=sender_id,
                    mid=mid,
                    received_at=received_at,
                )
            )
            session.commit()

    # --- failure injection --------------------------------------------------------------------

    def _consume_failure(self, account: AccountRef, operation: str) -> SimFailureRule | None:
        """Take the next matching scripted failure (decrementing ``remaining``), if any.

        Done in its own short transaction so a failing call still consumes its rule.
        """
        with self._session_factory() as session:
            stmt = (
                select(SimFailureRule)
                .where(
                    SimFailureRule.workspace_id == account.workspace_id,
                    SimFailureRule.social_account_id == account.social_account_id,
                    SimFailureRule.operation.in_((operation, "any")),
                    (SimFailureRule.remaining.is_(None)) | (SimFailureRule.remaining > 0),
                )
                .order_by(SimFailureRule.created_at, SimFailureRule.id)
                .limit(1)
                .with_for_update()
            )
            rule = session.scalars(stmt).first()
            if rule is None:
                return None
            if rule.remaining is not None:
                rule.remaining -= 1
            session.commit()
            session.expunge(rule)
            return rule

    @staticmethod
    def reauthorize(session: Session, account: SocialAccount) -> int:
        """Simulator support: the owner connected the account again with a fresh token, so the
        scripted "token revoked" failures of this account end. Runs in the caller's transaction
        and does not commit; returns how many rules were removed."""
        removed = session.execute(
            delete(SimFailureRule).where(
                SimFailureRule.workspace_id == account.workspace_id,
                SimFailureRule.social_account_id == account.id,
                SimFailureRule.mode == "auth_revoked",
            )
        )
        return int(removed.rowcount or 0)  # type: ignore[attr-defined]

    @staticmethod
    def _raise_for(rule: SimFailureRule) -> None:
        mode = rule.mode
        if mode == "transient":
            raise ProviderTransientError("simulated transient failure")
        if mode == "rate_limited":
            raise ProviderRateLimited(rule.retry_after_s or DEFAULT_RETRY_AFTER_S)
        if mode == "auth_revoked":
            raise ProviderAuthError("simulated revoked token")
        if mode == "permission_missing":
            raise ProviderPermissionError("simulated missing permission")
        if mode == "window_closed":
            raise ProviderWindowClosed("simulated closed window")
        if mode == "invalid_media":
            raise ProviderInvalidRequest("MEDIA_REJECTED", "simulated invalid media")
        raise ProviderTransientError(f"unknown simulated failure mode {mode}")

    def should_emit_echo(self, account: AccountRef) -> bool:
        """Simulator support: whether the "Instagram" echoes a message it accepted. A scripted
        ``echo`` failure rule suppresses it (and is consumed), so the no-echo path can be tried."""
        return self._consume_failure(account, "echo") is None

    # --- reads --------------------------------------------------------------------------------

    def get_account_profile(self, account: AccountRef) -> AccountProfile:
        rule = self._consume_failure(account, "profile")
        if rule is not None:
            self._raise_for(rule)
        with self._session_factory() as session:
            row = session.get(SocialAccount, account.social_account_id)
            username = row.username if row is not None else None
        return AccountProfile(external_account_id=account.external_account_id, username=username)

    def find_recent_outbound(
        self, account: AccountRef, recipient_id: str, since: datetime
    ) -> list[OutboundMessageInfo]:
        rule = self._consume_failure(account, "lookup")
        if rule is not None:
            self._raise_for(rule)
        with self._session_factory() as session:
            rows = session.scalars(
                select(SimSentMessage)
                .where(
                    SimSentMessage.workspace_id == account.workspace_id,
                    SimSentMessage.social_account_id == account.social_account_id,
                    SimSentMessage.recipient_id == recipient_id,
                    SimSentMessage.sent_at >= since,
                )
                .order_by(SimSentMessage.sent_at, SimSentMessage.id)
            ).all()
            return [
                OutboundMessageInfo(
                    message_id=r.message_id,
                    recipient_id=r.recipient_id,
                    text=r.text,
                    sent_at=r.sent_at,
                )
                for r in rows
            ]

    def _find_container(
        self, session: Session, account: AccountRef, container_id: str, *, lock: bool = False
    ) -> SimContainer:
        stmt = select(SimContainer).where(
            SimContainer.workspace_id == account.workspace_id,
            SimContainer.social_account_id == account.social_account_id,
            SimContainer.container_id == container_id,
        )
        container = session.scalars(stmt.with_for_update() if lock else stmt).one_or_none()
        if container is None:
            raise ProviderInvalidRequest("CONTAINER_NOT_FOUND")
        return container

    def _effective_status(self, container: SimContainer) -> ContainerStatus:
        """What the provider would report now. Only ``ERROR`` and ``PUBLISHED`` are stored; a
        container that was not published expires 24 h after creation, and one that is still
        ``IN_PROGRESS`` finishes at ``ready_at``."""
        if container.status == "PUBLISHED":
            return ContainerStatus("PUBLISHED", media_id=container.published_media_id)
        now = self._clock.now()
        if now >= container.expires_at:
            return ContainerStatus("EXPIRED")
        if container.status == "ERROR":
            return ContainerStatus("ERROR", "simulated media processing error")
        if now >= container.ready_at:
            return ContainerStatus("FINISHED")
        return ContainerStatus("IN_PROGRESS")

    def get_container_status(self, account: AccountRef, container_id: str) -> ContainerStatus:
        rule = self._consume_failure(account, "container_status")
        if rule is not None and rule.mode != "invalid_media":
            self._raise_for(rule)
        with self._session_factory() as session:
            container = self._find_container(session, account, container_id, lock=True)
            if rule is not None and container.status == "IN_PROGRESS":
                container.status = "ERROR"  # processing failed, and it stays failed
                session.commit()
            return self._effective_status(container)

    def get_media(self, account: AccountRef, media_id: str) -> MediaInfo:
        with self._session_factory() as session:
            media = session.scalars(
                select(SimPublishedMedia).where(
                    SimPublishedMedia.workspace_id == account.workspace_id,
                    SimPublishedMedia.social_account_id == account.social_account_id,
                    SimPublishedMedia.media_id == media_id,
                )
            ).one_or_none()
            if media is None:
                raise ProviderInvalidRequest("MEDIA_NOT_FOUND")
            return MediaInfo(
                media_id=media.media_id, permalink=media.permalink, timestamp=media.published_at
            )

    def _published_since(
        self, session: Session, account: AccountRef, since: datetime
    ) -> list[datetime]:
        return list(
            session.scalars(
                select(SimPublishedMedia.published_at)
                .where(
                    SimPublishedMedia.workspace_id == account.workspace_id,
                    SimPublishedMedia.social_account_id == account.social_account_id,
                    SimPublishedMedia.published_at > since,
                )
                .order_by(SimPublishedMedia.published_at)
            )
        )

    def get_publishing_quota(self, account: AccountRef) -> PublishingQuota:
        with self._session_factory() as session:
            used = len(self._published_since(session, account, self._clock.now() - QUOTA_WINDOW))
        return PublishingQuota(
            used=used,
            limit=self._daily_publish_limit,
            window_hours=int(QUOTA_WINDOW.total_seconds() // 3600),
        )

    # --- side effects (operations only, INV-15) -----------------------------------------------

    def _window_open(self, session: Session, account: AccountRef, recipient_id: str) -> bool:
        last = session.scalar(
            select(SimInboundMessage.received_at)
            .where(
                SimInboundMessage.workspace_id == account.workspace_id,
                SimInboundMessage.social_account_id == account.social_account_id,
                SimInboundMessage.sender_id == recipient_id,
            )
            .order_by(SimInboundMessage.received_at.desc())
            .limit(1)
        )
        return last is not None and self._clock.now() < last + MESSAGING_WINDOW

    def send_text_message(self, account: AccountRef, recipient_id: str, text: str) -> SendResult:
        rule = self._consume_failure(account, "send")
        if rule is not None and rule.mode != "timeout_after_success":
            self._raise_for(rule)
        if not text.strip():
            raise ProviderInvalidRequest("EMPTY_TEXT")
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ProviderInvalidRequest("TEXT_TOO_LONG")
        with self._session_factory() as session:
            if not self._window_open(session, account, recipient_id):
                raise ProviderWindowClosed()
            message_id = f"mock-mid-{uuid.uuid4().hex}"
            session.add(
                SimSentMessage(
                    workspace_id=account.workspace_id,
                    social_account_id=account.social_account_id,
                    message_id=message_id,
                    recipient_id=recipient_id,
                    text=text,
                    sent_at=self._clock.now(),
                )
            )
            session.commit()
        if rule is not None:  # timeout_after_success: the effect happened, the answer is lost
            raise ProviderOutcomeUnknown("simulated timeout after the message was accepted")
        return SendResult(message_id=message_id)

    def _check_fetchable_jpeg(self, image_url: str) -> None:
        """Resolve the ``localmedia:`` reference through the storage and check the JPEG magic
        bytes, as Instagram fetches the URL and refuses anything that is not a JPEG."""
        if self._storage is None:
            raise RuntimeError("the mock provider was built without a media storage")
        try:
            key, expires = parse_local_url(image_url)
        except ValueError as exc:
            raise ProviderInvalidRequest("MEDIA_REJECTED", "image URL is not fetchable") from exc
        if self._clock.now().timestamp() >= expires:
            raise ProviderInvalidRequest("MEDIA_REJECTED", "image URL has expired")
        try:
            with self._storage.open(key) as handle:
                head = handle.read(len(JPEG_MAGIC))
        except StorageObjectNotFound as exc:
            raise ProviderInvalidRequest("MEDIA_REJECTED", "image not found") from exc
        if head != JPEG_MAGIC:
            raise ProviderInvalidRequest("MEDIA_REJECTED", "image is not a JPEG")

    def create_media_container(self, account: AccountRef, spec: ContainerSpec) -> str:
        rule = self._consume_failure(account, "create_container")
        if rule is not None and rule.mode != "timeout_after_success":
            self._raise_for(rule)
        if spec.media_type == "STORIES" and spec.caption:
            raise ProviderInvalidRequest("CAPTION_NOT_ALLOWED", "a story has no caption")
        self._check_fetchable_jpeg(spec.image_url)
        now = self._clock.now()
        container_id = f"mock-container-{uuid.uuid4().hex}"
        with self._session_factory() as session:
            session.add(
                SimContainer(
                    workspace_id=account.workspace_id,
                    social_account_id=account.social_account_id,
                    container_id=container_id,
                    media_type=spec.media_type,
                    media_url=spec.image_url,
                    caption=spec.caption,
                    status="IN_PROGRESS",
                    ready_at=now + self._container_delay,
                    expires_at=now + CONTAINER_LIFETIME,
                )
            )
            session.commit()
        if rule is not None:  # timeout_after_success: the container exists, the answer is lost
            raise ProviderOutcomeUnknown("simulated timeout after the container was created")
        return container_id

    def publish_container(self, account: AccountRef, container_id: str) -> str:
        rule = self._consume_failure(account, "publish")
        if rule is not None and rule.mode != "timeout_after_success":
            self._raise_for(rule)
        media_id = f"mock-media-{uuid.uuid4().hex}"
        with self._session_factory() as session:
            container = self._find_container(session, account, container_id, lock=True)
            status = self._effective_status(container).status_code
            if status != "FINISHED":
                raise ProviderInvalidRequest(
                    "CONTAINER_NOT_READY" if status == "IN_PROGRESS" else f"CONTAINER_{status}",
                    f"container is {status}, not FINISHED",
                )
            now = self._clock.now()
            published = self._published_since(session, account, now - QUOTA_WINDOW)
            if len(published) >= self._daily_publish_limit:
                retry_after = int((published[0] + QUOTA_WINDOW - now).total_seconds())
                raise ProviderRateLimited(max(retry_after, 1), "publishing limit reached")
            container.status = "PUBLISHED"
            container.published_media_id = media_id
            session.add(
                SimPublishedMedia(
                    workspace_id=account.workspace_id,
                    social_account_id=account.social_account_id,
                    media_id=media_id,
                    container_id=container_id,
                    permalink=f"{PERMALINK_BASE}/{media_id}",
                    published_at=now,
                )
            )
            try:
                session.commit()
            except IntegrityError as exc:  # unique(container_id): a container publishes once
                raise ProviderInvalidRequest(
                    "CONTAINER_PUBLISHED", "container is already published"
                ) from exc
        if rule is not None:  # timeout_after_success: the post exists, the answer is lost
            raise ProviderOutcomeUnknown("simulated timeout after the media was published")
        return media_id

    def refresh_token(self, account: AccountRef) -> TokenInfo:
        raise NotImplementedError("the mock has no token to refresh")
