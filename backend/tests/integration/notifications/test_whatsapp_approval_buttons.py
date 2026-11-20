# ruff: noqa: F811
"""F-06, Feature Phase 5 Session 03: approve and reject buttons on WhatsApp.

Out: inside the 24-hour window an approval request is an interactive message whose two button ids
are single-use action tokens (Phase 9 machinery: hashed at rest, expiring, bound to the member);
outside the window it is the plain template without buttons. In: a button tap from a linked member
decides through the same approval service as the web and Telegram; replay, expiry, staleness, a
forwarded button, an unlinked or revoked sender, a duplicate webhook and an approval already
decided on the web are all refused or answered with the current state, never decided twice; free
text never decides. The Cloud API is an ``httpx.MockTransport`` (no network).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.approvals import callbacks
from app.approvals import service as approvals_service
from app.approvals.action_tokens import ActionTokenService, hash_action_token
from app.approvals.models import ActionToken, Approval
from app.audit.models import AuditLog
from app.core.config import Settings
from app.identity.models import ChannelLink, WorkspaceMember
from app.inbox.models import Conversation, Message, ReplyDraft
from app.integrations.channels.whatsapp.approval_buttons import (
    BODY_LIMIT,
    BUTTON_PREFIX,
    ELLIPSIS,
    REPLIES,
)
from app.integrations.channels.whatsapp.dispatcher import REPLIES as LINK_REPLIES
from app.integrations.channels.whatsapp.dispatcher import process_webhook
from app.integrations.channels.whatsapp.models import WhatsAppWebhookEvent
from app.integrations.instagram.models import SocialAccount
from app.jobs.models import Job
from tests.factories import knowledge_ctx, workspace_with_members
from tests.helpers.content import make_item
from tests.helpers.env import Env
from tests.integration.approvals.conftest import FakeSubject
from tests.integration.notifications.test_whatsapp_channel import (  # noqa: F401
    WA_ID,
    Cloud,
    cloud,
    deliveries,
    factory,
    link_owner,
    make_client,
    wa_settings,
    wired,
    work,
)
from tests.unit.integrations.channels.test_whatsapp_webhook_format import envelope

OTHER_WA_ID = "905550000002"
PAYLOAD = {"fact_id": str(uuid.UUID(int=7)), "from_version": 1, "new_value": {"amount": "7000.00"}}
SUMMARY = {"label": "Aylık üyelik", "old_formatted": "6.000 TL", "new_formatted": "7.000 TL"}
TR = REPLIES["tr"]


@pytest.fixture
def subject() -> Iterator[FakeSubject]:
    fake = FakeSubject()
    with callbacks.callbacks_snapshot(clear=True):
        callbacks.register(
            "owner_command",
            fake.on_decided,  # type: ignore[arg-type]
            current_version=lambda _s, _c, _i: fake.version,
            status_of=lambda _s, _c, _i: fake.status,
        )
        yield fake


def request_approval(env: Env, *, expires_in: timedelta = timedelta(hours=2)) -> Approval:
    """A pending authorization requested by staff; the owner holds the permission."""
    approval = approvals_service.request(
        env.session,
        env.clock,
        env.ctx(env.staff),
        kind="authorization",
        action="command.update_fact",
        subject_type="owner_command",
        subject_id=uuid.uuid4(),
        subject_version=1,
        payload=PAYLOAD,
        summary=SUMMARY,
        required_permission="knowledge.verify",
        expires_at=env.clock.now() + expires_in,
    )
    env.session.commit()
    return approval


def send_buttons(
    env: Env, cloud: Cloud, factory: sessionmaker[Session], **kwargs: Any
) -> tuple[Approval, dict[str, str]]:
    """Link the owner, request an approval, run the delivery job; return the approval and the
    ``{"approve": raw token, "reject": raw token}`` read from the message the owner received."""
    link_owner(env, **kwargs)
    approval = request_approval(env)
    assert work(env, factory) == 1
    (request,) = cloud.requests
    assert request["type"] == "interactive"
    ids = [b["reply"]["id"] for b in request["interactive"]["action"]["buttons"]]
    assert all(i.startswith(BUTTON_PREFIX) for i in ids)
    cut = len(BUTTON_PREFIX)
    return approval, {"approve": ids[0][cut:], "reject": ids[1][cut:]}


_seq = iter(range(1000, 100000))


def tap(
    env: Env,
    cloud: Cloud,
    settings: Settings,
    button_id: str,
    *,
    wa_id: str = WA_ID,
    wamid: str | None = None,
) -> Any:
    """One button reply, processed like the webhook does (the reply is sent after the commit)."""
    payload = envelope(
        [
            {
                "id": wamid or f"wamid.TAP{next(_seq)}",
                "from": wa_id,
                "timestamp": str(int(env.clock.now().timestamp())),
                "type": "interactive",
                "interactive": {"button_reply": {"id": button_id, "title": "x"}},
            }
        ]
    )
    return process_webhook(env.session, env.clock, payload, make_client(cloud), settings)


def act(token: str) -> str:
    return BUTTON_PREFIX + token


def fresh(env: Env, approval: Approval) -> Approval:
    env.session.expire_all()
    got = env.session.get(Approval, approval.id)
    assert got is not None
    return got


def last_reply(cloud: Cloud) -> str:
    assert cloud.requests[-1]["type"] == "text"
    return str(cloud.requests[-1]["text"]["body"])


def tokens(env: Env, approval: Approval) -> list[ActionToken]:
    env.session.expire_all()
    return list(
        env.session.scalars(select(ActionToken).where(ActionToken.approval_id == approval.id))
    )


# --- the message that carries the buttons ------------------------------------------------------


def test_inside_the_window_the_owner_gets_approve_and_reject_buttons(
    env: Env, cloud: Cloud, factory: sessionmaker[Session], subject: FakeSubject
) -> None:
    approval, raw = send_buttons(env, cloud, factory)
    message = cloud.requests[0]
    interactive = message["interactive"]
    assert interactive["type"] == "button" and message["to"] == WA_ID
    titles = [b["reply"]["title"] for b in interactive["action"]["buttons"]]
    assert titles == ["Onayla", "Reddet"] and all(len(t) <= 20 for t in titles)
    body = interactive["body"]["text"]
    assert "onay" in body.lower() and len(body) <= 1024
    # a fact change shows its own summary fields (what is being approved), nothing else
    assert "Aylık üyelik" in body and "6.000 TL" in body and "7.000 TL" in body
    assert "fact_id" not in body and str(uuid.UUID(int=7)) not in body
    # the ids carry only the opaque token: no approval id, workspace id or decision
    wire = json.dumps(message)
    assert str(approval.id) not in wire and str(env.workspace.id) not in wire
    assert all(len(token) <= 32 for token in raw.values())
    # tokens are stored hashed, bound to the owner, the approval, the decision and its hash
    rows = {t.decision: t for t in tokens(env, approval)}
    assert set(rows) == {"approved", "rejected"}
    for decision, key in (("approved", "approve"), ("rejected", "reject")):
        row = rows[decision]
        assert row.token_hash == hash_action_token(raw[key])
        assert row.token_hash == hashlib.sha256(raw[key].encode()).hexdigest()
        assert raw[key] not in (row.token_hash,)
        assert row.user_id == env.owner.user.id and row.approval_id == approval.id
        assert row.payload_hash == approval.payload_hash and row.used_at is None
        assert row.expires_at == approval.expires_at
    assert raw["approve"] != raw["reject"]
    (delivery,) = deliveries(env)
    meta = delivery.delivery_metadata
    assert meta["approval_buttons"] == "sent" and meta["approval_id"] == str(approval.id)
    assert meta["cost"]["send_mode"] == "session" and meta["cost"]["category"] == "service"
    # a token is a secret: never in the ledger row or the job payload
    env.session.expire_all()
    stored = json.dumps(meta) + json.dumps([j.payload for j in env.session.scalars(select(Job))])
    assert all(t not in stored for t in raw.values())


def test_english_owner_gets_english_buttons(
    env: Env, cloud: Cloud, factory: sessionmaker[Session], subject: FakeSubject
) -> None:
    env.owner.user.ui_locale = "en"
    env.session.commit()
    send_buttons(env, cloud, factory)
    buttons = cloud.requests[0]["interactive"]["action"]["buttons"]
    assert [b["reply"]["title"] for b in buttons] == ["Approve", "Reject"]


@pytest.mark.parametrize(
    "inbound_ago", [timedelta(hours=25), timedelta(hours=23, minutes=58), None]
)
def test_outside_the_window_it_is_the_plain_template_without_buttons(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    inbound_ago: timedelta | None,
) -> None:
    link_owner(env, inbound_ago=inbound_ago)
    approval = request_approval(env)
    assert work(env, factory) == 1
    (message,) = cloud.requests
    assert message["type"] == "template"
    assert message["template"]["name"] == "pivoris_approval_requested_v1"
    assert "interactive" not in message and "buttons" not in json.dumps(message)
    assert tokens(env, approval) == []  # no token exists for a message that has no buttons
    (delivery,) = deliveries(env)
    assert delivery.delivery_metadata["approval_buttons"] == "not_sent_outside_window"
    assert delivery.delivery_metadata["cost"]["is_template"] is True


def test_the_window_is_judged_at_send_time_not_at_notify_time(
    env: Env, cloud: Cloud, factory: sessionmaker[Session], subject: FakeSubject
) -> None:
    link_owner(env, inbound_ago=timedelta(hours=23, minutes=50))
    approval = request_approval(env)  # recorded while the window is open
    env.clock.advance(minutes=30)  # the worker runs after it closed
    assert work(env, factory) == 1
    assert cloud.requests[0]["type"] == "template" and tokens(env, approval) == []


def test_an_approval_decided_before_the_job_runs_is_not_announced(
    env: Env, cloud: Cloud, factory: sessionmaker[Session], subject: FakeSubject
) -> None:
    link_owner(env)
    approval = request_approval(env)
    approvals_service.decide(
        env.session,
        env.clock,
        env.ctx(env.owner),
        approval.id,
        decision="approve",
        payload_hash=approval.payload_hash,
    )
    assert work(env, factory) == 1
    assert cloud.requests == []
    (delivery,) = deliveries(env)
    assert delivery.status == "failed" and delivery.last_error == "approval_not_pending"
    assert tokens(env, approval) == []


def test_a_retried_send_mints_fresh_single_use_tokens(
    env: Env, cloud: Cloud, factory: sessionmaker[Session], subject: FakeSubject
) -> None:
    link_owner(env)
    approval = request_approval(env)
    cloud.script = [(500, {"error": {"code": 2}})]
    work(env, factory)
    env.clock.advance(seconds=10)
    work(env, factory)
    assert [r["type"] for r in cloud.requests] == ["interactive", "interactive"]
    # the first attempt's buttons were never delivered; all four are ordinary single-use rows
    assert len(tokens(env, approval)) == 4


# --- a tap decides through the approval service ------------------------------------------------


def test_approve_decides_once_through_the_approval_service(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
) -> None:
    approval, raw = send_buttons(env, cloud, factory)
    cloud.in_transaction = env.session.in_transaction
    env.clock.advance(minutes=5)
    result = tap(env, cloud, wa_settings, act(raw["approve"]))
    assert result.processed == 1
    done = fresh(env, approval)
    assert done.status == "approved" and done.decision_channel == "whatsapp"
    assert done.decided_by_user_id == env.owner.user.id
    assert subject.decided == [("approved", approval.id)]
    assert last_reply(cloud) == TR["approved"]
    assert cloud.seen_in_transaction[-1] is False  # the reply is sent after the commit
    used = {t.decision: t.used_at for t in tokens(env, approval)}
    assert used["approved"] == env.clock.now() and used["rejected"] is None
    audits = env.session.scalars(select(AuditLog).where(AuditLog.action == "approval.approved"))
    (entry,) = audits.all()
    assert entry.metadata_["channel"] == "whatsapp"
    # the tap is an inbound message: it moved the 24-hour window anchor forward
    link = env.session.scalar(select(ChannelLink).where(ChannelLink.channel == "whatsapp"))
    assert link is not None and link.last_inbound_at == env.clock.now()
    events = env.session.scalars(select(WhatsAppWebhookEvent)).all()
    assert [e.status for e in events] == ["processed"]


def test_reject_decides_as_rejected(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
) -> None:
    approval, raw = send_buttons(env, cloud, factory)
    tap(env, cloud, wa_settings, act(raw["reject"]))
    assert fresh(env, approval).status == "rejected"
    assert subject.decided == [("rejected", approval.id)]
    assert last_reply(cloud) == TR["rejected"]


def test_an_english_owner_gets_an_english_answer(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
) -> None:
    env.owner.user.ui_locale = "en"
    env.session.commit()
    approval, raw = send_buttons(env, cloud, factory)
    tap(env, cloud, wa_settings, act(raw["approve"]))
    assert last_reply(cloud) == REPLIES["en"]["approved"]


# --- edge cases in the style of P9-05 ----------------------------------------------------------


def test_replay_shows_the_current_state_and_decides_nothing_twice(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
) -> None:
    approval, raw = send_buttons(env, cloud, factory)
    tap(env, cloud, wa_settings, act(raw["approve"]))
    tap(env, cloud, wa_settings, act(raw["approve"]))  # the same button again
    assert last_reply(cloud) == TR["already_approved"]
    tap(env, cloud, wa_settings, act(raw["reject"]))  # the sibling button: no second decision
    assert last_reply(cloud) == TR["already_approved"]
    assert fresh(env, approval).status == "approved"
    assert subject.decided == [("approved", approval.id)]


def test_a_duplicate_webhook_delivery_is_processed_once(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
) -> None:
    approval, raw = send_buttons(env, cloud, factory)
    first = tap(env, cloud, wa_settings, act(raw["approve"]), wamid="wamid.SAME")
    sent = len(cloud.requests)
    second = tap(env, cloud, wa_settings, act(raw["approve"]), wamid="wamid.SAME")
    assert first.processed == 1 and second.duplicates == 1 and second.processed == 0
    assert len(cloud.requests) == sent  # no second reply
    assert subject.decided == [("approved", approval.id)]


def test_an_expired_button_is_refused_and_the_approval_stays_undecided(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
) -> None:
    approval, raw = send_buttons(env, cloud, factory)
    # Past the approval's two hours. The tap itself reopens the owner's window, so the answer is
    # a session message.
    env.clock.advance(hours=3)
    tap(env, cloud, wa_settings, act(raw["approve"]))
    assert last_reply(cloud) == TR["expired"]
    assert fresh(env, approval).status != "approved" and subject.decided == []


def test_a_button_tapped_at_the_exact_expiry_instant_never_approves(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
) -> None:
    approval, raw = send_buttons(env, cloud, factory)
    env.clock.advance(hours=2)
    tap(env, cloud, wa_settings, act(raw["reject"]))
    assert last_reply(cloud) == TR["expired"] and subject.decided == []
    assert fresh(env, approval).status != "rejected"


def test_a_forwarded_button_tapped_by_another_linked_member_reveals_nothing(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
) -> None:
    approval, raw = send_buttons(env, cloud, factory)
    link_owner(env, role="manager", wa_id=OTHER_WA_ID)
    tap(env, cloud, wa_settings, act(raw["approve"]), wa_id=OTHER_WA_ID)
    assert cloud.requests[-1]["to"] == OTHER_WA_ID
    assert last_reply(cloud) == TR["invalid"]
    assert fresh(env, approval).status == "pending" and subject.decided == []
    assert all(t.used_at is None for t in tokens(env, approval))  # the owner's buttons still work
    # after the owner decided, the manager learns nothing about the state either
    tap(env, cloud, wa_settings, act(raw["approve"]))
    assert last_reply(cloud) == TR["approved"]
    tap(env, cloud, wa_settings, act(raw["approve"]), wa_id=OTHER_WA_ID)
    assert cloud.requests[-1]["to"] == OTHER_WA_ID and last_reply(cloud) == TR["invalid"]


def test_a_forwarded_button_tapped_from_an_unlinked_number_gets_no_reply(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
) -> None:
    approval, raw = send_buttons(env, cloud, factory)
    sent = len(cloud.requests)
    result = tap(env, cloud, wa_settings, act(raw["approve"]), wa_id="905559999999", wamid="w.x")
    assert result.ignored == 1 and result.processed == 0
    assert len(cloud.requests) == sent
    assert fresh(env, approval).status == "pending"
    row = env.session.get(WhatsAppWebhookEvent, "w.x")
    assert row is not None and row.status == "ignored"


def test_an_unlinked_owner_cannot_use_a_button_sent_earlier(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
) -> None:
    approval, raw = send_buttons(env, cloud, factory)
    link = env.session.scalar(select(ChannelLink).where(ChannelLink.channel == "whatsapp"))
    assert link is not None
    link.status = "unlinked"
    env.session.commit()
    sent = len(cloud.requests)
    tap(env, cloud, wa_settings, act(raw["approve"]))
    assert len(cloud.requests) == sent and fresh(env, approval).status == "pending"


def test_a_revoked_member_cannot_decide(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
) -> None:
    approval, raw = send_buttons(env, cloud, factory)
    member = env.session.scalar(
        select(WorkspaceMember).where(WorkspaceMember.user_id == env.owner.user.id)
    )
    assert member is not None
    env.session.delete(member)
    env.session.commit()
    sent = len(cloud.requests)
    tap(env, cloud, wa_settings, act(raw["approve"]))
    assert len(cloud.requests) == sent
    assert fresh(env, approval).status == "pending" and subject.decided == []


def test_a_member_who_lost_the_permission_is_refused(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
) -> None:
    approval, raw = send_buttons(env, cloud, factory)
    member = env.session.scalar(
        select(WorkspaceMember).where(WorkspaceMember.user_id == env.owner.user.id)
    )
    assert member is not None
    member.role = "staff"  # staff may not decide a knowledge.verify authorization
    env.session.commit()
    tap(env, cloud, wa_settings, act(raw["approve"]))
    assert last_reply(cloud) == TR["forbidden"]
    assert fresh(env, approval).status == "pending" and subject.decided == []


def test_an_approval_decided_on_the_web_shows_its_current_state(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
) -> None:
    approval, raw = send_buttons(env, cloud, factory)
    approvals_service.decide(
        env.session,
        env.clock,
        env.ctx(env.manager),
        approval.id,
        decision="reject",
        payload_hash=approval.payload_hash,
    )
    tap(env, cloud, wa_settings, act(raw["approve"]))
    assert last_reply(cloud) == TR["already_rejected"]
    assert fresh(env, approval).status == "rejected"
    assert subject.decided == [("rejected", approval.id)]


def test_a_stale_approval_is_not_approved(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
) -> None:
    approval, raw = send_buttons(env, cloud, factory)
    subject.version = 2  # the subject changed after the buttons were sent
    tap(env, cloud, wa_settings, act(raw["approve"]))
    assert last_reply(cloud) == TR["stale"]
    assert fresh(env, approval).status == "pending" and subject.decided == []


def test_a_withdrawn_approval_shows_that_the_button_no_longer_applies(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
) -> None:
    approval, raw = send_buttons(env, cloud, factory)
    approvals_service.cancel_for_subject(
        env.session, env.clock, env.ctx(env.owner), "owner_command", approval.subject_id, "edited"
    )
    env.session.commit()
    tap(env, cloud, wa_settings, act(raw["approve"]))
    assert last_reply(cloud) == TR["stale"] and subject.decided == []


@pytest.mark.parametrize(
    "button_id",
    ["", "act:", "approve", "act:" + "A" * 300, "act:../../etc/passwd", "act:' OR 1=1 --", "x:y"],
)
def test_malformed_or_unknown_button_ids_are_refused_without_effect(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
    button_id: str,
) -> None:
    approval, _ = send_buttons(env, cloud, factory)
    tap(env, cloud, wa_settings, button_id)
    assert last_reply(cloud) == TR["invalid"]
    assert fresh(env, approval).status == "pending" and subject.decided == []


def test_a_token_of_another_workspace_is_refused(
    env: Env,
    db_session: Session,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
) -> None:
    """Workspace B's owner has her own number and token; A's owner cannot use that token."""
    approval_a, _ = send_buttons(env, cloud, factory)
    ws_b, users_b = workspace_with_members(db_session, name="Salon B", slug="salon-b")
    db_session.add(
        ChannelLink(
            workspace_id=ws_b.id,
            user_id=users_b["owner"].id,
            channel="whatsapp",
            channel_user_id=OTHER_WA_ID,
            channel_chat_id=OTHER_WA_ID,
            status="active",
            linked_at=env.clock.now(),
            last_inbound_at=env.clock.now(),
        )
    )
    db_session.commit()
    ctx_b = knowledge_ctx(ws_b, users_b["owner"], "owner")
    approval_b = approvals_service.request(
        db_session,
        env.clock,
        ctx_b,
        kind="confirmation",
        action="command.update_fact",
        subject_type="owner_command",
        subject_id=uuid.uuid4(),
        subject_version=1,
        payload=PAYLOAD,
        summary=SUMMARY,
        required_permission="knowledge.verify",
        expires_at=env.clock.now() + timedelta(hours=1),
    )
    raw_b = ActionTokenService.create_action_token(
        db_session, env.clock, ctx_b, approval_b, decision="approved", user_id=users_b["owner"].id
    )
    db_session.commit()
    tap(env, cloud, wa_settings, act(raw_b))  # A's number, B's token
    assert last_reply(cloud) == TR["invalid"] and cloud.requests[-1]["to"] == WA_ID
    db_session.expire_all()
    still_b = db_session.get(Approval, approval_b.id)
    assert still_b is not None and still_b.status == "pending"
    assert fresh(env, approval_a).status == "pending"


# --- free text never decides (ADR-027) ---------------------------------------------------------


def test_free_text_never_decides_even_when_it_contains_a_valid_token(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
) -> None:
    approval, raw = send_buttons(env, cloud, factory)
    texts = ["approve", "yes", "evet onayla", act(raw["approve"]), raw["approve"]]
    for index, text in enumerate(texts):
        payload = envelope(
            [{"id": f"w.t{index}", "from": WA_ID, "type": "text", "text": {"body": text}}]
        )
        process_webhook(env.session, env.clock, payload, make_client(cloud), wa_settings)
        assert last_reply(cloud) == LINK_REPLIES["tr"]["open_app"]
    assert fresh(env, approval).status == "pending" and subject.decided == []
    assert all(t.used_at is None for t in tokens(env, approval))


def test_a_token_never_reaches_the_logs(
    env: Env,
    cloud: Cloud,
    factory: sessionmaker[Session],
    subject: FakeSubject,
    wa_settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("DEBUG")
    _, raw = send_buttons(env, cloud, factory)
    tap(env, cloud, wa_settings, act(raw["approve"]))
    tap(env, cloud, wa_settings, act(raw["approve"]))
    tap(env, cloud, wa_settings, act(raw["reject"] + "x"))
    assert all(t not in caplog.text for t in raw.values())


# --- the message says what is being approved (and never the customer's message) ---------------

CUSTOMER_TEXT = "Merhaba, cumartesi fiyatınız nedir? Telefonum 0555 000 00 00"


def reply_approval(env: Env, text: str) -> Approval:
    """A pending customer-reply approval for a draft with ``text``; the customer's own message is
    stored in the conversation and must never reach WhatsApp."""
    account = SocialAccount(
        workspace_id=env.workspace.id,
        platform="instagram",
        provider_kind="mock",
        external_account_id="ext-wa-buttons",
        username="golkent.demo",
        status="connected",
        capabilities={},
        granted_scopes=[],
    )
    env.session.add(account)
    env.session.flush()
    conversation = Conversation(
        workspace_id=env.workspace.id,
        social_account_id=account.id,
        customer_external_id="cust-wa-buttons",
        customer_handle="musteri_ayse",
        handling_mode="automatic",
        attention="none",
        last_inbound_at=env.clock.now(),
    )
    env.session.add(conversation)
    env.session.flush()
    message = Message(
        workspace_id=env.workspace.id,
        social_account_id=account.id,
        conversation_id=conversation.id,
        direction="inbound",
        sender_kind="customer",
        external_message_id="msg-wa-buttons",
        text=CUSTOMER_TEXT,
        provider_timestamp=env.clock.now(),
    )
    env.session.add(message)
    env.session.flush()
    draft = ReplyDraft(
        workspace_id=env.workspace.id,
        conversation_id=conversation.id,
        covers_through_message_id=message.id,
        source="ai",
        origin="legacy",
        status="pending_approval",
        decision="approval_required",
        text=text,
        version=1,
        created_by_actor_type="system",
    )
    env.session.add(draft)
    env.session.flush()
    approval = approvals_service.request(
        env.session,
        env.clock,
        env.ctx(env.staff),
        kind="authorization",
        action="reply.send",
        subject_type="reply_draft",
        subject_id=draft.id,
        subject_version=draft.version,
        payload={"reply_draft_id": str(draft.id), "text": text},
        summary={"draft_id": str(draft.id)},
        required_permission="knowledge.verify",
        expires_at=env.clock.now() + timedelta(hours=2),
    )
    draft.approval_id = approval.id
    env.session.commit()
    return approval


def only_body(cloud: Cloud) -> str:
    (message,) = cloud.requests
    assert message["type"] == "interactive"
    return str(message["interactive"]["body"]["text"])


def test_a_reply_approval_shows_the_proposed_reply_but_never_the_customer_message(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env)
    proposed = "Merhaba! Cumartesi günü seans ücretimiz 1.000 TL dir. Randevu için yazabilirsiniz."
    approval = reply_approval(env, proposed)
    assert work(env, factory) == 1
    body = only_body(cloud)
    assert proposed in body and "müşteri yanıtı" in body
    assert "Son karar zamanı" in body and len(body) <= BODY_LIMIT <= 1024
    assert "cumartesi fiyatınız" not in body and "0555" not in body
    assert "musteri_ayse" not in body and CUSTOMER_TEXT not in body
    assert ELLIPSIS not in body and "tam metin" not in body  # nothing was cut
    assert approval.payload_hash  # the approval is bound to the full payload, whatever is shown


def test_a_long_reply_is_cut_with_an_ellipsis_and_a_pointer_to_the_app(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    link_owner(env)
    proposed = "Merhaba! " + ("Çok uzun bir yanıt metni. " * 120)
    approval = reply_approval(env, proposed)
    full_hash = approval.payload_hash
    assert work(env, factory) == 1
    body = only_body(cloud)
    assert len(body) <= BODY_LIMIT <= 1024
    assert "Merhaba! Çok uzun" in body and ELLIPSIS in body and "(tam metin uygulamada)" in body
    assert proposed not in body
    # the deadline and the instruction are never the part that gets cut
    assert body.rstrip().endswith("karar verebilirsiniz.")
    assert CUSTOMER_TEXT not in body
    # the buttons still bind to the full payload: the hash is unchanged
    env.session.expire_all()
    stored = env.session.get(Approval, approval.id)
    assert stored is not None and stored.payload_hash == full_hash
    assert {t.payload_hash for t in tokens(env, approval)} == {full_hash}


def test_the_english_cut_note_and_labels(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    env.owner.user.ui_locale = "en"
    env.session.commit()
    link_owner(env)
    reply_approval(env, "Hello! " + ("A very long proposed reply. " * 100))
    work(env, factory)
    body = only_body(cloud)
    assert "Proposed reply:" in body and "(full text in the app)" in body
    assert len(body) <= BODY_LIMIT and "customer reply" in body


def test_a_content_approval_shows_the_post(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    from tests.helpers.content import request_approval as request_content_approval

    link_owner(env)
    item = make_item(
        env,
        status="pending_approval",
        title="Hafta sonu kampanyası",
        caption="Cumartesi 10:00 seansı için 2 yer kaldı.",
    )
    request_content_approval(env, item)
    env.session.commit()
    assert work(env, factory) == 1
    body = only_body(cloud)
    assert "Hafta sonu kampanyası" in body and "2 yer kaldı" in body and "paylaşım" in body
    assert len(body) <= BODY_LIMIT


def test_a_secondary_field_is_clipped_and_the_body_always_fits(
    env: Env, cloud: Cloud, factory: sessionmaker[Session]
) -> None:
    from tests.helpers.content import request_approval as request_content_approval

    link_owner(env)
    item = make_item(env, status="pending_approval", title="T" * 500, caption="C" * 5000)
    request_content_approval(env, item)
    env.session.commit()
    work(env, factory)
    body = only_body(cloud)
    assert len(body) <= BODY_LIMIT and "T" * 100 not in body and ELLIPSIS in body
