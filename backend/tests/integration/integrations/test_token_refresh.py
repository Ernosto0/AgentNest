"""Daily refresh eligibility, ledger/credential fencing, retry and worker lifecycle."""

import uuid
from datetime import timedelta

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.audit.models import AuditLog
from app.core.security import TokenKeyRing, account_token_aad
from app.integrations.instagram import registry
from app.integrations.instagram.meta import MetaInstagramProvider
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.jobs.registry import get_handler
from app.jobs.testing import run_due_jobs
from app.notifications.models import Notification
from app.operations import accounts, jobs, refresh
from app.operations.models import Operation
from tests.factories import create_workspace
from tests.helpers.publishing import GuardedFactory

KEYS = "k1:a2tra2tra2tra2tra2tra2tra2tra2tra2tra2tra2s="


@pytest.fixture
def token_env(env, settings, shared_session_factory, monkeypatch):
    cfg = settings.model_copy(
        update={
            "instagram_enabled_providers": "meta",
            "token_encryption_keys": SecretStr(KEYS),
            "token_encryption_active_key_id": "k1",
        }
    )
    account = SocialAccount(
        workspace_id=env.workspace.id,
        provider_kind="meta",
        external_account_id="123",
        status="connected",
        token_expires_at=env.clock.now() + timedelta(days=10),
        token_refreshed_at=env.clock.now() - timedelta(days=2),
    )
    env.session.add(account)
    env.session.flush()
    account.token_ciphertext, account.token_key_id = TokenKeyRing(KEYS, "k1").encrypt(
        "synthetic-original", aad=account_token_aad(env.workspace.id, account.id)
    )
    env.session.commit()
    guard = GuardedFactory(shared_session_factory)
    responses = []
    calls = []
    hooks = []

    def handle(request):
        assert guard.open_transactions() == 0
        assert not env.session.in_transaction()
        assert request.url.params["access_token"] == "synthetic-original"
        calls.append(request)
        with guard() as session:
            op = session.scalar(select(Operation))
            assert op.status == "in_progress" and op.attempts >= 1
        if hooks:
            hooks.pop(0)()
        return (
            responses.pop(0)
            if responses
            else httpx.Response(
                200, json={"access_token": "synthetic-rotated", "expires_in": 5184000}
            )
        )

    monkeypatch.setattr(
        registry,
        "MetaInstagramProvider",
        lambda clock, secret, version: MetaInstagramProvider(
            clock, secret, version, transport=httpx.MockTransport(handle)
        ),
    )
    monkeypatch.setattr(jobs, "get_settings", lambda: cfg)
    return cfg, account, guard, responses, calls, hooks


def execute(env, token_env, **kwargs):
    cfg, account, guard, *_ = token_env
    env.session.commit()
    return refresh.execute_refresh(guard, env.clock, cfg, env.workspace.id, account.id, **kwargs)


def test_refresh_commits_ledger_encrypts_and_replay_is_idempotent(env, token_env):
    cfg, account, _, _, calls, _ = token_env
    before = account.token_ciphertext
    assert execute(env, token_env).kind == "done"
    env.session.refresh(account)
    assert account.token_ciphertext != before
    assert account.token_expires_at == env.clock.now() + timedelta(days=60)
    assert (
        TokenKeyRing(KEYS, "k1").decrypt(
            account.token_ciphertext,
            account.token_key_id,
            aad=account_token_aad(env.workspace.id, account.id),
        )
        == "synthetic-rotated"
    )
    op = env.session.scalar(select(Operation))
    assert op.status == "succeeded" and op.attempts == 1
    assert "synthetic" not in str(op.result) + str(op.provider_ref)
    assert env.session.scalar(
        select(AuditLog.id).where(AuditLog.action == "social_account.token_refreshed")
    )
    assert execute(env, token_env).kind == "done" and len(calls) == 1


@pytest.mark.parametrize(
    ("age", "expiry", "expected"),
    [(24, 20, True), (23, 20, False), (24, 21, False), (25, 19, True)],
)
def test_scan_boundaries_and_any_status_dedup(env, token_env, age, expiry, expected):
    cfg, account, *_ = token_env
    account.token_refreshed_at = env.clock.now() - timedelta(hours=age)
    account.token_expires_at = env.clock.now() + timedelta(days=expiry)
    env.session.commit()
    assert refresh.scan(env.session, env.clock, cfg) == int(expected)
    for job in env.session.scalars(select(Job).where(Job.job_type == "refresh_token")):
        job.status = "succeeded"
    env.session.commit()
    assert refresh.scan(env.session, env.clock, cfg) == 0


@pytest.mark.parametrize("status", ["needs_reauth", "disconnected"])
def test_scan_ignores_inactive_account(env, token_env, status):
    cfg, account, *_ = token_env
    account.status = status
    env.session.commit()
    assert refresh.scan(env.session, env.clock, cfg) == 0
    assert execute(env, token_env).kind == "done" and not token_env[4]


@pytest.mark.parametrize("expiry", [0, -1])
def test_expired_token_requires_reauth_without_network(env, token_env, expiry):
    cfg, account, *_ = token_env
    account.token_expires_at = env.clock.now() + timedelta(seconds=expiry)
    env.session.commit()
    refresh.scan(env.session, env.clock, cfg)
    env.session.refresh(account)
    assert account.status == "needs_reauth" and not token_env[4]
    assert (
        env.session.scalar(
            select(Notification.severity).where(Notification.type == "account.needs_reauth")
        )
        == "critical"
    )


