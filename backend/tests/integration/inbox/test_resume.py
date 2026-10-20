"""P5-00 Q6: reconnecting an account resumes the replies that waited for it (workflows.md §G.2).

A send that hit a revoked token leaves the draft ``queued`` and the account ``needs_reauth``.
Reconnecting must send that reply exactly once (INV-05/06), through the ordinary send job and
its ledger, and must not touch anything that can no longer be sent."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from app.inbox.models import ReplyDraft
from app.jobs.models import Job
from app.operations.models import Operation
from tests.integration.inbox.conftest import InboxEnv

PRICE_Q = "Aylık üyelik ne kadar?"


@pytest.fixture
def gym(inbox: InboxEnv):  # type: ignore[no-untyped-def]
    return inbox.seed_facts()


def reconnect(inbox: InboxEnv, role: str = "owner"):  # type: ignore[no-untyped-def]
    return inbox.env.call(
        getattr(inbox.env, role), "POST", f"/social-accounts/{inbox.account.id}/reconnect"
    )


def send_jobs(inbox: InboxEnv, draft: ReplyDraft) -> list[Job]:
    return [j for j in inbox.jobs("send_reply") if j.dedup_key == f"send_reply:{draft.id}"]


def waiting_for_reauth(inbox: InboxEnv) -> ReplyDraft:
    """An approved reply whose send found the token revoked: queued, account needs_reauth."""
    draft = inbox.ask(PRICE_Q)
    inbox.fail("send", "auth_revoked")
    assert inbox.decide(draft).status_code == 200
    inbox.process()  # the send job runs, hits the revoked token and waits
    inbox.session.expire_all()
    assert inbox.account.status == "needs_reauth"
    assert inbox.refreshed(draft).status == "queued"
    assert inbox.sim_sent() == []
    return draft


def test_reconnecting_sends_the_queued_reply_exactly_once(inbox: InboxEnv, gym) -> None:
    draft = waiting_for_reauth(inbox)
    (waiting,) = send_jobs(inbox, draft)
    assert waiting.status == "queued" and waiting.run_at > inbox.clock.now()  # sleeping in backoff

    response = reconnect(inbox)
    assert response.status_code == 200
    assert response.json()["status"] == "connected"
    assert response.json()["is_simulated"] is True

    inbox.process()  # resume_account makes the send due; the send job runs
    assert inbox.refreshed(draft).status == "sent"
    (sent,) = inbox.sim_sent()
    assert sent.text == "Merhaba! Aylık üyelik ücretimiz 6.000 ₺ / ay."
    operations = list(
        inbox.session.scalars(select(Operation).where(Operation.subject_id == draft.id))
    )
    assert [(o.status, o.attempts) for o in operations] == [("succeeded", 2)]  # one ledger row
    (job,) = send_jobs(inbox, draft)  # the same job row was expedited, not duplicated
    assert (job.id, job.status) == (waiting.id, "succeeded")
    assert inbox.process() == 0  # nothing left to do, nothing sent twice
    assert len(inbox.sim_sent()) == 1


def test_a_send_job_that_ran_out_of_attempts_is_replaced(inbox: InboxEnv, gym) -> None:
    draft = waiting_for_reauth(inbox)
    for _ in range(8):  # the job keeps waiting (5 minutes each) until its attempts are used up
        inbox.clock.advance(timedelta(minutes=6))
        inbox.process()
    (dead,) = send_jobs(inbox, draft)
    assert dead.status == "dead"
    assert inbox.refreshed(draft).status == "queued"  # waits for the window or a reconnection

    assert reconnect(inbox).status_code == 200
    inbox.process()
    assert inbox.refreshed(draft).status == "sent"
    assert len(inbox.sim_sent()) == 1
    jobs = send_jobs(inbox, draft)
    assert sorted(j.status for j in jobs) == ["dead", "succeeded"]


def test_reconnecting_is_audited_and_keeps_the_same_external_account(inbox: InboxEnv, gym) -> None:
    waiting_for_reauth(inbox)
    external_id = inbox.account.external_account_id
    assert reconnect(inbox).status_code == 200
    inbox.session.expire_all()
    assert inbox.account.external_account_id == external_id
    assert inbox.account.status == "connected" and inbox.account.last_error_code is None
    entry = inbox.session.scalars(
        select(AuditLog).where(AuditLog.action == "account.reconnected")
    ).one()
    assert entry.resource_id == inbox.account.id and entry.is_simulated is True
    assert entry.metadata_["from"] == "needs_reauth"


def test_a_reply_whose_window_has_closed_is_not_resumed(inbox: InboxEnv, gym) -> None:
    draft = waiting_for_reauth(inbox)
    inbox.clock.advance(timedelta(hours=24, minutes=1))
    assert reconnect(inbox).status_code == 200
    inbox.process()
    assert inbox.sim_sent() == []  # never sent after the window closed
    assert inbox.refreshed(draft).status == "expired"  # the send job's own window check


def test_a_reply_that_is_not_queued_is_left_alone(inbox: InboxEnv, gym) -> None:
    sent = inbox.ask(PRICE_Q)
    inbox.approve_and_send(sent)
    inbox.clock.advance(timedelta(minutes=1))
    pending = inbox.ask("ve çalışma saatleri?", mid="m-2")  # waits for approval, not queued
    assert pending.id != sent.id and pending.status == "pending_approval"
    inbox.account.status = "needs_reauth"
    inbox.session.commit()
    assert reconnect(inbox).status_code == 200
    inbox.process()
    assert inbox.refreshed(pending).status == "pending_approval"  # only a person approves it
    assert send_jobs(inbox, pending) == []
    assert len(inbox.sim_sent()) == 1  # the earlier reply, once


def test_reconnecting_needs_the_integrations_permission(inbox: InboxEnv, gym) -> None:
    waiting_for_reauth(inbox)
    for role in ("manager", "staff"):
        assert reconnect(inbox, role).status_code == 403
    inbox.session.expire_all()
    assert inbox.account.status == "needs_reauth"
    assert inbox.jobs("resume_account") == []
    assert reconnect(inbox, "owner").status_code == 200


def test_reconnecting_a_connected_account_is_a_conflict(inbox: InboxEnv, gym) -> None:
    response = reconnect(inbox)
    assert response.status_code == 409 and response.json()["code"] == "CONFLICT_STATE"
    assert inbox.jobs("resume_account") == []
    waiting_for_reauth(inbox)
    assert reconnect(inbox).status_code == 200
    assert reconnect(inbox).status_code == 409  # already connected: single use
    assert len(inbox.jobs("resume_account")) == 1
