"""Session 03: versioned account authority and executor fences."""

import uuid
from collections.abc import Callable
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.delegation import (
    ACTIONS,
    ActionRule,
    DelegationChange,
    DelegationPolicy,
    apply,
    authorize_action,
    decide,
    fence_action,
    record_effect_grant,
)
from app.agent.models import AccountAgent, AgentAction, AgentDelegation, AgentSession, AgentThread
from app.approvals import service as approvals_service
from app.approvals.models import Approval
from app.approvals.views import approval_out
from app.core.canonical import payload_hash
from app.core.clock import FrozenClock
from app.core.errors import AppError
from app.integrations.instagram.models import SocialAccount
from tests.helpers.env import Env, build_env


@pytest.fixture
def env(db_session: Session, make_client: Callable[[], TestClient], clock: FrozenClock) -> Env:
    return build_env(db_session, make_client, clock)


def _policy(*, dm: str = "off", delete: str = "off") -> DelegationPolicy:
    actions = {name: ActionRule(mode="off") for name in ACTIONS}
    actions["dm.send"] = ActionRule(mode=dm)
    actions["comment.delete"] = ActionRule(mode=delete)
    return DelegationPolicy(actions=actions)


def _change(policy: DelegationPolicy, config: int, version: int | None) -> DelegationChange:
    return DelegationChange(
        expected_config_version=config,
        expected_delegation_version=version,
        client_request_id=uuid.uuid4(),
        policy=policy,
    )


def _account(env: Env) -> tuple[SocialAccount, AccountAgent]:
    account = SocialAccount(
        workspace_id=env.workspace.id,
        provider_kind="mock",
        external_account_id=f"delegation-{uuid.uuid4().hex}",
        capabilities={"messaging": True, "comment_moderate": True},
    )
    env.session.add(account)
    env.session.flush()
    agent = env.session.scalar(
        select(AccountAgent).where(
            AccountAgent.workspace_id == env.workspace.id,
            AccountAgent.social_account_id == account.id,
        )
    )
    assert agent is not None
    return account, agent


def _action(env: Env, account: SocialAccount, agent: AccountAgent, kind: str) -> AgentAction:
    thread = AgentThread(
        workspace_id=env.workspace.id,
        social_account_id=account.id,
        surface="comment" if kind.startswith("comment.") else "owner_task",
        source_ref=str(uuid.uuid4()),
        controller_epoch=agent.controller_epoch,
    )
    env.session.add(thread)
    env.session.flush()
    run = AgentSession(
        workspace_id=env.workspace.id,
        thread_id=thread.id,
        initiating_event_cursor=0,
        goal_key=str(uuid.uuid4()),
    )
    env.session.add(run)
    env.session.flush()
    action = AgentAction(
        workspace_id=env.workspace.id,
        social_account_id=account.id,
        thread_id=thread.id,
        session_id=run.id,
        intent_key=uuid.uuid4().hex,
        action_type=kind,
        target_ref="own",
        payload_hash=payload_hash({"text": "hello"}),
        initiating_cursor=0,
    )
    env.session.add(action)
    env.session.flush()
    return action


@pytest.mark.parametrize("mode", ["automatic", "ask", "off"])
def test_pure_decision_respects_mode_and_guards(mode: str) -> None:
    result = decide(
        rule=ActionRule(mode=mode),
        source="customer",
        requester_allowed=True,
        account_active=True,
        capability_available=True,
        target_owned=True,
        visibility_allowed=True,
        claims_valid=True,
        quota_available=True,
    )
    assert result.kind == mode
    assert (
        decide(
            rule=ActionRule(mode=mode),
            source="owner_task",
            requester_allowed=False,
            account_active=True,
            capability_available=True,
            target_owned=True,
            visibility_allowed=True,
            claims_valid=True,
            quota_available=True,
        ).kind
        == "blocked"
    )
    assert decide(
        rule=ActionRule(mode=mode),
        source="customer",
        requester_allowed=True,
        account_active=True,
        capability_available=False,
        target_owned=True,
        visibility_allowed=True,
        claims_valid=True,
        quota_available=True,
    ).kind in ("off", "unavailable")


