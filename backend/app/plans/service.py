"""The monthly AI reply allowance: the counter, admission control and the warnings.

THE COUNTING RULE. One unit is spent for each customer reply draft the AI produced with reply
text, at the moment the draft is stored: a direct-message ``ReplyDraft`` (also one that policy
withheld, or a final text with its problems marked), a proposed public comment reply and a
proposed private reply. It counts whether the owner then approves, edits, auto-sends, discards
or lets it expire. It does not count: the validator's second model call for the same draft; a
run that ends without text (the model cannot answer, language not supported, model error, the
sandbox test chat); a draft thrown away before it was stored (a newer customer message arrived
while the model ran); a manual reply, an owner command, a content draft. Each draft has a ledger
key, so a retried job or a replayed action can never be charged twice. A model call costs nothing
against the allowance; ``LLM_MAX_CALLS_PER_WORKSPACE_PER_DAY`` is a separate safety net.

ADMISSION. Every path locks the workspace's plan row (``SELECT ... FOR UPDATE``), so two workers
cannot both slip past the limit or double-count. The legacy drafting job reserves a slot before
its model call (so that no model money is spent while paused), holds no lock during the call, and
consumes the reservation in the transaction that stores the draft. A reservation lapses after
five minutes (more than the job timeout), so a crashed worker cannot block drafting for long.
The account agent consumes in the transaction that stores its draft.

PERIODS roll forward lazily, on the next read or write after the period ends, by whole calendar
months from the anchor day; the counter restarts at zero and the warnings re-arm. States:
normal, warning (80%), grace (100%, up to 110%) and paused (110%). Paused is computed, not
stored, so a quota change, a plan change or a period reset resumes drafting by itself.
"""

import calendar
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.context import ActorRef, WorkspaceContext
from app.core.errors import AppError
from app.identity.models import Workspace
from app.notifications.service import notify_permission_holders
from app.plans.models import ReplyUsage, WorkspacePlan
from app.plans.tiers import (
    DEFAULT_PLAN,
    DEFAULT_STATUS,
    GRACE_PERCENT,
    TIERS,
    WARNING_PERCENT,
)
from app.plans.tiers import (
    PAUSED_REASON as PAUSED_REASON,
)


def next_month(start: datetime, day: int) -> datetime:
    year, month = (start.year + 1, 1) if start.month == 12 else (start.year, start.month + 1)
    return start.replace(year=year, month=month, day=min(day, calendar.monthrange(year, month)[1]))


def get_plan(db: Session, clock: Clock, workspace_id: uuid.UUID) -> WorkspacePlan:
    """The workspace's plan row, locked for the rest of the transaction and rolled forward to
    the current period. A workspace without a row (created by any path) gets the default."""
    row = _locked(db, workspace_id)
    if row is None:
        workspace = db.get(Workspace, workspace_id)
        if workspace is None:
            raise AppError("NOT_FOUND")
        start = workspace.created_at
        db.execute(
            insert(WorkspacePlan)
            .values(
                workspace_id=workspace_id,
                plan=DEFAULT_PLAN,
                monthly_quota=TIERS[DEFAULT_PLAN],
                status=DEFAULT_STATUS,
                period_start=start,
                period_end=next_month(start, start.day),
                anchor_day=start.day,
                period_id=uuid.uuid4(),
                used=0,
                warned_80=False,
                warned_100=False,
                warned_paused=False,
            )
            .on_conflict_do_nothing(index_elements=["workspace_id"])
        )
        row = _locked(db, workspace_id)
        if row is None:
            raise AppError("NOT_FOUND")
    # Calendar months, preserving the original day across February and short months. A period
    # nobody touched for a while is skipped over in one go: usage restarts at zero.
    while clock.now() >= row.period_end:
        row.period_start = row.period_end
        row.period_end = next_month(row.period_start, row.anchor_day)
        reset_usage(row)
    db.flush()
    return row


