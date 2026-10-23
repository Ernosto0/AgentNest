"""OAuth callback outside /api/v1; session and single-use state authenticate this GET."""

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import current_auth, get_app_settings, get_clock
from app.core.clock import Clock
from app.core.config import Settings
from app.core.db import get_db, get_session_factory
from app.identity.service import AuthenticatedSession
from app.operations import oauth_service

router = APIRouter(tags=["integrations"])


@router.get("/oauth/instagram/callback", status_code=303, response_class=RedirectResponse)
def callback(
    response: Response,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> RedirectResponse:
    user_id = auth.user.id
    db.commit()  # request authentication itself opened a transaction; finish it BEFORE HTTP.
    result = oauth_service.complete_callback(
        get_session_factory(), clock, settings, user_id, code=code, state=state, error=error
    )
    query = (
        {"oauth": "error", "code": result.error_code}
        if result.error_code
        else {"oauth": "connected"}
    )
    redirect = RedirectResponse(
        f"{settings.frontend_origin}/w/{result.workspace_id}/more/settings/connections?{urlencode(query)}",
        status_code=303,
    )
    for name, value in response.raw_headers:
        if name.lower() == b"set-cookie":
            redirect.raw_headers.append((name, value))
    return redirect
