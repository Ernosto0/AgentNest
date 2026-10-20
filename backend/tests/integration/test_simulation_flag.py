"""AC-X2 / INV-09: everything the mock Instagram produces is flagged as simulated, and the API
says so (the badge is the frontend's job; E2E proves it is shown).

Phase 4 proved it for messages, drafts and operations (``inbox/test_send.py``). This module covers
the Phase 5 records: content items, approvals, operations, notifications, audit entries, and the
simulator's own rows. ``is_simulated`` is derived from ``social_accounts.provider_kind`` and
copied at submit time; a draft has no account yet, so it reads ``false`` until then.

Media assets are not tied to an account (a file is uploaded before anyone picks where it is
posted), so they carry no flag; the item that uses one does.
"""

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select

from app.approvals.models import Approval
from app.audit.models import AuditLog
from app.content.models import ContentItem
from app.integrations.instagram.models import SimContainer, SimPublishedMedia, SocialAccount
from app.notifications.models import Notification
from app.operations.models import Operation
from tests.helpers.env import Env
from tests.helpers.publishing import Publishing
from tests.integration.content.conftest import app as app  # noqa: F401  (fixture)
from tests.integration.content.conftest import env as env  # noqa: F401  (fixture)
from tests.integration.content.conftest import make_pub as make_pub  # noqa: F401  (fixture)
from tests.integration.content.conftest import media_root as media_root  # noqa: F401  (fixture)

MakePub = Callable[..., Publishing]


def get_item(env: Env, item: ContentItem) -> dict[str, Any]:
    response = env.call(env.owner, "GET", f"/content-items/{item.id}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


@pytest.mark.invariant("INV-09")
def test_a_draft_has_no_account_so_it_is_not_simulated_until_it_is_submitted(
    env: Env, make_pub: MakePub
) -> None:
    pub = make_pub()
    item = pub.draft()
    assert get_item(env, item)["is_simulated"] is False  # nothing was posted anywhere

    scheduled = pub.schedule(item)
    assert scheduled.is_simulated is True  # copied from the mock account at submit
    assert get_item(env, scheduled)["is_simulated"] is True


@pytest.mark.invariant("INV-09")
def test_ac_x2_a_mock_publish_flags_every_record_it_produces(env: Env, make_pub: MakePub) -> None:
    pub = make_pub()
    item = pub.scheduled()
    assert pub.execute(item).kind == "published"
    published = pub.reload(item)
    assert published.status == "published"

    # the content item and its approval
    assert published.is_simulated is True
    approval = env.session.get(Approval, published.approval_id)
    assert approval is not None and approval.is_simulated is True
    # the ledger row
    (operation,) = env.session.scalars(select(Operation)).all()
    assert operation.operation_type == "publish_content" and operation.is_simulated is True
    # the notifications the publish created
    notes = list(
        env.session.scalars(select(Notification).where(Notification.type.like("content.%")))
    )
    assert notes and all(n.is_simulated for n in notes)
    # the audit trail: every content and operation entry of the flow
    entries = list(
        env.session.scalars(
            select(AuditLog).where(
                AuditLog.action.like("content.%") | AuditLog.action.like("operation.%")
            )
        )
    )
    assert {e.action for e in entries} >= {"content.scheduled", "content.published"}
    assert all(e.is_simulated for e in entries), [e.action for e in entries if not e.is_simulated]

    # the simulator's rows exist only under a mock account
    containers = list(env.session.scalars(select(SimContainer)))
    posts = list(env.session.scalars(select(SimPublishedMedia)))
    assert len(containers) == len(posts) == 1
    account = env.session.get(SocialAccount, posts[0].social_account_id)
    assert account is not None and account.provider_kind == "mock" and account.is_simulated


@pytest.mark.invariant("INV-09")
def test_ac_x2_the_api_exposes_the_flag_on_every_content_response(
    env: Env, make_pub: MakePub
) -> None:
    pub = make_pub()
    item = pub.scheduled()
    pub.execute(item)
    env.session.expire_all()  # the executor wrote through its own sessions

    detail = get_item(env, item)
    assert detail["status"] == "published" and detail["is_simulated"] is True
    assert detail["approval"] is not None

    listing = env.call(env.owner, "GET", "/content-items").json()["items"]
    assert [i["is_simulated"] for i in listing] == [True]

    approvals = env.call(env.owner, "GET", "/approvals").json()["items"]
    assert approvals and all(a["is_simulated"] is True for a in approvals)

    notes = env.call(env.owner, "GET", "/notifications").json()["items"]
    content_notes = [n for n in notes if n["type"].startswith("content.")]
    assert content_notes and all(n["is_simulated"] is True for n in content_notes)

    accounts = env.call(env.owner, "GET", "/social-accounts").json()["items"]
    assert accounts and all(a["is_simulated"] is True for a in accounts)

    dev = env.owner.client.get(
        f"/api/v1/dev/workspaces/{env.workspace.id}/simulator/published",
        headers=env.owner.headers,
    )
    assert dev.status_code == 200
    assert dev.json()["items"] and all(p["is_simulated"] is True for p in dev.json()["items"])


@pytest.mark.invariant("INV-09")
def test_an_item_for_a_real_provider_account_is_not_flagged(env: Env, make_pub: MakePub) -> None:
    """The flag is derived, not hard-wired: a non-mock account yields ``false`` everywhere."""
    pub = make_pub()
    pub.account.provider_kind = "meta"
    env.session.commit()

    item = pub.scheduled()
    assert item.is_simulated is False
    approval = env.session.get(Approval, item.approval_id)
    assert approval is not None and approval.is_simulated is False
    assert get_item(env, item)["is_simulated"] is False
