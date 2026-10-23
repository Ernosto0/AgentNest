"""Instagram Login Graph adapter. Offline contracts; real-account verification pending.

Only committed operations call mutations. Each request decrypts its token on demand,
has no internal retry, and emits no HTTP URL/body/header logs.
"""

import logging
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Literal, TypeVar, cast
from urllib.parse import urlsplit

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from app.core.clock import Clock
from app.core.logging import get_logger
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
from app.integrations.instagram.error_mapping import (
    malformed_response,
    response_error,
    transport_error,
)
from app.integrations.instagram.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderInvalidRequest,
    ProviderTransientError,
)
from app.integrations.instagram.webhook_format import WebhookCodec


class Shape(BaseModel):
    model_config = ConfigDict(strict=True)


class ID(Shape):
    id: str = Field(min_length=1)


class Profile(Shape):
    user_id: str = Field(min_length=1)
    username: str | None = None


class Sent(Shape):
    message_id: str = Field(min_length=1)


class Status(Shape):
    status_code: Literal["IN_PROGRESS", "FINISHED", "ERROR", "EXPIRED", "PUBLISHED"]


class Media(ID):
    permalink: str | None = None
    timestamp: AwareDatetime | None = None


class Refreshed(Shape):
    access_token: str = Field(min_length=1, repr=False)
    expires_in: int = Field(gt=0, le=366 * 86400)


class QuotaConfig(Shape):
    quota_total: int = Field(ge=0)
    quota_duration: int = Field(gt=0)


class Quota(Shape):
    quota_usage: int = Field(ge=0)
    config: QuotaConfig


class Quotas(Shape):
    data: list[Quota] = Field(min_length=1, max_length=1)


class Recipients(Shape):
    data: list[ID]


class Outbound(ID):
    sender: ID = Field(alias="from")
    to: Recipients
    message: str | None = None
    created_time: AwareDatetime


T = TypeVar("T", bound=BaseModel)
log = get_logger(__name__)


F = TypeVar("F", bound=Callable[..., Any])


def _logged(operation: str) -> Callable[[F], F]:
    def decorate(method: F) -> F:
        @wraps(method)
        def call(self: Any, *args: Any, **kwargs: Any) -> Any:
            started = self._clock.now()
            outcome = "ok"
            try:
                return method(self, *args, **kwargs)
            except ProviderError as exc:
                outcome = exc.code
                raise
            except Exception:
                outcome = "PROVIDER_ERROR"
                raise
            finally:
                log.info(
                    "instagram_request",
                    operation=operation,
                    provider_kind="meta",
                    duration_ms=(self._clock.now() - started).total_seconds() * 1000,
                    outcome=outcome,
                )

        return cast(F, call)

    return decorate


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
        raise ProviderInvalidRequest("INVALID_IDENTIFIER")
    return value


