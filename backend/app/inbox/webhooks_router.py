"""Instagram webhook routes (api-design.md §2.9). Outside ``/api/v1``: no session, no CSRF;
authenticated by the signature of the raw body instead.

The path selects the provider kind. Only enabled kinds are mounted, so a deployment without
the mock provider has no mock endpoint at all.
"""

import hmac
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_clock
from app.core.clock import Clock
from app.core.config import Settings
from app.core.db import get_db
from app.inbox.ingest import ingest_webhook


def _post_handler(kind: str) -> Callable[..., Awaitable[Response]]:
    async def receive(
        request: Request,
        db: Session = Depends(get_db),
        clock: Clock = Depends(get_clock),
        settings: Settings = Depends(get_app_settings),
    ) -> Response:
        raw_body = await request.body()
        result = await run_in_threadpool(
            ingest_webhook, db, clock, settings, kind, raw_body, dict(request.headers)
        )
        if result.status == "invalid_signature":
            return JSONResponse({"status": "invalid_signature"}, status_code=401)
        return JSONResponse({"status": "ok"})

    return receive


def create_webhooks_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/webhooks/instagram", tags=["webhooks"])
    kinds = settings.instagram_providers

    if "meta" in kinds:

        @router.get("")
        def handshake(
            mode: str | None = Query(default=None, alias="hub.mode"),
            verify_token: str | None = Query(default=None, alias="hub.verify_token"),
            challenge: str | None = Query(default=None, alias="hub.challenge"),
            app_settings: Settings = Depends(get_app_settings),
        ) -> Response:
            expected = app_settings.meta_webhook_verify_token.get_secret_value()
            if (
                mode == "subscribe"
                and challenge is not None
                and verify_token is not None
                and expected
                and hmac.compare_digest(verify_token, expected)
            ):
                return PlainTextResponse(challenge)
            return PlainTextResponse("forbidden", status_code=403)

        router.add_api_route("", _post_handler("meta"), methods=["POST"])
    if "mock" in kinds:
        router.add_api_route("/mock", _post_handler("mock"), methods=["POST"])
    return router
