"""Approval-ladder suggestions (D-02): the weekly "send this topic automatically?" proposal.

A weekly job counts, per reply topic, how often the owner approved the assistant's draft exactly
as written, and how often they edited, rejected or saw a failure. A topic that policy allows to
be automatic and has a clean record becomes at most one suggestion and one notification per
workspace per local week. The suggestion is only a proposal: nothing changes until the owner
reviews it through the existing delegation preview and apply endpoints (``DelegationChange
.suggestion_id``), and free text never accepts it. A dismissal silences that topic for a
cool-down. Every step is audited (INV-12).

Only topics with one narrow, fact-grounded intent are ever suggested (``SUGGESTIBLE``). Pricing,
booking, promotions and the general FAQ are never suggested, and intents that always go to a
person (complaints, refunds, discounts, sensitive topics) have no automation class at all.
"""

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.agent.delegation import ACTIONS, ActionRule, DelegationChange, DelegationPolicy
from app.agent.models import AccountAgent, DelegationSuggestion
from app.approvals.models import Approval
from app.audit import service as audit
from app.core.canonical import payload_hash
from app.core.clock import Clock
from app.core.config import get_settings
from app.core.context import ActorRef, WorkspaceContext
from app.core.errors import AppError
from app.identity.models import User, Workspace, WorkspaceMember
from app.inbox.approval_payload import approval_payload
from app.inbox.models import Conversation, ReplyDraft
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.jobs.queue import enqueue
from app.jobs.registry import JobContext, job_handler
from app.jobs.scheduler import register_periodic
from app.notifications.service import notify
from app.policy.models import AutomationPolicy
from app.policy.service import auto_allowed, get_policies

# Deliberately one intent per topic: the intent a draft was classified as, and the automation
# class that governs it. Never broaden this to greeting or to price-, booking- or promotion-type
# topics, which keep a person in the loop by default.
SUGGESTIBLE: dict[str, str] = {
    "hours": "reply.hours",
    "location_contact": "reply.location_contact",
    "services": "reply.services",
}
SUGGESTION_LIFETIME = timedelta(days=7)
# The weekly job waits until the owner's morning on Monday, so the notification is not at night.
FIRST_HOUR_ON_MONDAY = 9
NEGATIVE_SIGNALS = ("edited", "rejected", "failed")


class SuggestionOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    intent: str
    action_class: str
    counts: dict[str, int]
    window_days: int
    expires_at: datetime
    change: DelegationChange


def evidence(
    session: Session, clock: Clock, workspace_id: uuid.UUID, account_id: uuid.UUID
) -> dict[str, dict[str, int]]:
    """Per intent, how the owner treated this account's drafts in the window.

    Each draft is counted once. Only a draft the assistant wrote, that a signed-in owner approved
    through the web or Telegram without changing a character (the approval is bound to this exact
    version and payload hash) and that was then sent, is positive evidence. Edits, rejections and
    failures are counted separately and stop a suggestion. Simulated drafts never count.
    """
    now = clock.now()
    since = now - timedelta(days=get_settings().delegation_suggestion_window_days)
    rows = session.execute(
        select(ReplyDraft, Conversation)
        .join(
            Conversation,
            (Conversation.id == ReplyDraft.conversation_id)
            & (Conversation.workspace_id == ReplyDraft.workspace_id),
        )
        .where(
            ReplyDraft.workspace_id == workspace_id,
            Conversation.social_account_id == account_id,
            ReplyDraft.origin == "legacy",
            ReplyDraft.is_simulated.is_(False),
            ReplyDraft.created_at >= since,
            ReplyDraft.created_at <= now,
            ReplyDraft.intent.is_not(None),
        )
    ).all()
    approvals = session.scalars(
        select(Approval).where(
            Approval.workspace_id == workspace_id,
            Approval.subject_type == "reply_draft",
            Approval.created_at >= since,
            Approval.created_at <= now,
        )
    ).all()
    by_subject: dict[uuid.UUID, list[Approval]] = {}
    for approval in approvals:
        by_subject.setdefault(approval.subject_id, []).append(approval)
    result: dict[str, dict[str, int]] = {}
    for draft, conversation in rows:
        if draft.intent is None:
            continue
        counts = result.setdefault(
            draft.intent, {"unchanged": 0, "edited": 0, "rejected": 0, "failed": 0}
        )
        decisions = by_subject.get(draft.id, [])
        edited = draft.version > 1 or "OWNER_EDIT" in draft.decision_reasons
        rejected = any(a.status == "rejected" for a in decisions)
        failed = draft.status in {"failed", "outcome_unknown"} or draft.failure_code is not None
        counts["edited"] += int(edited)
        counts["rejected"] += int(rejected)
        counts["failed"] += int(failed)
        if edited or rejected or failed or draft.source != "ai" or draft.status != "sent":
            continue
        expected_hash = payload_hash(approval_payload(draft, conversation))
        if any(
            a.status == "approved"
            and a.decision_channel in {"web", "telegram"}
            and a.decided_by_user_id is not None
            and a.decided_at is not None
            and since <= a.decided_at <= now
            and not a.is_simulated
            and a.subject_version == draft.version
            and a.payload_hash == expected_hash
            for a in decisions
        ):
            counts["unchanged"] += 1
    return result


