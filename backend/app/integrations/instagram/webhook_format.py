"""Meta-format webhook payloads: build, sign, verify and parse (integrations.md §3.3).

The simulator builds payloads in exactly the format Meta sends, signs them with the app
secret and submits the raw bytes to the same ingestion function as a real webhook, so the
pipeline cannot tell them apart except by the provider kind of the receiving account.
The Meta adapter (Phase 7) reuses ``verify`` and ``parse`` unchanged.
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

from app.integrations.instagram.base import NormalizedInboundEvent

SIGNATURE_HEADER = "X-Hub-Signature-256"
SIGNATURE_PREFIX = "sha256="


# --- signing --------------------------------------------------------------------------------


def serialize(payload: dict[str, Any]) -> bytes:
    """The exact bytes that are signed and sent (compact JSON, UTF-8)."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign(raw_body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"{SIGNATURE_PREFIX}{digest}"


def verify(raw_body: bytes, signature_header: str | None, secret: str) -> bool:
    """Constant-time comparison of the HMAC-SHA256 of the **raw** body (before any parsing)."""
    if not signature_header or not secret:
        return False
    return hmac.compare_digest(sign(raw_body, secret), signature_header.strip())


class WebhookCodec:
    """Verify and parse for one app secret: what ingestion needs, with no database access.

    The mock provider and the Meta adapter (Phase 7) both delegate to it.
    """

    def __init__(self, secret: str) -> None:
        self._secret = secret

    def verify_signature(self, raw_body: bytes, signature_header: str | None) -> bool:
        return verify(raw_body, signature_header, self._secret)

    def parse_webhook(self, payload: Any) -> list[NormalizedInboundEvent]:
        return parse(payload)


# --- building -------------------------------------------------------------------------------


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _wrap(account_id: str, moment: datetime, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "object": "instagram",
        "entry": [{"id": account_id, "time": _ms(moment), "messaging": items}],
    }


def message_item(
    account_id: str,
    customer_id: str,
    mid: str,
    text: str | None,
    moment: datetime,
    *,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {"mid": mid}
    if text is not None:
        message["text"] = text
    if attachments:
        message["attachments"] = [
            {"type": a.get("type", "file"), "payload": {"url": a.get("url", "")}}
            for a in attachments
        ]
    return {
        "sender": {"id": customer_id},
        "recipient": {"id": account_id},
        "timestamp": _ms(moment),
        "message": message,
    }


def echo_item(
    account_id: str,
    customer_id: str,
    mid: str,
    text: str | None,
    moment: datetime,
    *,
    app_id: str | None = None,
) -> dict[str, Any]:
    """A message the business sent (from this app or from the native Instagram app)."""
    message: dict[str, Any] = {"mid": mid, "is_echo": True}
    if text is not None:
        message["text"] = text
    if app_id is not None:
        message["app_id"] = app_id
    return {
        "sender": {"id": account_id},
        "recipient": {"id": customer_id},
        "timestamp": _ms(moment),
        "message": message,
    }


def reaction_item(
    account_id: str, customer_id: str, mid: str, moment: datetime, *, emoji: str = "❤"
) -> dict[str, Any]:
    return {
        "sender": {"id": customer_id},
        "recipient": {"id": account_id},
        "timestamp": _ms(moment),
        "reaction": {"mid": mid, "action": "react", "reaction": "love", "emoji": emoji},
    }


def read_item(account_id: str, customer_id: str, mid: str, moment: datetime) -> dict[str, Any]:
    return {
        "sender": {"id": customer_id},
        "recipient": {"id": account_id},
        "timestamp": _ms(moment),
        "read": {"mid": mid},
    }


def build_payload(account_id: str, moment: datetime, *items: dict[str, Any]) -> dict[str, Any]:
    return _wrap(account_id, moment, list(items))


def build_message_payload(
    account_id: str,
    customer_id: str,
    mid: str,
    text: str | None,
    moment: datetime,
    *,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    item = message_item(account_id, customer_id, mid, text, moment, attachments=attachments)
    return _wrap(account_id, moment, [item])


def build_echo_payload(
    account_id: str,
    customer_id: str,
    mid: str,
    text: str | None,
    moment: datetime,
    *,
    app_id: str | None = None,
) -> dict[str, Any]:
    return _wrap(
        account_id, moment, [echo_item(account_id, customer_id, mid, text, moment, app_id=app_id)]
    )


# --- parsing --------------------------------------------------------------------------------


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _id(node: Any) -> str | None:
    if isinstance(node, dict):
        value = node.get("id")
        if isinstance(value, str | int) and not isinstance(value, bool) and str(value):
            return str(value)
    return None


def _attachments(message: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    raw = message.get("attachments")
    if not isinstance(raw, list):
        return result
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        payload = entry.get("payload")
        url = payload.get("url") if isinstance(payload, dict) else None
        kind = entry.get("type")
        result.append(
            {
                "type": kind if isinstance(kind, str) else "file",
                "url": url if isinstance(url, str) else None,
                "note": None,
            }
        )
    return result


def _normalize(item: dict[str, Any], entry_id: str | None) -> NormalizedInboundEvent:
    sender = _id(item.get("sender"))
    recipient = _id(item.get("recipient"))
    when = _timestamp(item.get("timestamp"))
    message = item.get("message")
    if isinstance(message, dict):
        mid = message.get("mid") if isinstance(message.get("mid"), str) else None
        text = message.get("text") if isinstance(message.get("text"), str) else None
        if message.get("is_echo") is True:
            app_id = message.get("app_id")
            return NormalizedInboundEvent(
                event_type="echo",
                account_id=sender or entry_id,
                customer_id=recipient,
                provider_timestamp=when,
                mid=mid,
                text=text,
                attachments=_attachments(message),
                is_echo=True,
                app_id=str(app_id) if app_id is not None else None,
                raw_item=item,
            )
        return NormalizedInboundEvent(
            event_type="message",
            account_id=recipient or entry_id,
            customer_id=sender,
            provider_timestamp=when,
            mid=mid,
            text=text,
            attachments=_attachments(message),
            raw_item=item,
        )
    for field_name in ("reaction", "read", "postback"):
        node = item.get(field_name)
        if isinstance(node, dict):
            mid = node.get("mid") if isinstance(node.get("mid"), str) else None
            return NormalizedInboundEvent(
                event_type=field_name,
                account_id=recipient or entry_id,
                customer_id=sender,
                provider_timestamp=when,
                mid=mid,
                raw_item=item,
            )
    return NormalizedInboundEvent(
        event_type="other",
        account_id=recipient or entry_id,
        customer_id=sender,
        provider_timestamp=when,
        raw_item=item,
    )


def parse(payload: Any) -> list[NormalizedInboundEvent]:
    """One normalised event per ``entry[].messaging[]`` item. Unknown shapes become ``other``
    (stored and ignored); a payload that is not an Instagram event yields no events."""
    if not isinstance(payload, dict) or payload.get("object") != "instagram":
        return []
    events: list[NormalizedInboundEvent] = []
    entries = payload.get("entry")
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        entry_id = _id(entry)
        items = entry.get("messaging")
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                events.append(_normalize(item, entry_id))
    return events
