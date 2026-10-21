"""AC-G3 (workflows.md G.2, plan H10-H12): the circuit breaker, the health check and recovery."""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from app.inbox.models import ReplyDraft
from app.inbox.system import system_context
from app.integrations.instagram.mock import MockInstagramProvider
from app.integrations.instagram.models import SocialAccount
from app.jobs.scheduler import scheduler_tick
from app.notifications.models import Notification
from app.operations import health, health_check
from tests.helpers.publishing import Publishing
from tests.integration.inbox.conftest import InboxEnv

PRICE_Q = "Aylık üyelik ne kadar?"
CUSTOMERS = [f"cust-{n}" for n in range(1, 6)]


def account_of(inbox: InboxEnv) -> SocialAccount:
    inbox.session.expire_all()
    row = inbox.session.get(SocialAccount, inbox.account.id)
    assert row is not None
    return row


def count(inbox: InboxEnv, model: Any, **where: object) -> int:
    inbox.session.expire_all()
    return len(list(inbox.session.scalars(select(model).filter_by(**where))))


def fail_now(inbox: InboxEnv, n: int = 1) -> None:
    ctx = system_context(inbox.session, inbox.env.workspace.id, "test")
    assert ctx is not None
    account = account_of(inbox)
    for _ in range(n):
        health.record_transient_failure(
            inbox.session, inbox.clock, ctx, account, "PROVIDER_UNAVAILABLE"
        )
    inbox.session.commit()


# --- the window (H10) --------------------------------------------------------------------------


def test_five_failures_within_ten_minutes_open_the_circuit(inbox: InboxEnv) -> None:
    for _ in range(4):
        fail_now(inbox)
        inbox.clock.advance(minutes=2)
        assert account_of(inbox).status == "connected"
    fail_now(inbox)  # the fifth, 8 minutes after the first
    account = account_of(inbox)
    assert account.status == "degraded"
    assert account.degraded_until == inbox.clock.now() + timedelta(minutes=10)
    assert count(inbox, AuditLog, action="social_account.degraded") == 1
    degraded = list(
        inbox.session.scalars(select(Notification).where(Notification.type == "account.degraded"))
    )
    assert degraded and {n.severity for n in degraded} == {"attention"}


def test_five_failures_spread_over_eleven_minutes_do_not(inbox: InboxEnv) -> None:
    for _ in range(4):
        fail_now(inbox)
        inbox.clock.advance(minutes=2, seconds=45)
    fail_now(inbox)  # 11 minutes after the first: a new window
    account = account_of(inbox)
    assert (account.status, account.consecutive_failures) == ("connected", 1)
    assert count(inbox, AuditLog, action="social_account.degraded") == 0


def test_a_success_resets_the_counter(inbox: InboxEnv) -> None:
    fail_now(inbox, 4)
    ctx = system_context(inbox.session, inbox.env.workspace.id, "test")
    assert ctx is not None
    health.record_success(inbox.session, inbox.clock, ctx, account_of(inbox))
    inbox.session.commit()
    fail_now(inbox)
    assert account_of(inbox).consecutive_failures == 1


# --- the open circuit: replies (H11, H12) ------------------------------------------------------


def degrade_with_five_failed_sends(inbox: InboxEnv) -> list[ReplyDraft]:
    inbox.seed_facts()
    drafts = [inbox.ask(PRICE_Q, customer=customer) for customer in CUSTOMERS]
    inbox.fail("send", "transient", remaining=5)
    for draft in drafts:
        assert inbox.decide(draft).status_code == 200
    inbox.process()  # five sends, five transient failures within seconds
    assert account_of(inbox).status == "degraded"
    assert inbox.sim_sent() == []
    return drafts