def clean(counts: dict[str, int]) -> bool:
    """No edit, rejection or failure in the window."""
    return not any(counts.get(key, 0) for key in NEGATIVE_SIGNALS)


def qualifies(counts: dict[str, int]) -> bool:
    minimum = get_settings().delegation_suggestion_min_unchanged
    return counts.get("unchanged", 0) >= minimum and clean(counts)


def week_start(clock: Clock, timezone: str) -> date:
    """Monday of the workspace-local week (INV-19)."""
    today = clock.now().astimezone(ZoneInfo(timezone)).date()
    return today - timedelta(days=today.weekday())


def _cooling_down(
    session: Session, clock: Clock, workspace_id: uuid.UUID, action_class: str
) -> bool:
    return bool(
        session.scalar(
            select(
                exists().where(
                    DelegationSuggestion.workspace_id == workspace_id,
                    DelegationSuggestion.action_class == action_class,
                    DelegationSuggestion.cooldown_until > clock.now(),
                )
            )
        )
    )


def _cooldown_end(clock: Clock) -> datetime:
    return clock.now() + timedelta(days=get_settings().delegation_suggestion_cooldown_days)


def generate(
    session: Session, clock: Clock, workspace_id: uuid.UUID
) -> DelegationSuggestion | None:
    """Create this week's suggestion and its one notification, if any topic qualifies."""
    # One lock serialises generation and decisions for the whole workspace, all accounts included.
    workspace = session.scalar(
        select(Workspace).where(Workspace.id == workspace_id).with_for_update()
    )
    if workspace is None or workspace.status != "active":
        return None
    now = clock.now()
    for stale in session.scalars(
        select(DelegationSuggestion).where(
            DelegationSuggestion.workspace_id == workspace_id,
            DelegationSuggestion.status == "pending",
            DelegationSuggestion.expires_at <= now,
        )
    ):
        stale.status = "expired"
    week = week_start(clock, workspace.timezone)
    if session.scalar(
        select(
            exists().where(
                DelegationSuggestion.workspace_id == workspace_id,
                DelegationSuggestion.week == week,
            )
        )
    ):
        return None  # at most one per workspace per week, whatever happened to it
    owner_id = session.scalar(
        select(WorkspaceMember.user_id)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == "owner",
            User.is_active.is_(True),
        )
        .order_by(WorkspaceMember.user_id)
        .limit(1)
    )
    if owner_id is None:
        return None
    ctx = WorkspaceContext(
        workspace_id,
        ActorRef.system("delegation_suggestion"),
        None,
        workspace.timezone,
        workspace.default_locale,
        workspace.is_demo,
    )
    if not auto_allowed(session, clock, ctx)[0]:
        return None  # readiness does not allow any automatic class yet
    modes = get_policies(session, workspace_id)
    accounts = session.scalars(
        select(AccountAgent)
        .join(
            SocialAccount,
            (SocialAccount.id == AccountAgent.social_account_id)
            & (SocialAccount.workspace_id == AccountAgent.workspace_id),
        )
        .where(
            AccountAgent.workspace_id == workspace_id,
            AccountAgent.controller_mode == "legacy",
            SocialAccount.provider_kind != "mock",
            SocialAccount.status == "connected",
            SocialAccount.disconnected_at.is_(None),
        )
        .order_by(SocialAccount.created_at, SocialAccount.id)
    ).all()
    for account in accounts:
        counts = evidence(session, clock, workspace_id, account.social_account_id)
        for intent, action_class in SUGGESTIBLE.items():
            if modes[action_class] != "approval" or not qualifies(counts.get(intent, {})):
                continue
            if _cooling_down(session, clock, workspace_id, action_class):
                continue
            row = DelegationSuggestion(
                workspace_id=workspace_id,
                social_account_id=account.social_account_id,
                week=week,
                intent=intent,
                action_class=action_class,
                counts=counts[intent],
                status="pending",
                created_at=now,
                expires_at=now + SUGGESTION_LIFETIME,
            )
            session.add(row)
            session.flush()
            notify(
                session,
                clock,
                ctx,
                recipient_user_id=owner_id,
                type="delegation_suggestion",
                params={"account_id": str(account.social_account_id), "intent": intent},
                subject_type="delegation_suggestion",
                subject_id=row.id,
                dedup_key=f"delegation_suggestion:{workspace_id}:{week.isoformat()}",
            )
            audit.record(
                session,
                ctx,
                "agent.delegation_suggested",
                "delegation_suggestion",
                row.id,
                {
                    "intent": intent,
                    "action_class": action_class,
                    "counts": row.counts,
                    "window_days": get_settings().delegation_suggestion_window_days,
                },
                clock=clock,
            )
            return row
    return None


