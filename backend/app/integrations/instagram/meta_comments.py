"""Provisional comment transport, restricted to synthetic HTTP fixtures.

R75-01 through R75-06 remain open. These request/response shapes are engineering
assumptions, not authenticated Meta contracts. The registry never constructs this
class. Its mandatory MockTransport prevents these provisional mutations reaching
Instagram even when a caller accidentally supplies a real account reference.
"""

from datetime import datetime, timedelta

import httpx

from app.core.clock import Clock
from app.integrations.instagram.base import AccountRef, PrivateReplyResult, PublicEffectResult
from app.integrations.instagram.errors import ProviderInvalidRequest
from app.integrations.instagram.meta import (
    ID,
    Comment,
    CommentSuccess,
    MetaInstagramProvider,
    _identifier,
)


class SyntheticMetaCommentProvider(MetaInstagramProvider):
    """Offline-only scaffold; inherited request safety/error taxonomy is exercised."""

    def __init__(self, clock: Clock, api_version: str, *, transport: httpx.MockTransport) -> None:
        if type(transport) is not httpx.MockTransport:
            raise ValueError("Synthetic comments require an exact MockTransport")
        super().__init__(clock, "synthetic-only", api_version, transport=transport)

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

    def _private_deadline(self, posted_at: datetime) -> None:
        if not posted_at <= self._clock.now() < posted_at + timedelta(days=7):
            raise ProviderInvalidRequest("PRIVATE_REPLY_EXPIRED")

    def find_private_reply(
        self, account: AccountRef, operation_key: str
    ) -> PrivateReplyResult | None:
        return None
