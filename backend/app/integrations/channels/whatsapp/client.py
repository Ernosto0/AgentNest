"""Synchronous Cloud API client. No retries, including ambiguous sends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import SecretStr

from app.core.config import get_settings


class WhatsAppValidationError(ValueError):
    """Invalid local message shape; no request was made."""


class WhatsAppApiError(Exception):
    """Safe structured error; provider bodies and transport messages are never retained."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_code: int | str | None = None,
        error_subcode: int | str | None = None,
        error_type: str | None = None,
        retryable: bool = False,
        *,
        ambiguous: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.error_subcode = error_subcode
        self.error_type = error_type
        self.retryable = retryable
        self.ambiguous = ambiguous


@dataclass(frozen=True)
class WhatsAppSendResult:
    message_id: str
    recipient_wa_id: str | None = None


class WhatsAppClient:
    def __init__(
        self,
        access_token: SecretStr | None = None,
        phone_number_id: str | None = None,
        api_base_url: str | None = None,
        api_version: str | None = None,
        timeout: float = 15.0,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self._token = access_token or settings.whatsapp_access_token or SecretStr("")
        self._phone_number_id = phone_number_id or settings.whatsapp_phone_number_id or ""
        self._base_url = (api_base_url or settings.whatsapp_api_base_url).rstrip("/")
        self._version = api_version or settings.whatsapp_api_version
        self._timeout = timeout
        self._client = client or httpx.Client(transport=transport, timeout=timeout)

    def _send(self, to: str, kind: str, content: dict[str, Any]) -> WhatsAppSendResult:
        token = self._token.get_secret_value().strip()
        if not token or not self._phone_number_id:
            raise WhatsAppApiError("WhatsApp credentials are not configured")
        try:
            response = self._client.post(
                f"{self._base_url}/{self._version}/{self._phone_number_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": to,
                    "type": kind,
                    kind: content,
                },
                timeout=self._timeout,
            )
        except httpx.RequestError:
            raise WhatsAppApiError(
                "WhatsApp transport error", retryable=True, ambiguous=True
            ) from None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not 200 <= response.status_code < 300:
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            if not isinstance(error, dict):
                error = {}

            # Meta can echo credentials in arbitrary error strings. Redact all textual fields.
            def safe(value: Any) -> str | int | None:
                if isinstance(value, str):
                    return value.replace(token, "[redacted]")
                return value if isinstance(value, int) else None

            raise WhatsAppApiError(
                str(safe(error.get("message")) or "WhatsApp API request failed"),
                status_code=response.status_code,
                error_code=safe(error.get("code", response.status_code)),
                error_subcode=safe(error.get("error_subcode")),
                error_type=(
                    error["type"].replace(token, "[redacted]")
                    if isinstance(error.get("type"), str)
                    else None
                ),
                retryable=response.status_code == 429 or 500 <= response.status_code < 600,
            )
        try:
            message_id = payload["messages"][0]["id"]
            if not isinstance(message_id, str) or not message_id:
                raise ValueError
        except (KeyError, IndexError, TypeError, ValueError):
            raise WhatsAppApiError(
                "WhatsApp response missing message id",
                status_code=response.status_code,
                ambiguous=True,
            ) from None
        recipient = None
        contacts = payload.get("contacts")
        if isinstance(contacts, list) and contacts and isinstance(contacts[0], dict):
            value = contacts[0].get("wa_id")
            recipient = value if isinstance(value, str) else None
        return WhatsAppSendResult(message_id, recipient)

    def send_template(
        self,
        to: str,
        name: str,
        language_code: str,
        body_parameters: list[str] | None = None,
        parameter_names: list[str] | None = None,
    ) -> WhatsAppSendResult:
        parameters = body_parameters or []
        if parameter_names is not None and len(parameter_names) != len(parameters):
            raise WhatsAppValidationError("Parameter names must match body parameters")
        template: dict[str, Any] = {"name": name, "language": {"code": language_code}}
        if parameters:
            values: list[dict[str, str]] = []
            for index, value in enumerate(parameters):
                item = {"type": "text", "text": value}
                if parameter_names is not None:
                    item["parameter_name"] = parameter_names[index]
                values.append(item)
            template["components"] = [{"type": "body", "parameters": values}]
        return self._send(to, "template", template)

    def send_interactive_buttons(
        self,
        to: str,
        body: str,
        buttons: list[tuple[str, str]],
        footer: str | None = None,
    ) -> WhatsAppSendResult:
        if not 1 <= len(buttons) <= 3 or not 1 <= len(body) <= 1024:
            raise WhatsAppValidationError("Invalid button count or body length")
        if footer is not None and len(footer) > 60:
            raise WhatsAppValidationError("Footer exceeds 60 characters")
        ids = [item[0] for item in buttons]
        titles = [item[1] for item in buttons]
        if (
            any(not 1 <= len(item) <= 256 for item in ids)
            or any(not 1 <= len(item) <= 20 for item in titles)
            or len(set(ids)) != len(ids)
            or len(set(titles)) != len(titles)
        ):
            raise WhatsAppValidationError("Invalid or duplicate button id or title")
        interactive: dict[str, Any] = {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": key, "title": title}}
                    for key, title in buttons
                ]
            },
        }
        if footer is not None:
            interactive["footer"] = {"text": footer}
        return self._send(to, "interactive", interactive)

    def send_text(self, to: str, body: str, preview_url: bool = False) -> WhatsAppSendResult:
        if not 1 <= len(body) <= 4096:
            raise WhatsAppValidationError("Text must contain 1 to 4096 characters")
        return self._send(to, "text", {"body": body, "preview_url": preview_url})

    def close(self) -> None:
        self._client.close()
