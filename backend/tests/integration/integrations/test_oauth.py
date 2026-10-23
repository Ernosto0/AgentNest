"""Session-bound OAuth lifecycle, all HTTP via explicitly synthetic MockTransport."""

import uuid
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.audit.models import AuditLog
from app.core.security import TokenKeyRing, account_token_aad, hash_token
from app.identity.models import AuthSession, WorkspaceMember
from app.inbox.models import Conversation, Message, ReplyDraft
from app.inbox.payloads import SendReplyPayload
from app.integrations.instagram import oauth, registry
from app.integrations.instagram.meta import MetaInstagramProvider
from app.integrations.instagram.models import OAuthState, SocialAccount
from app.jobs.models import Job
from app.jobs.queue import enqueue
from app.jobs.registry import JobContext, get_handler
from app.operations import oauth_router
from app.operations.payloads import ResumeAccountPayload
from tests.factories import create_workspace
from tests.helpers.publishing import GuardedFactory

KEYS = "k1:a2tra2tra2tra2tra2tra2tra2tra2tra2tra2tra2s="


@pytest.fixture
def flow(env, settings, app, shared_session_factory, monkeypatch):
    cfg = settings.model_copy(
        update={
            "instagram_enabled_providers": "meta",
            "token_encryption_keys": SecretStr(KEYS),
            "token_encryption_active_key_id": "k1",
            "meta_stories_enabled": False,
        }
    )
    app.state.settings = cfg
    guard = GuardedFactory(shared_session_factory)
    monkeypatch.setattr(oauth_router, "get_session_factory", lambda: guard)
    original = oauth.exchange_code_for_long_lived_token
    calls = []
    hooks = []

    def handle(request):
        assert guard.open_transactions() == 0
        assert not env.session.in_transaction(), "request-auth transaction leaked across OAuth HTTP"
        calls.append(request)
        if hooks:
            hooks.pop(0)()
        if request.url.host == "api.instagram.com":
            return httpx.Response(
                200,
                json={
                    "access_token": "synthetic-short",
                    "user_id": "123",
                    "permissions": [oauth.SCOPES[1]],
                },
            )
        if request.url.path == "/access_token":
            return httpx.Response(
                200, json={"access_token": "synthetic-long", "expires_in": 5184000}
            )
        return httpx.Response(200, json={"user_id": "123", "username": "offline-account"})

    monkeypatch.setattr(
        oauth,
        "exchange_code_for_long_lived_token",
        lambda settings, code: original(settings, code, transport=httpx.MockTransport(handle)),
    )
    monkeypatch.setattr(
        registry,
        "MetaInstagramProvider",
        lambda clock, secret, version: MetaInstagramProvider(
            clock, secret, version, transport=httpx.MockTransport(handle)
        ),
    )
    return cfg, guard, calls, hooks


def start(env, **kwargs):
    response = env.call(env.owner, "POST", "/social-accounts/instagram/connect", json=kwargs)
    assert response.status_code == 200, response.text
    return parse_qs(urlsplit(response.json()["authorize_url"]).query)["state"][0]


def callback(env, state, **kwargs):
    return env.owner.client.get(
        "/oauth/instagram/callback",
        params={"state": state, "code": "synthetic-code", **kwargs},
        follow_redirects=False,
    )


def test_connect_consumes_before_exchange_encrypts_and_whitelists_response(env, flow):
    cfg, guard, calls, hooks = flow
    raw = start(env)
    row = env.session.scalar(select(OAuthState))
    assert row.state_hash == hash_token(raw) and raw not in repr(row.state_hash)
    assert row.expires_at == env.clock.now() + timedelta(minutes=10)
    env.session.commit()

    def consumed():
        with guard() as session:
            assert session.scalar(select(OAuthState.used_at)) is not None

    hooks.append(consumed)
    response = callback(env, raw)
    assert response.status_code == 303 and response.headers["location"].endswith("?oauth=connected")
    env.session.expire_all()
    account = env.session.scalar(select(SocialAccount))
    assert account.status == "connected" and not account.is_simulated
    assert account.capabilities == {
        "messaging": True,
        "publish_feed_image": False,
        "publish_story_image": False,
    }
    assert (
        TokenKeyRing(KEYS, "k1").decrypt(
            account.token_ciphertext,
            account.token_key_id,
            aad=account_token_aad(env.workspace.id, account.id),
        )
        == "synthetic-long"
    )
    assert env.session.scalar(
        select(AuditLog.id).where(AuditLog.action == "social_account.connected")
    )
    listed = env.call(env.owner, "GET", "/social-accounts").json()
    assert "synthetic-long" not in str(listed) and "token_ciphertext" not in str(listed)
    assert callback(env, raw).status_code == 400
    assert len(calls) == 3


