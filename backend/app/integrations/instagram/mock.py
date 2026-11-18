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
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, ClassVar

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.integrations.instagram import webhook_format
from app.integrations.instagram.base import (
    MOCK_PRIVATE_REPLY_WINDOW,
    SUPPORTED_MESSAGE_TAGS,
    AccountInsightsMetric,
    AccountProfile,
    AccountRef,
    AudienceData,
    ContainerSpec,
    ContainerStatus,
    MediaInfo,
    MediaInsightsData,
    NormalizedInboundEvent,
    OutboundMessageInfo,
    PrivateReplyResult,
    ProfileDetails,
    ProviderKind,
    PublicEffectResult,
    PublishingQuota,
    RecentCaption,
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
HUMAN_AGENT_WINDOW = timedelta(days=7)  # a message with the HUMAN_AGENT tag
MAX_TEXT_BYTES = 1000
DEFAULT_RETRY_AFTER_S = 30
CONTAINER_LIFETIME = timedelta(hours=24)
QUOTA_WINDOW = timedelta(hours=24)
DEFAULT_CONTAINER_DELAY_S = 2
DEFAULT_REEL_PROCESSING_S = 20
DEFAULT_DAILY_PUBLISH_LIMIT = 50
JPEG_MAGIC = b"\xff\xd8\xff"
FAKE_VIDEO_MAGIC = b"FAKEVIDEO1 "
PERMALINK_BASE = "https://instagram.example/sim"

SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class ProfileFixture:
    biography: str | None
    website: str | None
    name: str | None
    captions: list[tuple[timedelta, str]]


DEFAULT_PROFILE = ProfileFixture(
    "Gölkent Fitness 💪\nAylık üyelik 6.000 TL\nTel: 0555 123 45 67\nBucak / Burdur",
    "https://golkent-fitness.example",
    "Gölkent Fitness",
    [
        (timedelta(days=5), "Yeni sezon başladı! 3 aylık üyelik 16.500 TL"),
        (timedelta(days=40), "Hafta sonu grup dersleri herkese açık."),
        (timedelta(days=200), "Yaz kampanyası: aylık üyelik 4.500 TL"),
    ],
)


class MockInstagramProvider:
    kind: ProviderKind = "mock"
    _profile_fixtures: ClassVar[dict[uuid.UUID, ProfileFixture]] = {}

    @classmethod
    def set_profile_fixture(
        cls, social_account_id: uuid.UUID, fixture: ProfileFixture | None
    ) -> None:
        """Process-local, test-only overrides; the dev stack uses DEFAULT_PROFILE."""
        if fixture is None:
            cls._profile_fixtures.pop(social_account_id, None)
        else:
            cls._profile_fixtures[social_account_id] = fixture

    @classmethod
    def clear_profile_fixtures(cls) -> None:
        cls._profile_fixtures.clear()

    def get_profile_details(self, account: AccountRef) -> ProfileDetails:
        rule = self._consume_failure(account, "profile")
        if rule is not None:
            self._raise_for(rule)
        with self._session_factory() as session:
            row = session.get(SocialAccount, account.social_account_id)
            username = (
                row.username
                if row is not None and row.workspace_id == account.workspace_id
                else None
            )
        fixture = self._profile_fixtures.get(account.social_account_id, DEFAULT_PROFILE)
        return ProfileDetails(
            account.external_account_id, username, fixture.name, fixture.biography, fixture.website
        )

    def list_recent_captions(self, account: AccountRef, limit: int) -> list[RecentCaption]:
        rule = self._consume_failure(account, "profile")
        if rule is not None:
            self._raise_for(rule)
        fixture = self._profile_fixtures.get(account.social_account_id, DEFAULT_PROFILE)
        captions = [
            RecentCaption(
                f"profile-{account.social_account_id}-{i}",
                text,
                self._clock.now() - ago,
                f"{PERMALINK_BASE}/profile-{account.social_account_id}-{i}",
                "IMAGE",
            )
            for i, (ago, text) in enumerate(fixture.captions)
        ]
        captions.sort(
            key=lambda item: item.posted_at.timestamp() if item.posted_at else float("-inf"),
            reverse=True,
        )
        return captions[: min(max(limit, 1), 50)]

    def __init__(
        self,
        session_factory: SessionFactory,
        clock: Clock,
        app_secret: str,
        *,
        storage: MediaStorage | None = None,
        container_delay_s: int = DEFAULT_CONTAINER_DELAY_S,
        reel_processing_s: int = DEFAULT_REEL_PROCESSING_S,
        daily_publish_limit: int = DEFAULT_DAILY_PUBLISH_LIMIT,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._codec = webhook_format.WebhookCodec(app_secret, synthetic_comments=True)
        self._storage = storage
        self._container_delay = timedelta(seconds=container_delay_s)
        self._reel_delay = timedelta(seconds=reel_processing_s)
        self._daily_publish_limit = daily_publish_limit

    # --- webhooks -----------------------------------------------------------------------------

    def verify_signature(self, raw_body: bytes, signature_header: str | None) -> bool:
        return self._codec.verify_signature(raw_body, signature_header)

    def parse_webhook(self, payload: dict[str, Any]) -> list[NormalizedInboundEvent]:
        return self._codec.parse_webhook(payload)

    # --- simulator support (not part of the provider protocol) --------------------------------

    def record_simulated_comment(self, account: AccountRef, value: dict[str, Any]) -> None:
        """Persist provisional remote state before delivering its signed notification."""
        from app.comments.codec import CommentEvent
        from app.comments.models import SimPublicComment

        event = CommentEvent.model_validate(value)
        with self._session_factory() as session:
            social = session.scalar(
                select(SocialAccount)
                .where(
                    SocialAccount.id == account.social_account_id,
                    SocialAccount.workspace_id == account.workspace_id,
                    SocialAccount.provider_kind == "mock",
                )
                .with_for_update()
            )
            if social is None or social.status == "disconnected":
                raise ProviderInvalidRequest("ACCOUNT_NOT_CONNECTED")
            row = session.scalar(
                select(SimPublicComment).where(
                    SimPublicComment.workspace_id == account.workspace_id,
                    SimPublicComment.social_account_id == account.social_account_id,
                    SimPublicComment.external_id == event.id,
                )
            )
            if row is None:
                row = SimPublicComment(
                    workspace_id=account.workspace_id,
                    social_account_id=account.social_account_id,
                    external_id=event.id,
                    value=None,
                    updated_at=self._clock.now(),
                )
                session.add(row)
            if row.value is None or (
                row.value.get("state") != "deleted" and event.version > row.value.get("version", 0)
            ):
                row.value = event.model_dump(mode="json", by_alias=True)
                row.updated_at = self._clock.now()
            session.commit()

    def simulated_comments(self, account: AccountRef, *, limit: int = 20) -> list[dict[str, Any]]:
        from app.comments.models import SimPublicComment

        if not 1 <= limit <= 50:
            raise ProviderInvalidRequest("INVALID_LIMIT")
        with self._session_factory() as session:
            return [
                row.value
                for row in session.scalars(
                    select(SimPublicComment)
                    .where(
                        SimPublicComment.workspace_id == account.workspace_id,
                        SimPublicComment.social_account_id == account.social_account_id,
                        SimPublicComment.value.is_not(None),
                    )
                    .order_by(SimPublicComment.id)
                    .limit(limit)
                )
                if row.value is not None
            ]

    def perform_comment_effect(
        self,
        account: AccountRef,
        target_id: str,
        effect: str,
        text: str | None,
        operation_key: str,
    ) -> PublicEffectResult:
        """One remote effect with persistent independent evidence and lost-answer injection."""
        from app.comments.models import SimCommentEffect, SimPublicComment

        if effect not in {"reply", "hide", "unhide", "delete"}:
            raise ProviderInvalidRequest("INVALID_COMMENT_ACTION")
        rule = self._consume_failure(account, f"comment_{effect}")
        if rule is not None and rule.mode != "timeout_after_success":
            self._raise_for(rule)
        if effect == "reply" and (not text or not text.strip() or len(text.encode("utf-8")) > 1000):
            raise ProviderInvalidRequest("INVALID_COMMENT_REPLY")
        with self._session_factory() as session:
            prior = session.scalar(
                select(SimCommentEffect).where(
                    SimCommentEffect.social_account_id == account.social_account_id,
                    SimCommentEffect.operation_key == operation_key,
                )
            )
            if prior is not None:
                return PublicEffectResult(
                    prior.provider_id,
                    {"hide": "hidden", "unhide": "visible", "delete": "deleted"}.get(prior.effect),
                )
            target = session.scalar(
                select(SimPublicComment)
                .where(
                    SimPublicComment.workspace_id == account.workspace_id,
                    SimPublicComment.social_account_id == account.social_account_id,
                    SimPublicComment.external_id == target_id,
                )
                .with_for_update()
            )
            if target is None or target.value is None or target.value.get("state") == "deleted":
                raise ProviderInvalidRequest("COMMENT_NOT_FOUND")
            provider_id = f"mock-comment-effect-{uuid.uuid4().hex}"
            if effect != "reply":
                value = dict(target.value)
                value["state"] = {"hide": "hidden", "unhide": "visible", "delete": "deleted"}[
                    effect
                ]
                value["version"] = value.get("version", 0) + 1
                if effect == "delete":
                    value["text"] = None
                target.value, target.updated_at = value, self._clock.now()
            session.add(
                SimCommentEffect(
                    workspace_id=account.workspace_id,
                    social_account_id=account.social_account_id,
                    operation_key=operation_key,
                    target_external_id=target_id,
                    effect=effect,
                    provider_id=provider_id,
                    text=text if effect == "reply" else None,
                    created_at=self._clock.now(),
                )
            )
            session.commit()
        if rule is not None:
            raise ProviderOutcomeUnknown("simulated timeout after public effect")
        return PublicEffectResult(
            provider_id, {"hide": "hidden", "unhide": "visible", "delete": "deleted"}.get(effect)
        )

    def find_comment_effect(
        self, account: AccountRef, operation_key: str
    ) -> PublicEffectResult | None:
        from app.comments.models import SimCommentEffect

        rule = self._consume_failure(account, "comment_lookup")
        if rule is not None:
            self._raise_for(rule)
        with self._session_factory() as session:
            row = session.scalar(
                select(SimCommentEffect).where(
                    SimCommentEffect.workspace_id == account.workspace_id,
                    SimCommentEffect.social_account_id == account.social_account_id,
                    SimCommentEffect.operation_key == operation_key,
                )
            )
            if row is None:
                return None
            return PublicEffectResult(
                row.provider_id,
                {"hide": "hidden", "unhide": "visible", "delete": "deleted"}.get(row.effect),
            )

    def send_private_reply(
        self, account: AccountRef, comment_id: str, text: str, operation_key: str
    ) -> PrivateReplyResult:
        """Provisional one-shot mock rule; this never opens a normal DM window."""
        from app.comments.models import SimPrivateReply, SimPublicComment

        rule = self._consume_failure(account, "comment_private_reply")
        if rule is not None and rule.mode != "timeout_after_success":
            self._raise_for(rule)
        if not text.strip() or len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ProviderInvalidRequest("INVALID_PRIVATE_REPLY")
        with self._session_factory() as session:
            prior = session.scalar(
                select(SimPrivateReply).where(
                    SimPrivateReply.workspace_id == account.workspace_id,
                    SimPrivateReply.social_account_id == account.social_account_id,
                    SimPrivateReply.comment_external_id == comment_id,
                )
            )
            if prior is not None:
                if prior.operation_key != operation_key:
                    raise ProviderInvalidRequest("PRIVATE_REPLY_ALREADY_USED")
                return PrivateReplyResult(prior.provider_reply_id, prior.recipient_external_id)
            source = session.scalar(
                select(SimPublicComment)
                .where(
                    SimPublicComment.workspace_id == account.workspace_id,
                    SimPublicComment.social_account_id == account.social_account_id,
                    SimPublicComment.external_id == comment_id,
                )
                .with_for_update()
            )
            if source is None or source.value is None or source.value.get("state") != "visible":
                raise ProviderInvalidRequest("COMMENT_NOT_FOUND")
            # The explicit provisional remote fixture independently enforces the
            # seven-day opportunity; the application cannot extend it by retrying.
            timestamp = source.value.get("timestamp")
            if not isinstance(timestamp, str):
                raise ProviderInvalidRequest("PRIVATE_REPLY_TIMESTAMP_UNKNOWN")
            try:
                posted_at = datetime.fromisoformat(timestamp)
            except ValueError as exc:
                raise ProviderInvalidRequest("PRIVATE_REPLY_TIMESTAMP_UNKNOWN") from exc
            if self._clock.now() >= posted_at + MOCK_PRIVATE_REPLY_WINDOW:
                raise ProviderInvalidRequest("PRIVATE_REPLY_EXPIRED")
            recipient = source.value.get("author_id")
            row = SimPrivateReply(
                workspace_id=account.workspace_id,
                social_account_id=account.social_account_id,
                comment_external_id=comment_id,
                operation_key=operation_key,
                provider_reply_id=f"mock-private-reply-{uuid.uuid4().hex}",
                recipient_external_id=recipient if isinstance(recipient, str) else None,
                text=text,
                created_at=self._clock.now(),
            )
            session.add(row)
            session.commit()
            answer = PrivateReplyResult(row.provider_reply_id, row.recipient_external_id)
        if rule is not None:
            raise ProviderOutcomeUnknown("simulated timeout after private reply")
        return answer

    def find_private_reply(
        self, account: AccountRef, operation_key: str
    ) -> PrivateReplyResult | None:
        from app.comments.models import SimPrivateReply

        rule = self._consume_failure(account, "private_reply_lookup")
        if rule is not None:
            self._raise_for(rule)
        with self._session_factory() as session:
            row = session.scalar(
                select(SimPrivateReply).where(
                    SimPrivateReply.workspace_id == account.workspace_id,
                    SimPrivateReply.social_account_id == account.social_account_id,
                    SimPrivateReply.operation_key == operation_key,
                )
            )
            return (
                PrivateReplyResult(row.provider_reply_id, row.recipient_external_id)
                if row is not None
                else None
            )

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
            if rule.skip_first > 0:
                rule.skip_first -= 1
                session.commit()
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
        waiting finishes (or surfaces a delayed processing error) at ``ready_at``."""
        if container.status == "PUBLISHED":
            return ContainerStatus("PUBLISHED", media_id=container.published_media_id)
        now = self._clock.now()
        if now >= container.expires_at:
            return ContainerStatus("EXPIRED")
        if now < container.ready_at:
            return ContainerStatus("IN_PROGRESS")
        if container.status == "ERROR":
            detail = (
                f"SUBCODE_{container.error_subcode}"
                if container.error_subcode is not None
                else "simulated media processing error"
            )
            return ContainerStatus("ERROR", detail)
        return ContainerStatus("FINISHED")

    def get_container_status(self, account: AccountRef, container_id: str) -> ContainerStatus:
        rule = self._consume_failure(account, "container_status")
        if rule is not None and rule.mode != "invalid_media":
            self._raise_for(rule)
        with self._session_factory() as session:
            container = self._find_container(session, account, container_id, lock=True)
            if rule is not None and container.status == "IN_PROGRESS":
                container.status = "ERROR"  # processing failed, and it stays failed
                container.ready_at = min(container.ready_at, self._clock.now())
                if rule.error_subcode is not None:
                    container.error_subcode = rule.error_subcode
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

    def _window_open(
        self,
        session: Session,
        account: AccountRef,
        recipient_id: str,
        message_tag: str | None = None,
    ) -> bool:
        """24 hours for a normal message; 7 days when the message carries the Human Agent tag."""
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
        window = HUMAN_AGENT_WINDOW if message_tag == "HUMAN_AGENT" else MESSAGING_WINDOW
        return last is not None and self._clock.now() < last + window

    def send_text_message(
        self,
        account: AccountRef,
        recipient_id: str,
        text: str,
        message_tag: str | None = None,
    ) -> SendResult:
        rule = self._consume_failure(account, "send")
        if rule is not None and rule.mode != "timeout_after_success":
            self._raise_for(rule)
        if not text.strip():
            raise ProviderInvalidRequest("EMPTY_TEXT")
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ProviderInvalidRequest("TEXT_TOO_LONG")
        if message_tag is not None and message_tag not in SUPPORTED_MESSAGE_TAGS:
            raise ProviderInvalidRequest("UNSUPPORTED_MESSAGE_TAG")
        with self._session_factory() as session:
            if not self._window_open(session, account, recipient_id, message_tag):
                raise ProviderWindowClosed()
            message_id = f"mock-mid-{uuid.uuid4().hex}"
            session.add(
                SimSentMessage(
                    workspace_id=account.workspace_id,
                    social_account_id=account.social_account_id,
                    message_id=message_id,
                    recipient_id=recipient_id,
                    text=text,
                    message_tag=message_tag,
                    sent_at=self._clock.now(),
                )
            )
            session.commit()
        if rule is not None:  # timeout_after_success: the effect happened, the answer is lost
            raise ProviderOutcomeUnknown("simulated timeout after the message was accepted")
        return SendResult(message_id=message_id)

    def _parse_and_check_local_url(self, media_url: str, *, label: str) -> str:
        if self._storage is None:
            raise RuntimeError("the mock provider was built without a media storage")
        try:
            key, expires = parse_local_url(media_url)
        except ValueError as exc:
            raise ProviderInvalidRequest("MEDIA_REJECTED", f"{label} URL is not fetchable") from exc
        if self._clock.now().timestamp() >= expires:
            raise ProviderInvalidRequest("MEDIA_REJECTED", f"{label} URL has expired")
        return key

    def _check_fetchable_jpeg(self, image_url: str) -> None:
        """Resolve the ``localmedia:`` reference through the storage and check the JPEG magic
        bytes, as Instagram fetches the URL and refuses anything that is not a JPEG."""
        key = self._parse_and_check_local_url(image_url, label="image")
        try:
            with self._storage.open(key) as handle:  # type: ignore[union-attr]
                head = handle.read(len(JPEG_MAGIC))
        except StorageObjectNotFound as exc:
            raise ProviderInvalidRequest("MEDIA_REJECTED", "image not found") from exc
        if head != JPEG_MAGIC:
            raise ProviderInvalidRequest("MEDIA_REJECTED", "image is not a JPEG")

    def _check_fetchable_video(self, video_url: str) -> None:
        """Resolve the ``localmedia:`` reference through storage and verify fake/MP4/MOV header."""
        key = self._parse_and_check_local_url(video_url, label="video")
        try:
            with self._storage.open(key) as handle:  # type: ignore[union-attr]
                head = handle.read(len(FAKE_VIDEO_MAGIC))
        except StorageObjectNotFound as exc:
            raise ProviderInvalidRequest("MEDIA_REJECTED", "video not found") from exc
        if not head:
            raise ProviderInvalidRequest("MEDIA_REJECTED", "video is empty")
        if head.startswith(FAKE_VIDEO_MAGIC) or (len(head) >= 8 and head[4:8] == b"ftyp"):
            return
        raise ProviderInvalidRequest("MEDIA_REJECTED", "video is not MP4 or MOV")

    def create_media_container(self, account: AccountRef, spec: ContainerSpec) -> str:
        operation = (
            "create_carousel_container"
            if spec.media_type == "CAROUSEL"
            else "create_reel_container"
            if spec.media_type == "REELS"
            else "create_carousel_item"
            if spec.is_carousel_item
            else "create_container"
        )
        rule = self._consume_failure(account, operation)
        if rule is not None and rule.mode not in (
            "timeout_after_success",
            "slow_processing",
            "processing_error",
        ):
            self._raise_for(rule)
        if spec.media_type == "STORIES" and spec.caption:
            raise ProviderInvalidRequest("CAPTION_NOT_ALLOWED", "a story has no caption")
        if spec.media_type == "REELS":
            if spec.video_url is None:
                raise ProviderInvalidRequest("MEDIA_REJECTED")
            self._check_fetchable_video(spec.video_url)
            if spec.cover_url is not None:
                self._check_fetchable_jpeg(spec.cover_url)
        elif spec.media_type != "CAROUSEL":
            if spec.image_url is None:
                raise ProviderInvalidRequest("MEDIA_REJECTED")
            self._check_fetchable_jpeg(spec.image_url)
        now = self._clock.now()
        container_id = f"mock-container-{uuid.uuid4().hex}"
        default_delay = self._reel_delay if spec.media_type == "REELS" else self._container_delay
        delay = (
            timedelta(seconds=rule.delay_s)
            if rule is not None and rule.delay_s is not None
            else default_delay
        )
        initial_status = (
            "ERROR" if rule is not None and rule.mode == "processing_error" else "IN_PROGRESS"
        )
        error_subcode = (
            rule.error_subcode if rule is not None and rule.mode == "processing_error" else None
        )
        with self._session_factory() as session:
            if spec.media_type == "CAROUSEL":
                if len(spec.children) < 2:
                    raise ProviderInvalidRequest("TOO_FEW_CHILDREN")
                if len(spec.children) > 20:
                    raise ProviderInvalidRequest("TOO_MANY_CHILDREN")
                for child_id in spec.children:
                    try:
                        child = self._find_container(session, account, child_id, lock=True)
                    except ProviderInvalidRequest as exc:
                        raise ProviderInvalidRequest("CHILD_NOT_FOUND") from exc
                    state = self._effective_status(child).status_code
                    if state == "EXPIRED":
                        raise ProviderInvalidRequest("CHILD_EXPIRED")
                    if not child.is_carousel_item or state != "FINISHED":
                        raise ProviderInvalidRequest("CHILD_NOT_READY")
                    used = session.scalar(
                        select(SimContainer.id)
                        .where(
                            SimContainer.workspace_id == account.workspace_id,
                            SimContainer.social_account_id == account.social_account_id,
                            SimContainer.status == "PUBLISHED",
                            SimContainer.children.contains([child_id]),
                        )
                        .limit(1)
                    )
                    if used is not None:
                        raise ProviderInvalidRequest("CHILD_NOT_READY")
            session.add(
                SimContainer(
                    workspace_id=account.workspace_id,
                    social_account_id=account.social_account_id,
                    container_id=container_id,
                    media_type=spec.media_type,
                    media_url=spec.video_url if spec.media_type == "REELS" else spec.image_url,
                    is_carousel_item=spec.is_carousel_item,
                    children=list(spec.children) if spec.children else None,
                    cover_url=spec.cover_url,
                    thumb_offset_ms=spec.thumb_offset_ms,
                    share_to_feed=spec.share_to_feed,
                    caption=spec.caption,
                    status=initial_status,
                    error_subcode=error_subcode,
                    ready_at=now + delay,
                    expires_at=now + CONTAINER_LIFETIME,
                )
            )
            session.commit()
        if rule is not None and rule.mode == "timeout_after_success":
            raise ProviderOutcomeUnknown("simulated timeout after the container was created")
        return container_id

    def publish_container(self, account: AccountRef, container_id: str) -> str:
        rule = self._consume_failure(account, "publish")
        if rule is not None and rule.mode != "timeout_after_success":
            self._raise_for(rule)
        media_id = f"mock-media-{uuid.uuid4().hex}"
        with self._session_factory() as session:
            container = self._find_container(session, account, container_id, lock=True)
            if container.is_carousel_item:
                raise ProviderInvalidRequest("CONTAINER_NOT_PUBLISHABLE")
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

    def get_account_insights(
        self, account: AccountRef, metrics: list[str], since: datetime, until: datetime
    ) -> list[AccountInsightsMetric]:
        seed = int(account.social_account_id.int % 1000)
        results: list[AccountInsightsMetric] = []
        cur = since.date()
        end = until.date()
        step = timedelta(days=1)
        base_vals = {
            "reach": 240,
            "views": 580,
            "total_interactions": 32,
            "accounts_engaged": 45,
            "follower_count": 1420,
            "profile_links_taps": 12,
        }
        while cur <= end:
            day_offset = (cur.toordinal() + seed) % 31
            d_str = cur.isoformat()
            for m in metrics:
                base = base_vals.get(m, 50)
                # Deterministic variance +/- 25%
                variance = int(base * 0.25 * ((day_offset % 7) - 3) / 3)
                results.append(
                    AccountInsightsMetric(metric=m, value=max(0, base + variance), date=d_str)
                )
            cur += step
        return results

    def get_media_insights(
        self, account: AccountRef, media_id: str, media_type: str
    ) -> MediaInsightsData:
        if media_type in ("feed_carousel", "CAROUSEL", "carousel", "reel", "REELS"):
            raise ProviderInvalidRequest("MEDIA_INSIGHTS_NOT_SUPPORTED")
        h = hash(media_id) % 100
        if media_type == "story_image" or media_type == "story":
            return MediaInsightsData(
                ig_media_id=media_id,
                metrics={
                    "reach": 180 + h,
                    "views": 220 + h * 2,
                    "replies": max(1, h % 8),
                    "shares": max(0, h % 5),
                    "navigation": 15 + (h % 10),
                    "total_interactions": max(1, (h % 8) + (h % 5)),
                },
            )
        return MediaInsightsData(
            ig_media_id=media_id,
            metrics={
                "reach": 420 + h * 3,
                "views": 850 + h * 6,
                "likes": 45 + h,
                "comments": max(2, h % 15),
                "shares": max(1, h % 10),
                "saved": max(1, h % 12),
                "total_interactions": 50 + h + (h % 15) + (h % 10) + (h % 12),
            },
        )

    def get_audience(self, account: AccountRef) -> AudienceData:
        # Deterministic 24h distribution peaking 19:00 - 21:00
        online = {
            f"{h:02d}": 120 + (500 if 18 <= h <= 21 else 250 if 12 <= h <= 17 else 40)
            for h in range(24)
        }
        demographics = {
            "top_cities": {"Istanbul": 0.65, "Ankara": 0.15, "Izmir": 0.10, "Bursa": 0.05},
            "age_gender": {
                "25-34": {"F": 0.42, "M": 0.18},
                "18-24": {"F": 0.22, "M": 0.08},
                "35-44": {"F": 0.07, "M": 0.03},
            },
        }
        return AudienceData(
            follower_count=1420,
            online_followers=online,
            demographics=demographics,
        )
