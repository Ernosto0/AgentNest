"""AC-C4: a fact change reaches content (workflows.md section B step 3.4, plan.md G14).

The change is made the way the owner makes it, by command and confirmation, so the whole path
is covered: the confirmation card counts the content, the confirmed update holds scheduled posts,
and the people who approve content are told, the changer included.
"""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.approvals.grants import record_policy_grant
from app.approvals.models import Approval
from app.audit.models import AuditLog
from app.content.models import ContentItem
from app.content.payload import publish_job_key
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from app.knowledge import impact
from app.notifications.models import Notification
from app.operations.models import Operation
from tests.factories import workspace_with_members
from tests.helpers.content import (
    connect_account,
    make_item,
    make_media,
    publish_job,
    request_approval,
)
from tests.integration.commands.conftest import MONTHLY, QUARTER, CommandEnv, cmd, provider
from tests.integration.content.test_schedule import ITEMS

__all__ = ["cmd", "provider"]  # fixtures used below

OLD_PRICE = "Aylık üyelik 6.000 ₺ / ay, bu ay geçerli"
UPDATE = "Aylık üyelik artık 7.000 TL"


def post(
    cmd: CommandEnv,
    status: str,
    *,
    caption: str | None = OLD_PRICE,
    reference: str | None = MONTHLY,
    owner: Any = None,
    **columns: Any,
) -> ContentItem:
    """An item in ``status`` as the services leave it: a reference row to the fact (unless
    ``reference`` is ``None``), the approval and the queued job its status implies."""
    env = cmd.env
    if not env.session.scalars(select(SocialAccount)).first():
        connect_account(env)
    account = env.session.scalars(select(SocialAccount)).one()
    scheduled = status in ("scheduled", "retry_scheduled", "pending_approval", "publishing")
    item = make_item(
        env,
        status=status,
        caption=caption,
        owner=owner,
        media_asset_id=make_media(env).id,
        social_account_id=account.id if scheduled else None,
        scheduled_at=env.clock.now() + timedelta(hours=2) if scheduled else None,
        published_at=env.clock.now() if status == "published" else None,
        **columns,
    )
    if reference is not None:
        fact = cmd.facts[reference]
        impact.replace_references(
            env.session, env.ctx(env.owner), "content_item", item.id, [(fact.id, 1)]
        )
    if status == "pending_approval":
        request_approval(env, item, requester=env.staff)
    elif status in ("scheduled", "retry_scheduled", "publishing"):
        approval = record_policy_grant(
            env.session,
            env.clock,
            env.ctx(env.owner),
            action="content.publish",
            subject_type="content_item",
            subject_id=item.id,
            subject_version=item.version,
            payload={"content_id": str(item.id), "version": item.version},
            summary={"title": item.title},
            required_permission="content.approve",
            expires_at=env.clock.now() + timedelta(hours=2),
            self_approved=True,
        )
        item.approval_id = approval.id
    if status in ("scheduled", "retry_scheduled"):
        publish_job(env, item)
    env.session.commit()
    return item


def operation(cmd: CommandEnv, item: ContentItem, status: str) -> Operation:
    env = cmd.env
    op = Operation(
        workspace_id=env.workspace.id,
        operation_type="publish_content",
        idempotency_key=publish_job_key(item.id, item.version),
        subject_type="content_item",
        subject_id=item.id,
        social_account_id=item.social_account_id,
        provider_kind="mock",
        status=status,
        attempts=1,
        is_simulated=True,
    )
    env.session.add(op)
    env.session.commit()
    return op


def change_price(cmd: CommandEnv) -> dict[str, Any]:
    """The owner's command, confirmed. Returns the confirmation card shown before."""
    command = cmd.run(cmd.env.owner, UPDATE)
    card: dict[str, Any] = command["approval"]
    response = cmd.decide(cmd.env.owner, card)
    assert response.status_code == 200, response.text
    cmd.env.session.expire_all()
    return card


def fresh(cmd: CommandEnv, item: ContentItem) -> ContentItem:
    cmd.env.session.expire_all()
    return cmd.env.session.get(ContentItem, item.id)  # type: ignore[return-value]


def notes(cmd: CommandEnv, kind: str = "content.on_hold") -> list[Notification]:
    cmd.env.session.expire_all()
    return list(cmd.env.session.scalars(select(Notification).where(Notification.type == kind)))


def jobs(cmd: CommandEnv, item: ContentItem) -> list[Job]:
    cmd.env.session.expire_all()
    return list(
        cmd.env.session.scalars(
            select(Job).where(Job.dedup_key == publish_job_key(item.id, item.version))
        )
    )


# --- AC-C4 ------------------------------------------------------------------------------------


