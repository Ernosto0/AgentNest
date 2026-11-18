"""Owner/manager call-back list and audited, CSRF-protected CSV export."""

import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_clock, require_membership
from app.audit import service as audit
from app.core.clock import Clock
from app.core.config import get_settings
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.reporting import leads
from app.reporting.leads_csv import render_csv
from app.reporting.schemas import ReportLinkOut

router = APIRouter(prefix="/workspaces/{workspace_id}/leads", tags=["reports"])


class LeadOut(BaseModel):
    conversation_id: uuid.UUID
    customer_handle: str | None
    last_question: str | None
    last_question_at: datetime
    intent: Literal["pricing", "booking"]
    link: ReportLinkOut


class LeadListOut(BaseModel):
    period_from: date
    period_to: date
    timezone: str
    total: int
    limit: int
    offset: int
    items: list[LeadOut]
    has_simulated_data: Literal[False] = False


class LeadExportRequest(BaseModel):
    from_date: date | None = Field(default=None, alias="from")
    to_date: date | None = Field(default=None, alias="to")


@router.get("", response_model=LeadListOut)
def get_leads(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: WorkspaceContext = Depends(require_membership("reports.view")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> LeadListOut:
    page = leads.list_leads(db, clock, ctx, from_date, to_date, limit=limit, offset=offset)
    return LeadListOut(
        period_from=page.period_from,
        period_to=page.period_to,
        timezone=page.timezone,
        total=page.total,
        limit=limit,
        offset=offset,
        items=[
            LeadOut(
                conversation_id=r.conversation_id,
                customer_handle=r.customer_handle,
                last_question=r.last_question,
                last_question_at=r.last_question_at,
                intent=r.intent,
                link=ReportLinkOut(**r.link),
            )
            for r in page.items
        ],
    )


@router.post("/export", response_class=Response, responses={200: {"content": {"text/csv": {}}}})
def export_leads(
    body: LeadExportRequest,
    ctx: WorkspaceContext = Depends(require_membership("reports.view")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> Response:
    page, truncated = leads.all_leads(
        db, clock, ctx, body.from_date, body.to_date, cap=leads.MAX_EXPORT_ROWS
    )
    settings = get_settings()
    content = (
        "\ufeff"
        + render_csv(
            page.items,
            timezone=ctx.timezone,
            link_base=(settings.frontend_origin or settings.app_base_url).rstrip("/"),
        )
    ).encode("utf-8")
    response = Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="leads-{page.period_from}_{page.period_to}.csv"'
            ),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Row-Count": str(len(page.items)),
            "X-Truncated": str(truncated).lower(),
        },
    )
    audit.record(
        db,
        ctx,
        "leads.exported",
        "lead_export",
        None,
        {
            "period_from": page.period_from.isoformat(),
            "period_to": page.period_to.isoformat(),
            "row_count": len(page.items),
            "truncated": truncated,
            "columns": 4,
        },
        clock=clock,
    )
    db.commit()
    return response