def test_apply_is_versioned_idempotent_and_owner_only(env: Env) -> None:
    account, agent = _account(env)
    change = _change(_policy(dm="automatic"), agent.config_version, None)
    with pytest.raises(AppError, match="FORBIDDEN"):
        apply(env.session, env.clock, env.ctx(env.manager), account.id, change)
    first = apply(env.session, env.clock, env.ctx(env.owner), account.id, change)
    env.session.flush()
    assert first.version == 1 and first.grantor_user_id == env.owner.user.id
    assert agent.state == "inactive" and agent.controller_mode == "legacy"
    assert apply(env.session, env.clock, env.ctx(env.owner), account.id, change).id == first.id
    second = apply(
        env.session,
        env.clock,
        env.ctx(env.owner),
        account.id,
        _change(_policy(dm="ask"), agent.config_version, first.version),
    )
    env.session.flush()
    assert first.revoked_at == env.clock.now() and second.version == 2
    assert (
        env.session.scalar(select(AgentDelegation).where(AgentDelegation.id == second.id))
        is not None
    )
    with pytest.raises(AppError, match="VERSION_CONFLICT"):
        apply(
            env.session,
            env.clock,
            env.ctx(env.owner),
            account.id,
            change.model_copy(update={"client_request_id": uuid.uuid4()}),
        )


def test_automatic_action_has_policy_evidence_and_revocation_fences_projection(env: Env) -> None:
    account, agent = _account(env)
    first = apply(
        env.session,
        env.clock,
        env.ctx(env.owner),
        account.id,
        _change(_policy(dm="automatic", delete="automatic"), agent.config_version, None),
    )
    agent.controller_mode = "agent"
    agent.state = "active"
    action = _action(env, account, agent, "dm.send")
    result = authorize_action(
        env.session,
        env.clock,
        env.ctx(env.owner),
        action.id,
        source="customer",
        target_owned=True,
        visibility_allowed=True,
        claims_valid=True,
        quota_available=True,
    )
    assert result.kind == "automatic" and action.status == "authorized"
    assert action.policy_grant is not None
    assert action.policy_grant["grantor_user_id"] == str(env.owner.user.id)
    assert action.approval_id is None
    assert fence_action(env.session, env.clock, env.workspace.id, action.id) is action
    deletion = _action(env, account, agent, "comment.delete")
    assert (
        authorize_action(
            env.session,
            env.clock,
            env.ctx(env.owner),
            deletion.id,
            source="customer",
            target_owned=True,
            visibility_allowed=True,
            claims_valid=True,
            quota_available=True,
        ).kind
        == "automatic"
    )
    assert deletion.policy_grant is not None and deletion.approval_id is None
    with pytest.raises(AppError, match="APPROVAL_STALE"):
        record_effect_grant(
            env.session,
            env.clock,
            env.ctx(env.owner),
            action_id=action.id,
            subject_type="content_item",
            subject_id=uuid.uuid4(),
            subject_version=1,
            payload={"text": "hello"},
            summary={},
            required_permission="content.approve",
            expires_at=env.clock.now() + timedelta(hours=1),
        )
    apply(
        env.session,
        env.clock,
        env.ctx(env.owner),
        account.id,
        _change(_policy(dm="off"), agent.config_version, first.version),
    )
    with pytest.raises(AppError, match="APPROVAL_STALE"):
        fence_action(env.session, env.clock, env.workspace.id, action.id)


