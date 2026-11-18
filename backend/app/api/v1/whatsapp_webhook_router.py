"""WhatsApp signed ingress; raw bytes are authenticated before JSON parsing."""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_app_settings, get_clock
from app.core.clock import Clock
from app.core.config import Settings
from app.core.db import get_db
from app.integrations.channels.whatsapp.client import WhatsAppClient
from app.integrations.channels.whatsapp.dispatcher import process_webhook
from app.integrations.channels.whatsapp.webhook_format import (
    SIGNATURE_HEADER,
    verify_handshake,
    verify_signature,
)

router = APIRouter(tags=["webhooks"])


def get_whatsapp_client(settings: Settings = Depends(get_app_settings)) -> Iterator[WhatsAppClient]:
    client = WhatsAppClient(
        access_token=settings.whatsapp_access_token,
        phone_number_id=settings.whatsapp_phone_number_id,
        api_base_url=settings.whatsapp_api_base_url,
        api_version=settings.whatsapp_api_version,
    )
    try:
        yield client
    finally:
        client.close()


@router.get("/webhooks/whatsapp")
@router.get("/api/v1/webhooks/whatsapp")
def whatsapp_handshake(
    request: Request, settings: Settings = Depends(get_app_settings)
) -> Response:
    expected = settings.whatsapp_webhook_verify_token
    challenge = verify_handshake(
        request.query_params.get("hub.mode"),
        request.query_params.get("hub.verify_token"),
        request.query_params.get("hub.challenge"),
        expected.get_secret_value() if expected else "",
    )
    if not settings.whatsapp_configured or challenge is None:
        return PlainTextResponse("Forbidden", status_code=403)
    return PlainTextResponse(challenge)


@router.post("/webhooks/whatsapp")
@router.post("/api/v1/webhooks/whatsapp")
async def whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
    client: WhatsAppClient = Depends(get_whatsapp_client),
) -> Response:
    raw_body = await request.body()
    secret = settings.whatsapp_app_secret
    if not settings.whatsapp_configured or not verify_signature(
        raw_body, request.headers.get(SIGNATURE_HEADER), secret.get_secret_value() if secret else ""
    ):
        return JSONResponse({"status": "unauthorized"}, status_code=401)
    try:
        payload = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError):
        return JSONResponse({"status": "invalid_json"}, status_code=400)
    try:
        # Non-object signed JSON is a valid, ignored provider event.
        await run_in_threadpool(
            process_webhook,
            db,
            clock,
            payload if isinstance(payload, dict) else {},
            client,
            settings,
        )
        if db.in_transaction():
            db.commit()
    except Exception:
        db.rollback()
        return JSONResponse({"status": "error"}, status_code=500)
    return JSONResponse({"status": "ok"})
