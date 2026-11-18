"""The Human Agent message tag: when a person's reply may go out after the 24-hour window.

Instagram lets a **person** reply up to 7 days after the customer's last message when the message
carries the ``HUMAN_AGENT`` tag (docs/research/platform-capabilities.md section 1.5). The tag is
for human-typed support replies only, so this rule is the single deterministic gate for it:
the service that creates a reply and the send executor both call :func:`evaluate_message_tag`,
and the reply policy rules (R1 to R18) never produce a tagged decision (R2 stays a 24-hour rule).

Pure: no I/O, no clock, no model output. Any automated source (an AI or approved-answer draft, a
follow-up, an agent draft, a job, a system actor) is rejected whatever else is true.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

HUMAN_AGENT_TAG = "HUMAN_AGENT"
STANDARD_WINDOW = timedelta(hours=24)
HUMAN_AGENT_WINDOW = timedelta(days=7)

WindowState = Literal["open", "human_agent_only", "closed"]

DISABLED = "HUMAN_AGENT_DISABLED"
AUTOMATED_SOURCE = "HUMAN_AGENT_AUTOMATED_SOURCE"
WINDOW_CLOSED = "MESSAGING_WINDOW_CLOSED"


def window_state(
    last_inbound_at: datetime | None,
    now: datetime,
    *,
    human_agent_available: bool,
    margin: timedelta = timedelta(0),
) -> WindowState:
    """``open`` (a normal reply), ``human_agent_only`` (only a person's tagged reply) or
    ``closed``. ``margin`` is taken off the end of each window (nothing is sent that close)."""
    if last_inbound_at is None:
        return "closed"
    if now < last_inbound_at + STANDARD_WINDOW - margin:
        return "open"
    if human_agent_available and now < last_inbound_at + HUMAN_AGENT_WINDOW - margin:
        return "human_agent_only"
    return "closed"


@dataclass(frozen=True)
class MessageTagInput:
    now: datetime
    last_inbound_at: datetime | None
    # The capability flag: the setting and the account's granted permission, decided by the caller.
    human_agent_available: bool
    # Who wrote the text.
    source: str  # reply_drafts.source: ai | approved_answer | owner
    origin: str  # reply_drafts.origin: legacy | agent
    actor_type: str  # reply_drafts.created_by_actor_type: user | agent | system
    is_agent_action: bool = False
    is_follow_up: bool = False
    # The draft already carries the tag (a send-time re-check): a missing capability is then
    # reported as ``HUMAN_AGENT_DISABLED`` rather than as a plain closed window.
    tag_requested: bool = False
    margin: timedelta = timedelta(0)


@dataclass(frozen=True)
class MessageTagDecision:
    allowed: bool
    # True only when the message must carry the tag (the standard window is over).
    use_tag: bool
    reasons: tuple[str, ...]


def automated_reasons(i: MessageTagInput) -> tuple[str, ...]:
    """Why this reply is not a person's own typed reply (empty when it is)."""
    automated = (
        i.source != "owner"
        or i.origin != "legacy"
        or i.actor_type != "user"
        or i.is_agent_action
        or i.is_follow_up
    )
    return (AUTOMATED_SOURCE,) if automated else ()


def evaluate_message_tag(i: MessageTagInput) -> MessageTagDecision:
    """Allow a reply after the standard window only if a person typed it, the capability is on and
    the 7-day window is open. Inside the standard window no tag is needed (``use_tag`` False)."""
    state = window_state(
        i.last_inbound_at, i.now, human_agent_available=i.human_agent_available, margin=i.margin
    )
    automated = automated_reasons(i)
    if state == "open":
        if i.tag_requested and automated:  # an automated source never holds the tag
            return MessageTagDecision(False, False, automated)
        return MessageTagDecision(True, False, ())
    # The standard window is over: only the tag could carry this message.
    if automated:
        return MessageTagDecision(False, False, automated)
    if not i.human_agent_available:
        return MessageTagDecision(False, False, (DISABLED if i.tag_requested else WINDOW_CLOSED,))
    if state == "closed":
        return MessageTagDecision(False, False, (WINDOW_CLOSED,))
    return MessageTagDecision(True, True, ())
