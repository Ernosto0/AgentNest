"""Cross-origin access for the landing page, scoped to the waitlist route only.

The app itself is same-origin in production (CORS off). The landing page is a separate static
site, so ``POST /api/v1/waitlist`` must answer it. Every other path is passed through untouched,
and credentials are never allowed: the form needs no cookies.
"""

from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

WAITLIST_PATH = "/api/v1/waitlist"


class WaitlistCORSMiddleware:
    def __init__(self, app: ASGIApp, origins: list[str]) -> None:
        self._app = app
        self._cors = CORSMiddleware(
            app,
            allow_origins=origins,
            allow_methods=["POST"],
            allow_headers=["Content-Type", "Accept"],
            allow_credentials=False,
            max_age=600,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] == WAITLIST_PATH:
            await self._cors(scope, receive, send)
        else:
            await self._app(scope, receive, send)
