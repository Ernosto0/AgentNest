"""The Activity feed (plan H7, api-design.md section 2.8): groups, the local-day filter, a stable
cursor, labels resolved at read time, no message text, and the permission."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.activity.groups import GROUP_NAMES, GROUPS
from app.audit.models import AuditLog
from app.content.models import ContentItem
from app.core.clock import FrozenClock
from app.inbox.models import Conversation, Message
from app.integrations.instagram.models import SocialAccount
from tests.factories import create_user
from tests.helpers.env import Env, build_env

SAMPLE = {
    "messages": "message.received",
    "replies": "reply.sent",
    "approvals": "approval.requested",
    "content": "content.published",
    "knowledge": "fact.updated",
    "commands": "command.executed",
    "accounts": "social_account.needs_reauth",
    "members": "member.joined",
    "system": "report.generated",
}
CUSTOMER_TEXT = "Aylık üyelik ne kadar? Telefonum 0555 000 00 00"


@pytest.fixture
def env(db_session: Session, make_client: Callable[[], TestClient], clock: FrozenClock) -> Env:
    built = build_env(db_session, make_client, clock)
    db_session.commit()
    return built


def entry(
    env: Env,
    action: str,
    when: datetime,
    *,
    actor_type: str = "system",
    actor_id: str | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    simulated: bool = False,
    workspace_id: uuid.UUID | None = None,
    row_id: uuid.UUID | None = None,
) -> AuditLog:
    row = AuditLog(
        id=row_id or uuid.uuid4(),
        workspace_id=workspace_id or env.workspace.id,
        occurred_at=when,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        is_simulated=simulated,
    )
    env.session.add(row)
    env.session.flush()
    return row


def feed(env: Env, role: Any = None, **params: Any) -> Any:
    return env.call(role or env.owner, "GET", "/activity", params=params)


T0 = datetime(2026, 3, 10, 9, 0, tzinfo=UTC)


def test_every_group_filter_returns_only_that_group(env: Env) -> None:
    assert set(SAMPLE) == set(GROUP_NAMES)
    for group, action in SAMPLE.items():
        assert GROUPS[action] == group
        entry(env, action, T0)
    env.session.commit()

    everything = feed(env).json()["items"]
    assert {e["group"] for e in everything} == set(GROUP_NAMES)
    for group, action in SAMPLE.items():
        response = feed(env, type=group)
        assert response.status_code == 200, response.text
        assert [(e["action"], e["group"]) for e in response.json()["items"]] == [(action, group)]


def test_the_system_group_also_holds_actions_nobody_claims(env: Env) -> None:
    entry(env, "something.new_in_a_later_version", T0)
    env.session.commit()
    items = feed(env, type="system").json()["items"]
    assert [e["action"] for e in items] == ["something.new_in_a_later_version"]
    assert items[0]["group"] == "system" and items[0]["text"]


def test_an_unknown_group_is_a_422(env: Env) -> None:
    assert feed(env, type="nonsense").status_code == 422


def test_the_date_filter_follows_the_local_midnight_of_istanbul(env: Env) -> None:
    # Istanbul is UTC+3: local 23:59:59 on 10 March is 20:59:59Z, local midnight is 21:00:00Z.
    entry(env, "fact.updated", datetime(2026, 3, 9, 20, 59, 59, tzinfo=UTC))  # 9 March 23:59:59
    entry(env, "fact.created", datetime(2026, 3, 9, 21, 0, 0, tzinfo=UTC))  # 10 March 00:00:00
    entry(env, "fact.verified", datetime(2026, 3, 10, 20, 59, 59, tzinfo=UTC))  # 10 March 23:59:59
    entry(env, "fact.archived", datetime(2026, 3, 10, 21, 0, 0, tzinfo=UTC))  # 11 March 00:00:00
    env.session.commit()

    tenth = [e["action"] for e in feed(env, date="2026-03-10").json()["items"]]
    assert tenth == ["fact.verified", "fact.created"]  # newest first
    ninth = [e["action"] for e in feed(env, date="2026-03-09").json()["items"]]
    assert ninth == ["fact.updated"]
    eleventh = [e["action"] for e in feed(env, date="2026-03-11").json()["items"]]
    assert eleventh == ["fact.archived"]
    # The filters combine.
    assert feed(env, date="2026-03-10", type="members").json()["items"] == []
    assert feed(env, date="garbage").status_code == 422


def test_the_cursor_is_stable_when_entries_share_a_timestamp(env: Env) -> None:
    ids = [uuid.UUID(int=i + 1) for i in range(7)]
    for row_id in ids:
        entry(env, "message.received", T0, row_id=row_id)  # the very same instant
    entry(env, "fact.updated", datetime(2026, 3, 10, 8, 0, tzinfo=UTC))  # older
    entry(env, "fact.created", datetime(2026, 3, 10, 10, 0, tzinfo=UTC))  # newer
    env.session.commit()

    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        params: dict[str, Any] = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        body = feed(env, **params).json()
        seen.extend(e["id"] for e in body["items"])
        pages += 1
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert pages == 3
    assert len(seen) == len(set(seen)) == 9  # nothing skipped, nothing repeated
    same_instant = [s for s in seen if uuid.UUID(s) in ids]
    assert same_instant == [str(i) for i in sorted(ids, reverse=True)]


def test_a_malformed_cursor_is_a_422(env: Env) -> None:
    assert feed(env, cursor="not-a-cursor").status_code == 422


def test_actor_labels_and_a_removed_member(env: Env, db_session: Session) -> None:
    former = create_user(db_session, display_name="Ayrılan Kişi")  # never a member here
    entry(env, "fact.updated", T0, actor_type="user", actor_id=str(env.owner.user.id))
    entry(env, "fact.created", T0, actor_type="user", actor_id=str(former.id))
    entry(env, "reply.sent", T0, actor_type="agent")
    entry(env, "message.received", T0, actor_type="provider")
    entry(env, "report.generated", T0, actor_type="system")
    db_session.commit()

    by_action = {e["action"]: e["actor"] for e in feed(env).json()["items"]}
    assert by_action["fact.updated"] == {"type": "user", "label": "Owner User"}
    assert by_action["fact.created"] == {"type": "user", "label": "Eski üye"}
    assert by_action["reply.sent"] == {"type": "agent", "label": "Yapay zekâ"}
    assert by_action["message.received"] == {"type": "provider", "label": "Instagram"}
    assert by_action["report.generated"] == {"type": "system", "label": "Sistem"}


def test_texts_and_labels_follow_the_readers_language(env: Env, db_session: Session) -> None:
    env.owner.user.ui_locale = "en"
    entry(env, "fact.created", T0, actor_type="user", actor_id=str(uuid.uuid4()))
    db_session.commit()
    item = feed(env).json()["items"][0]
    assert item["text"] == "Information added"
    assert item["actor"]["label"] == "Former member"


def test_labels_are_read_from_the_records_and_a_missing_record_is_neutral(
    env: Env, db_session: Session
) -> None:
    account = SocialAccount(
        workspace_id=env.workspace.id,
        provider_kind="mock",
        external_account_id="mock-1",
        username="golkent.demo",
        status="connected",
    )
    db_session.add(account)
    db_session.flush()
    conversation = Conversation(
        workspace_id=env.workspace.id,
        social_account_id=account.id,
        customer_external_id="cust-1",
        customer_handle="ayse_k",
        is_simulated=True,
    )
    db_session.add(conversation)
    db_session.flush()
    message = Message(
        workspace_id=env.workspace.id,
        conversation_id=conversation.id,
        social_account_id=account.id,
        direction="inbound",
        sender_kind="customer",
        external_message_id="mid-1",
        text=CUSTOMER_TEXT,
        provider_timestamp=T0,
        is_simulated=True,
    )
    content = ContentItem(
        workspace_id=env.workspace.id,
        content_type="feed_image",
        status="draft",
        title="Yaz kampanyası",
        created_by_user_id=env.owner.user.id,
        is_simulated=True,
    )
    db_session.add_all([message, content])
    db_session.flush()
    entry(
        env, "message.received", T0, resource_type="message", resource_id=message.id, simulated=True
    )
    entry(env, "content.created", T0, resource_type="content_item", resource_id=content.id)
    entry(
        env, "social_account.connected", T0, resource_type="social_account", resource_id=account.id
    )
    entry(env, "content.updated", T0, resource_type="content_item", resource_id=uuid.uuid4())
    db_session.commit()

    response = feed(env)
    assert response.status_code == 200, response.text
    by_action = {e["action"]: e for e in response.json()["items"]}
    ws = env.workspace.id
    assert by_action["message.received"]["resource"] == {
        "type": "message",
        "id": str(message.id),
        "label": "ayse_k",
        "link": f"/w/{ws}/inbox/{conversation.id}",
    }
    assert by_action["message.received"]["is_simulated"] is True
    assert by_action["content.created"]["resource"]["label"] == "Yaz kampanyası"
    assert by_action["content.created"]["resource"]["link"] == f"/w/{ws}/content/{content.id}"
    assert by_action["social_account.connected"]["resource"]["label"] == "golkent.demo"
    gone = by_action["content.updated"]["resource"]
    assert gone["label"] == "Silinmiş kayıt" and gone["link"] is None

    # INV-12: no customer text anywhere in the output (the message above carries some).
    assert "üyelik" not in response.text and "0555" not in response.text


def test_the_feed_uses_a_constant_number_of_queries(env: Env, db_session: Session) -> None:
    from sqlalchemy import event

    for _ in range(30):
        entry(env, "content.updated", T0, resource_type="content_item", resource_id=uuid.uuid4())
        entry(env, "fact.updated", T0, actor_type="user", actor_id=str(uuid.uuid4()))
    db_session.commit()
    statements: list[str] = []

    def count(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        statements.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", count)
    try:
        assert feed(env, limit=60).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", count)
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) < 20, len(selects)  # not one per row


def test_owner_and_manager_may_read_and_staff_may_not(env: Env) -> None:
    entry(env, "fact.updated", T0)
    env.session.commit()
    assert feed(env, env.owner).status_code == 200
    assert feed(env, env.manager).status_code == 200
    denied = feed(env, env.staff)
    assert denied.status_code == 403 and denied.json()["code"] == "FORBIDDEN"


def test_a_signed_out_caller_is_refused(env: Env, make_client: Any) -> None:
    assert make_client().get(f"{env.base}/activity").status_code == 401


def test_other_workspaces_and_system_rows_never_show(env: Env, db_session: Session) -> None:
    other = uuid.uuid4()
    entry(env, "fact.updated", T0)
    entry(env, "fact.created", T0, workspace_id=other)
    row = AuditLog(
        workspace_id=None,
        occurred_at=T0,
        actor_type="system",
        action="webhook.signature_invalid",
        is_simulated=False,
    )
    db_session.add(row)
    db_session.commit()
    assert [e["action"] for e in feed(env).json()["items"]] == ["fact.updated"]