def test_ac_c4_a_price_change_by_command_holds_the_scheduled_post(cmd: CommandEnv) -> None:
    item = post(cmd, "scheduled")
    approval_id = item.approval_id
    (job,) = jobs(cmd, item)
    assert job.status == "queued"

    card = change_price(cmd)

    # The confirmation card counted the post before anything changed.
    entry = next(
        e for e in card["summary"]["impact"]["items"] if e["referrer_type"] == "content_item"
    )
    assert entry["counts"] == {"scheduled": 1} and entry["total"] == 1

    held = fresh(cmd, item)
    assert (held.status, held.hold_reason, held.version) == ("on_hold", "FACT_CHANGED", 1)
    # The queued job is gone: nothing can publish version 1.
    (job,) = jobs(cmd, item)
    assert job.status == "cancelled"
    # An approval never leaves ``approved`` (session 4); it authorises nothing because the item
    # left ``scheduled``, and re-approving creates a new approval for version 2.
    approval = cmd.env.session.get(Approval, approval_id)
    assert approval is not None and approval.status == "approved"
    # The post that was held is still the old text (nothing is rewritten).
    assert held.caption == OLD_PRICE

    # content.on_hold reaches everyone who may approve content, the changer (owner) included.
    got = {n.recipient_user_id: n for n in notes(cmd)}
    assert set(got) == {cmd.env.owner.user.id, cmd.env.manager.user.id}
    note = got[cmd.env.owner.user.id]
    assert note.severity == "attention"
    assert (note.subject_type, note.subject_id) == ("content_item", item.id)
    assert note.params["reason"] == "FACT_CHANGED" and "caption" not in note.params
    # The fact notification still skips the changer (Phase 3 D7).
    fact_notes = notes(cmd, "knowledge.fact_changed")
    assert [n.recipient_user_id for n in fact_notes] == [cmd.env.manager.user.id]
    assert fact_notes[0].params["impact"]["by_referrer"]["content_item"] == {"on_hold": 1}


def test_the_author_who_cannot_approve_is_told_too(cmd: CommandEnv) -> None:
    item = post(cmd, "scheduled", owner=cmd.env.staff)
    change_price(cmd)
    recipients = {n.recipient_user_id for n in notes(cmd)}
    assert recipients == {cmd.env.owner.user.id, cmd.env.manager.user.id, cmd.env.staff.user.id}
    assert fresh(cmd, item).status == "on_hold"


def test_a_post_waiting_for_a_retry_is_held_and_its_waiting_operation_cancelled(
    cmd: CommandEnv,
) -> None:
    item = post(cmd, "retry_scheduled")
    op = operation(cmd, item, "retry_wait")

    change_price(cmd)

    assert fresh(cmd, item).status == "on_hold"
    cmd.env.session.refresh(op)
    assert op.status == "cancelled"
    assert [j.status for j in jobs(cmd, item)] == ["cancelled"]
    assert len(notes(cmd)) == 2


def test_an_operation_that_is_running_is_left_to_the_ledger(cmd: CommandEnv) -> None:
    item = post(cmd, "scheduled")
    op = operation(cmd, item, "in_progress")
    change_price(cmd)
    cmd.env.session.refresh(op)
    assert fresh(cmd, item).status == "on_hold" and op.status == "in_progress"


# --- the other statuses -----------------------------------------------------------------------


def test_an_item_waiting_for_approval_goes_back_to_a_draft_and_its_approval_is_cancelled(
    cmd: CommandEnv,
) -> None:
    item = post(cmd, "pending_approval", owner=cmd.env.staff)
    approval = cmd.env.session.get(Approval, item.approval_id)
    assert approval is not None and approval.status == "pending"
    card = change_price(cmd)
    entry = next(
        e for e in card["summary"]["impact"]["items"] if e["referrer_type"] == "content_item"
    )
    assert entry["counts"] == {"pending_approval": 1}

    back = fresh(cmd, item)
    assert (back.status, back.hold_reason, back.version) == ("draft", "FACT_CHANGED", 1)
    cmd.env.session.refresh(approval)
    assert (approval.status, approval.cancel_reason) == ("cancelled", "FACT_CHANGED")
    # Nobody can approve the old text any more.
    late = cmd.env.call(
        cmd.env.owner,
        "POST",
        f"/approvals/{approval.id}/decision",
        json={"decision": "approve", "payload_hash": approval.payload_hash},
    )
    assert late.status_code == 409
    assert notes(cmd) == []  # only a post that was scheduled is announced as held


def test_a_draft_is_marked_stale_and_otherwise_unchanged(cmd: CommandEnv) -> None:
    item = post(cmd, "draft")
    change_price(cmd)
    draft = fresh(cmd, item)
    assert (draft.status, draft.version, draft.caption) == ("draft", 1, OLD_PRICE)
    assert draft.validation["stale"] is True
    assert draft.hold_reason is None
    assert notes(cmd) == []


@pytest.mark.invariant("INV-17")
def test_published_and_publishing_items_are_untouched(cmd: CommandEnv) -> None:
    published = post(cmd, "published", external_media_id="m-1")
    publishing = post(cmd, "publishing")
    op = operation(cmd, publishing, "in_progress")

    card = change_price(cmd)

    assert not [
        e for e in card["summary"]["impact"]["items"] if e["referrer_type"] == "content_item"
    ]
    assert fresh(cmd, published).status == "published"
    assert fresh(cmd, published).validation == {"passed": True, "issues": [], "stale": False}
    # A publish in flight cannot be recalled; the ledger resolves its outcome.
    assert fresh(cmd, publishing).status == "publishing"
    cmd.env.session.refresh(op)
    assert op.status == "in_progress"
    assert notes(cmd) == []