def _scoped(
    session: Session,
    ctx: WorkspaceContext,
    suggestion_id: uuid.UUID,
    account_id: uuid.UUID | None = None,
) -> DelegationSuggestion:
    query = select(DelegationSuggestion).where(
        DelegationSuggestion.workspace_id == ctx.workspace_id,
        DelegationSuggestion.id == suggestion_id,
    )
    if account_id is not None:
        query = query.where(DelegationSuggestion.social_account_id == account_id)
    row = session.scalar(query.with_for_update())
    if row is None:
        raise AppError("NOT_FOUND")
    return row


def proposal(session: Session, row: DelegationSuggestion) -> DelegationChange:
    """The exact change the owner is asked to confirm. The delegation itself stays as it is: the
    suggestion changes only the topic's automation mode, on accept."""
    from app.agent.delegation import current_delegation
    from app.agent.repository import scoped_account

    account = scoped_account(session, row.workspace_id, row.social_account_id)
    current = current_delegation(session, row.workspace_id, row.social_account_id)
    policy = (
        DelegationPolicy.model_validate(current.policy)
        if current
        else DelegationPolicy(actions={action: ActionRule() for action in ACTIONS})
    )
    return DelegationChange(
        expected_config_version=account.config_version,
        expected_delegation_version=current.version if current else None,
        client_request_id=row.id,
        policy=policy,
        suggestion_id=row.id,
    )


def to_out(session: Session, row: DelegationSuggestion) -> SuggestionOut:
    return SuggestionOut(
        id=row.id,
        account_id=row.social_account_id,
        intent=row.intent,
        action_class=row.action_class,
        counts=row.counts,
        window_days=get_settings().delegation_suggestion_window_days,
        expires_at=row.expires_at,
        change=proposal(session, row),
    )


def list_pending(session: Session, clock: Clock, ctx: WorkspaceContext) -> list[SuggestionOut]:
    """Suggestions the owner can still act on: pending, unexpired, and the topic is still on
    approval (a rule the owner already changed by hand is not offered again)."""
    modes = get_policies(session, ctx.workspace_id)
    rows = session.scalars(
        select(DelegationSuggestion)
        .where(
            DelegationSuggestion.workspace_id == ctx.workspace_id,
            DelegationSuggestion.status == "pending",
            DelegationSuggestion.expires_at > clock.now(),
        )
        .order_by(DelegationSuggestion.created_at.desc())
    ).all()
    return [to_out(session, row) for row in rows if modes.get(row.action_class) == "approval"]


def validate(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account_id: uuid.UUID,
    change: DelegationChange,
    *,
    applying: bool = False,
) -> DelegationSuggestion:
    """Everything that must still hold when the owner previews or confirms. Raises otherwise."""
    from app.agent.repository import scoped_account

    session.scalar(select(Workspace).where(Workspace.id == ctx.workspace_id).with_for_update())
    if change.suggestion_id is None:
        raise AppError("CONFLICT_STATE", reason="suggestion_missing")
    row = _scoped(session, ctx, change.suggestion_id, account_id)
    if row.status != "pending" or clock.now() >= row.expires_at:
        raise AppError("CONFLICT_STATE", reason="suggestion_not_pending")
    counts = evidence(session, clock, ctx.workspace_id, account_id).get(row.intent, {})
    if (
        scoped_account(session, ctx.workspace_id, account_id).controller_mode != "legacy"
        or SUGGESTIBLE.get(row.intent) != row.action_class
        or get_policies(session, ctx.workspace_id)[row.action_class] != "approval"
        or not auto_allowed(session, clock, ctx)[0]
        # A new edit, rejection or failure since the suggestion withdraws it. Old approvals
        # ageing out of the window do not: the owner confirms what the card showed.
        or not clean(counts)
    ):
        raise AppError("CONFLICT_STATE", reason="suggestion_ineligible")
    if proposal(session, row) != change:
        raise AppError("VERSION_CONFLICT")
    if applying and (
        row.preview_hash != payload_hash(change.model_dump(mode="json"))
        or row.previewed_by != ctx.actor.id
    ):
        raise AppError("CONFLICT_STATE", reason="suggestion_preview_required")
    return row