class MetaInstagramProvider:
    kind: ProviderKind = "meta"

    def __init__(
        self,
        clock: Clock,
        app_secret: str,
        api_version: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not re.fullmatch(r"v\d+\.\d+", api_version):
            raise ValueError("Invalid Meta API version")
        self._clock = clock
        self._codec = WebhookCodec(app_secret)
        self._version = api_version
        self._transport = transport
        # httpx logs request URLs at INFO (refresh has a mandatory query token).
        # Explicit levels also suppress httpcore DEBUG under application LOG_LEVEL=DEBUG.
        for name in ("httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.WARNING)

    def verify_signature(self, raw_body: bytes, signature_header: str | None) -> bool:
        return self._codec.verify_signature(raw_body, signature_header)

    def parse_webhook(self, payload: dict[str, Any]) -> list[NormalizedInboundEvent]:
        return self._codec.parse_webhook(payload)

    def _request(
        self,
        account: AccountRef,
        path: str,
        *,
        method: str = "GET",
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        ambiguous: bool = False,
        refresh: bool = False,
    ) -> dict[str, Any]:
        try:
            token = account.token_provider() if account.token_provider else None
        except Exception:
            raise ProviderAuthError("TOKEN_UNAVAILABLE") from None
        if not token:
            raise ProviderAuthError("TOKEN_UNAVAILABLE")
        query = dict(params or {})
        headers = {} if refresh else {"Authorization": f"Bearer {token}"}
        if refresh:
            query["access_token"] = token
        url = "https://graph.instagram.com/" + ("" if refresh else f"{self._version}/") + path
        try:
            with httpx.Client(
                transport=self._transport, timeout=15.0, follow_redirects=False, trust_env=False
            ) as client:
                response = client.request(method, url, params=query, json=body, headers=headers)
        except httpx.RequestError as exc:
            raise transport_error(exc, ambiguous=ambiguous) from None
        try:
            data = response.json()
        except ValueError:
            # An invalid error body still has an authoritative HTTP classification.
            error = response_error(response.status_code, {}, ambiguous=ambiguous)
            raise error or malformed_response(ambiguous=ambiguous) from None
        error = response_error(
            response.status_code,
            data,
            response.headers.get("Retry-After"),
            ambiguous=ambiguous,
            now=self._clock.now(),
        )
        if error:
            raise error
        if not isinstance(data, dict):
            raise malformed_response(ambiguous=ambiguous)
        return data

    @staticmethod
    def _shape(model: type[T], data: Any, *, ambiguous: bool = False) -> T:
        try:
            # JSON mode permits ISO timestamps while retaining strict scalar validation.
            import json

            return model.model_validate_json(json.dumps(data))
        except (ValidationError, ValueError, TypeError):
            raise malformed_response(ambiguous=ambiguous) from None

    @_logged("get_account_profile")
    def get_account_profile(self, account: AccountRef) -> AccountProfile:
        value = self._shape(
            Profile,
            self._request(
                account,
                _identifier(account.external_account_id),
                params={"fields": "user_id,username"},
            ),
        )
        return AccountProfile(value.user_id, value.username)

    @_logged("send_text_message")
    def send_text_message(self, account: AccountRef, recipient_id: str, text: str) -> SendResult:
        if not text.strip():
            raise ProviderInvalidRequest("EMPTY_TEXT")
        if len(text.encode("utf-8")) > 1000:
            raise ProviderInvalidRequest("MESSAGE_TOO_LONG")
        value = self._shape(
            Sent,
            self._request(
                account,
                f"{_identifier(account.external_account_id)}/messages",
                method="POST",
                body={"recipient": {"id": recipient_id}, "message": {"text": text}},
                ambiguous=True,
            ),
            ambiguous=True,
        )
        return SendResult(value.message_id)

    def _pages(
        self, account: AccountRef, path: str, params: dict[str, str]
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for _ in range(100):
            data = self._request(account, path, params=params)
            entries = data.get("data")
            if not isinstance(entries, list) or any(not isinstance(v, dict) for v in entries):
                raise malformed_response(ambiguous=False)
            result.extend(entries)
            cursor = self._cursor(data)
            if cursor is None:
                return result
            if cursor in seen:
                break
            seen.add(cursor)
            params = {**params, "after": cursor}
        raise ProviderTransientError("INCOMPLETE_PROVIDER_RESPONSE")

    @staticmethod
    def _cursor(data: dict[str, Any]) -> str | None:
        paging = data.get("paging")
        if not paging:
            return None
        if not isinstance(paging, dict):
            raise malformed_response(ambiguous=False)
        if not paging.get("next"):
            return None
        cursors = paging.get("cursors")
        cursor = cursors.get("after") if isinstance(cursors, dict) else None
        if not isinstance(cursor, str) or not cursor:
            raise malformed_response(ambiguous=False)
        # Never follow Graph's next URL: rebuild a request to our fixed host and path.
        return cursor

    @_logged("find_recent_outbound")
    def find_recent_outbound(
        self, account: AccountRef, recipient_id: str, since: datetime
    ) -> list[OutboundMessageInfo]:
        fields = "id,from,to,message,created_time"
        conversations = self._pages(
            account,
            f"{_identifier(account.external_account_id)}/conversations",
            {"user_id": recipient_id, "fields": f"messages{{{fields}}}"},
        )
        found: dict[str, OutboundMessageInfo] = {}
        for conversation in conversations:
            messages = conversation.get("messages")
            if not isinstance(messages, dict) or not isinstance(messages.get("data"), list):
                raise malformed_response(ambiguous=False)
            entries = messages["data"]
            cursor = self._cursor(messages)
            if cursor:
                cid = self._shape(ID, conversation).id
                entries += self._pages(
                    account, f"{_identifier(cid)}/messages", {"fields": fields, "after": cursor}
                )
            for entry in entries:
                value = self._shape(Outbound, entry)
                if (
                    value.sender.id == account.external_account_id
                    and any(v.id == recipient_id for v in value.to.data)
                    and value.created_time >= since
                ):
                    found[value.id] = OutboundMessageInfo(
                        value.id, recipient_id, value.message, value.created_time
                    )
        return sorted(found.values(), key=lambda v: (v.sent_at, v.message_id))

    @_logged("create_media_container")
    def create_media_container(self, account: AccountRef, spec: ContainerSpec) -> str:
        if spec.media_type == "STORIES" and spec.caption is not None:
            raise ProviderInvalidRequest("CAPTION_NOT_ALLOWED")
        try:
            url = urlsplit(spec.image_url)
        except ValueError:
            raise ProviderInvalidRequest("MEDIA_URL_NOT_PUBLIC") from None
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ProviderInvalidRequest("MEDIA_URL_NOT_PUBLIC")
        body = {"image_url": spec.image_url}
        if spec.media_type == "STORIES":
            body["media_type"] = "STORIES"
        elif spec.caption is not None:
            body["caption"] = spec.caption
        return self._shape(
            ID,
            self._request(
                account,
                f"{_identifier(account.external_account_id)}/media",
                method="POST",
                body=body,
            ),
        ).id

    @_logged("get_container_status")
    def get_container_status(self, account: AccountRef, container_id: str) -> ContainerStatus:
        value = self._shape(
            Status,
            self._request(
                account, _identifier(container_id), params={"fields": "id,status_code,status"}
            ),
        )
        # Graph does not document the published media ID on this read; never invent one.
        return ContainerStatus(
            value.status_code, "MEDIA_PROCESSING_ERROR" if value.status_code == "ERROR" else None
        )

    @_logged("publish_container")
    def publish_container(self, account: AccountRef, container_id: str) -> str:
        return self._shape(
            ID,
            self._request(
                account,
                f"{_identifier(account.external_account_id)}/media_publish",
                method="POST",
                body={"creation_id": container_id},
                ambiguous=True,
            ),
            ambiguous=True,
        ).id

    @_logged("get_media")
    def get_media(self, account: AccountRef, media_id: str) -> MediaInfo:
        value = self._shape(
            Media,
            self._request(
                account, _identifier(media_id), params={"fields": "id,permalink,timestamp"}
            ),
        )
        return MediaInfo(value.id, value.permalink, value.timestamp)

    @_logged("get_publishing_quota")
    def get_publishing_quota(self, account: AccountRef) -> PublishingQuota:
        value = self._shape(
            Quotas,
            self._request(
                account,
                f"{_identifier(account.external_account_id)}/content_publishing_limit",
                params={"fields": "config,quota_usage"},
            ),
        ).data[0]
        if value.config.quota_duration % 3600:
            raise malformed_response(ambiguous=False)
        return PublishingQuota(
            value.quota_usage, value.config.quota_total, value.config.quota_duration // 3600
        )

    @_logged("refresh_token")
    def refresh_token(self, account: AccountRef) -> TokenInfo:
        value = self._shape(
            Refreshed,
            self._request(
                account,
                "refresh_access_token",
                params={"grant_type": "ig_refresh_token"},
                refresh=True,
            ),
        )
        return TokenInfo(
            self._clock.now() + timedelta(seconds=value.expires_in), value.access_token
        )
