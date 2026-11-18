"""Pure webhook cryptography and synthetic provider envelope parsing."""

from __future__ import annotations

import pytest

from app.integrations.channels.whatsapp.webhook_format import (
    InboundButtonReply,
    InboundOther,
    InboundStatus,
    InboundText,
    parse_webhook,
    sign,
    verify_handshake,
    verify_signature,
)


def envelope(messages: list[dict], statuses: list[dict] | None = None, number: str = "123") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": number},
                            "messages": messages,
                            "statuses": statuses or [],
                        },
                    }
                ]
            }
        ],
    }


def test_signature() -> None:
    body = b'{"a":1}'
    signature = sign(body, "secret")
    assert signature.startswith("sha256=")
    assert verify_signature(body, signature, "secret")
    for header in [None, "", "bad", signature[7:], "sha256=bad", "\u2603"]:
        assert not verify_signature(body, header, "secret")
    assert not verify_signature(body, signature, "")
    assert not verify_signature(body + b" ", signature, "secret")


@pytest.mark.parametrize(
    ("mode", "token", "expected", "result"),
    [
        ("subscribe", "verify", "verify", "123"),
        ("wrong", "verify", "verify", None),
        ("subscribe", "bad", "verify", None),
        ("subscribe", "", "", None),
    ],
)
def test_handshake(mode: str, token: str, expected: str, result: str | None) -> None:
    assert verify_handshake(mode, token, "123", expected) == result


def test_parser() -> None:
    messages = [
        {
            "id": "text",
            "from": "90",
            "timestamp": "1",
            "type": "text",
            "text": {"body": "LINK ABCD1234"},
        },
        {
            "id": "button",
            "from": "90",
            "type": "interactive",
            "interactive": {"button_reply": {"id": "a", "title": "Yes"}},
        },
        {"id": "other", "from": "90", "type": "image"},
        {"id": "no-sender", "type": "text", "text": {"body": "ignored"}},
    ]
    events = parse_webhook(
        envelope(
            messages,
            [
                {
                    "id": "status",
                    "recipient_id": "90",
                    "status": "delivered",
                    "pricing": {"billable": True},
                }
            ],
        ),
        "123",
    )
    assert len(events) == 4
    assert isinstance(events[0], InboundText) and events[0].text == "LINK ABCD1234"
    assert events[0].timestamp == "1" and events[0].phone_number_id == "123"
    assert isinstance(events[1], InboundButtonReply) and events[1].button_id == "a"
    assert isinstance(events[2], InboundOther)
    assert isinstance(events[3], InboundStatus) and events[3].pricing == {"billable": True}
    assert not parse_webhook(envelope(messages), "wrong")
    assert not parse_webhook({"object": "unknown", "entry": []})
    payload = envelope(messages[:1])
    change = payload["entry"][0]["changes"][0]
    payload["entry"][0]["changes"].append(change)
    payload["entry"].append({"changes": [change, {"field": "other", "value": {}}]})
    assert len(parse_webhook(payload, "123")) == 3
    assert not parse_webhook({})