def test_degraded_account_gets_no_provider_calls_and_recovery_resumes_the_replies(
    inbox: InboxEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    drafts = degrade_with_five_failed_sends(inbox)
    sends: list[str] = []
    real = MockInstagramProvider.send_text_message

    def counting(self: MockInstagramProvider, account: Any, recipient_id: str, text: str) -> Any:
        sends.append(recipient_id)
        return real(self, account, recipient_id, text)

    monkeypatch.setattr(MockInstagramProvider, "send_text_message", counting)

    # The backoff (60 s) ends inside the cooldown: the jobs come back, call nothing, and wait.
    inbox.clock.advance(minutes=2)
    inbox.process()
    inbox.clock.advance(minutes=5)
    inbox.process()
    assert sends == []
    row = account_of(inbox)
    assert row.status == "degraded"
    assert [inbox.refreshed(d).status for d in drafts] == ["queued"] * 5
    operation = inbox.operation(drafts[0])
    assert operation is not None and operation.attempts == 1  # no attempt was spent waiting

    # A health check that fails starts the cooldown again.
    inbox.fail("profile", "transient", remaining=1)
    before = row.degraded_until
    assert before is not None
    inbox.clock.advance(minutes=1)
    result = health_check.run_health_check(
        inbox.factory, inbox.clock, inbox.settings, inbox.env.workspace.id, inbox.account.id
    )
    assert result == "still_degraded"
    row = account_of(inbox)
    assert row.status == "degraded"
    assert row.degraded_until == inbox.clock.now() + timedelta(minutes=10)
    assert row.degraded_until > before

    # The next one works: connected again, and the queued replies go out once each.
    result = health_check.run_health_check(
        inbox.factory, inbox.clock, inbox.settings, inbox.env.workspace.id, inbox.account.id
    )
    assert result == "recovered"
    row = account_of(inbox)
    assert (row.status, row.consecutive_failures, row.degraded_until) == ("connected", 0, None)
    assert count(inbox, Notification, type="account.recovered") >= 1
    connected = [
        a
        for a in inbox.session.scalars(select(AuditLog).order_by(AuditLog.created_at))
        if a.action == "social_account.connected"
    ]
    assert connected and connected[-1].metadata_["recovered"] is True

    inbox.process()
    assert [inbox.refreshed(d).status for d in drafts] == ["sent"] * 5
    assert len(sends) == 5 and len(inbox.sim_sent()) == 5
    inbox.process()
    assert len(inbox.sim_sent()) == 5


def test_the_health_check_job_is_enqueued_for_degraded_accounts_only(inbox: InboxEnv) -> None:
    scheduler_tick(inbox.factory, inbox.clock)
    assert inbox.jobs("account_health_check") == []
    fail_now(inbox, 5)
    assert account_of(inbox).status == "degraded"
    scheduler_tick(inbox.factory, inbox.clock)
    scheduler_tick(inbox.factory, inbox.clock)  # the same bucket: still one job
    assert len(inbox.jobs("account_health_check")) == 1
    inbox.process()
    assert account_of(inbox).status == "connected"  # the job probed and the mock answered


def test_the_dev_route_runs_the_health_check_now(inbox: InboxEnv) -> None:
    fail_now(inbox, 5)
    owner = inbox.env.owner
    response = owner.client.post(
        f"/api/v1/dev/workspaces/{inbox.env.workspace.id}/health-check", headers=owner.headers
    )
    assert response.status_code == 200
    assert response.json() == {"checked": 1, "recovered": 1}
    assert account_of(inbox).status == "connected"
    foreign = owner.client.post(
        "/api/v1/dev/workspaces/00000000-0000-0000-0000-000000000001/health-check",
        headers=owner.headers,
    )
    assert foreign.status_code == 404


# --- the open circuit: publishing (H11) --------------------------------------------------------


def test_a_publish_is_rescheduled_not_held_while_degraded_and_goes_out_after_recovery(
    pub: Publishing,
) -> None:
    items = [pub.scheduled() for _ in range(6)]
    pub.fail("create_container", "transient", remaining=5)
    for failing in items[:5]:
        assert pub.execute(failing).kind == "retry"  # five transient failures within seconds
    account = pub.account_now()
    assert account.status == "degraded" and account.degraded_until is not None

    item = items[5]
    pub.calls.clear()
    outcome = pub.execute(item)
    assert outcome.kind == "rescheduled" and outcome.error_code == "ACCOUNT_DEGRADED"
    assert outcome.run_at == account.degraded_until
    assert pub.calls == []  # zero provider calls, not even the quota read
    assert pub.reload(item).status == "retry_scheduled"  # not on_hold
    op = pub.operation(item)
    assert op is not None and op.attempts == 0

    result = health_check.run_health_check(
        pub.factory,  # type: ignore[arg-type]
        pub.clock,
        pub.settings,
        pub.workspace.id,
        pub.account.id,
        provider=pub.provider,
    )
    assert result == "recovered"
    pub.advance_past(outcome.run_at)
    pub.process()
    assert pub.reload(item).status == "published"
    assert len(pub.posts()) == 6  # the five that failed once were retried, and this one
