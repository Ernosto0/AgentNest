"""``POST /api/v1/waitlist``: the public landing page's pilot request (no session, no CSRF)."""

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_clock
from app.core.clock import Clock
from app.core.config import Settings
from app.core.db import get_db
from app.identity import throttling
from app.waitlist import service
from app.waitlist.schemas import WaitlistRequest, WaitlistResponse

router = APIRouter(tags=["waitlist"])


@router.post("/waitlist", response_model=WaitlistResponse, status_code=202)
def join_waitlist(
    body: WaitlistRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    clock: Clock = Depends(get_clock),
) -> WaitlistResponse:
    """Store a pilot request once per email and tell the operator. A repeated email answers the
    same way and sends nothing, so the response never reveals whether an email was already known."""
    ip = throttling.extract_client_ip(request, settings)
    new_entry = service.submit(db, clock, body=body, ip_address=ip)
    if new_entry is not None:
        background_tasks.add_task(
            service.notify_operator, settings, new_entry
        )  # after the response
    return WaitlistResponse()
