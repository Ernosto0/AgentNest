"""Telegram webhook HTTP endpoint (ADR-012, Phase 9 Session 04).

Authenticates via X-Telegram-Bot-Api-Secret-Token, rejects duplicates immediately
with 200 {"status": "duplicate"} (INV-06), and dispatches updates to the pipeline.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_clock
from app.core.clock import Clock
from app.core.config import Settings
from app.core.db import get_db
from app.integrations.channels.telegram.client import TelegramClient
from app.integrations.channels.telegram.dispatcher import process_update

router = APIRouter(tags=["webhooks"])


def get_telegram_client(
    settings: Settings = Depends(get_app_settings),
) -> TelegramClient:
    return TelegramClient(token=settings.telegram_bot_token)


@router.post("/webhooks/telegram")
@router.post("/api/v1/webhooks/telegram")
async def telegram_webhook(
    request: Request,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
    client: TelegramClient = Depends(get_telegram_client),
) -> Response:
    """Ingest incoming Telegram Bot API update."""
    expected_secret = (
        settings.telegram_webhook_secret.get_secret_value().strip()
        if settings.telegram_webhook_secret
        else ""
    )
    secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "").strip()

    if (
        not expected_secret
        or not secret_header
        or not hmac.compare_digest(secret_header, expected_secret)
    ):
        return JSONResponse(
            {"status": "unauthorized", "error": "Invalid or missing secret token"},
            status_code=401,
        )

    try:
        raw_json = await request.json()
    except Exception:
        return JSONResponse({"status": "invalid_json"}, status_code=400)

    if not isinstance(raw_json, dict) or "update_id" not in raw_json:
        return JSONResponse({"status": "missing_update_id"}, status_code=400)

    result = process_update(db, clock, raw_json, client=client)
    db.commit()

    if result.status == "duplicate":
        return JSONResponse({"status": "duplicate"}, status_code=200)

    if result.status == "failed":
        return JSONResponse(
            {"status": "error", "error": result.error},
            status_code=500,
        )

    return JSONResponse(
        {"status": "ok", "action": result.action},
        status_code=200,
    )