def test_ask_creates_bound_human_approval_and_staff_cannot_decide(env: Env) -> None:
    account, agent = _account(env)
    apply(
        env.session,
        env.clock,
        env.ctx(env.owner),
        account.id,
        _change(_policy(dm="ask"), agent.config_version, None),
    )
    agent.controller_mode = "agent"
    agent.state = "active"
    action = _action(env, account, agent, "dm.send")
    assert (
        authorize_action(
            env.session,
            env.clock,
            env.ctx(env.owner),
            action.id,
            source="customer",
            target_owned=True,
            visibility_allowed=True,
            claims_valid=True,
            quota_available=True,
        ).kind
        == "ask"
    )
    approval = env.session.get(Approval, action.approval_id)
    assert approval is not None and approval.status == "pending"
    assert approval.subject_type == "agent_action" and approval.decided_by_user_id is None
    assert approval.required_permission == "reply.approve"
    assert approval.payload_hash == action.payload_hash
    with pytest.raises(AppError, match="FORBIDDEN"):
        approvals_service.decide(
            env.session,
            env.clock,
            env.ctx(env.staff),
            approval.id,
            decision="approve",
            payload_hash=approval.payload_hash,
        )
    approvals_service.decide(
        env.session,
        env.clock,
        env.ctx(env.owner),
        approval.id,
        decision="approve",
        payload_hash=approval.payload_hash,
    )
    assert action.status == "authorized"


def test_foreign_account_route_is_404_and_staff_cannot_apply(env: Env) -> None:
    account, agent = _account(env)
    body = _change(_policy(dm="automatic"), agent.config_version, None).model_dump(mode="json")
    denied = env.call(
        env.staff, "POST", f"/accounts/{account.id}/agent/delegation/apply", json=body
    )
    assert denied.status_code == 403
    missing = env.call(
        env.owner, "POST", f"/accounts/{uuid.uuid4()}/agent/delegation/preview", json=body
    )
    assert missing.status_code == 404


def test_policy_edit_fences_pending_agent_approval(env: Env) -> None:
    account, agent = _account(env)
    first = apply(
        env.session,
        env.clock,
        env.ctx(env.owner),
        account.id,
        _change(_policy(dm="ask"), agent.config_version, None),
    )
    agent.controller_mode = "agent"
    agent.state = "active"
    action = _action(env, account, agent, "dm.send")
    authorize_action(
        env.session,
        env.clock,
        env.ctx(env.owner),
        action.id,
        source="customer",
        target_owned=True,
        visibility_allowed=True,
        claims_valid=True,
        quota_available=True,
    )
    approval = env.session.get(Approval, action.approval_id)
    assert approval is not None and approval.status == "pending"
    apply(
        env.session,
        env.clock,
        env.ctx(env.owner),
        account.id,
        _change(_policy(dm="off"), agent.config_version, first.version),
    )
    with pytest.raises(AppError, match="APPROVAL_STALE"):
        approvals_service.decide(
            env.session,
            env.clock,
            env.ctx(env.owner),
            approval.id,
            decision="approve",
            payload_hash=approval.payload_hash,
        )
    assert action.status == "waiting_approval" and approval.status == "pending"
    assert approval_out(env.session, env.clock, env.ctx(env.owner), approval).can_decide is False


def test_daily_action_limit_is_reserved_under_account_lock(env: Env) -> None:
    account, agent = _account(env)
    rules = {name: ActionRule(mode="off") for name in ACTIONS}
    rules["dm.send"] = ActionRule(mode="automatic", max_per_day=1)
    apply(
        env.session,
        env.clock,
        env.ctx(env.owner),
        account.id,
        _change(DelegationPolicy(actions=rules), agent.config_version, None),
    )
    agent.controller_mode = "agent"
    agent.state = "active"
    first = _action(env, account, agent, "dm.send")
    second = _action(env, account, agent, "dm.send")
    for action, expected in ((first, "automatic"), (second, "unavailable")):
        decision = authorize_action(
            env.session,
            env.clock,
            env.ctx(env.owner),
            action.id,
            source="customer",
            target_owned=True,
            visibility_allowed=True,
            claims_valid=True,
            quota_available=True,
        )
        assert decision.kind == expected
    assert first.authorized_at == env.clock.now() and second.authorized_at is None