@pytest.mark.parametrize("case", ["unknown", "expired", "used", "invalidated", "wrong_user"])
def test_invalid_states_never_exchange_or_leak_workspace(env, flow, case):
    raw = start(env)
    row = env.session.scalar(select(OAuthState))
    if case == "unknown":
        raw = "unknown-state"
    if case == "expired":
        row.expires_at = env.clock.now()
    if case == "used":
        row.used_at = env.clock.now()
    if case == "invalidated":
        row.invalidated_at = env.clock.now()
    env.session.commit()
    client = env.manager.client if case == "wrong_user" else env.owner.client
    response = client.get(
        "/oauth/instagram/callback",
        params={"state": raw, "code": "private-code"},
        follow_redirects=False,
    )
    assert response.status_code == 400 and response.json()["code"] == "OAUTH_STATE_INVALID"
    assert str(env.workspace.id) not in response.text
    assert not flow[2]
    if case == "wrong_user":
        env.session.refresh(row)
        assert row.used_at is None


def test_denial_consumes_and_discards_untrusted_text(env, flow):
    raw = start(env)
    response = callback(env, raw, error="secret-provider-message")
    assert (
        response.status_code == 303 and "code=OAUTH_STATE_INVALID" in response.headers["location"]
    )
    assert "secret-provider-message" not in str(response.headers)
    assert not flow[2]
    assert callback(env, raw).status_code == 400


@pytest.mark.parametrize("when", ["before", "during"])
def test_revoked_permission_cannot_connect(env, flow, when):
    raw = start(env)

    def revoke():
        with flow[1]() as session:
            member = session.get(WorkspaceMember, (env.workspace.id, env.owner.user.id))
            member.role = "staff"
            session.commit()

    if when == "before":
        revoke()
    else:
        flow[3].append(revoke)
    response = callback(env, raw)
    assert "code=FORBIDDEN" in response.headers["location"]
    assert env.session.scalar(select(SocialAccount.id)) is None
    assert env.session.scalar(select(OAuthState.used_at)) is not None


@pytest.mark.parametrize("external", ["123", "different"])
def test_reconnect_same_external_only_and_resume_job(env, flow, external):
    account = SocialAccount(
        workspace_id=env.workspace.id,
        provider_kind="meta",
        external_account_id=external,
        status="needs_reauth",
    )
    env.session.add(account)
    env.session.commit()
    raw = start(env, purpose="reconnect", social_account_id=str(account.id))
    response = callback(env, raw)
    env.session.refresh(account)
    if external == "different":
        assert "code=ACCOUNT_MISMATCH" in response.headers["location"]
        assert account.token_ciphertext is None and account.status == "needs_reauth"
    else:
        assert response.headers["location"].endswith("oauth=connected")
        assert account.status == "connected"
        assert env.session.scalar(select(Job.id).where(Job.job_type == "resume_account"))
        assert env.session.scalar(
            select(AuditLog.id).where(AuditLog.action == "account.reconnected")
        )


def test_tenant_foreign_key_for_oauth_reconnect(env, flow):
    foreign = create_workspace(env.session)
    account = SocialAccount(
        workspace_id=foreign.id,
        provider_kind="meta",
        external_account_id="other",
        status="needs_reauth",
    )
    env.session.add(account)
    env.session.flush()
    with pytest.raises(IntegrityError), env.session.begin_nested():  # noqa: PT012
        env.session.add(
            OAuthState(
                workspace_id=env.workspace.id,
                user_id=env.owner.user.id,
                state_hash=b"x" * 32,
                purpose="reconnect",
                social_account_id=account.id,
                expires_at=env.clock.now() + timedelta(minutes=10),
            )
        )
        env.session.flush()


def test_connect_permissions_csrf_disabled_and_foreign_ids(env, flow):
    assert env.call(env.staff, "POST", "/social-accounts/instagram/connect").status_code == 403
    assert env.owner.client.post(env.base + "/social-accounts/instagram/connect").status_code == 403
    assert (
        env.call(
            env.owner,
            "POST",
            "/social-accounts/instagram/connect",
            json={"purpose": "reconnect", "social_account_id": str(uuid.uuid4())},
        ).status_code
        == 404
    )