def _locked(db: Session, workspace_id: uuid.UUID) -> WorkspacePlan | None:
    db.flush()  # populate_existing below would otherwise discard this session's pending changes
    return db.scalars(
        select(WorkspacePlan)
        .where(WorkspacePlan.workspace_id == workspace_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()


def reset_usage(row: WorkspacePlan) -> None:
    row.used = 0
    row.period_id = uuid.uuid4()
    row.warned_80 = row.warned_100 = row.warned_paused = False


def quota(row: WorkspacePlan) -> int:
    return row.quota_override if row.quota_override is not None else row.monthly_quota


def limit(row: WorkspacePlan) -> int:
    """The quota plus the 10% grace buffer (rounded up, so even a tiny override has one)."""
    return quota(row) + -(-quota(row) * GRACE_PERCENT // 100)


def state(row: WorkspacePlan) -> str:
    if row.used >= limit(row):
        return "paused"
    if row.used >= quota(row):
        return "grace"
    return "warning" if row.used * 100 >= quota(row) * WARNING_PERCENT else "normal"


def context(db: Session, workspace_id: uuid.UUID) -> WorkspaceContext:
    ws = db.get(Workspace, workspace_id)
    if ws is None:
        raise AppError("NOT_FOUND")
    return WorkspaceContext(
        ws.id, ActorRef.system("reply_quota"), None, ws.timezone, ws.default_locale, ws.is_demo
    )


def warnings(db: Session, clock: Clock, row: WorkspacePlan) -> None:
    for attr, reached, kind in (
        ("warned_80", row.used * 100 >= quota(row) * WARNING_PERCENT, "quota.warning"),
        ("warned_100", row.used >= quota(row), "quota.grace"),
        ("warned_paused", row.used >= limit(row), "quota.paused"),
    ):
        if reached and not getattr(row, attr):
            notify_permission_holders(
                db,
                clock,
                context(db, row.workspace_id),
                permission="system_health.view",
                type=kind,
                severity="attention",
                params={
                    "used": row.used,
                    "quota": quota(row),
                    "period_end": row.period_end.isoformat(),
                },
                dedup_key=f"{kind}:{row.period_id}",
            )
            setattr(row, attr, True)


def reserve(db: Session, clock: Clock, workspace_id: uuid.UUID, key: str) -> ReplyUsage | None:
    row = get_plan(db, clock, workspace_id)
    old = db.scalar(
        select(ReplyUsage).where(
            ReplyUsage.workspace_id == workspace_id, ReplyUsage.draft_key == key
        )
    )
    if old is not None and old.state == "consumed":
        return old
    if (
        old is not None
        and old.state == "reserved"
        and old.period_id == row.period_id
        and old.expires_at > clock.now()
    ):
        return old
    reserved = (
        db.scalar(
            select(func.count())
            .select_from(ReplyUsage)
            .where(
                ReplyUsage.workspace_id == workspace_id,
                ReplyUsage.period_id == row.period_id,
                ReplyUsage.state == "reserved",
                ReplyUsage.expires_at > clock.now(),
            )
        )
        or 0
    )
    if row.used + reserved >= limit(row):
        warnings(db, clock, row)
        return None
    ticket = old or ReplyUsage(workspace_id=workspace_id, draft_key=key)
    ticket.period_id, ticket.state = row.period_id, "reserved"
    ticket.expires_at = clock.now() + timedelta(minutes=5)
    db.add(ticket)
    db.flush()
    return ticket


def finish(
    db: Session, clock: Clock, workspace_id: uuid.UUID, ticket_id: uuid.UUID, *, produced: bool
) -> bool:
    row = get_plan(db, clock, workspace_id)
    ticket = db.scalar(
        select(ReplyUsage)
        .where(ReplyUsage.workspace_id == workspace_id, ReplyUsage.id == ticket_id)
        .with_for_update()
    )
    if ticket is None:
        return False
    if ticket.state == "consumed":
        return True
    if (
        ticket.state != "reserved"
        or ticket.period_id != row.period_id
        or ticket.expires_at <= clock.now()
    ):
        return False
    if produced and row.used >= limit(row):
        ticket.state = "released"
        return False
    ticket.state = "consumed" if produced else "released"
    if produced:
        row.used += 1
        warnings(db, clock, row)
    db.flush()
    return True


def consume(db: Session, clock: Clock, workspace_id: uuid.UUID, key: str) -> bool:
    ticket = reserve(db, clock, workspace_id, key)
    return ticket is not None and finish(db, clock, workspace_id, ticket.id, produced=True)


def is_paused(db: Session, clock: Clock, workspace_id: uuid.UUID) -> bool:
    """Whether drafting is paused now. Also makes sure the owner has been told (once)."""
    row = get_plan(db, clock, workspace_id)
    if state(row) != "paused":
        return False
    warnings(db, clock, row)
    return True


def notify_paused_conversation(
    db: Session, clock: Clock, workspace_id: uuid.UUID, conversation_id: uuid.UUID
) -> None:
    """The account agent skipped a customer message because drafting is paused: tell the people
    who answer customers, like any other message that waits for a person. The legacy drafting
    job needs none of this: its needs-human draft carries the same reason."""
    from app.inbox.models import Conversation

    conversation = db.scalar(
        select(Conversation).where(
            Conversation.workspace_id == workspace_id, Conversation.id == conversation_id
        )
    )
    if conversation is None:
        return
    conversation.attention = "needs_human"
    notify_permission_holders(
        db,
        clock,
        context(db, workspace_id),
        permission="reply.approve",
        type="conversation.needs_human",
        severity="attention",
        params={"conversation_id": str(conversation_id), "reasons": [PAUSED_REASON]},
        subject_type="conversation",
        subject_id=conversation_id,
        dedup_key=f"needs-human:{conversation_id}",
        is_simulated=conversation.is_simulated,
    )
