"""Telegram Bot API HTTP client wrapper (ADR-012, Phase 9 Session 04).

Supports synchronous and asynchronous execution, test transport injection,
and structured error mapping without automatic 4xx retry.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

import httpx
from pydantic import SecretStr

from app.core.config import get_settings


class TelegramApiError(Exception):
    """Structured error raised when Telegram Bot API requests fail."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_code: int | None = None,
        description: str | None = None,
        raw_response: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.description = description
        self.raw_response = raw_response


def _clean_token(token: str | SecretStr | None) -> str:
    if isinstance(token, SecretStr):
        return token.get_secret_value().strip()
    if isinstance(token, str):
        return token.strip()
    with contextlib.suppress(Exception):
        settings = get_settings()
        if settings.telegram_bot_token:
            return settings.telegram_bot_token.get_secret_value().strip()
    return ""


class TelegramClient:
    """Synchronous Telegram Bot API client using httpx.Client."""

    def __init__(
        self,
        token: str | SecretStr | None = None,
        base_url: str = "https://api.telegram.org",
        timeout: float = 15.0,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._raw_token = _clean_token(token)
        self._client = client or httpx.Client(
            transport=transport,
            timeout=timeout,
        )

    def _get_token(self) -> str:
        if not self._raw_token:
            self._raw_token = _clean_token(None)
        if not self._raw_token:
            raise TelegramApiError("Telegram bot token is not configured")
        return self._raw_token

    def _api_url(self, method: str) -> str:
        return f"{self.base_url}/bot{self._get_token()}/{method}"

    def _file_url(self, file_path: str) -> str:
        return f"{self.base_url}/file/bot{self._get_token()}/{file_path.lstrip('/')}"

    def _request(
        self,
        method: str,
        api_method: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: Any | None = None,
        timeout: float | None = None,
    ) -> Any:
        url = self._api_url(api_method)
        req_timeout = timeout if timeout is not None else self.timeout

        try:
            resp = self._client.request(
                method,
                url,
                params=params,
                json=json_data,
                data=data,
                files=files,
                timeout=req_timeout,
            )
        except httpx.RequestError as exc:
            raise TelegramApiError(f"Telegram transport error: {exc}") from exc

        try:
            body = resp.json()
        except json.JSONDecodeError:
            body = None

        if resp.status_code >= 400:
            desc = body.get("description") if isinstance(body, dict) else resp.text
            err_code = body.get("error_code") if isinstance(body, dict) else resp.status_code
            raise TelegramApiError(
                f"Telegram API error {err_code}: {desc}",
                status_code=resp.status_code,
                error_code=err_code,
                description=desc,
                raw_response=body if isinstance(body, dict) else None,
            )

        if not isinstance(body, dict) or not body.get("ok"):
            desc = body.get("description") if isinstance(body, dict) else "Unknown API error"
            err_code = body.get("error_code") if isinstance(body, dict) else None
            raise TelegramApiError(
                f"Telegram API returned not ok: {desc}",
                status_code=resp.status_code,
                error_code=err_code,
                description=desc,
                raw_response=body if isinstance(body, dict) else None,
            )

        return body.get("result")

    def send_message(
        self,
        chat_id: int | str,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        disable_web_page_preview: bool | None = None,
    ) -> dict[str, Any]:
        """Send text message."""
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        if disable_web_page_preview is not None:
            payload["disable_web_page_preview"] = disable_web_page_preview
        result: dict[str, Any] = self._request("POST", "sendMessage", json_data=payload)
        return result

    def send_photo(
        self,
        chat_id: int | str,
        photo: str | bytes | tuple[str, bytes],
        *,
        caption: str | None = None,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send photo by file_id, URL, or raw bytes."""
        data_payload: dict[str, Any] = {"chat_id": str(chat_id)}
        if caption:
            data_payload["caption"] = caption
        if parse_mode:
            data_payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            data_payload["reply_markup"] = json.dumps(reply_markup)

        if isinstance(photo, str):
            data_payload["photo"] = photo
            result: dict[str, Any] = self._request("POST", "sendPhoto", data=data_payload)
            return result
        elif isinstance(photo, bytes):
            files: Any = {"photo": ("photo.jpg", photo, "image/jpeg")}
            result = self._request("POST", "sendPhoto", data=data_payload, files=files)
            return result
        else:
            files_tuple: Any = {"photo": photo}
            result = self._request("POST", "sendPhoto", data=data_payload, files=files_tuple)
            return result

    def answer_callback_query(
        self,
        callback_query_id: str,
        *,
        text: str | None = None,
        show_alert: bool = False,
    ) -> bool | dict[str, Any]:
        """Acknowledge or answer an incoming callback query."""
        payload: dict[str, Any] = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert,
        }
        if text:
            payload["text"] = text
        result: bool | dict[str, Any] = self._request(
            "POST", "answerCallbackQuery", json_data=payload
        )
        return result

    def edit_message_text(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Edit text of a previously sent message."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result: dict[str, Any] = self._request("POST", "editMessageText", json_data=payload)
        return result

    def edit_message_reply_markup(
        self,
        chat_id: int | str,
        message_id: int,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Edit only the reply markup of a message."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result: dict[str, Any] = self._request("POST", "editMessageReplyMarkup", json_data=payload)
        return result

    def get_file(self, file_id: str) -> dict[str, Any]:
        """Retrieve basic file info including file_path for download."""
        result: dict[str, Any] = self._request("POST", "getFile", json_data={"file_id": file_id})
        return result

    def download_file(self, file_path: str) -> bytes:
        """Download raw binary content of a file."""
        url = self._file_url(file_path)
        try:
            resp = self._client.get(url, timeout=self.timeout)
        except httpx.RequestError as exc:
            raise TelegramApiError(f"Telegram file download error: {exc}") from exc

        if resp.status_code >= 400:
            raise TelegramApiError(
                f"Telegram file download failed: {resp.status_code}",
                status_code=resp.status_code,
            )
        return resp.content

    def get_updates(
        self,
        *,
        offset: int | None = None,
        limit: int | None = 100,
        timeout: int | None = 30,
        allowed_updates: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch incoming updates via long-polling."""
        payload: dict[str, Any] = {}
        if offset is not None:
            payload["offset"] = offset
        if limit is not None:
            payload["limit"] = limit
        if timeout is not None:
            payload["timeout"] = timeout
        if allowed_updates is not None:
            payload["allowed_updates"] = allowed_updates

        # HTTP request timeout must exceed Telegram's server-side poll timeout
        http_timeout = (timeout or 0) + 5.0
        result: list[dict[str, Any]] = self._request(
            "POST", "getUpdates", json_data=payload, timeout=http_timeout
        )
        return result

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()


class AsyncTelegramClient:
    """Asynchronous Telegram Bot API client using httpx.AsyncClient."""

    def __init__(
        self,
        token: str | SecretStr | None = None,
        base_url: str = "https://api.telegram.org",
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._raw_token = _clean_token(token)
        self._client = client or httpx.AsyncClient(
            transport=transport,
            timeout=timeout,
        )

    def _get_token(self) -> str:
        if not self._raw_token:
            self._raw_token = _clean_token(None)
        if not self._raw_token:
            raise TelegramApiError("Telegram bot token is not configured")
        return self._raw_token

    def _api_url(self, method: str) -> str:
        return f"{self.base_url}/bot{self._get_token()}/{method}"

    def _file_url(self, file_path: str) -> str:
        return f"{self.base_url}/file/bot{self._get_token()}/{file_path.lstrip('/')}"

    async def _request(
        self,
        method: str,
        api_method: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: Any | None = None,
        timeout: float | None = None,
    ) -> Any:
        url = self._api_url(api_method)
        req_timeout = timeout if timeout is not None else self.timeout

        try:
            resp = await self._client.request(
                method,
                url,
                params=params,
                json=json_data,
                data=data,
                files=files,
                timeout=req_timeout,
            )
        except httpx.RequestError as exc:
            raise TelegramApiError(f"Telegram transport error: {exc}") from exc

        try:
            body = resp.json()
        except json.JSONDecodeError:
            body = None

        if resp.status_code >= 400:
            desc = body.get("description") if isinstance(body, dict) else resp.text
            err_code = body.get("error_code") if isinstance(body, dict) else resp.status_code
            raise TelegramApiError(
                f"Telegram API error {err_code}: {desc}",
                status_code=resp.status_code,
                error_code=err_code,
                description=desc,
                raw_response=body if isinstance(body, dict) else None,
            )

        if not isinstance(body, dict) or not body.get("ok"):
            desc = body.get("description") if isinstance(body, dict) else "Unknown API error"
            err_code = body.get("error_code") if isinstance(body, dict) else None
            raise TelegramApiError(
                f"Telegram API returned not ok: {desc}",
                status_code=resp.status_code,
                error_code=err_code,
                description=desc,
                raw_response=body if isinstance(body, dict) else None,
            )

        return body.get("result")

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        disable_web_page_preview: bool | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        if disable_web_page_preview is not None:
            payload["disable_web_page_preview"] = disable_web_page_preview
        result: dict[str, Any] = await self._request("POST", "sendMessage", json_data=payload)
        return result

    async def send_photo(
        self,
        chat_id: int | str,
        photo: str | bytes | tuple[str, bytes],
        *,
        caption: str | None = None,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data_payload: dict[str, Any] = {"chat_id": str(chat_id)}
        if caption:
            data_payload["caption"] = caption
        if parse_mode:
            data_payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            data_payload["reply_markup"] = json.dumps(reply_markup)

        if isinstance(photo, str):
            data_payload["photo"] = photo
            result: dict[str, Any] = await self._request("POST", "sendPhoto", data=data_payload)
            return result
        elif isinstance(photo, bytes):
            files: Any = {"photo": ("photo.jpg", photo, "image/jpeg")}
            result = await self._request("POST", "sendPhoto", data=data_payload, files=files)
            return result
        else:
            files_tuple: Any = {"photo": photo}
            result = await self._request("POST", "sendPhoto", data=data_payload, files=files_tuple)
            return result

    async def answer_callback_query(
        self,
        callback_query_id: str,
        *,
        text: str | None = None,
        show_alert: bool = False,
    ) -> bool | dict[str, Any]:
        payload: dict[str, Any] = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert,
        }
        if text:
            payload["text"] = text
        result: bool | dict[str, Any] = await self._request(
            "POST", "answerCallbackQuery", json_data=payload
        )
        return result

    async def edit_message_text(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result: dict[str, Any] = await self._request("POST", "editMessageText", json_data=payload)
        return result

    async def edit_message_reply_markup(
        self,
        chat_id: int | str,
        message_id: int,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result: dict[str, Any] = await self._request(
            "POST", "editMessageReplyMarkup", json_data=payload
        )
        return result

    async def get_file(self, file_id: str) -> dict[str, Any]:
        result: dict[str, Any] = await self._request(
            "POST", "getFile", json_data={"file_id": file_id}
        )
        return result

    async def download_file(self, file_path: str) -> bytes:
        url = self._file_url(file_path)
        try:
            resp = await self._client.get(url, timeout=self.timeout)
        except httpx.RequestError as exc:
            raise TelegramApiError(f"Telegram file download error: {exc}") from exc

        if resp.status_code >= 400:
            raise TelegramApiError(
                f"Telegram file download failed: {resp.status_code}",
                status_code=resp.status_code,
            )
        return resp.content

    async def get_updates(
        self,
        *,
        offset: int | None = None,
        limit: int | None = 100,
        timeout: int | None = 30,
        allowed_updates: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {}
        if offset is not None:
            payload["offset"] = offset
        if limit is not None:
            payload["limit"] = limit
        if timeout is not None:
            payload["timeout"] = timeout
        if allowed_updates is not None:
            payload["allowed_updates"] = allowed_updates

        http_timeout = (timeout or 0) + 5.0
        result: list[dict[str, Any]] = await self._request(
            "POST", "getUpdates", json_data=payload, timeout=http_timeout
        )
        return result

    async def close(self) -> None:
        await self._client.aclose()
