"""Meta deauthorization and data-deletion callback routers (ADR-025 §3.4, P8-05 / V-06).

Exposes:
- POST /api/v1/webhooks/meta/deauthorize
- POST /api/v1/webhooks/meta/data-deletion
- GET /api/v1/webhooks/meta/data-deletion/{confirmation_code}
As well as public proxy routes under /webhooks/meta/... without /api/v1 prefix.
"""

import contextlib
from typing import Any

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_clock
from app.core.clock import Clock
from app.core.config import Settings
from app.core.db import get_db
from app.operations.meta_callbacks import (
    InvalidSignatureError,
    InvalidSignedRequestError,
    get_data_deletion_status,
    handle_data_deletion_request,
    handle_deauthorization,
)

router = APIRouter(tags=["meta-callbacks"])


class SignedRequestBody(BaseModel):
    signed_request: str | None = None


async def _extract_signed_request(request: Request, signed_request_form: str | None = None) -> str:
    """Extracts signed_request from Form, JSON, or Query string."""
    if signed_request_form:
        return signed_request_form.strip()

    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        with contextlib.suppress(Exception):
            body = await request.json()
            if isinstance(body, dict) and "signed_request" in body:
                return str(body["signed_request"]).strip()
    elif "application/x-www-form-urlencoded" in content_type:
        with contextlib.suppress(Exception):
            form = await request.form()
            sr = form.get("signed_request")
            if sr:
                return str(sr).strip()

    # Fallback: check query parameter
    sr_query = request.query_params.get("signed_request")
    if sr_query:
        return sr_query.strip()

    raise HTTPException(status_code=400, detail="Missing signed_request parameter")


def _render_status_html(status_data: dict[str, Any]) -> str:
    """Renders a privacy-safe, bilingual HTML status page for end users."""
    code = status_data["confirmation_code"]
    status = status_data["status"]
    req_at = status_data.get("requested_at") or "-"
    comp_at = status_data.get("completed_at") or "-"

    status_color = "#16a34a" if status == "completed" else "#ca8a04"
    status_label_en = status.replace("_", " ").title()
    status_label_tr = (
        "Tamamlandı"
        if status == "completed"
        else "İşleniyor"
        if status in ("in_progress", "pending")
        else "Bulunamadı veya Zaten Silindi"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Data Deletion Status - AgentNest</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f8fafc;
      color: #0f172a;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      padding: 1rem;
    }}
    .card {{
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
      max-width: 540px;
      width: 100%;
      padding: 2rem;
    }}
    .title {{
      font-size: 1.5rem;
      font-weight: 700;
      margin-top: 0;
      margin-bottom: 0.5rem;
      color: #1e293b;
    }}
    .badge {{
      display: inline-block;
      padding: 0.25rem 0.75rem;
      border-radius: 9999px;
      font-size: 0.875rem;
      font-weight: 600;
      color: #ffffff;
      background-color: {status_color};
      margin-bottom: 1.5rem;
    }}
    .field {{
      margin-bottom: 1rem;
    }}
    .label {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #64748b;
      margin-bottom: 0.25rem;
    }}
    .value {{
      font-size: 0.95rem;
      font-weight: 500;
      color: #334155;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      word-break: break-all;
    }}
    .divider {{
      border-top: 1px solid #e2e8f0;
      margin: 1.5rem 0;
    }}
    .notice {{
      font-size: 0.875rem;
      color: #64748b;
      line-height: 1.5;
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1 class="title">Data Deletion Status / Veri Silme Durumu</h1>
    <div class="badge">{status_label_en} / {status_label_tr}</div>

    <div class="field">
      <div class="label">Confirmation Code / Onay Kodu</div>
      <div class="value">{code}</div>
    </div>

    <div class="field">
      <div class="label">Requested At / Talep Tarihi</div>
      <div class="value">{req_at}</div>
    </div>

    <div class="field">
      <div class="label">Completed At / Tamamlanma Tarihi</div>
      <div class="value">{comp_at}</div>
    </div>

    <div class="divider"></div>

    <div class="notice">
      <p><strong>EN:</strong> Your data deletion request has been processed securely
      in compliance with platform terms. No personal identifiers are retained.</p>
      <p><strong>TR:</strong> Veri silme talebiniz platform kuralları ve gizlilik ilkeleri
      doğrultusunda güvenle işlenmiştir. Hiçbir kişisel veri saklanmamaktadır.</p>
    </div>
  </div>
</body>
</html>
"""


@router.post("/api/v1/webhooks/meta/deauthorize")
@router.post("/webhooks/meta/deauthorize")
async def meta_deauthorize(
    request: Request,
    signed_request: str | None = Form(default=None),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, str]:
    """Meta Deauthorization Callback endpoint (ADR-025 §3.4)."""
    raw_sr = await _extract_signed_request(request, signed_request)
    try:
        return handle_deauthorization(db, clock, settings, raw_sr)
    except InvalidSignatureError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except InvalidSignedRequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v1/webhooks/meta/data-deletion")
@router.post("/webhooks/meta/data-deletion")
async def meta_data_deletion(
    request: Request,
    signed_request: str | None = Form(default=None),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, str]:
    """Meta Data Deletion Callback endpoint (ADR-025 §3.4).

    Returns {"url": "<status_url>", "confirmation_code": "<code>"}.
    """
    raw_sr = await _extract_signed_request(request, signed_request)
    try:
        return handle_data_deletion_request(db, clock, settings, raw_sr)
    except InvalidSignatureError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except InvalidSignedRequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/v1/webhooks/meta/data-deletion/{confirmation_code}")
@router.get("/webhooks/meta/data-deletion/{confirmation_code}")
def meta_data_deletion_status(
    confirmation_code: str,
    accept: str | None = Header(default=None),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> Response:
    """Privacy-safe Meta Data Deletion Status query endpoint (ADR-025 §3.4)."""
    status_data = get_data_deletion_status(db, clock, confirmation_code)
    if not status_data:
        raise HTTPException(
            status_code=404,
            detail="Confirmation code not found or already purged",
        )

    if accept and "text/html" in accept.lower():
        html_content = _render_status_html(status_data)
        return HTMLResponse(content=html_content, status_code=200)

    return JSONResponse(content=status_data, status_code=200)