def test_items_that_quote_another_fact_are_not_touched(cmd: CommandEnv) -> None:
    other = post(cmd, "scheduled", caption="3 aylık paket 16.500 ₺ / paket", reference=QUARTER)
    change_price(cmd)
    assert fresh(cmd, other).status == "scheduled"
    assert [j.status for j in jobs(cmd, other)] == ["queued"]


# --- the string sweep -------------------------------------------------------------------------


def test_the_old_display_in_a_caption_counts_even_without_a_reference_row(
    cmd: CommandEnv,
) -> None:
    typed = post(cmd, "scheduled", reference=None)  # the owner typed the price by hand
    unrelated = post(cmd, "scheduled", caption="Cuma günü görüşürüz", reference=None)
    bigger = post(cmd, "scheduled", caption="Premium 16.000 ₺ / ay", reference=None)
    overlay = post(
        cmd,
        "scheduled",
        caption=None,
        reference=None,
        overlay=["Aylık 6.000 ₺ / ay"],
    )
    draft = post(cmd, "draft", reference=None)

    card = change_price(cmd)

    entry = next(
        e for e in card["summary"]["impact"]["items"] if e["referrer_type"] == "content_item"
    )
    assert entry["counts"] == {"scheduled": 2, "draft": 1}  # the confirmation card saw them too
    assert fresh(cmd, typed).status == "on_hold"
    assert fresh(cmd, overlay).status == "on_hold"
    assert fresh(cmd, draft).validation["stale"] is True
    # A different price that merely contains the digits, and a post without a price, stay.
    assert fresh(cmd, bigger).status == "scheduled"
    assert fresh(cmd, unrelated).status == "scheduled"


def test_a_text_that_already_shows_the_new_value_is_not_held(cmd: CommandEnv) -> None:
    current = post(cmd, "scheduled", caption="Aylık üyelik 7.000 ₺ / ay", reference=None)
    change_price(cmd)
    assert fresh(cmd, current).status == "scheduled"


# --- isolation --------------------------------------------------------------------------------


@pytest.mark.invariant("INV-01")
def test_another_workspaces_content_is_never_counted_or_held(cmd: CommandEnv) -> None:
    session = cmd.env.session
    stranger, members = workspace_with_members(
        session, roles=("owner",), name="Başka", slug="baska"
    )
    other = ContentItem(
        workspace_id=stranger.id,
        content_type="feed_image",
        status="scheduled",
        version=1,
        title="Başkası",
        caption=OLD_PRICE,
        overlay_text_suggestions=[],
        validation={"passed": True, "issues": [], "stale": False},
        created_by_user_id=members["owner"].id,
        scheduled_at=cmd.env.clock.now() + timedelta(hours=2),
        created_at=cmd.env.clock.now(),
        updated_at=cmd.env.clock.now(),
    )
    session.add(other)
    session.commit()
    mine = post(cmd, "scheduled")

    card = change_price(cmd)

    entry = next(
        e for e in card["summary"]["impact"]["items"] if e["referrer_type"] == "content_item"
    )
    assert entry["counts"] == {"scheduled": 1}
    assert fresh(cmd, mine).status == "on_hold"
    assert fresh(cmd, other).status == "scheduled" and fresh(cmd, other).hold_reason is None
    assert all(n.workspace_id == cmd.env.workspace.id for n in notes(cmd))


# --- G2 ---------------------------------------------------------------------------------------


@pytest.mark.invariant("INV-02")
def test_re_approving_after_the_hold_fails_while_the_caption_shows_the_old_price(
    cmd: CommandEnv,
) -> None:
    item = post(cmd, "scheduled")
    change_price(cmd)
    held = fresh(cmd, item)
    assert held.status == "on_hold"

    response = cmd.env.call(
        cmd.env.owner,
        "POST",
        f"{ITEMS}/{item.id}/reapprove",
        json={
            "schedule": {"local_date": "2026-01-15", "local_time": "19:00"},
            "expected_version": held.version,
        },
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "CONTENT_VALIDATION_FAILED"
    claim = next(e for e in body["errors"] if e["code"] == "CLAIM_VALIDATION_FAILED")
    (issue,) = claim["params"]["issues"]
    assert issue["text"].startswith("6.000") and issue["matches_verified"] is False
    still = fresh(cmd, item)
    assert (still.status, still.version) == ("on_hold", 1)  # nothing was scheduled
    assert [j.status for j in jobs(cmd, item)] == ["cancelled"]


def test_the_hold_is_audited_with_its_reason(cmd: CommandEnv) -> None:
    item = post(cmd, "scheduled")
    change_price(cmd)
    (entry,) = cmd.env.session.scalars(
        select(AuditLog).where(
            AuditLog.resource_id == item.id, AuditLog.action == "content.on_hold"
        )
    ).all()
    assert entry.metadata_["reason"] == "FACT_CHANGED" and entry.metadata_["from"] == "scheduled"
