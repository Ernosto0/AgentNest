"""Account-scoped, versioned action delegation and deterministic authorization.

The legacy topic automation policy is deliberately separate. A proposed agent action is
never authority: this module checks the current account grant and stores exact evidence.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.models import AccountAgent, AgentAction, AgentDelegation, AgentThread
from app.agent.repository import AgentScopeError, scoped_account
from app.approvals import service as approvals
from app.approvals.grants import record_policy_grant
from app.audit import service as audit
from app.core.canonical import payload_hash
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity.models import User, WorkspaceMember
from app.identity.permissions import has_permission
from app.integrations.instagram import queries

ActionName = Literal[
    "dm.send",
    "comment.reply",
    "comment.private_reply",
    "comment.hide",
    "comment.unhide",
    "comment.delete",
    "content.prepare",
    "content.schedule",
    "content.publish",
    "content.cancel",
]
Mode = Literal["automatic", "ask", "off"]
Source = Literal["customer", "owner_task"]
DecisionKind = Literal["automatic", "ask", "off", "unavailable", "blocked"]

ACTIONS: tuple[ActionName, ...] = (
    "dm.send",
    "comment.reply",
    "comment.private_reply",
    "comment.hide",
    "comment.unhide",
    "comment.delete",
    "content.prepare",
    "content.schedule",
    "content.publish",
    "content.cancel",
)
CAPABILITIES: dict[str, str | None] = {
    "dm.send": "messaging",
    "comment.reply": "comment_reply",
    "comment.private_reply": "comment_private_reply",
    "comment.hide": "comment_moderate",
    "comment.unhide": "comment_moderate",
    "comment.delete": "comment_moderate",
    "content.prepare": None,
    "content.schedule": None,
    "content.publish": "publish_feed_image",
    "content.cancel": None,
}
APPROVALS: dict[str, tuple[str, str]] = {
    "dm.send": ("reply.send", "reply.approve"),
    "comment.reply": ("comments.approve", "comments.approve"),
    "comment.private_reply": ("comments.approve", "comments.approve"),
    "comment.hide": ("comments.approve", "comments.approve"),
    "comment.unhide": ("comments.approve", "comments.approve"),
    "comment.delete": ("comments.approve", "comments.approve"),
    "content.prepare": ("content.prepare", "content.edit"),
    "content.schedule": ("content.schedule", "content.approve"),
    "content.publish": ("content.publish", "content.approve"),
    "content.cancel": ("content.cancel", "content.approve"),
}
REQUESTER_PERMISSIONS: dict[str, str] = {
    "dm.send": "reply.write",
    "comment.reply": "comments.approve",
    "comment.private_reply": "comments.approve",
    "comment.hide": "comments.approve",
    "comment.unhide": "comments.approve",
    "comment.delete": "comments.approve",
    "content.prepare": "content.edit",
    "content.schedule": "content.approve",
    "content.publish": "content.approve",
    "content.cancel": "content.approve",
}


class ActionRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Mode = "off"
    max_per_day: int | None = Field(default=None, ge=1, le=10000)
    sources: frozenset[Source] = frozenset({"customer", "owner_task"})


class DelegationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: dict[ActionName, ActionRule]

    @field_validator("actions")
    @classmethod
    def all_actions_present(
        cls, actions: dict[ActionName, ActionRule]
    ) -> dict[ActionName, ActionRule]:
        if set(actions) != set(ACTIONS):
            raise ValueError("all action modes must be specified")
        return actions


class DelegationChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_config_version: int = Field(ge=1)
    expected_delegation_version: int | None = Field(default=None, ge=1)
    client_request_id: uuid.UUID
    policy: DelegationPolicy


@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    reason: str


def decide(
    *,
    rule: ActionRule,
    source: Source,
    requester_allowed: bool,
    account_active: bool,
    capability_available: bool,
    target_owned: bool,
    visibility_allowed: bool,
    claims_valid: bool,
    quota_available: bool,
) -> Decision:
    """Pure authorization rule; a caller must derive facts from scoped persisted records."""
    if not account_active:
        return Decision("blocked", "agent_inactive")
    if source not in rule.sources or (source == "owner_task" and not requester_allowed):
        return Decision("blocked", "source_not_authorized")
    if not target_owned or not visibility_allowed or not claims_valid:
        return Decision("blocked", "target_or_claims_invalid")
    if rule.mode == "off":
        return Decision("off", "delegation_off")
    if not capability_available:
        return Decision("unavailable", "provider_capability_missing")
    if not quota_available:
        return Decision("unavailable", "quota_exhausted")
    return Decision(rule.mode, "delegated")


def current_delegation(
    session: Session, workspace_id: uuid.UUID, account_id: uuid.UUID, *, lock: bool = False
) -> AgentDelegation | None:
    query = select(AgentDelegation).where(
        AgentDelegation.workspace_id == workspace_id,
        AgentDelegation.social_account_id == account_id,
        AgentDelegation.revoked_at.is_(None),
    )
    if lock:
        query = query.with_for_update()
    return session.scalar(query)


def _read_versions(
    account: AccountAgent, current: AgentDelegation | None, change: DelegationChange
) -> None:
    if (
        account.config_version != change.expected_config_version
        or (current.version if current else None) != change.expected_delegation_version
    ):
        raise AppError("VERSION_CONFLICT")


def preview(
    session: Session, ctx: WorkspaceContext, account_id: uuid.UUID, change: DelegationChange
) -> dict[str, object]:
    if not has_permission(ctx.role, "agent.delegation.manage"):
        raise AppError("FORBIDDEN", permission="agent.delegation.manage")
    try:
        account = scoped_account(session, ctx.workspace_id, account_id)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    current = current_delegation(session, ctx.workspace_id, account_id)
    _read_versions(account, current, change)
    previous = DelegationPolicy.model_validate(current.policy) if current else None
    changed = [
        action
        for action in ACTIONS
        if previous is None or previous.actions[action] != change.policy.actions[action]
    ]
    return {"next_version": (current.version + 1) if current else 1, "changed_actions": changed}


def apply(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account_id: uuid.UUID,
    change: DelegationChange,
) -> AgentDelegation:
    """Atomically replace a grant; no agent is activated by a policy edit."""
    if not has_permission(ctx.role, "agent.delegation.manage") or ctx.actor.type != "user":
        raise AppError("FORBIDDEN", permission="agent.delegation.manage")
    try:
        account = scoped_account(session, ctx.workspace_id, account_id, lock=True)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    existing = session.scalar(
        select(AgentDelegation).where(
            AgentDelegation.workspace_id == ctx.workspace_id,
            AgentDelegation.social_account_id == account_id,
            AgentDelegation.client_request_id == change.client_request_id,
        )
    )
    canonical = change.policy.model_dump(mode="json")
    hash_value = payload_hash(canonical)
    if existing is not None:
        if existing.policy_hash != hash_value:
            raise AppError("CONFLICT_STATE", reason="request_id_reused")
        return existing
    current = current_delegation(session, ctx.workspace_id, account_id, lock=True)
    _read_versions(account, current, change)
    user_id = uuid.UUID(ctx.actor.id) if ctx.actor.id else None
    member = session.get(WorkspaceMember, (ctx.workspace_id, user_id)) if user_id else None
    if member is None or member.role != "owner":
        raise AppError("FORBIDDEN", permission="agent.delegation.manage")
    now = clock.now()
    if current is not None:
        current.revoked_at = now
    delegation = AgentDelegation(
        workspace_id=ctx.workspace_id,
        social_account_id=account_id,
        version=(current.version + 1) if current else 1,
        grantor_user_id=user_id,
        policy=canonical,
        policy_hash=hash_value,
        client_request_id=change.client_request_id,
        effective_at=now,
        created_at=now,
    )
    session.add(delegation)
    account.config_version += 1
    account.controller_epoch += 1
    from app.agent.control import adopt_threads

    adopt_threads(session, clock, account)
    from app.agent.jobs import enqueue_cleanup

    enqueue_cleanup(session, clock, ctx.workspace_id, account_id, account.controller_epoch)
    account.updated_at = now
    session.flush()
    audit.record(
        session,
        ctx,
        "agent.delegation_applied",
        "account_agent",
        account.id,
        {"version": delegation.version, "changed_actions": preview_actions(current, canonical)},
        clock=clock,
    )
    return delegation


def preview_actions(previous: AgentDelegation | None, policy: dict[str, object]) -> list[str]:
    old = previous.policy.get("actions", {}) if previous else {}
    new = policy["actions"]
    if not isinstance(old, dict) or not isinstance(new, dict):
        return list(ACTIONS)
    return [name for name in ACTIONS if old.get(name) != new.get(name)]


def _grantor_still_owner(session: Session, workspace_id: uuid.UUID, grantor_id: uuid.UUID) -> bool:
    member = session.get(WorkspaceMember, (workspace_id, grantor_id))
    user = session.get(User, grantor_id)
    return member is not None and member.role == "owner" and user is not None and user.is_active


def current_action_authority(session: Session, action: AgentAction) -> bool:
    """Read-side status for approval cards; dispatch still uses locked ``fence_action``."""
    if action.status in {"cancelled", "failed"}:
        return False
    try:
        account = scoped_account(session, action.workspace_id, action.social_account_id)
    except AgentScopeError:
        return False
    delegation = current_delegation(session, action.workspace_id, action.social_account_id)
    thread = session.scalar(
        select(AgentThread).where(
            AgentThread.workspace_id == action.workspace_id,
            AgentThread.id == action.thread_id,
            AgentThread.social_account_id == action.social_account_id,
        )
    )
    return (
        account.controller_mode == "agent"
        and account.state == "active"
        and delegation is not None
        and action.delegation_version == delegation.version
        and thread is not None
        and action.ownership_generation == thread.ownership_generation
        and (action.action_type != "dm.send" or action.initiating_cursor == thread.event_cursor)
        and thread.handling_mode == "agent"
        and thread.controller_epoch == account.controller_epoch
        and _grantor_still_owner(session, action.workspace_id, delegation.grantor_user_id)
    )


def fence_action(
    session: Session,
    clock: Clock,
    workspace_id: uuid.UUID,
    action_id: uuid.UUID,
    *,
    account_id: uuid.UUID | None = None,
    payload_hash_value: str | None = None,
    allow_waiting_approval: bool = False,
    expected_action: str | None = None,
) -> AgentAction:
    """Executor-side current-policy fence before an operation is started or retried."""
    candidate = session.scalar(
        select(AgentAction).where(
            AgentAction.workspace_id == workspace_id, AgentAction.id == action_id
        )
    )
    if candidate is None or (account_id is not None and candidate.social_account_id != account_id):
        raise AppError("NOT_FOUND")
    account = scoped_account(session, workspace_id, candidate.social_account_id, lock=True)
    action = session.scalar(
        select(AgentAction)
        .where(AgentAction.workspace_id == workspace_id, AgentAction.id == action_id)
        .with_for_update()
    )
    if action is None:
        raise AppError("NOT_FOUND")
    delegation = current_delegation(session, workspace_id, action.social_account_id, lock=True)
    thread = session.scalar(
        select(AgentThread).where(
            AgentThread.workspace_id == workspace_id, AgentThread.id == action.thread_id
        )
    )
    allowed_statuses = {"authorized", "queued", "in_progress", "outcome_unknown"}
    if allow_waiting_approval:
        allowed_statuses.add("waiting_approval")
    grant = action.policy_grant
    if (
        account.controller_mode != "agent"
        or account.state != "active"
        or delegation is None
        or action.delegation_version != delegation.version
        or thread is None
        or action.ownership_generation != thread.ownership_generation
        or (action.action_type == "dm.send" and action.initiating_cursor != thread.event_cursor)
        or thread.handling_mode != "agent"
        or thread.controller_epoch != account.controller_epoch
        or action.status not in allowed_statuses
        or (action.execute_before is not None and clock.now() >= action.execute_before)
        or (payload_hash_value is not None and action.payload_hash != payload_hash_value)
        or (expected_action is not None and action.action_type != expected_action)
        or not _grantor_still_owner(session, workspace_id, delegation.grantor_user_id)
        or (
            grant is not None
            and (
                grant.get("delegation_id") != str(delegation.id)
                or grant.get("delegation_version") != delegation.version
                or grant.get("controller_epoch") != account.controller_epoch
                or grant.get("action_version") != action.version
                or grant.get("payload_hash") != action.payload_hash
                or grant.get("target_ref") != action.target_ref
            )
        )
    ):
        raise AppError("APPROVAL_STALE")
    return action


def authorize_action(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    action_id: uuid.UUID,
    *,
    source: Source,
    requester_user_id: uuid.UUID | None = None,
    target_owned: bool,
    visibility_allowed: bool,
    claims_valid: bool,
    quota_available: bool,
    require_human: bool = False,
) -> Decision:
    """Authorize a scoped proposed action; call with facts from server-owned domain checks."""
    candidate = session.scalar(
        select(AgentAction).where(
            AgentAction.workspace_id == ctx.workspace_id, AgentAction.id == action_id
        )
    )
    if candidate is None:
        raise AppError("NOT_FOUND")
    account = scoped_account(session, ctx.workspace_id, candidate.social_account_id, lock=True)
    action = session.scalar(
        select(AgentAction)
        .where(AgentAction.workspace_id == ctx.workspace_id, AgentAction.id == action_id)
        .with_for_update()
    )
    if action is None:
        raise AppError("NOT_FOUND")
    if action.status != "proposed":
        raise AppError("CONFLICT_STATE", entity="agent_action", status=action.status)
    delegation = current_delegation(session, ctx.workspace_id, action.social_account_id, lock=True)
    if delegation is None:
        return Decision("off", "no_delegation")
    if not _grantor_still_owner(session, ctx.workspace_id, delegation.grantor_user_id):
        return Decision("blocked", "grantor_authority_lost")
    policy = DelegationPolicy.model_validate(delegation.policy)
    if action.action_type not in policy.actions:
        return Decision("off", "unknown_action")
    rule = policy.actions[action.action_type]
    within_rule_limit = True
    if rule.max_per_day is not None:
        now_utc = clock.now().astimezone(UTC)
        day_start = datetime.combine(now_utc.date(), time.min, tzinfo=UTC)
        used = (
            session.scalar(
                select(func.count(AgentAction.id)).where(
                    AgentAction.workspace_id == ctx.workspace_id,
                    AgentAction.social_account_id == action.social_account_id,
                    AgentAction.action_type == action.action_type,
                    AgentAction.delegation_version == delegation.version,
                    AgentAction.status.in_(
                        ("authorized", "queued", "in_progress", "succeeded", "outcome_unknown")
                    ),
                    AgentAction.authorized_at >= day_start,
                )
            )
            or 0
        )
        within_rule_limit = used < rule.max_per_day
    provider_account = queries.get_account_in_workspace(
        session, ctx.workspace_id, action.social_account_id
    )
    requester_allowed = source == "customer"
    if source == "owner_task" and requester_user_id is not None:
        requester = session.get(WorkspaceMember, (ctx.workspace_id, requester_user_id))
        user = session.get(User, requester_user_id)
        requester_allowed = (
            requester is not None
            and user is not None
            and user.is_active
            and has_permission(requester.role, REQUESTER_PERMISSIONS[action.action_type])
        )
    capability = CAPABILITIES[action.action_type]
    thread = session.scalar(
        select(AgentThread).where(
            AgentThread.workspace_id == ctx.workspace_id,
            AgentThread.social_account_id == action.social_account_id,
            AgentThread.id == action.thread_id,
        )
    )
    decision = decide(
        rule=rule,
        source=source,
        requester_allowed=requester_allowed,
        account_active=account.controller_mode == "agent"
        and account.state == "active"
        and thread is not None
        and thread.handling_mode == "agent"
        and thread.controller_epoch == account.controller_epoch,
        capability_available=provider_account is not None
        and provider_account.status in ("connected", "degraded")
        and (capability is None or provider_account.capabilities.get(capability) is True),
        target_owned=target_owned,
        visibility_allowed=visibility_allowed,
        claims_valid=claims_valid,
        quota_available=quota_available and within_rule_limit,
    )
    if decision.kind not in ("automatic", "ask"):
        return decision
    if require_human and decision.kind == "automatic":
        decision = Decision("ask", "explicit_approval_requested")
    action.delegation_version = delegation.version
    action.execute_before = clock.now() + timedelta(hours=24)
    if decision.kind == "automatic":
        action.authorized_at = clock.now()
        action.policy_grant = {
            "delegation_id": str(delegation.id),
            "delegation_version": delegation.version,
            "grantor_user_id": str(delegation.grantor_user_id),
            "controller_epoch": account.controller_epoch,
            "action_id": str(action.id),
            "action_version": action.version,
            "payload_hash": action.payload_hash,
            "target_ref": action.target_ref,
            "initiating_event_id": str(action.initiating_event_id)
            if action.initiating_event_id
            else None,
            "execute_before": action.execute_before.isoformat(),
        }
        action.status = "authorized"
        audit.record(
            session,
            ctx,
            "agent.action_authorized",
            "agent_action",
            action.id,
            {"delegation_version": delegation.version, "mode": "automatic"},
            clock=clock,
        )
    else:
        approval_action, permission = APPROVALS[action.action_type]
        approval = approvals.request(
            session,
            clock,
            ctx,
            kind="authorization",
            action=approval_action,
            subject_type="agent_action",
            subject_id=action.id,
            subject_version=action.version,
            payload={
                "agent_action_id": str(action.id),
                "payload_hash": action.payload_hash,
                "action_type": action.action_type,
                "version": action.version,
            },
            summary={
                "action_type": action.action_type,
                "target_ref": action.target_ref,
                "payload_hash": action.payload_hash,
            },
            required_permission=permission,
            expires_at=action.execute_before,
            execute_before=action.execute_before,
            is_simulated=provider_account.is_simulated if provider_account else False,
            exact_payload_hash=action.payload_hash,
        )
        action.approval_id = approval.id
        action.status = "waiting_approval"
    session.flush()
    return decision


def record_effect_grant(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    action_id: uuid.UUID,
    subject_type: str,
    subject_id: uuid.UUID,
    subject_version: int,
    payload: dict[str, object],
    summary: dict[str, object],
    required_permission: str,
    expires_at: datetime,
) -> uuid.UUID:
    """Project an automatic action into a legacy exact-payload executor subject.

    Session 07 uses this for a ReplyDraft, with ``approval_payload`` as ``payload``.
    It records a policy-channel approval for the existing executor, while the action keeps
    the immutable delegation evidence. The hash must be the same exact effect payload.
    """
    action = fence_action(session, clock, ctx.workspace_id, action_id)
    if action.policy_grant is None or action.approval_id is not None:
        raise AppError("CONFLICT_STATE", entity="agent_action", status=action.status)
    expected = {
        "dm.send": ("reply_draft", "reply.approve"),
        "content.publish": ("content_item", "content.approve"),
    }.get(action.action_type)
    if expected != (subject_type, required_permission):
        raise AppError("APPROVAL_STALE")
    if action.payload_hash != payload_hash(payload):
        raise AppError("APPROVAL_STALE")
    approval = record_policy_grant(
        session,
        clock,
        ctx,
        action=APPROVALS[action.action_type][0],
        subject_type=subject_type,
        subject_id=subject_id,
        subject_version=subject_version,
        payload=payload,
        summary=summary,
        required_permission=required_permission,
        expires_at=expires_at,
        execute_before=action.execute_before,
    )
    action.approval_id = approval.id
    return approval.id
