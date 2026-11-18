"""Pure signed webhook parsing. Optional provider fields never establish authority."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

SIGNATURE_HEADER = "X-Hub-Signature-256"
_log = logging.getLogger(__name__)


def sign(raw_body: bytes, app_secret: str) -> str:
    return "sha256=" + hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()


def verify_signature(raw_body: bytes, header: str | None, app_secret: str) -> bool:
    return bool(
        app_secret
        and header
        and hmac.compare_digest(sign(raw_body, app_secret).encode(), header.encode())
    )


def verify_handshake(
    mode: str | None, token: str | None, challenge: str | None, expected_token: str
) -> str | None:
    if (
        mode == "subscribe"
        and expected_token
        and token
        and hmac.compare_digest(token.encode(), expected_token.encode())
    ):
        return challenge
    return None


class ProviderModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class InboundText(ProviderModel):
    message_id: str
    wa_id: str
    timestamp: str | None = None
    text: str = ""
    phone_number_id: str | None = None


class InboundButtonReply(ProviderModel):
    message_id: str
    wa_id: str
    timestamp: str | None = None
    button_id: str | None = None
    title: str | None = None
    phone_number_id: str | None = None


class InboundStatus(ProviderModel):
    message_id: str
    recipient_id: str | None = None
    status: str | None = None
    pricing: dict[str, Any] | None = None


class InboundOther(ProviderModel):
    message_id: str
    wa_id: str
    type: str | None = None
    timestamp: str | None = None


InboundEvent = InboundText | InboundButtonReply | InboundStatus | InboundOther


class Message(ProviderModel):
    id: str | None = None
    from_: str | None = Field(default=None, alias="from")
    timestamp: str | None = None
    type: str | None = None
    text: dict[str, Any] | None = None
    interactive: dict[str, Any] | None = None


class Status(ProviderModel):
    id: str | None = None
    recipient_id: str | None = None
    status: str | None = None
    pricing: dict[str, Any] | None = None


class Value(ProviderModel):
    metadata: dict[str, Any] | None = None
    messages: list[Message] | None = None
    statuses: list[Status] | None = None


class Change(ProviderModel):
    field: str | None = None
    value: Value | None = None


class Entry(ProviderModel):
    changes: list[Change] | None = None


class Envelope(ProviderModel):
    object: str | None = None
    entry: list[Entry] | None = None


def parse_webhook(
    payload: dict[str, Any], phone_number_id: str | None = None
) -> list[InboundEvent]:
    """Flatten events; the dispatcher always supplies its configured receiving number."""
    try:
        envelope = Envelope.model_validate(payload)
    except ValidationError:
        return []
    if envelope.object != "whatsapp_business_account":
        return []
    events: list[InboundEvent] = []
    dropped = 0
    for entry in envelope.entry or []:
        for change in entry.changes or []:
            if change.field != "messages" or change.value is None:
                continue
            value = change.value
            raw_number = (value.metadata or {}).get("phone_number_id")
            number = raw_number if isinstance(raw_number, str) else None
            if phone_number_id is not None and number != phone_number_id:
                continue
            for message in value.messages or []:
                if not message.from_:
                    dropped += 1
                    continue
                if not message.id:
                    continue
                common = {
                    "message_id": message.id,
                    "wa_id": message.from_,
                    "timestamp": message.timestamp,
                    "phone_number_id": number,
                }
                if message.type == "text":
                    body = (message.text or {}).get("body")
                    if isinstance(body, str):
                        events.append(InboundText(**common, text=body))
                elif message.type == "interactive" and isinstance(
                    (message.interactive or {}).get("button_reply"), dict
                ):
                    reply = (message.interactive or {})["button_reply"]
                    events.append(
                        InboundButtonReply(
                            **common,
                            button_id=reply.get("id") if isinstance(reply.get("id"), str) else None,
                            title=reply.get("title")
                            if isinstance(reply.get("title"), str)
                            else None,
                        )
                    )
                else:
                    events.append(InboundOther(**common, type=message.type))
            for status in value.statuses or []:
                if status.id:
                    events.append(
                        InboundStatus(
                            message_id=status.id,
                            recipient_id=status.recipient_id,
                            status=status.status,
                            pricing=status.pricing,
                        )
                    )
    if dropped:
        _log.info("whatsapp_missing_sender count=%d", dropped)
    return events
