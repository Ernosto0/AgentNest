"""The report routes (api-design.md section 2.8): shape, links, drill-down equality (AC-E3),
the staff filter (H2), validation, regeneration and the localised summary."""

from collections.abc import Callable
from datetime import timedelta
from statistics import median
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.identity.models import Workspace
from app.reporting.definitions import BY_KEY, INBOX_KEYS, KEYS
from tests.factories import login, workspace_with_members
from tests.helpers.reporting import DAY, EXPECTED, EXPECTED_BREAKDOWN, EXPECTED_BURSTS, at
from tests.integration.reporting.conftest import ReportEnv

D = DAY.isoformat()


def _report(env: ReportEnv, role: Any = None, **params: str) -> Any:
    return env.env.call(
        role or env.env.owner, "GET", "/reports/daily", params={"date": D, **params}
    )


def _get(env: Any, api_path: str) -> Any:
    """Follow a link the API returned, as the owner."""
    return env.owner.client.get(api_path, headers=env.owner.headers)


def _all_items(env: ReportEnv, key: str, role: Any = None, limit: int = 7) -> tuple[dict, list]:
    """Every page of a drill-down; returns the first page's envelope and all items."""
    items: list[dict[str, Any]] = []
    first: dict[str, Any] | None = None
    cursor: str | None = None
    for _ in range(100):
        params: dict[str, Any] = {"limit": limit, **({"cursor": cursor} if cursor else {})}
        response = env.env.call(
            role or env.env.owner, "GET", f"/reports/daily/{D}/metrics/{key}", params=params
        )
        assert response.status_code == 200, response.text
        body = response.json()
        first = first or body
        items.extend(body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert first is not None and cursor is None
    return first, items


# --- the report -------------------------------------------------------------------------------


def test_a_past_day_comes_back_complete_with_a_link_on_every_number(report_env: ReportEnv) -> None:
    response = _report(report_env)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["local_date"] == D and body["timezone"] == "Europe/Istanbul"
    assert body["period_start"] == "2026-03-09T21:00:00Z"
    assert body["period_end"] == "2026-03-10T21:00:00Z"
    assert body["is_partial"] is False
    assert body["definitions_version"] == "2"
    assert body["has_simulated_data"] is True
    assert [m["key"] for m in body["metrics"]] == list(KEYS)
    ws = report_env.env.workspace.id
    for metric in body["metrics"]:
        key = metric["key"]
        assert metric["value"] == EXPECTED[key], key
        definition = BY_KEY[key]
        assert (metric["kind"], metric["section"]) == (definition.kind, definition.section)
        query = f"?snapshot_id={body['snapshot_id']}"
        assert metric["link"] == {
            "api": f"/api/v1/workspaces/{ws}/reports/daily/{D}/metrics/{key}{query}",
            "route": f"/w/{ws}/more/reports/{D}/{key}{query}",
        }
        has_breakdown = key == "pending_approvals_now"
        assert (
            (metric["breakdown"] == EXPECTED_BREAKDOWN)
            if has_breakdown
            else (metric["breakdown"] is None)
        )


def test_screen_links_exist_only_where_an_exact_filter_does(report_env: ReportEnv) -> None:
    ws = report_env.env.workspace.id
    screens = {m["key"]: m["screen_link"] for m in _report(report_env).json()["metrics"]}
    assert {k for k, v in screens.items() if v} == {"pending_approvals_now", "content_on_hold_now"}
    assert screens["pending_approvals_now"] == {
        "api": f"/api/v1/workspaces/{ws}/approvals?status=pending",
        "route": f"/w/{ws}/approvals",
    }
    assert screens["content_on_hold_now"] == {
        "api": f"/api/v1/workspaces/{ws}/content-items?status=on_hold",
        "route": f"/w/{ws}/content?status=on_hold",
    }


def test_every_metric_link_leads_to_the_drill_down(report_env: ReportEnv) -> None:
    env = report_env.env
    for metric in _report(report_env).json()["metrics"]:
        response = _get(env, metric["link"]["api"])
        assert response.status_code == 200, metric["key"]
        assert response.json()["key"] == metric["key"]


def test_the_report_is_stored_by_the_first_read_of_a_past_day(report_env: ReportEnv) -> None:
    first = _report(report_env).json()
    builder = report_env.builder()
    builder.message(builder.conversation(at(DAY, 9, 0)), "inbound", at(DAY, 9, 59))
    report_env.env.session.commit()
    second = _report(report_env).json()
    assert second["generated_at"] == first["generated_at"]
    assert second["metrics"] == first["metrics"]  # re-read, not recomputed


def test_today_is_live_and_partial(report_env: ReportEnv) -> None:
    env = report_env
    env.clock.advance(hours=10)  # 10:00 local, the next day
    body = env.env.call(env.env.owner, "GET", "/reports/daily").json()  # no date: today
    assert body["local_date"] == (DAY + timedelta(days=1)).isoformat()
    assert body["is_partial"] is True and body["period_end"] == body["generated_at"]
    assert body["period_end"].startswith("2026-03-11T07:00:00")
    assert {m["key"]: m["value"] for m in body["metrics"]}["inbound_messages"] == 0
    builder = env.builder()
    day = DAY + timedelta(days=1)
    builder.message(builder.conversation(at(day, 8, 0)), "inbound", at(day, 9, 0))
    env.env.session.commit()
    again = env.env.call(env.env.owner, "GET", "/reports/daily").json()
    assert {m["key"]: m["value"] for m in again["metrics"]}["inbound_messages"] == 1


def test_generate_selects_a_new_generation_and_keeps_the_old_links(report_env: ReportEnv) -> None:
    env = report_env
    stored = _report(env).json()
    builder = env.builder()
    builder.message(builder.conversation(at(DAY, 9, 0)), "inbound", at(DAY, 9, 59))
    env.env.session.commit()
    env.clock.advance(minutes=1)

    response = env.env.call(env.env.owner, "POST", "/reports/daily/generate", json={"date": D})
    assert response.status_code == 200, response.text
    regenerated = response.json()
    values = {m["key"]: m["value"] for m in regenerated["metrics"]}
    assert values["inbound_messages"] == EXPECTED["inbound_messages"] + 1
    assert regenerated["generated_at"] > stored["generated_at"]
    assert _report(env).json()["metrics"] == regenerated["metrics"]  # the stored copy changed
    assert regenerated["snapshot_id"] != stored["snapshot_id"]
    old = _get(env.env, stored["metrics"][0]["link"]["api"])
    assert old.status_code == 200
    assert old.json()["value"] == EXPECTED["inbound_messages"]


def test_the_manager_may_generate_and_staff_may_not(report_env: ReportEnv) -> None:
    env = report_env.env
    assert (
        env.call(env.manager, "POST", "/reports/daily/generate", json={"date": D}).status_code
        == 200
    )
    denied = env.call(env.staff, "POST", "/reports/daily/generate", json={"date": D})
    assert denied.status_code == 403 and denied.json()["code"] == "FORBIDDEN"


@pytest.mark.parametrize("bad", ["garbage", "2026-13-40", "tomorrow", "10.03.2026"])
def test_an_invalid_date_is_a_422(report_env: ReportEnv, bad: str) -> None:
    env = report_env.env
    assert env.call(env.owner, "GET", "/reports/daily", params={"date": bad}).status_code == 422
    assert (
        env.call(env.owner, "GET", f"/reports/daily/{bad}/metrics/inbound_messages").status_code
        == 422
    )
    assert (
        env.call(env.owner, "POST", "/reports/daily/generate", json={"date": bad}).status_code
        == 422
    )
    assert env.call(env.owner, "POST", "/reports/daily/generate", json={}).status_code == 422


def test_a_future_date_is_a_422_with_a_field_error(report_env: ReportEnv) -> None:
    env = report_env.env
    future = (DAY + timedelta(days=3)).isoformat()
    for response in (
        env.call(env.owner, "GET", "/reports/daily", params={"date": future}),
        env.call(env.owner, "POST", "/reports/daily/generate", json={"date": future}),
        env.call(env.owner, "GET", f"/reports/daily/{future}/metrics/inbound_messages"),
    ):
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "VALIDATION_FAILED"


def test_an_unknown_key_is_a_404(report_env: ReportEnv) -> None:
    env = report_env.env
    response = env.call(env.owner, "GET", f"/reports/daily/{D}/metrics/no_such_metric")
    assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"


def test_a_signed_out_caller_is_refused(report_env: ReportEnv, make_client: Any) -> None:
    anonymous = make_client()
    base = f"/api/v1/workspaces/{report_env.env.workspace.id}/reports/daily"
    assert anonymous.get(base).status_code == 401
    assert anonymous.get(f"{base}/{D}/metrics/inbound_messages").status_code == 401


# --- the staff filter (H2) ---------------------------------------------------------------------


def test_staff_see_the_inbox_metrics_only(report_env: ReportEnv) -> None:
    env = report_env
    body = _report(env, env.env.staff).json()
    keys = [m["key"] for m in body["metrics"]]
    assert keys == [k for k in KEYS if k in INBOX_KEYS]
    assert all(m["screen_link"] is None for m in body["metrics"])
    # The summary is built from what they may see: messages only.
    assert [s["section"] for s in body["summary"]["sections"]] == ["messages"]
    owner = _report(env).json()
    assert {s["section"] for s in owner["summary"]["sections"]} == {
        "messages",
        "approvals",
        "content",
        "knowledge",
        "problems",
    }


def test_staff_may_drill_into_inbox_numbers_but_not_the_others(report_env: ReportEnv) -> None:
    env = report_env.env
    for key in KEYS:
        response = env.call(env.staff, "GET", f"/reports/daily/{D}/metrics/{key}")
        if key in INBOX_KEYS:
            assert response.status_code == 200, key
        else:
            assert response.status_code == 403, key
            assert response.json()["code"] == "FORBIDDEN"


# --- drill-down: the list is the number (AC-E3) ------------------------------------------------


@pytest.mark.parametrize("key", KEYS)
def test_the_drill_down_has_as_many_rows_as_the_number(report_env: ReportEnv, key: str) -> None:
    first, items = _all_items(report_env, key)
    value = {m["key"]: m["value"] for m in _report(report_env).json()["metrics"]}[key]
    assert first["key"] == key and first["value"] == value == EXPECTED[key]
    if BY_KEY[key].value == "median":
        # The rows are the answered bursts; the number is their median.
        measures = sorted(i["measure"] for i in items)
        assert measures == [float(m) for m in EXPECTED_BURSTS]
        assert median(measures) == value
    else:
        assert len(items) == value
        assert all(i["measure"] is None for i in items)
    assert len({i["id"] for i in items}) == len(items)  # a page boundary neither repeats nor drops
    times = [i["occurred_at"] for i in items]
    assert times == sorted(times, reverse=True)  # newest first
    assert all(i["is_simulated"] is True for i in items)  # INV-09
    assert all(i["label"] for i in items)


def test_paging_with_equal_timestamps_keeps_every_row_once(report_env: ReportEnv) -> None:
    env = report_env
    builder = env.builder()
    moment = at(DAY, 22, 30)
    for _ in range(9):
        builder.message(builder.conversation(at(DAY, 22, 0)), "inbound", moment)
    env.env.session.commit()
    env.env.call(env.env.owner, "POST", "/reports/daily/generate", json={"date": D})

    for limit in (1, 2, 4):
        first, items = _all_items(env, "inbound_messages", limit=limit)
        assert first["value"] == len(items) == EXPECTED["inbound_messages"] + 9
        assert len({i["id"] for i in items}) == len(items)
        assert [i["occurred_at"] for i in items[:9]] == [items[0]["occurred_at"]] * 9


def test_an_invalid_cursor_is_a_422(report_env: ReportEnv) -> None:
    env = report_env.env
    for cursor in ("not-a-cursor", "e30"):
        response = env.call(
            env.owner,
            "GET",
            f"/reports/daily/{D}/metrics/inbound_messages",
            params={"cursor": cursor},
        )
        assert response.status_code == 422, cursor
    too_many = env.call(
        env.owner, "GET", f"/reports/daily/{D}/metrics/inbound_messages", params={"limit": 0}
    )
    assert too_many.status_code == 422


def test_drill_down_rows_link_to_their_screens(report_env: ReportEnv) -> None:
    env = report_env.env
    ws = env.workspace.id
    messages = _all_items(report_env, "inbound_messages")[1]
    conversation = messages[0]["link"]
    assert conversation["route"].startswith(f"/w/{ws}/inbox/")
    assert _get(env, conversation["api"]).status_code == 200

    published = _all_items(report_env, "content_published")[1]
    assert published[0]["label"] == "post"  # the item's own title
    assert published[0]["link"]["route"].startswith(f"/w/{ws}/content/")
    assert (
        env.owner.client.get(published[0]["link"]["api"], headers=env.owner.headers).status_code
        == 200
    )

    approvals = _all_items(report_env, "pending_approvals_now")[1]
    assert sorted(i["label"] for i in approvals) == [
        "Bilgi değişikliği onayı",
        "Yanıt onayı",
        "Yanıt onayı",
        "Yayın onayı",
    ]
    assert (
        env.owner.client.get(approvals[0]["link"]["api"], headers=env.owner.headers).status_code
        == 200
    )
    assert approvals[0]["link"]["route"] == f"/w/{ws}/approvals"

    errors = _all_items(report_env, "integration_errors")[1]
    assert {i["kind"] for i in errors} == {"operation", "inbound_event", "audit_log"}
    assert any(i["link"] is None for i in errors if i["kind"] == "inbound_event")


def test_a_customer_is_labelled_by_handle_never_by_message_text(report_env: ReportEnv) -> None:
    env = report_env
    builder = env.builder()
    conversation = builder.conversation(at(DAY, 22, 0))
    conversation.customer_handle = "@ayse"
    message = builder.message(conversation, "inbound", at(DAY, 22, 5))
    message.text = "Fiyat nedir? Telefonum 0555 123 45 67"
    env.env.session.commit()
    env.env.call(env.env.owner, "POST", "/reports/daily/generate", json={"date": D})

    response = env.env.call(
        env.env.owner, "GET", f"/reports/daily/{D}/metrics/inbound_messages", params={"limit": 1}
    )
    top = response.json()["items"][0]
    assert top["label"] == "@ayse"
    assert "Fiyat" not in response.text and "0555" not in response.text


# --- the summary (H4) ----------------------------------------------------------------------------


def test_the_summary_is_templated_and_follows_the_readers_language(report_env: ReportEnv) -> None:
    env = report_env
    tr = _report(env).json()["summary"]
    assert tr["empty"] is False
    assert "Gelen mesajlar: 15" in tr["text"] and "Mesajlar" in tr["text"]
    assert "Medyan ilk yanıt süresi: 6,5 dk" in tr["text"]  # a Turkish decimal comma
    env.env.owner.user.ui_locale = "en"
    env.env.session.commit()
    en = _report(env).json()["summary"]
    assert "Messages received: 15" in en["text"]
    assert "Median first response time: 6.5 min" in en["text"]
    assert [s["title"] for s in en["sections"]][:2] == ["Messages", "Approvals"]
    assert en["sections"][0]["lines"][0] == "Messages received: 15"


def test_a_workspace_with_no_records_has_the_empty_text(
    report_env: ReportEnv, make_client: Callable[[], TestClient]
) -> None:
    session = report_env.env.session
    _, users = workspace_with_members(session, name="Boş", slug="bos", timezone="Europe/Istanbul")
    session.commit()
    client = make_client()
    headers = login(client, users["owner"])
    workspace = session.scalar(select(Workspace).where(Workspace.slug == "bos"))
    assert workspace is not None
    response = client.get(
        f"/api/v1/workspaces/{workspace.id}/reports/daily", params={"date": D}, headers=headers
    )
    body = response.json()
    summary = body["summary"]
    assert summary["empty"] is True and summary["sections"] == []
    assert summary["text"] == "Bu gün için kayıtlı bir hareket yok."
    values = {m["key"]: m["value"] for m in body["metrics"]}
    assert values["inbound_messages"] == 0 and values["median_first_response_minutes"] is None
    assert body["has_simulated_data"] is False  # nothing simulated contributed (INV-09)