def test_redirect_preserves_sliding_cookie(env, flow):
    raw = start(env)
    for row in env.session.scalars(select(AuthSession)):
        row.last_seen_at = env.clock.now() - timedelta(hours=2)
    env.session.commit()
    response = callback(env, raw)
    assert "agentnest_session=" in response.headers.get("set-cookie", "")


def test_reconnect_callback_resumes_queued_reply_through_registered_handler(env, flow):
    account = SocialAccount(
        workspace_id=env.workspace.id,
        provider_kind="meta",
        external_account_id="123",
        status="needs_reauth",
    )
    env.session.add(account)
    env.session.flush()
    conversation = Conversation(
        workspace_id=env.workspace.id,
        social_account_id=account.id,
        customer_external_id="customer",
        last_inbound_at=env.clock.now(),
    )
    env.session.add(conversation)
    env.session.flush()
    message = Message(
        workspace_id=env.workspace.id,
        conversation_id=conversation.id,
        social_account_id=account.id,
        direction="inbound",
        sender_kind="customer",
        text="hello",
        provider_timestamp=env.clock.now(),
    )
    env.session.add(message)
    env.session.flush()
    draft = ReplyDraft(
        workspace_id=env.workspace.id,
        conversation_id=conversation.id,
        covers_through_message_id=message.id,
        source="owner",
        text="hello",
        decision="approval_required",
        status="queued",
        created_by_actor_type="user",
    )
    env.session.add(draft)
    env.session.flush()
    job_id = enqueue(
        env.session,
        "send_reply",
        SendReplyPayload(reply_draft_id=draft.id),
        workspace_id=env.workspace.id,
        correlation_id=None,
        dedup_key=f"send_reply:{draft.id}",
        run_at=env.clock.now() + timedelta(hours=1),
        clock=env.clock,
    )
    env.session.commit()
    raw = start(env, purpose="reconnect", social_account_id=str(account.id))
    assert callback(env, raw).headers["location"].endswith("oauth=connected")
    resume_job = env.session.scalar(select(Job).where(Job.job_type == "resume_account"))
    handler = get_handler("resume_account")
    assert handler is not None
    env.session.commit()
    handler.func(
        JobContext(
            resume_job.id,
            "resume_account",
            env.workspace.id,
            None,
            ResumeAccountPayload(social_account_id=account.id),
            1,
            3,
            flow[1],
            env.clock,
            lambda: None,
        )
    )
    env.session.expire_all()
    send_job = env.session.get(Job, job_id)
    assert send_job.status == "queued" and send_job.run_at == env.clock.now()
    assert (
        len(list(env.session.scalars(select(Job).where(Job.dedup_key == f"send_reply:{draft.id}"))))
        == 1
    )


def test_disconnect_during_exchange_cannot_resurrect_account(env, flow):
    from app.operations import accounts

    account = SocialAccount(
        workspace_id=env.workspace.id,
        provider_kind="meta",
        external_account_id="123",
        status="needs_reauth",
    )
    env.session.add(account)
    env.session.commit()
    raw = start(env, purpose="reconnect", social_account_id=str(account.id))

    def disconnect():
        with flow[1]() as session:
            accounts.disconnect(session, env.clock, env.ctx(env.owner), account.id)

    flow[3].append(disconnect)
    response = callback(env, raw)
    assert "code=OAUTH_STATE_INVALID" in response.headers["location"]
    env.session.refresh(account)
    assert account.status == "disconnected" and account.token_ciphertext is None


def test_reuses_latest_disconnected_row_and_handles_external_conflict(env, flow):
    for _ in range(2):
        env.session.add(
            SocialAccount(
                workspace_id=env.workspace.id,
                provider_kind="meta",
                external_account_id="123",
                status="disconnected",
            )
        )
    env.session.commit()
    raw = start(env)
    assert callback(env, raw).headers["location"].endswith("oauth=connected")
    assert len(list(env.session.scalars(select(SocialAccount)))) == 2


def test_external_account_connected_elsewhere_is_safe_conflict(env, flow):
    other = create_workspace(env.session)
    env.session.add(
        SocialAccount(
            workspace_id=other.id,
            provider_kind="meta",
            external_account_id="123",
            status="connected",
        )
    )
    env.session.commit()
    raw = start(env)
    assert "code=CONFLICT_STATE" in callback(env, raw).headers["location"]
