"""Signed fixtures through broker, approval and ledger to MockTransport."""

import json
import uuid
from datetime import timedelta

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.agent.coordinator import claim
from app.agent.delegation import DelegationChange, DelegationPolicy, apply
from app.agent.grounding import FactEvidence
from app.agent.models import AccountAgent, AgentAction, AgentDelegation
from app.agent.tools.broker import ToolInputError, build_default_broker
from app.approvals import service as approvals
from app.approvals.models import Approval
from app.comments.models import PrivateReplyOpportunity, PublicComment, PublicMedia
from app.comments.private_reply import PrivateReplyArgs, real_refusal
from app.comments.private_reply import propose as propose_private
from app.core.config import get_settings
from app.identity.models import Workspace
from app.inbox.ingest import ingest_webhook
from app.inbox.models import InboundEvent
from app.integrations.instagram.base import AccountRef
from app.integrations.instagram.meta import MetaInstagramProvider
from app.integrations.instagram.models import SocialAccount
from app.integrations.instagram.oauth import COMMENTS_SCOPE, compute_capabilities
from app.integrations.instagram.webhook_format import serialize, sign
from app.operations.models import Operation
from app.operations.private_reply import execute, reconcile
from tests.factories import create_fact, money
from tests.integration.agent.test_comments import context, process
from tests.integration.agent.test_coordinator import deps
from tests.integration.agent.test_dm import setup

pytestmark = pytest.mark.commits


def world_meta(factory, clock, *, flag=True, mode=None):
    world = setup(factory, clock)
    settings = world[3].model_copy(
        update={
            "instagram_enabled_providers": "mock,meta",
            "meta_app_secret": SecretStr("offline-secret"),
        }
    )
    world = (*world[:3], settings)
    with factory() as db:
        account = db.get(SocialAccount, world[1])
        account.provider_kind = "meta"
        account.comment_automation_enabled = flag
        account.granted_scopes = [COMMENTS_SCOPE]
        account.capabilities = compute_capabilities(account.granted_scopes, True, flag)
        delegation = db.scalar(
            select(AgentDelegation).where(AgentDelegation.social_account_id == account.id)
        )
        agent = db.scalar(select(AccountAgent).where(AccountAgent.social_account_id == account.id))
        policy = DelegationPolicy.model_validate(delegation.policy)
        policy.actions["comment.private_reply"].mode = mode or "ask"
        apply(
            db,
            clock,
            world[0],
            account.id,
            DelegationChange(
                expected_config_version=agent.config_version,
                expected_delegation_version=delegation.version,
                client_request_id=uuid.uuid4(),
                policy=policy,
            ),
        )
        db.commit()
    return world


def deliver(factory, clock, world, *, external="comment", author="person", parent=None):
    value = {
        "id": external,
        "from": {"id": author, "username": "not-stored"},
        "text": "What is the price?",
        "media": {"id": "media", "media_product_type": "FEED"},
    }
    if parent:
        value["parent_id"] = parent
    raw = serialize(
        {
            "object": "instagram",
            "entry": [
                {
                    "id": world[2],
                    "time": int(clock.now().timestamp()),
                    "changes": [{"field": "comments", "value": value}],
                }
            ],
        }
    )
    with factory() as db:
        result = ingest_webhook(
            db,
            clock,
            world[3],
            "meta",
            raw,
            {"X-Hub-Signature-256": sign(raw, world[3].meta_app_secret.get_secret_value())},
        )
    process(factory, clock, world)
    return result


def prepare(factory, clock, world):
    assert deliver(factory, clock, world).received == 1
    with factory() as db:
        ctx = context(db, world)
        source = db.scalar(select(PublicComment).where(PublicComment.social_account_id == world[1]))
        target = (source.id, source.version)
    assert claim(deps(factory, clock), world[0].workspace_id, ctx.thread_id)
    return ctx, target


