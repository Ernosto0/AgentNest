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
    metadata: dict[str, Any] | None = None,
    correlation_id: uuid.UUID | None = None,
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
        metadata_=metadata or {},
        correlation_id=correlation_id,
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


# --- Classification, descriptions, grouping and summary (redesigned Activity) ---------------

ALERT_META = {
    "alert_key": "agent_health:stuck_session:5d0c",
    "category": "agent",
    "severity": "warning",
    "summary": "Account agent session 5d0c stuck > 30 minutes in state running",
    "is_refire": True,
    "notification_count": 4,
}


def test_entries_carry_level_routine_details_and_a_collapse_key(env: Env) -> None:
    entry(env, "reply.sent", T0)
    entry(env, "content.failed", T0, metadata={"error_code": "PROVIDER_RATE_LIMITED"})
    entry(env, "social_account.degraded", T0)
    entry(env, "agent.step_transition", T0, metadata={"from": "model_pending", "to": "consumed"})
    entry(env, "agent.step_transition", T0, metadata={"from": "claimed", "to": "failed"})
    entry(env, "reply_draft.sent", T0, actor_type="system")
    entry(env, "something.new_in_a_later_version", T0)
    env.session.commit()

    items = feed(env).json()["items"]
    shape = sorted((e["action"], e["level"], e["routine"]) for e in items)
    assert shape == sorted(
        [
            ("reply.sent", "success", False),
            ("content.failed", "failure", False),
            ("social_account.degraded", "warning", False),
            ("agent.step_transition", "info", True),
            # A failed step is a problem: never routine, and it says so.
            ("agent.step_transition", "failure", False),
            ("reply_draft.sent", "success", True),
            ("something.new_in_a_later_version", "info", False),
        ]
    )
    failed_step = next(
        e for e in items if e["action"] == "agent.step_transition" and e["level"] == "failure"
    )
    assert failed_step["text"] == "Asistan adımı başarısız oldu"
    failed = next(e for e in items if e["action"] == "content.failed")
    detail = {"key": "error_code", "label": "Neden kodu", "value": "PROVIDER_RATE_LIMITED"}
    assert detail in failed["details"]
    assert all(isinstance(e["collapse_key"], str) and e["collapse_key"] for e in items)


def test_an_operator_alert_names_its_condition_and_hides_operator_text(env: Env) -> None:
    alert_id = uuid.uuid4()
    for i in range(3):
        entry(
            env,
            "security.operator_alert_fired",
            datetime(2026, 3, 10, 9 + i, 0, tzinfo=UTC),
            resource_type="operator_alert",
            resource_id=alert_id,
            metadata={**ALERT_META, "is_refire": i > 0, "notification_count": i + 1},
        )
    entry(
        env,
        "security.operator_alert_fired",
        T0,
        resource_type="operator_alert",
        resource_id=uuid.uuid4(),
        metadata={"alert_key": "dead_job:send_reply", "severity": "critical", "is_refire": False},
    )
    entry(
        env,
        "security.alert_delivery_failed",
        T0,
        resource_type="operator_alert",
        resource_id=alert_id,
        metadata={"alert_key": ALERT_META["alert_key"], "error": "SMTP auth failed for x@y.z"},
    )
    env.session.commit()

    response = feed(env)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    stuck = [e for e in items if "ilerlemiyor" in e["text"] and "fired" in e["action"]]
    assert len(stuck) == 3
    first = next(e for e in stuck if e["occurred_at"].startswith("2026-03-10T09"))
    latest = next(e for e in stuck if e["occurred_at"].startswith("2026-03-10T11"))
    condition = "asistan oturumu 30 dakikadan uzun süredir ilerlemiyor"
    assert first["text"] == f"Operatör uyarısı: {condition}"
    assert first["level"] == "warning" and first["routine"] is False
    assert latest["text"] == f"Operatör uyarısı sürüyor: {condition}"
    assert latest["level"] == "info" and latest["routine"] is True
    assert latest["resource"]["label"] == condition
    assert latest["resource"]["link"] == f"/w/{env.workspace.id}/more/settings/system-health"
    count = {"key": "notification_count", "label": "Bildirim sırası", "value": "3"}
    assert count in latest["details"]
    # Re-notifications of one condition group together; another condition does not join them.
    assert len({e["collapse_key"] for e in stuck}) == 1
    dead = next(e for e in items if "kalıcı" in e["text"])
    assert dead["level"] == "failure" and dead["collapse_key"] != latest["collapse_key"]
    undelivered = next(e for e in items if e["action"] == "security.alert_delivery_failed")
    assert undelivered["level"] == "failure"
    # Operator summaries and exception strings never reach the reader.
    assert "stuck >" not in response.text and "SMTP" not in response.text


def test_fact_values_and_unsafe_values_in_details(env: Env) -> None:
    entry(
        env,
        "fact.updated",
        T0,
        actor_type="user",
        actor_id=str(env.owner.user.id),
        metadata={
            "key": "pricing.membership_monthly",
            "version": 3,
            "old_display": "5.500 ₺ / ay",
            "new_display": "6.000 ₺ / ay",
            "reason": "not a code; free text here",
            "original_filename": "secret-plan.png",
        },
    )
    env.session.commit()
    item = feed(env).json()["items"][0]
    pairs = {d["key"]: d["value"] for d in item["details"]}
    assert pairs["old_display"] == "5.500 ₺ / ay" and pairs["new_display"] == "6.000 ₺ / ay"
    assert pairs["version"] == "3" and pairs["key"] == "pricing.membership_monthly"
    assert "reason" not in pairs and "original_filename" not in pairs


