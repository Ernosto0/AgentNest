"""Provisional comment transport, restricted to synthetic HTTP fixtures.

R75-01 through R75-06 remain open. These request/response shapes are engineering
assumptions, not authenticated Meta contracts. The registry never constructs this
class. Its mandatory MockTransport prevents these provisional mutations reaching
Instagram even when a caller accidentally supplies a real account reference.
"""

from datetime import datetime, timedelta
from typing import Literal

import httpx
from pydantic import Field

from app.core.clock import Clock
from app.integrations.instagram.base import AccountRef, PrivateReplyResult, PublicEffectResult
from app.integrations.instagram.errors import ProviderInvalidRequest
from app.integrations.instagram.meta import ID, Comment, MetaInstagramProvider, Shape, _identifier


class CommentMedia(ID):
    owner: ID


class CommentSuccess(Shape):
    success: Literal[True]


class PrivateSent(Shape):
    message_id: str = Field(min_length=1)
    # Never infer this from a comment author, username or ordinary send response.
    recipient_id: str | None = Field(default=None, min_length=1)


class SyntheticMetaCommentProvider(MetaInstagramProvider):
    """Offline-only scaffold; inherited request safety/error taxonomy is exercised."""

    def __init__(self, clock: Clock, api_version: str, *, transport: httpx.MockTransport) -> None:
        if type(transport) is not httpx.MockTransport:
            raise ValueError("Synthetic comments require an exact MockTransport")
        super().__init__(clock, "synthetic-only", api_version, transport=transport)

    def _owned_media(self, account: AccountRef, media_id: str) -> None:
        media = self._shape(
            CommentMedia,
            self._request(account, _identifier(media_id), params={"fields": "id,owner"}),
        )
        if media.id != media_id or media.owner.id != account.external_account_id:
            raise ProviderInvalidRequest("COMMENT_MEDIA_NOT_OWNED")

    def read_comments(self, account: AccountRef, media_id: str) -> list[Comment]:
        self._owned_media(account, media_id)
        values = self._pages(
            account,
            f"{_identifier(media_id)}/comments",
            {"fields": "id,media,timestamp,text,hidden", "limit": "50"},
        )
        comments = [self._shape(Comment, value) for value in values]
        if any(value.media.id != media_id for value in comments):
            raise ProviderInvalidRequest("COMMENT_MEDIA_MISMATCH")
        return comments

    def read_comment(self, account: AccountRef, comment_id: str) -> Comment:
        value = self._shape(
            Comment,
            self._request(
                account,
                _identifier(comment_id),
                params={"fields": "id,media,timestamp,text,hidden"},
            ),
        )
        if value.id != comment_id:
            raise ProviderInvalidRequest("COMMENT_TARGET_MISMATCH")
        self._owned_media(account, value.media.id)
        return value

    @staticmethod
    def _text(text: str | None) -> str:
        if not text or not text.strip() or len(text.encode("utf-8")) > 1000:
            raise ProviderInvalidRequest("INVALID_COMMENT_REPLY")
        return text

    def perform_comment_effect(
        self,
        account: AccountRef,
        target_id: str,
        effect: str,
        text: str | None,
        operation_key: str,
    ) -> PublicEffectResult:
        if effect not in {"reply", "hide", "unhide", "delete"} or not operation_key:
            raise ProviderInvalidRequest("INVALID_COMMENT_ACTION")
        if effect == "reply":
            self._text(text)
        elif text is not None:
            raise ProviderInvalidRequest("UNEXPECTED_COMMENT_TEXT")
        self.read_comment(account, target_id)
        if effect == "reply":
            result = self._shape(
                ID,
                self._request(
                    account,
                    f"{_identifier(target_id)}/replies",
                    method="POST",
                    body={"message": text},
                    ambiguous=True,
                ),
                ambiguous=True,
            )
            return PublicEffectResult(result.id)
        self._shape(
            CommentSuccess,
            self._request(
                account,
                _identifier(target_id),
                method="DELETE" if effect == "delete" else "POST",
                body=None if effect == "delete" else {"hide": effect == "hide"},
                ambiguous=True,
            ),
            ambiguous=True,
        )
        # A success acknowledgement is not independently verified state readback.
        return PublicEffectResult(target_id)

    def find_comment_effect(
        self, account: AccountRef, operation_key: str
    ) -> PublicEffectResult | None:
        # No remote idempotency/readback contract binds our local operation key.
        # Current visible state or a 404 cannot attribute an effect to this operation.
        return None

    def send_private_reply(
        self, account: AccountRef, comment_id: str, text: str, operation_key: str
    ) -> PrivateReplyResult:
        self._text(text)
        if not operation_key:
            raise ProviderInvalidRequest("INVALID_COMMENT_ACTION")
        comment = self.read_comment(account, comment_id)
        # Seven days is ONLY the conservative synthetic mock assumption (R75-04).
        self._private_deadline(comment.timestamp)
        value = self._shape(
            PrivateSent,
            self._request(
                account,
                f"{_identifier(account.external_account_id)}/messages",
                method="POST",
                body={"recipient": {"comment_id": comment_id}, "message": {"text": text}},
                ambiguous=True,
            ),
            ambiguous=True,
        )
        return PrivateReplyResult(value.message_id, value.recipient_id)

    def _private_deadline(self, posted_at: datetime) -> None:
        if not posted_at <= self._clock.now() < posted_at + timedelta(days=7):
            raise ProviderInvalidRequest("PRIVATE_REPLY_EXPIRED")

    def find_private_reply(
        self, account: AccountRef, operation_key: str
    ) -> PrivateReplyResult | None:
        return None