def test_auth_error_is_terminal_and_notifies(env, token_env):
    token_env[3].append(
        httpx.Response(401, json={"error": {"code": 190, "message": "private-token"}})
    )
    execute(env, token_env)
    env.session.refresh(token_env[1])
    assert token_env[1].status == "needs_reauth"
    op = env.session.scalar(select(Operation))
    assert (op.status, op.last_error_code) == ("failed", "ACCOUNT_NEEDS_REAUTH")
    assert env.session.scalar(
        select(Notification.id).where(Notification.type == "account.needs_reauth")
    )


def test_rate_retry_and_three_attempt_budget(env, token_env):
    token_env[3].extend(
        [
            httpx.Response(429, headers={"Retry-After": "90"}, json={"error": {"code": 4}})
            for _ in range(3)
        ]
    )
    for attempt in range(1, 4):
        result = execute(env, token_env)
        assert result.kind == "retry" and result.retry_after_seconds == 90
        op = env.session.scalar(select(Operation))
        env.session.refresh(op)
        assert op.attempts == attempt and op.status == ("retry_wait" if attempt < 3 else "failed")
    assert execute(env, token_env).kind == "done" and len(token_env[4]) == 3
    env.session.refresh(token_env[1])
    assert token_env[1].consecutive_failures == 0


@pytest.mark.parametrize("failure", [False, True])
@pytest.mark.parametrize("mutation", ["disconnect", "replace"])
def test_stale_result_or_auth_error_cannot_restore_or_damage_new_credentials(
    env, token_env, failure, mutation
):
    _, account, guard, responses, _, hooks = token_env
    if failure:
        responses.append(httpx.Response(401, json={"error": {"code": 190}}))

    def change():
        with guard() as session:
            if mutation == "disconnect":
                accounts.disconnect(session, env.clock, env.ctx(env.owner), account.id)
            else:
                current = session.get(SocialAccount, account.id)
                current.token_ciphertext = b"newer-encrypted-snapshot"
                current.token_refreshed_at = env.clock.now()
                session.commit()

    hooks.append(change)
    execute(env, token_env)
    env.session.refresh(account)
    assert account.status == ("disconnected" if mutation == "disconnect" else "connected")
    assert account.token_ciphertext == (
        None if mutation == "disconnect" else b"newer-encrypted-snapshot"
    )
    assert env.session.scalar(select(Operation.status)) == "failed"
    assert (
        env.session.scalar(
            select(Notification.id).where(Notification.type == "account.needs_reauth")
        )
        is None
    )


def test_foreign_workspace_never_refreshes(env, token_env):
    foreign = create_workspace(env.session)
    env.session.commit()
    assert (
        refresh.execute_refresh(
            token_env[2], env.clock, token_env[0], foreign.id, token_env[1].id
        ).kind
        == "done"
    )
    assert not token_env[4]


def test_periodic_daily_0300_utc_dedup_all_statuses(env, token_env):
    env.clock.advance(hours=14, minutes=59)
    assert jobs.enqueue_token_refreshes(env.session, env.clock) == 0
    env.clock.advance(minutes=1)
    assert jobs.enqueue_token_refreshes(env.session, env.clock) == 1
    for status in ("queued", "running", "succeeded", "dead", "cancelled"):
        row = env.session.scalar(select(Job).where(Job.job_type == "refresh_tokens"))
        row.status = status
        env.session.commit()
        assert jobs.enqueue_token_refreshes(env.session, env.clock) == 0


def test_crash_recovery_lease_and_dead_hook_audit(env, token_env):
    cfg, account, guard, _, _, hooks = token_env

    class Crash(BaseException):
        pass

    hooks.append(lambda: (_ for _ in ()).throw(Crash()))
    job_id = uuid.uuid4()
    with pytest.raises(Crash):
        execute(env, token_env, job_id=job_id)
    assert execute(env, token_env, job_id=job_id).kind == "waiting"
    env.clock.advance(minutes=3)
    # Marking a dead job is auditable and closes the committed operation.
    with guard() as session:
        refresh.abandon(session, env.clock, env.workspace.id, job_id, "INTERNAL_ERROR")
    op = env.session.scalar(select(Operation))
    assert op.status == "failed"
    assert env.session.scalar(select(AuditLog.id).where(AuditLog.action == "operation.failed"))


def test_worker_scan_and_refresh_handlers_registered(env, token_env, shared_session_factory):
    assert get_handler("refresh_token").max_attempts == 3
    refresh.scan(env.session, env.clock, token_env[0])
    result = run_due_jobs(env.clock, session_factory=shared_session_factory)
    assert result
    env.session.refresh(token_env[1])
    assert token_env[1].token_refreshed_at == env.clock.now()


def test_expired_lease_reuses_same_operation_and_completes(env, token_env):
    class Crash(BaseException):
        pass

    token_env[5].append(lambda: (_ for _ in ()).throw(Crash()))
    job_id = uuid.uuid4()
    with pytest.raises(Crash):
        execute(env, token_env, job_id=job_id)
    original = env.session.scalar(select(Operation.id))
    env.session.commit()
    env.clock.advance(minutes=3)
    assert execute(env, token_env, job_id=job_id).kind == "done"
    rows = list(env.session.scalars(select(Operation)))
    assert len(rows) == 1 and rows[0].id == original
    assert rows[0].status == "succeeded" and rows[0].attempts == 2
    assert len(token_env[4]) == 2


def test_recovered_refresh_after_disconnect_closes_stale_ledger_without_call(env, token_env):
    class Crash(BaseException):
        pass

    token_env[5].append(lambda: (_ for _ in ()).throw(Crash()))
    job_id = uuid.uuid4()
    with pytest.raises(Crash):
        execute(env, token_env, job_id=job_id)
    account = token_env[1]
    accounts.disconnect(env.session, env.clock, env.ctx(env.owner), account.id)
    assert execute(env, token_env, job_id=job_id).kind == "done"
    assert env.session.scalar(select(Operation.status)) == "failed"
    assert len(token_env[4]) == 1
