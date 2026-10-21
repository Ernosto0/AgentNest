"""AC-X2 / INV-09: everything the mock Instagram produces is flagged as simulated, and the API
says so (the badge is the frontend's job; E2E proves it is shown).

Phase 4 proved it for messages, drafts and operations (``inbox/test_send.py``). This module covers
the Phase 5 records: content items, approvals, operations, notifications, audit entries, and the
simulator's own rows. ``is_simulated`` is derived from ``social_accounts.provider_kind`` and
copied at submit time; a draft has no account yet, so it reads ``false`` until then.

Media assets are not tied to an account (a file is uploaded before anyone picks where it is
posted), so they carry no flag; the item that uses one does.
"""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select

from app.approvals.models import Approval
from app.audit import service as audit
from app.audit.models import AuditLog
from app.content.models import ContentItem
from app.integrations.instagram.models import SimContainer, SimPublishedMedia, SocialAccount
from app.notifications.models import Notification
from app.operations import health
from app.operations.models import Operation
from app.reporting import service as reporting
from app.reporting.models import DailyReport
from app.reporting.periods import local_date_of
from tests.helpers.env import Env
from tests.helpers.publishing import Publishing
from tests.helpers.reporting import Builder
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


# --- Phase 6 additions (session 9): reports, notifications, activity, the account circuit ------


def _generate_todays_report(env: Env, *, scheduled: bool = True) -> str:
    """Generate (and store) today's report as the scheduled run does; returns its local date.
    The clock moves on a minute first: the period is half-open, so a record stamped at the very
    instant of generation would belong to the next report."""
    env.clock.advance(minutes=1)
    local_date = local_date_of(env.clock.now(), env.workspace.timezone)
    reporting.generate_daily_report(
        env.session, env.clock, env.ctx(env.owner), local_date, scheduled=scheduled
    )
    env.session.commit()
    return local_date.isoformat()


@pytest.mark.invariant("INV-09")
def test_ac_x2_a_report_over_simulated_records_is_flagged_everywhere(
    env: Env, make_pub: MakePub
) -> None:
    pub = make_pub()
    item = pub.scheduled()
    assert pub.execute(item).kind == "published"
    env.session.expire_all()
    day = _generate_todays_report(env)

    # the stored row
    (row,) = env.session.scalars(select(DailyReport)).all()
    assert row.has_simulated_data is True
    # the notification that announces it, and the audit entry that records it
    (ready,) = env.session.scalars(
        select(Notification).where(
            Notification.type == "report.daily_ready",
            Notification.recipient_user_id == env.owner.user.id,
        )
    )
    assert ready.is_simulated is True
    (generated,) = env.session.scalars(
        select(AuditLog).where(AuditLog.action == "report.generated")
    )
    assert generated.is_simulated is True
    # the API: the report, its drill-down items and the notification list
    body = env.call(env.owner, "GET", f"/reports/daily?date={day}").json()
    assert body["has_simulated_data"] is True
    drill = env.call(env.owner, "GET", f"/reports/daily/{day}/metrics/content_published").json()
    assert drill["items"] and all(i["is_simulated"] is True for i in drill["items"])
    notes = env.call(env.owner, "GET", "/notifications").json()["items"]
    assert [n["is_simulated"] for n in notes if n["type"] == "report.daily_ready"] == [True]


@pytest.mark.invariant("INV-09")
def test_ac_x2_a_report_over_real_records_is_not_flagged(env: Env) -> None:
    """The flag is derived from the records behind the numbers, not hard-wired."""
    builder = Builder(env.session, env.workspace, env.owner.user, simulated=False)
    conversation = builder.conversation(env.clock.now())
    builder.message(conversation, "inbound", env.clock.now())
    env.session.commit()
    day = _generate_todays_report(env)

    (row,) = env.session.scalars(select(DailyReport)).all()
    assert row.has_simulated_data is False
    (ready,) = env.session.scalars(
        select(Notification).where(
            Notification.type == "report.daily_ready",
            Notification.recipient_user_id == env.owner.user.id,
        )
    )
    assert ready.is_simulated is False
    body = env.call(env.owner, "GET", f"/reports/daily?date={day}").json()
    assert body["has_simulated_data"] is False
    values = {m["key"]: m["value"] for m in body["metrics"]}
    assert values["inbound_messages"] == 1  # the real record is counted, and not flagged


@pytest.mark.invariant("INV-09")
def test_ac_x2_the_activity_feed_flags_what_the_mock_produced(env: Env, make_pub: MakePub) -> None:
    pub = make_pub()
    item = pub.scheduled()
    pub.execute(item)
    env.session.expire_all()
    _generate_todays_report(env)

    entries = env.call(env.owner, "GET", "/activity?limit=100").json()["items"]
    by_action = {e["action"]: e for e in entries}
    assert {"content.scheduled", "content.published", "report.generated"} <= set(by_action)
    for action in ("content.scheduled", "content.published", "report.generated"):
        assert by_action[action]["is_simulated"] is True, action
    # an entry about something real is not flagged: a member change has no provider behind it
    audit.record(
        env.session, env.ctx(env.owner), "member.removed", "user", uuid.uuid4(), {}, clock=env.clock
    )
    env.session.commit()
    removed = [
        e
        for e in env.call(env.owner, "GET", "/activity?limit=100").json()["items"]
        if e["action"] == "member.removed"
    ]
    assert [e["is_simulated"] for e in removed] == [False]


@pytest.mark.invariant("INV-09")
def test_ac_x2_the_account_notifications_and_audit_follow_the_provider_kind(
    env: Env, make_pub: MakePub
) -> None:
    pub = make_pub()
    account = pub.account
    ctx = env.ctx(env.owner)
    health.handle_auth_error(env.session, env.clock, ctx, account)
    health.handle_permission_error(env.session, env.clock, ctx, account, "messaging")
    health.recover(env.session, env.clock, ctx, account)
    env.session.commit()

    types = {"account.needs_reauth", "account.permission_missing", "account.recovered"}
    notes = list(env.session.scalars(select(Notification).where(Notification.type.in_(types))))
    assert {n.type for n in notes} == types and all(n.is_simulated for n in notes)
    entries = list(
        env.session.scalars(select(AuditLog).where(AuditLog.action.like("social_account.%")))
    )
    assert entries and all(e.is_simulated for e in entries)

    # the same events on a real account are not flagged (one active account per workspace: the
    # simulated one becomes a Meta account, and the earlier notifications are read)
    for note in notes:
        note.read_at = env.clock.now()
    account.provider_kind = "meta"
    env.session.flush()
    assert account.is_simulated is False
    health.handle_auth_error(env.session, env.clock, ctx, account)
    env.session.commit()
    fresh = list(
        env.session.scalars(
            select(Notification).where(
                Notification.type == "account.needs_reauth", Notification.read_at.is_(None)
            )
        )
    )
    assert fresh and all(n.is_simulated is False for n in fresh)