def propose(factory, clock, ctx, target, template="Hello!", evidence=None):
    request = PrivateReplyArgs(
        comment_id=target[0],
        comment_version=target[1],
        reply={"template": template, "language": "en", "fact_sources": evidence or []},
    )
    with factory() as db:
        answer = build_default_broker().dispatch(
            db,
            clock,
            ctx,
            name="comment.private_reply",
            version="v1",
            arguments=request.model_dump(mode="json"),
        )
        db.commit()
        return answer


def transport(monkeypatch, factory, clock, world, outcome="ok"):
    posts = []

    def handle(request):
        # An independent transaction must see the write-ahead ledger before any request.
        with factory() as db:
            assert db.scalar(select(Operation)).status == "in_progress"
        if request.method == "POST":
            posts.append(json.loads(request.content))
            if outcome == "unknown":
                raise httpx.ReadTimeout("secret-token", request=request)
            return httpx.Response(
                400 if outcome == "failed" else 200,
                json=(
                    {"error": {"code": 100, "message": "secret-token"}}
                    if outcome == "failed"
                    else {"message_id": "reply", "recipient_id": "dm-person"}
                ),
            )
        if request.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "media", "owner": {"id": world[2]}})
        return httpx.Response(
            200,
            json={
                "id": "comment",
                "media": {"id": "media"},
                "timestamp": clock.now().isoformat(),
                "text": "price?",
                "hidden": False,
            },
        )

    provider = MetaInstagramProvider(clock, "", "v25.0", transport=httpx.MockTransport(handle))

    def lookup(kind, **kwargs):
        assert kind == "meta"
        return provider

    monkeypatch.setattr("app.operations.private_reply.get_provider", lookup)
    monkeypatch.setattr(
        "app.operations.private_reply.account_ref",
        lambda account, settings: AccountRef(
            account.id, account.workspace_id, account.external_account_id, lambda: "secret-token"
        ),
    )
    return posts


@pytest.mark.parametrize("outcome", ["ok", "unknown", "failed"])
def test_approval_first_verified_answer_and_no_resend(
    session_factory, clock, monkeypatch, outcome, caplog
):
    factory = session_factory
    world = world_meta(factory, clock)
    ctx, target = prepare(factory, clock, world)
    # Bare prices and unverified placeholders cannot create an opportunity.
    denied = propose(factory, clock, ctx, target, "The price is 6000 TRY.")
    assert not denied.ok or not denied.data.get("valid", True)
    with factory() as db:
        workspace = db.get(Workspace, world[0].workspace_id)
        fact = create_fact(
            db, workspace, "custom.price", money(), value_type="money", verified=False
        )
        fact_id = fact.id
        db.commit()
    denied = propose(
        factory,
        clock,
        ctx,
        target,
        "Price: {{fact:custom.price}}",
        [FactEvidence(id=fact_id, version=1)],
    )
    assert not denied.ok or not denied.data.get("valid", True)
    # Use another verified key; preserve history of the unverified fact.
    with factory() as db:
        workspace = db.get(Workspace, world[0].workspace_id)
        create_fact(db, workspace, "policy.price_disclosure", {"value": "share"})
        fact = create_fact(db, workspace, "custom.verified_price", money(), value_type="money")
        evidence = [FactEvidence(id=fact.id, version=1)]
        db.commit()
    answer = propose(factory, clock, ctx, target, "Price: {{fact:custom.verified_price}}", evidence)
    assert answer.ok, answer.error
    assert answer.data.get("status") == "waiting_approval", answer.data
    action_id = uuid.UUID(answer.data["action_id"])
    posts = transport(monkeypatch, factory, clock, world, outcome)
    execute(factory, clock, world[3], world[0].workspace_id, action_id)
    assert posts == []
    with factory() as db:
        approval = db.get(Approval, uuid.UUID(answer.data["approval_id"]))
        approvals.decide(
            db, clock, world[0], approval.id, decision="approve", payload_hash=approval.payload_hash
        )
    execute(factory, clock, world[3], world[0].workspace_id, action_id)
    execute(factory, clock, world[3], world[0].workspace_id, action_id)
    with factory() as db:
        op = db.scalar(select(Operation))
        expected = {"ok": "succeeded", "unknown": "outcome_unknown", "failed": "failed"}[outcome]
        assert op.status == expected
        assert not op.is_simulated and op.provider_kind == "meta" and op.attempts == 1
        assert "secret-token" not in str(op.provider_ref) + str(op.result)
        op_id = op.id
        assert db.scalar(select(PublicMedia)).ownership_state == "verified_provider"
    reconcile(factory, clock, world[3], world[0].workspace_id, op_id)
    assert len(posts) == 1 and "6000" in posts[0]["message"]["text"].replace(",", "").replace(
        ".", ""
    )
    assert "{{fact:" not in posts[0]["message"]["text"]
    assert "secret-token" not in caplog.text


