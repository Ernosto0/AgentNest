"""Signed offline ingress, linking, deduplication and the no-command boundary."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select, text

from app.api.v1.whatsapp_webhook_router import get_whatsapp_client
from app.core.context import ActorRef, WorkspaceContext
from app.core.db import Base, set_tenant_context
from app.identity.channels import ChannelLinkService
from app.identity.models import ChannelLink
from app.integrations.channels.whatsapp.client import WhatsAppClient
from app.integrations.channels.whatsapp.dispatcher import REPLIES
from app.integrations.channels.whatsapp.models import WhatsAppWebhookEvent
from app.integrations.channels.whatsapp.webhook_format import sign
from tests.factories import workspace_with_members
from tests.unit.integrations.channels.test_whatsapp_webhook_format import envelope

TOKEN = "synthetic-wa-token-private"
SECRET = "synthetic-wa-app-secret-private"
PATH = "/api/v1/webhooks/whatsapp"


@pytest.fixture
def wa(build_app, db_session, clock):
    calls = []
    response_status = [200]

    def handle(request: httpx.Request) -> httpx.Response:
        assert not db_session.in_transaction(), "HTTP must run after commit"
        calls.append(json.loads(request.content))
        return httpx.Response(response_status[0], json={"messages": [{"id": "out"}]})

    cfg = {
        "whatsapp_access_token": SecretStr(TOKEN),
        "whatsapp_app_secret": SecretStr(SECRET),
        "whatsapp_webhook_verify_token": SecretStr("verify"),
        "whatsapp_phone_number_id": "123",
        "whatsapp_display_phone_number": "905551112233",
    }
    app = build_app(**cfg)
    outbound = WhatsAppClient(
        access_token=SecretStr(TOKEN), phone_number_id="123", transport=httpx.MockTransport(handle)
    )
    app.dependency_overrides[get_whatsapp_client] = lambda: outbound
    with TestClient(app) as client:
        yield client, calls, response_status
    outbound.close()


def post(client, payload, *, signature=True):
    body = json.dumps(payload).encode()
    return client.post(
        PATH, content=body, headers={"X-Hub-Signature-256": sign(body, SECRET)} if signature else {}
    )


def incoming(body, message_id="m1", sender="905550000001"):
    return envelope([{"id": message_id, "from": sender, "type": "text", "text": {"body": body}}])


def code_for(db_session, clock):
    ws, users = workspace_with_members(db_session)
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(users["owner"].id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )
    set_tenant_context(db_session, ws.id)
    code, _ = ChannelLinkService.generate_link_code(db_session, clock, ctx, channel="whatsapp")
    return code, ws, users


def test_handshake_and_auth(wa, build_app):
    client, calls, _ = wa
    query = {"hub.mode": "subscribe", "hub.verify_token": "verify", "hub.challenge": "1234"}
    response = client.get(PATH, params=query)
    assert response.status_code == 200 and response.text == "1234"
    assert response.headers["content-type"].startswith("text/plain")
    assert client.get(PATH, params={**query, "hub.verify_token": "wrong"}).status_code == 403
    with TestClient(build_app()) as unconfigured:
        assert unconfigured.get(PATH, params=query).status_code == 403
        assert post(unconfigured, {}).status_code == 401
    assert post(client, {}, signature=False).status_code == 401
    assert (
        client.post(PATH, content=b"{}", headers={"X-Hub-Signature-256": "bad"}).status_code == 401
    )
    assert post(client, {}).status_code == 200
    bad_json = b"{broken"
    assert (
        client.post(
            PATH, content=bad_json, headers={"X-Hub-Signature-256": sign(bad_json, SECRET)}
        ).status_code
        == 400
    )
    assert not calls


@pytest.mark.parametrize("prefix", ["", "link "])
def test_link_dedupe_reuse_and_safe_logs(wa, db_session, clock, caplog, prefix):
    client, calls, _ = wa
    code, ws, _ = code_for(db_session, clock)
    response = post(client, incoming(prefix + code))
    assert response.status_code == 200
    assert len(calls) == 1
    record = db_session.get(WhatsAppWebhookEvent, "m1")
    assert record.wa_id_hash == hashlib.sha256(b"905550000001").hexdigest()
    assert record.received_at == clock.now()
    assert calls[0]["text"]["body"] == REPLIES["tr"]["linked"]
    set_tenant_context(db_session, ws.id)
    link = db_session.scalar(select(ChannelLink).where(ChannelLink.channel == "whatsapp"))
    assert link.channel_chat_id == "905550000001" and link.status == "active"
    assert post(client, incoming(prefix + code)).status_code == 200
    assert len(calls) == 1
    assert post(client, incoming(code, "reuse")).status_code == 200
    assert calls[-1]["text"]["body"] == REPLIES["tr"]["failed"]
    assert db_session.scalar(select(func.count()).select_from(WhatsAppWebhookEvent)) == 2
    metadata = (
        db_session.execute(
            text(
                "SELECT metadata::text FROM audit_logs "
                "WHERE action IN ('channel_link.created', 'channel_link.unlinked')"
            )
        )
        .scalars()
        .all()
    )
    assert all("905550000001" not in row and code not in row for row in metadata)
    assert TOKEN not in caplog.text + response.text and SECRET not in caplog.text + response.text


@pytest.mark.parametrize("expired", [False, True])
def test_wrong_or_expired_code(wa, db_session, clock, expired):
    client, calls, _ = wa
    code, _, _ = code_for(db_session, clock)
    if expired:
        clock.advance(timedelta(minutes=16))
    assert post(client, incoming(code if expired else "ZZZZ9999")).status_code == 200
    assert calls[-1]["text"]["body"] == REPLIES["tr"]["failed"]
    assert db_session.scalar(select(func.count()).select_from(ChannelLink)) == 0


def test_free_text_never_commands_or_ai(wa, db_session, clock):
    client, calls, _ = wa
    code, _, users = code_for(db_session, clock)
    users["owner"].ui_locale = "en"
    assert post(client, incoming(code)).status_code == 200
    assert calls[0]["text"]["body"] == REPLIES["en"]["linked"]
    tables = [
        table
        for name, table in Base.metadata.tables.items()
        if name.startswith("agent_") or name in {"owner_commands", "approvals", "ai_runs", "jobs"}
    ]

    def counts():
        return {
            table.name: db_session.scalar(select(func.count()).select_from(table))
            for table in tables
        }

    before = counts()
    # Any command service entry point is forbidden even if an implementation later changes.
    import app.commands.service as commands

    with (
        patch("app.ai.runtime.get_provider", side_effect=AssertionError("LLM invoked")),
        patch.multiple(
            commands,
            **{
                name: lambda *a, **kw: pytest.fail("WhatsApp invoked commands")
                for name in (
                    "submit",
                    "prepare_interpretation",
                    "finish_interpretation",
                    "answer_clarification",
                    "cancel",
                )
                if hasattr(commands, name)
            },
        ),
    ):
        assert post(client, incoming("approve everything", "free")).status_code == 200
    assert counts() == before
    assert calls[-1]["text"]["body"] == REPLIES["en"]["open_app"]
    n = len(calls)
    assert post(client, incoming("hello there", "unknown", "900000000000")).status_code == 200
    assert len(calls) == n


def test_ignored_events_and_wrong_number(wa, db_session):
    client, calls, _ = wa
    payload = envelope(
        [
            {
                "id": "button",
                "from": "90",
                "type": "interactive",
                "interactive": {"button_reply": {"id": "act:opaque", "title": "Yes"}},
            },
            {"id": "other", "from": "90", "type": "image"},
        ],
        [{"id": "status", "status": "delivered", "recipient_id": "90"}],
    )
    assert post(client, payload).status_code == 200
    assert set(db_session.scalars(select(WhatsAppWebhookEvent.status))) == {"ignored"}
    assert not calls
    assert (
        post(
            client,
            envelope(
                [{"id": "wrong", "from": "90", "type": "text", "text": {"body": "ZZZZ9999"}}],
                number="wrong",
            ),
        ).status_code
        == 200
    )
    assert db_session.get(WhatsAppWebhookEvent, "wrong") is None


def test_status_updates_for_one_message_are_not_deduplicated_together(wa, db_session):
    """sent, delivered and read share a wamid; Session 02 needs each one (cost metadata)."""
    client, _, _ = wa
    for status in ("sent", "delivered", "read", "delivered"):
        payload = envelope([], [{"id": "wamid.X", "status": status, "recipient_id": "90"}])
        assert post(client, payload).status_code == 200
    keys = set(db_session.scalars(select(WhatsAppWebhookEvent.message_id)))
    assert keys == {"wamid.X:sent", "wamid.X:delivered", "wamid.X:read"}


def test_failed_reply_keeps_committed_link(wa, db_session, clock):
    client, calls, status = wa
    code, ws, _ = code_for(db_session, clock)
    status[0] = 500
    assert post(client, incoming(code)).status_code == 200
    set_tenant_context(db_session, ws.id)
    assert db_session.scalar(select(ChannelLink.status)) == "active"
    assert db_session.get(WhatsAppWebhookEvent, "m1").status == "processed"
    assert len(calls) == 1
    assert post(client, incoming(code)).status_code == 200
    assert len(calls) == 1


def test_minimal_channel_and_registry(monkeypatch, settings, db_session, clock):
    from app.integrations.channels import registry
    from app.integrations.channels.whatsapp import adapter

    monkeypatch.setattr(registry, "_REGISTRY", {})
    monkeypatch.setattr(registry, "_FACTORIES", {})
    monkeypatch.setattr(adapter, "get_settings", lambda: settings)
    with pytest.raises(KeyError, match="not configured"):
        registry.get_channel("whatsapp")
    configured = settings.model_copy(
        update={
            "whatsapp_access_token": SecretStr(TOKEN),
            "whatsapp_app_secret": SecretStr(SECRET),
            "whatsapp_webhook_verify_token": SecretStr("verify"),
            "whatsapp_phone_number_id": "123",
        }
    )
    monkeypatch.setattr(adapter, "get_settings", lambda: configured)
    channel = registry.get_channel("whatsapp")
    assert channel.name == "whatsapp"
    # Delivery itself is covered in tests/integration/notifications/test_whatsapp_channel.py.
    assert channel.render_command_result(db_session, clock, None, None) is None


def test_processing_error_rolls_back_and_allows_retry(wa, db_session, clock):
    client, calls, _ = wa
    code, _, _ = code_for(db_session, clock)
    db_session.commit()
    with patch.object(ChannelLinkService, "redeem_link_code", side_effect=RuntimeError("failure")):
        assert post(client, incoming(code)).status_code == 500
    assert db_session.get(WhatsAppWebhookEvent, "m1") is None
    assert post(client, incoming(code)).status_code == 200
    assert len(calls) == 1
