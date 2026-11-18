"""Offline Cloud API payload, validation, outcome and credential contracts."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from app.integrations.channels.whatsapp.client import (
    WhatsAppApiError,
    WhatsAppClient,
    WhatsAppValidationError,
)

TOKEN = "synthetic-whatsapp-token"


def make_client(handler: object) -> WhatsAppClient:
    return WhatsAppClient(
        access_token=SecretStr(TOKEN),
        phone_number_id="123",
        api_version="v27.0",
        transport=httpx.MockTransport(handler),
    )


def test_payloads() -> None:
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://graph.facebook.com/v27.0/123/messages"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert request.method == "POST"
        calls.append(json.loads(request.content))
        return httpx.Response(
            200, json={"messages": [{"id": "wamid.1"}], "contacts": [{"wa_id": "90"}]}
        )

    client = make_client(handle)
    result = client.send_template("90", "notice", "tr", ["one", "two"])
    assert (result.message_id, result.recipient_wa_id) == ("wamid.1", "90")
    client.send_template("90", "notice", "en", ["one"], ["name"])
    client.send_template("90", "notice", "en")
    client.send_interactive_buttons("90", "Choose", [("a", "Yes"), ("b", "No")], "Footer")
    client.send_text("90", "Hello")
    common = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": "90"}
    assert calls[0] == {
        **common,
        "type": "template",
        "template": {
            "name": "notice",
            "language": {"code": "tr"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": "one"},
                        {"type": "text", "text": "two"},
                    ],
                }
            ],
        },
    }
    assert calls[1]["template"]["components"][0]["parameters"] == [
        {
            "type": "text",
            "text": "one",
            "parameter_name": "name",
        }
    ]
    assert "components" not in calls[2]["template"]
    assert calls[3] == {
        **common,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "Choose"},
            "footer": {"text": "Footer"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "a", "title": "Yes"}},
                    {"type": "reply", "reply": {"id": "b", "title": "No"}},
                ]
            },
        },
    }
    assert calls[4] == {**common, "type": "text", "text": {"body": "Hello", "preview_url": False}}
    client.close()


@pytest.mark.parametrize(
    ("buttons", "body", "footer"),
    [
        ([], "ok", None),
        ([(str(i), str(i)) for i in range(4)], "ok", None),
        ([("a", "x" * 21)], "ok", None),
        ([("a", "same"), ("b", "same")], "ok", None),
        ([("a", "one"), ("a", "two")], "ok", None),
        ([("x" * 257, "ok")], "ok", None),
        ([("", "ok")], "ok", None),
        ([("a", "")], "ok", None),
        ([("a", "ok")], "x" * 1025, None),
        ([("a", "ok")], "", None),
        ([("a", "ok")], "ok", "x" * 61),
    ],
)
def test_buttons_validate_before_http(
    buttons: list[tuple[str, str]], body: str, footer: str | None
) -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid input made an HTTP request")

    with pytest.raises(WhatsAppValidationError):
        make_client(forbidden).send_interactive_buttons("90", body, buttons, footer)


@pytest.mark.parametrize("body", ["", "x" * 4097])
def test_text_limits(body: str) -> None:
    with pytest.raises(WhatsAppValidationError):
        make_client(lambda _: pytest.fail("HTTP called")).send_text("90", body)


@pytest.mark.parametrize(
    ("status", "retryable"), [(400, False), (401, False), (429, True), (500, True), (503, True)]
)
def test_api_errors(status: int, retryable: bool) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={
                "error": {
                    "message": f"Rejected {TOKEN}",
                    "type": "OAuthException",
                    "code": 987654,
                    "error_subcode": 123,
                    "fbtrace_id": "unused",
                }
            },
        )

    client = make_client(handle)
    with pytest.raises(WhatsAppApiError) as caught:
        client.send_text("90", "Hello")
    exc = caught.value
    assert (exc.status_code, exc.error_code, exc.error_subcode, exc.error_type) == (
        status,
        987654,
        123,
        "OAuthException",
    )
    assert exc.retryable is retryable
    assert not exc.ambiguous
    assert TOKEN not in str(exc) + repr(exc) + repr(client)


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError])
def test_transport_ambiguity(error: type[httpx.RequestError]) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise error(TOKEN, request=request)

    client = make_client(handle)
    with pytest.raises(WhatsAppApiError) as caught:
        client.send_text("90", "Hello")
    assert caught.value.ambiguous and caught.value.retryable
    assert TOKEN not in str(caught.value) + repr(caught.value) + repr(client)


@pytest.mark.parametrize("payload", [{}, {"messages": []}, {"messages": [{"id": ""}]}, None])
def test_missing_id_is_ambiguous(payload: object) -> None:
    client = make_client(lambda _: httpx.Response(200, json=payload))
    with pytest.raises(WhatsAppApiError) as caught:
        client.send_text("90", "Hello")
    assert caught.value.ambiguous and not caught.value.retryable


def test_status_fallback_and_optional_contact() -> None:
    client = make_client(lambda _: httpx.Response(403, text="not json"))
    with pytest.raises(WhatsAppApiError) as caught:
        client.send_text("90", "Hello")
    assert caught.value.error_code == 403
    client = make_client(lambda _: httpx.Response(200, json={"messages": [{"id": "m"}]}))
    assert client.send_text("90", "Hello").recipient_wa_id is None
