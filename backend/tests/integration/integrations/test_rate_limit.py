"""AC-G2 (workflows.md G.1): a rate limit waits for Retry-After and is not a health failure."""

from datetime import timedelta

from app.integrations.instagram.models import SocialAccount
from app.operations.send import SEND_MAX_ATTEMPTS
from tests.integration.inbox.conftest import InboxEnv

PRICE_Q = "Aylık üyelik ne kadar?"


def account(inbox: InboxEnv) -> SocialAccount:
    inbox.session.expire_all()
    row = inbox.session.get(SocialAccount, inbox.account.id)
    assert row is not None
    return row


def test_the_retry_waits_for_retry_after_and_the_account_stays_healthy(inbox: InboxEnv) -> None:
    inbox.seed_facts()
    draft = inbox.ask(PRICE_Q)
    inbox.fail("send", "rate_limited", remaining=1, retry_after=120)
    assert inbox.decide(draft).status_code == 200
    started = inbox.clock.now()
    inbox.process()
    assert inbox.sim_sent() == []

    (job,) = [j for j in inbox.jobs("send_reply") if j.dedup_key == f"send_reply:{draft.id}"]
    assert job.run_at >= started + timedelta(seconds=120)  # not the 60 s backoff

    inbox.clock.advance(seconds=119)
    assert inbox.process() == 0 and inbox.sim_sent() == []  # still waiting
    inbox.clock.advance(seconds=2)
    inbox.process()
    assert inbox.refreshed(draft).status == "sent" and len(inbox.sim_sent()) == 1
    row = account(inbox)
    assert (row.status, row.consecutive_failures) == ("connected", 0)


def test_a_rate_limit_that_never_ends_stops_at_the_attempt_budget(inbox: InboxEnv) -> None:
    inbox.seed_facts()
    draft = inbox.ask(PRICE_Q)
    inbox.fail("send", "rate_limited", remaining=None, retry_after=60)
    assert inbox.decide(draft).status_code == 200
    for _ in range(SEND_MAX_ATTEMPTS + 3):
        inbox.process()
        inbox.clock.advance(minutes=31)
    operation = inbox.operation(draft)
    assert operation is not None
    assert operation.attempts == SEND_MAX_ATTEMPTS and operation.status == "failed"
    assert inbox.sim_sent() == []
    row = account(inbox)
    assert (row.status, row.consecutive_failures) == ("connected", 0)  # never counted