def test_flag_off_stops_pending_automatic_reply(session_factory, clock, monkeypatch):
    world = world_meta(session_factory, clock, mode="automatic")
    ctx, target = prepare(session_factory, clock, world)
    answer = propose(session_factory, clock, ctx, target)
    assert answer.ok and answer.data["status"] == "queued"
    with session_factory() as db:
        account = db.get(SocialAccount, world[1])
        account.comment_automation_enabled = False
        db.commit()
    monkeypatch.setattr(
        "app.operations.private_reply.get_provider",
        lambda *a, **k: pytest.fail("dispatch after opt-out"),
    )
    action_id = uuid.UUID(answer.data["action_id"])
    execute(session_factory, clock, world[3], world[0].workspace_id, action_id)
    with session_factory() as db:
        assert db.get(AgentAction, action_id).outcome_code == "CAPABILITY_MISSING"
        assert db.scalar(select(Operation)) is None


def test_opt_out_redacts_and_duplicate_delivery(session_factory, clock):
    world = world_meta(session_factory, clock, flag=False)
    assert deliver(session_factory, clock, world).ignored == 1
    assert deliver(session_factory, clock, world).duplicates == 1
    with session_factory() as db:
        row = db.scalar(select(InboundEvent))
        assert row.payload == {} and row.ignore_reason == "COMMENT_AUTOMATION_OFF"
        assert db.scalar(select(PublicComment)) is None


def test_commenter_limit_across_comments_and_relaxed_setting(session_factory, clock, monkeypatch):
    world = world_meta(session_factory, clock, mode="automatic")
    ctx, target = prepare(session_factory, clock, world)
    assert propose(session_factory, clock, ctx, target).ok
    deliver(session_factory, clock, world, external="second")
    with session_factory() as db:
        second = db.scalar(select(PublicComment).where(PublicComment.external_id == "second"))
        assert real_refusal(db, clock, second) == "PRIVATE_REPLY_COMMENTER_LIMIT"
        monkeypatch.setenv("COMMENT_PRIVATE_REPLY_LIMIT_SCOPE", "comment")
        get_settings.cache_clear()
        assert real_refusal(db, clock, second) is None
        monkeypatch.setenv("COMMENT_PRIVATE_REPLY_LIMIT_SCOPE", "commenter")
        get_settings.cache_clear()
        first = db.scalar(select(PrivateReplyOpportunity))
        for state in ["failed", "cancelled"]:
            first.status = state
            db.flush()
            assert real_refusal(db, clock, second) is None
        first.status = "reserved"
        first.eligibility_expires_at = clock.now() - timedelta(seconds=1)
        db.flush()
        assert real_refusal(db, clock, second) is None
        first.status = "outcome_unknown"
        db.flush()
        assert real_refusal(db, clock, second) == "PRIVATE_REPLY_COMMENTER_LIMIT"


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ("expired", "PRIVATE_REPLY_WINDOW_EXPIRED"),
        ("author", "PRIVATE_REPLY_COMMENTER_UNKNOWN"),
        ("parent", "PRIVATE_REPLY_NOT_TOP_LEVEL"),
        ("used", "PRIVATE_REPLY_COMMENT_ALREADY_USED"),
    ],
)
def test_proposal_refusal_reason_codes(session_factory, clock, change, code):
    from app.integrations.instagram.base import META_PRIVATE_REPLY_WINDOW

    world = world_meta(session_factory, clock)
    ctx, target = prepare(session_factory, clock, world)
    if change == "used":
        assert propose(session_factory, clock, ctx, target).ok
    else:
        with session_factory() as db:
            comment = db.get(PublicComment, target[0])
            if change == "expired":
                comment.provider_timestamp = clock.now() - META_PRIVATE_REPLY_WINDOW
            elif change == "author":
                comment.author_external_id = None
            db.commit()
        if change == "parent":
            deliver(session_factory, clock, world, external="child", parent="comment")
            with session_factory() as db:
                comment = db.scalar(
                    select(PublicComment).where(PublicComment.external_id == "child")
                )
                target = (comment.id, comment.version)
    request = PrivateReplyArgs(
        comment_id=target[0],
        comment_version=target[1],
        reply={"template": "Hello!", "language": "en"},
    )
    with session_factory() as db, pytest.raises(ToolInputError, match=code):
        propose_private(db, clock, ctx, request)


