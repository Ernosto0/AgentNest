"""AC-G1 (workflows.md G.2): a revoked token is not a failure to retry, it needs the owner.

Sending and publishing both flag the account, tell the managers (critical), keep what can wait
and hold what cannot. Reconnecting clears the simulator's revoked-token rule and the reply that
waited goes out exactly once (INV-05/06)."""

from sqlalchemy import select

from app.integrations.instagram.mock import MockInstagramProvider
from app.integrations.instagram.models import SimFailureRule, SocialAccount
from app.notifications.models import Notification
from tests.helpers.publishing import Publishing
from tests.integration.inbox.conftest import InboxEnv

PRICE_Q = "Aylık üyelik ne kadar?"


def notes(inbox: InboxEnv, kind: str) -> list[Notification]:
    inbox.session.expire_all()
    return list(inbox.session.scalars(select(Notification).where(Notification.type == kind)))


def rules(inbox: InboxEnv) -> list[SimFailureRule]:
    inbox.session.expire_all()
    return list(inbox.session.scalars(select(SimFailureRule)))


def test_send_revoked_token_then_reconnect_sends_the_reply_once(inbox: InboxEnv) -> None:
    inbox.seed_facts()
    draft = inbox.ask(PRICE_Q)
    inbox.fail("send", "auth_revoked", remaining=None)  # every call, until the owner reconnects
    assert inbox.decide(draft).status_code == 200
    inbox.process()

    inbox.session.expire_all()
    account = inbox.session.get(SocialAccount, inbox.account.id)
    assert account is not None and account.status == "needs_reauth"
    assert inbox.refreshed(draft).status == "queued"  # waits; nothing was sent
    assert inbox.sim_sent() == []
    needs_reauth = notes(inbox, "account.needs_reauth")
    assert needs_reauth and {n.severity for n in needs_reauth} == {"critical"}

    response = inbox.env.call(
        inbox.env.owner, "POST", f"/social-accounts/{inbox.account.id}/reconnect"
    )
    assert response.status_code == 200
    assert rules(inbox) == []  # the revoked-token rule ended with the old token

    inbox.process()
    assert inbox.refreshed(draft).status == "sent"
    assert len(inbox.sim_sent()) == 1
    inbox.process()
    assert len(inbox.sim_sent()) == 1  # and never again


def test_publish_revoked_token_holds_the_item_and_a_due_post_is_held_too(pub: Publishing) -> None:
    first, second = pub.scheduled(), pub.scheduled()  # both due now
    pub.fail("create_container", "auth_revoked", remaining=1)
    pub.process()
    first, second = pub.reload(first), pub.reload(second)
    assert (first.status, first.hold_reason) == ("on_hold", "ACCOUNT_UNAVAILABLE")
    assert (second.status, second.hold_reason) == ("on_hold", "ACCOUNT_UNAVAILABLE")
    assert pub.account_now().status == "needs_reauth"
    assert pub.posts() == []
    assert {n.severity for n in pub.notifications("account.needs_reauth")} == {"critical"}


def test_reauthorize_only_removes_revoked_token_rules(inbox: InboxEnv) -> None:
    inbox.fail("send", "auth_revoked", remaining=None)
    inbox.fail("send", "transient", remaining=3)
    removed = MockInstagramProvider.reauthorize(inbox.session, inbox.account)
    inbox.session.commit()
    assert removed == 1
    assert [r.mode for r in rules(inbox)] == ["transient"]
