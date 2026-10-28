"""The Instagram provider contract (integrations.md §3.1, ADR-010).

One protocol, two implementations: ``MockInstagramProvider`` (a stateful simulator, Phase 4)
and the Meta adapter (Phase 7). Only ``operations`` may call the side-effecting methods
(``send_text_message``, ``create_media_container``, ``publish_container``, ``refresh_token``)
and the reconciliation reads (INV-15); ``inbox`` uses only ``verify_signature`` and
``parse_webhook``.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol

ProviderKind = Literal["mock", "meta"]
MOCK_PRIVATE_REPLY_WINDOW = timedelta(days=7)  # Provisional simulator fixture only.
EventType = Literal["message", "echo", "delete", "reaction", "read", "postback", "other", "comment"]


@dataclass(frozen=True)
class AccountRef:
    """What an adapter needs to act for one connected account."""

    social_account_id: uuid.UUID
    workspace_id: uuid.UUID
    external_account_id: str
    # Meta only: returns the decrypted token on demand so it is never held longer than a call.
    token_provider: Callable[[], str] | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class NormalizedInboundEvent:
    """One ``entry[].messaging[]`` item in provider-neutral form.

    ``account_id`` is always the business account and ``customer_id`` always the other party,
    for customer messages and for echoes alike (Meta swaps sender and recipient in an echo).
    """

    event_type: EventType
    account_id: str | None
    customer_id: str | None
    provider_timestamp: datetime | None
    mid: str | None = None
    text: str | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)
    is_echo: bool = False
    app_id: str | None = None
    raw_item: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SendResult:
    message_id: str


@dataclass(frozen=True)
class PublicEffectResult:
    provider_id: str
    state: str | None = None


@dataclass(frozen=True)
class PrivateReplyResult:
    reply_id: str
    recipient_id: str | None


@dataclass(frozen=True)
class AccountProfile:
    external_account_id: str
    username: str | None


@dataclass(frozen=True)
class OutboundMessageInfo:
    message_id: str
    recipient_id: str
    text: str | None
    sent_at: datetime


# Content publishing shapes (integrations.md §3.1).
@dataclass(frozen=True)
class ContainerSpec:
    media_type: Literal["IMAGE", "STORIES"]
    image_url: str
    caption: str | None = None


@dataclass(frozen=True)
class ContainerStatus:
    status_code: Literal["IN_PROGRESS", "FINISHED", "ERROR", "EXPIRED", "PUBLISHED"]
    error_detail: str | None = None
    # Only with ``PUBLISHED``: the media the container became. It lets reconciliation fetch the
    # permalink after a lost ``publish_container`` answer (plan.md G18, P5-06 decision).
    media_id: str | None = None


@dataclass(frozen=True)
class MediaInfo:
    media_id: str
    permalink: str | None = None
    timestamp: datetime | None = None


@dataclass(frozen=True)
class PublishingQuota:
    used: int
    limit: int
    window_hours: int


@dataclass(frozen=True)
class TokenInfo:
    expires_at: datetime | None
    # Refresh consumer encrypts this immediately; never serialize or log this shape.
    access_token: str | None = field(default=None, repr=False)


class InstagramProvider(Protocol):
    kind: ProviderKind

    def verify_signature(self, raw_body: bytes, signature_header: str | None) -> bool: ...

    def parse_webhook(self, payload: dict[str, Any]) -> list[NormalizedInboundEvent]: ...

    def get_account_profile(self, account: AccountRef) -> AccountProfile: ...

    def get_container_status(self, account: AccountRef, container_id: str) -> ContainerStatus: ...

    def get_media(self, account: AccountRef, media_id: str) -> MediaInfo: ...

    def get_publishing_quota(self, account: AccountRef) -> PublishingQuota: ...

    def find_recent_outbound(
        self, account: AccountRef, recipient_id: str, since: datetime
    ) -> list[OutboundMessageInfo]: ...

    # --- side effects: operations only (INV-15) ---
    def send_text_message(
        self, account: AccountRef, recipient_id: str, text: str
    ) -> SendResult: ...

    def perform_comment_effect(
        self,
        account: AccountRef,
        target_id: str,
        effect: str,
        text: str | None,
        operation_key: str,
    ) -> PublicEffectResult: ...

    def find_comment_effect(
        self,
        account: AccountRef,
        operation_key: str,
    ) -> PublicEffectResult | None: ...

    def send_private_reply(
        self, account: AccountRef, comment_id: str, text: str, operation_key: str
    ) -> PrivateReplyResult: ...

    def find_private_reply(
        self, account: AccountRef, operation_key: str
    ) -> PrivateReplyResult | None: ...

    def create_media_container(self, account: AccountRef, spec: ContainerSpec) -> str: ...

    def publish_container(self, account: AccountRef, container_id: str) -> str: ...

    def refresh_token(self, account: AccountRef) -> TokenInfo: ...