def preview_suggestion(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account_id: uuid.UUID,
    change: DelegationChange,
) -> str:
    """Bind the owner's preview to the exact change; returns the automation class it affects."""
    row = validate(session, clock, ctx, account_id, change)
    row.preview_hash = payload_hash(change.model_dump(mode="json"))
    row.previewed_by = ctx.actor.id
    audit.record(
        session,
        ctx,
        "agent.delegation_suggestion_previewed",
        "delegation_suggestion",
        row.id,
        {"action_class": row.action_class},
        clock=clock,
    )
    return row.action_class


def accept(
    session: Session, clock: Clock, ctx: WorkspaceContext, row: DelegationSuggestion
) -> None:
    """Turn the topic to automatic. Called only by ``delegation.apply``, after ``validate``."""
    now = clock.now()
    user_id = uuid.UUID(ctx.actor.id) if ctx.actor.id else None
    policy = session.get(AutomationPolicy, (ctx.workspace_id, row.action_class))
    if policy is None:
        policy = AutomationPolicy(workspace_id=ctx.workspace_id, action_class=row.action_class)
        session.add(policy)
    policy.mode, policy.updated_at, policy.updated_by_user_id = "auto", now, user_id
    row.status, row.decided_at, row.decided_by_user_id = "accepted", now, user_id
    # If the owner later turns this back to approval, do not propose it again straight away.
    row.cooldown_until = _cooldown_end(clock)
    audit.record(
        session,
        ctx,
        "policy.updated",
        "workspace",
        ctx.workspace_id,
        {"changed": {row.action_class: {"from": "approval", "to": "auto"}}},
        clock=clock,
    )
    audit.record(
        session,
        ctx,
        "agent.delegation_suggestion_accepted",
        "delegation_suggestion",
        row.id,
        {"action_class": row.action_class, "intent": row.intent},
        clock=clock,
    )


def dismiss(
    session: Session, clock: Clock, ctx: WorkspaceContext, suggestion_id: uuid.UUID
) -> DelegationSuggestion:
    """The owner says no: silence this topic for the cool-down. A repeat changes nothing."""
    session.scalar(select(Workspace).where(Workspace.id == ctx.workspace_id).with_for_update())
    row = _scoped(session, ctx, suggestion_id)
    if row.status == "dismissed":
        return row
    if row.status != "pending":
        raise AppError("CONFLICT_STATE", reason="suggestion_not_pending")
    now = clock.now()
    row.status, row.decided_at = "dismissed", now
    row.decided_by_user_id = uuid.UUID(ctx.actor.id) if ctx.actor.id else None
    row.cooldown_until = _cooldown_end(clock)
    audit.record(
        session,
        ctx,
        "agent.delegation_suggestion_dismissed",
        "delegation_suggestion",
        row.id,
        {"action_class": row.action_class, "cooldown_until": row.cooldown_until.isoformat()},
        clock=clock,
    )
    return row


class DelegationSuggestionPayload(BaseModel):
    workspace_id: uuid.UUID
    week: date


@job_handler("delegation_suggestion", DelegationSuggestionPayload, max_attempts=3)
def run_suggestions(job: JobContext) -> None:
    payload = job.payload
    if not isinstance(payload, DelegationSuggestionPayload):
        return
    with job.session_factory() as session:
        workspace = session.get(Workspace, payload.workspace_id)
        if workspace and week_start(job.clock, workspace.timezone) == payload.week:
            generate(session, job.clock, payload.workspace_id)
            session.commit()


@register_periodic
def enqueue_suggestions(session: Session, clock: Clock) -> int:
    count = 0
    now = clock.now()
    for workspace in session.scalars(select(Workspace).where(Workspace.status == "active")):
        local = now.astimezone(ZoneInfo(workspace.timezone))
        if local.weekday() == 0 and local.hour < FIRST_HOUR_ON_MONDAY:
            continue
        week = week_start(clock, workspace.timezone)
        key = f"delegation_suggestion:{workspace.id}:{week.isoformat()}"
        if session.scalar(select(exists().where(Job.dedup_key == key))):
            continue  # this week has had its job
        enqueue(
            session,
            "delegation_suggestion",
            DelegationSuggestionPayload(workspace_id=workspace.id, week=week),
            workspace_id=workspace.id,
            correlation_id=None,
            dedup_key=key,
            clock=clock,
        )
        count += 1
    return count
