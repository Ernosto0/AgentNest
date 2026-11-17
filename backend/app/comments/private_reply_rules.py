"""Pure, conservative real-account private reply admission rules (live evidence pending)."""

from datetime import datetime
from typing import Literal

from app.integrations.instagram.base import META_PRIVATE_REPLY_WINDOW


def refusal(
    *,
    now: datetime,
    posted_at: datetime | None,
    author_id: str | None,
    parent_id: str | None,
    comment_used: bool = False,
    commenter_used: bool = False,
    limit_scope: Literal["commenter", "comment"] = "commenter",
) -> str | None:
    if comment_used:
        return "PRIVATE_REPLY_COMMENT_ALREADY_USED"
    if not author_id:
        return "PRIVATE_REPLY_COMMENTER_UNKNOWN"
    if parent_id is not None:
        return "PRIVATE_REPLY_NOT_TOP_LEVEL"
    if posted_at is None or not posted_at <= now < posted_at + META_PRIVATE_REPLY_WINDOW:
        return "PRIVATE_REPLY_WINDOW_EXPIRED"
    if limit_scope == "commenter" and commenter_used:
        return "PRIVATE_REPLY_COMMENTER_LIMIT"
    return None