def test_dispatch_rechecks_expiry_and_real_owner_grant(session_factory, clock, monkeypatch):
    from app.integrations.instagram.base import META_PRIVATE_REPLY_WINDOW

    world = world_meta(session_factory, clock, mode="automatic")
    ctx, target = prepare(session_factory, clock, world)
    answer = propose(session_factory, clock, ctx, target)
    action_id = uuid.UUID(answer.data["action_id"])
    with session_factory() as db:
        action = db.get(AgentAction, action_id)
        assert action.policy_grant is not None and action.approval_id is None
    clock.advance(META_PRIVATE_REPLY_WINDOW)
    monkeypatch.setattr(
        "app.operations.private_reply.get_provider",
        lambda *a, **kw: pytest.fail("expired dispatch"),
    )
    execute(session_factory, clock, world[3], world[0].workspace_id, action_id)
    with session_factory() as db:
        assert db.get(AgentAction, action_id).outcome_code == "PRIVATE_REPLY_WINDOW_EXPIRED"


def test_opt_out_hides_tool_and_refuses_stale_tool_request(session_factory, clock):
    world = world_meta(session_factory, clock)
    ctx, target = prepare(session_factory, clock, world)
    with session_factory() as db:
        account = db.get(SocialAccount, world[1])
        account.comment_automation_enabled = False
        account.capabilities = compute_capabilities(account.granted_scopes, True, False)
        offered = build_default_broker().available(ctx, capabilities=account.capabilities)
        assert "comment.private_reply" not in {tool.name for tool in offered}
        db.commit()
    answer = propose(session_factory, clock, ctx, target)
    assert not answer.ok
    request = PrivateReplyArgs(
        comment_id=target[0],
        comment_version=target[1],
        reply={"template": "Hello!", "language": "en"},
    )
    with session_factory() as db, pytest.raises(ToolInputError, match="CAPABILITY_MISSING"):
        propose_private(db, clock, ctx, request)


@pytest.mark.parametrize("revoked", [False, True])
def test_automatic_real_reply_requires_current_owner_grant(
    session_factory, clock, monkeypatch, revoked
):
    from app.identity.models import WorkspaceMember

    world = world_meta(session_factory, clock, mode="automatic")
    ctx, target = prepare(session_factory, clock, world)
    answer = propose(session_factory, clock, ctx, target)
    assert answer.ok and answer.data["status"] == "queued"
    action_id = uuid.UUID(answer.data["action_id"])
    posts = transport(monkeypatch, session_factory, clock, world)
    with session_factory() as db:
        action = db.get(AgentAction, action_id)
        assert action.policy_grant is not None and action.approval_id is None
        if revoked:
            delegation = db.scalar(
                select(AgentDelegation).where(
                    AgentDelegation.social_account_id == world[1],
                    AgentDelegation.revoked_at.is_(None),
                )
            )
            member = db.get(WorkspaceMember, (world[0].workspace_id, delegation.grantor_user_id))
            member.role = "manager"
        db.commit()
    execute(session_factory, clock, world[3], world[0].workspace_id, action_id)
    assert len(posts) == (0 if revoked else 1)
    with session_factory() as db:
        assert db.get(AgentAction, action_id).status == ("cancelled" if revoked else "succeeded")
