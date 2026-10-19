"""``MockInstagramProvider``: a stateful simulator behind the real provider contract (ADR-010).

State lives in the database (``sim_*`` tables) so it survives restarts and is shared by the API
and the worker. It models the documented behaviour: the 24 h customer-service window (derived
from the simulated inbound messages), the 1000-byte text limit, one stored message per
accepted send, and scripted failures. Time comes from the injected clock.

Container methods are not implemented until Phase 5.
"""

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
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
    SimFailureRule,
    SimInboundMessage,
    SimSentMessage,
    SocialAccount,
)

MESSAGING_WINDOW = timedelta(hours=24)
MAX_TEXT_BYTES = 1000
DEFAULT_RETRY_AFTER_S = 30

SessionFactory = Callable[[], Session]


class MockInstagramProvider:
    kind: ProviderKind = "mock"

    def __init__(self, session_factory: SessionFactory, clock: Clock, app_secret: str) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._secret = app_secret

    # --- webhooks -----------------------------------------------------------------------------

    def verify_signature(self, raw_body: bytes, signature_header: str | None) -> bool:
        return webhook_format.verify(raw_body, signature_header, self._secret)

    def parse_webhook(self, payload: dict[str, Any]) -> list[NormalizedInboundEvent]:
        return webhook_format.parse(payload)

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
            raise ProviderInvalidRequest("INVALID_MEDIA", "simulated invalid media")
        raise ProviderTransientError(f"unknown simulated failure mode {mode}")

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

    def get_container_status(self, account: AccountRef, container_id: str) -> ContainerStatus:
        raise NotImplementedError("content publishing arrives in Phase 5")

    def get_media(self, account: AccountRef, media_id: str) -> MediaInfo:
        raise NotImplementedError("content publishing arrives in Phase 5")

    def get_publishing_quota(self, account: AccountRef) -> PublishingQuota:
        raise NotImplementedError("content publishing arrives in Phase 5")

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

    def create_media_container(self, account: AccountRef, spec: ContainerSpec) -> str:
        raise NotImplementedError("content publishing arrives in Phase 5")

    def publish_container(self, account: AccountRef, container_id: str) -> str:
        raise NotImplementedError("content publishing arrives in Phase 5")

    def refresh_token(self, account: AccountRef) -> TokenInfo:
        raise NotImplementedError("the mock has no token to refresh")