def test_level_routine_and_correlation_filters(env: Env) -> None:
    flow = uuid.uuid4()
    entry(env, "message.received", T0, correlation_id=flow)
    entry(env, "reply.sent", T0, correlation_id=flow)
    entry(env, "operation.succeeded", T0, correlation_id=flow)
    entry(env, "reply.failed", T0)
    entry(env, "reply.outcome_unknown", T0)
    env.session.commit()

    def actions(**params: Any) -> list[str]:
        response = feed(env, **params)
        assert response.status_code == 200, response.text
        return sorted(e["action"] for e in response.json()["items"])

    assert actions(level="failure") == ["reply.failed"]
    assert actions(level=["failure", "warning"]) == ["reply.failed", "reply.outcome_unknown"]
    assert actions(level="success") == ["operation.succeeded", "reply.sent"]
    assert actions(level="success", include_routine="false") == ["reply.sent"]
    assert "operation.succeeded" not in actions(include_routine="false")
    flow_actions = ["message.received", "operation.succeeded", "reply.sent"]
    assert actions(correlation=str(flow)) == flow_actions
    assert feed(env, level="nonsense").status_code == 422
    assert feed(env, correlation="nope").status_code == 422


def _sample_rows() -> list[tuple[str, str, dict[str, Any]]]:
    """Every rule, with each metadata value it knows, an unknown value and none, for a system
    and a user actor."""
    from app.activity.classify import RULES

    rows: list[tuple[str, str, dict[str, Any]]] = []
    for action, rule in RULES.items():
        metas: list[dict[str, Any]] = [{}]
        for name in rule.fields:
            metas += [{name: value} for value in [*rule.by_value, "something_else"]]
        for meta in metas:
            for actor in ("system", "user"):
                rows.append((action, actor, meta))
    rows.append(("an.unknown_action", "system", {}))
    return rows


def test_the_sql_filters_agree_with_the_row_classification(env: Env) -> None:
    from app.activity.classify import LEVELS, classify

    expected: dict[str, tuple[str, bool]] = {}
    for action, actor, meta in _sample_rows():
        row = entry(env, action, T0, actor_type=actor, metadata=meta)
        found = classify(action, actor, meta)
        expected[str(row.id)] = (found.level, found.routine)
    env.session.commit()

    def ids(**params: Any) -> set[str]:
        seen: set[str] = set()
        cursor: str | None = None
        while True:
            page_params = {"limit": 100, **params, **({"cursor": cursor} if cursor else {})}
            body = feed(env, **page_params).json()
            seen.update(e["id"] for e in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                return seen

    assert ids() == set(expected)
    for level in LEVELS:
        assert ids(level=level) == {k for k, v in expected.items() if v[0] == level}, level
    assert ids(include_routine="false") == {k for k, v in expected.items() if not v[1]}
    # A routine entry is never a problem.
    problems = {k for k, v in expected.items() if v[0] in ("failure", "warning")}
    assert problems <= ids(include_routine="false")


def test_routine_is_never_a_problem_nor_a_persons_own_action() -> None:
    from app.activity.classify import classify

    for action, actor, meta in _sample_rows():
        found = classify(action, actor, meta)
        if found.routine:
            assert found.level in ("info", "success"), (action, meta)
            assert actor != "user", action


def test_the_summary_counts_recent_local_days_like_the_filters(
    env: Env, clock: FrozenClock
) -> None:
    now = clock.now()  # 2026-01-15 12:00Z = 15:00 in Istanbul
    entry(env, "reply.sent", now)
    entry(env, "reply.failed", now)
    entry(env, "social_account.degraded", now)
    entry(env, "operation.succeeded", now)  # routine
    entry(env, "agent.step_transition", now, metadata={"to": "failed"})  # a failure
    # 9 January 00:00 in Istanbul is 8 January 21:00Z: the first instant of the 7-day window.
    entry(env, "message.received", datetime(2026, 1, 8, 21, 0, tzinfo=UTC))
    entry(env, "message.received", datetime(2026, 1, 8, 20, 59, tzinfo=UTC))  # just before
    entry(env, "reply.failed", now, workspace_id=uuid.uuid4())  # another workspace
    env.session.commit()

    response = env.call(env.owner, "GET", "/activity/summary")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["days"] == 7
    assert body["period_start"].startswith("2026-01-08T21:00:00")
    assert (body["total"], body["routine"]) == (5, 1)
    assert (body["failure"], body["warning"], body["success"]) == (2, 1, 1)

    one_day = env.call(env.owner, "GET", "/activity/summary", params={"days": 1}).json()
    assert one_day["total"] == 4
    assert env.call(env.owner, "GET", "/activity/summary", params={"days": 0}).status_code == 422
    assert env.call(env.staff, "GET", "/activity/summary").status_code == 403
