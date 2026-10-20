"""Resume what waited for an account that is connected again (workflows.md §G, background-jobs.md).

A reply whose account needed re-authorisation stays ``queued`` (its ``send_reply`` job retries
every few minutes and may even have run out of attempts). When the owner reconnects, those
replies that can still be sent are sent now, through the normal send job and its ledger: this
module only makes sure a job exists and is due. It never calls the provider itself.

Content that went ``on_hold`` for an unavailable account is **not** resumed (Phase 5): the owner
approves it again, because the schedule it was approved for may have passed.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.inbox.context import MESSAGING_WINDOW
from app.inbox.models import Conversation, ReplyDraft
from app.inbox.payloads import SendReplyPayload
from app.integrations.instagram import queries
from app.jobs.queue import enqueue, expedite
from app.operations.send import SEND_MARGIN


def resume_queued_replies(
    session: Session,
    clock: Clock,
    workspace_id: uuid.UUID,
    social_account_id: uuid.UUID,
    *,
    correlation_id: uuid.UUID | None = None,
) -> int:
    """Make the ``send_reply`` job of every queued draft of this account due now. No commit.

    Returns the number of drafts looked after. The account must be usable; otherwise nothing is
    done (the send job would only wait again). Drafts whose messaging window is (nearly) over are
    left to the expiry sweep. Job state is handled per draft: a queued job is made due, a
    running one is left alone, and a missing or finished one is replaced by a new job.
    """
    account = queries.get_account_in_workspace(session, workspace_id, social_account_id)
    if (
        account is None
        or account.status != "connected"
        or account.capabilities.get("messaging") is not True
    ):
        return 0
    now = clock.now()
    queued = session.scalars(
        select(ReplyDraft)
        .join(
            Conversation,
            (Conversation.workspace_id == ReplyDraft.workspace_id)
            & (Conversation.id == ReplyDraft.conversation_id),
        )
        .where(
            ReplyDraft.workspace_id == workspace_id,
            ReplyDraft.status == "queued",
            Conversation.social_account_id == social_account_id,
            Conversation.last_inbound_at > now - MESSAGING_WINDOW + SEND_MARGIN,
        )
        .order_by(ReplyDraft.created_at, ReplyDraft.id)
    ).all()
    for draft in queued:
        key = f"send_reply:{draft.id}"
        enqueue(
            session,
            "send_reply",
            SendReplyPayload(reply_draft_id=draft.id),
            workspace_id=workspace_id,
            correlation_id=correlation_id,
            run_at=now,
            dedup_key=key,
            clock=clock,
        )
        expedite(session, key, clock)  # an existing job may be sleeping in its backoff
    return len(queued)
