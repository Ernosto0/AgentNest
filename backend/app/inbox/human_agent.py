"""The Human Agent tag around a stored reply (policy/message_tag.py holds the rules).

A person's own typed reply may go out 24 hours to 7 days after the customer's last message when
the capability is on. This module only gathers the facts (the account's capability, who wrote the
draft, whether it is a follow-up) and delegates the decision to the pure policy function, so the
service that creates the reply and the send executor can never disagree.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.inbox.models import ConversationFollowUp, ReplyDraft
from app.integrations.instagram.models import SocialAccount
from app.policy.message_tag import (
    HUMAN_AGENT_TAG,
    MessageTagDecision,
    MessageTagInput,
    WindowState,
    evaluate_message_tag,
    window_state,
)

REASON = "HUMAN_AGENT_TAG"  # shown on the draft and in the approval summary
# Nothing new is accepted this close to the end of a window (the send executor adds its own).
NEW_REPLY_MARGIN = timedelta(minutes=2)

__all__ = [
    "NEW_REPLY_MARGIN",
    "REASON",
    "HUMAN_AGENT_TAG",
    "available",
    "decide_for_draft",
    "decide_new_reply",
    "is_follow_up_draft",
    "state_for",
]


def available(settings: Settings | None, account: SocialAccount | None) -> bool:
    """The capability flag: the account holds the ``human_agent`` capability and, for a real
    (Meta) account, the operator confirmed Meta's approval of the Human Agent feature."""
    if settings is None or account is None:
        return False
    if account.capabilities.get("human_agent") is not True:
        return False
    return account.provider_kind == "mock" or settings.meta_human_agent_enabled


def state_for(
    last_inbound_at: datetime | None,
    now: datetime,
    *,
    human_agent_available: bool,
    margin: timedelta = timedelta(0),
) -> WindowState:
    return window_state(
        last_inbound_at, now, human_agent_available=human_agent_available, margin=margin
    )


def is_follow_up_draft(session: Session, workspace_id: uuid.UUID, draft_id: uuid.UUID) -> bool:
    return (
        session.scalar(
            select(ConversationFollowUp.id).where(
                ConversationFollowUp.workspace_id == workspace_id,
                ConversationFollowUp.reply_draft_id == draft_id,
            )
        )
        is not None
    )


def decide_new_reply(
    *,
    now: datetime,
    last_inbound_at: datetime | None,
    human_agent_available: bool,
    actor_type: str,
    margin: timedelta,
) -> MessageTagDecision:
    """A reply a person is typing right now in the inbox (source ``owner``, legacy origin)."""
    return evaluate_message_tag(
        MessageTagInput(
            now=now,
            last_inbound_at=last_inbound_at,
            human_agent_available=human_agent_available,
            source="owner",
            origin="legacy",
            actor_type=actor_type,
            margin=margin,
        )
    )


def decide_for_draft(
    session: Session,
    draft: ReplyDraft,
    *,
    now: datetime,
    last_inbound_at: datetime | None,
    human_agent_available: bool,
    margin: timedelta,
) -> MessageTagDecision:
    """The send-time re-check of a stored draft, from its own persisted fields."""
    return evaluate_message_tag(
        MessageTagInput(
            now=now,
            last_inbound_at=last_inbound_at,
            human_agent_available=human_agent_available,
            source=draft.source,
            origin=draft.origin,
            actor_type=draft.created_by_actor_type,
            is_agent_action=draft.agent_action_id is not None,
            is_follow_up=is_follow_up_draft(session, draft.workspace_id, draft.id),
            tag_requested=draft.message_tag is not None,
            margin=margin,
        )
    )
