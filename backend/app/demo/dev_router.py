"""Developer tools (api-design.md §2.10): simulate customers and failures, run due jobs.

Mounted only when ``DEMO_TOOLS_ENABLED`` is true, which production refuses (INV-20). The
workspace-scoped routes need the owner's permission to manage the integration.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import current_auth, enforce_csrf, get_app_settings, get_clock, require_membership
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.errors import AppError
from app.core.pagination import Page
from app.demo import simulator
from app.identity import repository as identity_repo
from app.identity.service import AuthenticatedSession
from app.integrations.instagram.models import FAILURE_MODES, FAILURE_OPERATIONS
from app.jobs.models import Job
from app.jobs.testing import run_due_jobs

router = APIRouter(prefix="/api/v1/dev", tags=["dev"], dependencies=[Depends(enforce_csrf)])


class ScriptOut(BaseModel):
    id: str
    label: dict[str, str]
    customer_alias: str
    text: str | None
    attachments: list[dict[str, str]]
    expect: str


class CustomerMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    script_id: str | None = None
    customer_alias: str | None = Field(default=None, min_length=1, max_length=60)
    text: str | None = Field(default=None, max_length=1000)


class SimulationOut(BaseModel):
    received: int
    duplicates: int
    ignored: int


class NativeReplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: uuid.UUID
    text: str = Field(min_length=1, max_length=1000)


class FailureRuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal[*FAILURE_OPERATIONS]  # type: ignore[valid-type]
    mode: Literal[*FAILURE_MODES]  # type: ignore[valid-type]
    remaining: int | None = Field(default=1, ge=1, le=100)  # null: every matching call
    retry_after_s: int | None = Field(default=None, ge=1, le=3600)


class FailureRuleOut(BaseModel):
    id: uuid.UUID
    operation: str
    mode: str
    remaining: int | None
    retry_after_s: int | None


class JobOut(BaseModel):
    id: uuid.UUID
    job_type: str
    status: str
    run_at: str
    attempts: int
    last_error_code: str | None


class RunDueOut(BaseModel):
    ran: int


def _factory(db: Session) -> sessionmaker[Session]:
    """Sessions on the request's connection, so the simulator works in the request's world."""
    return sessionmaker(
        bind=db.get_bind(),
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )


@router.get("/scripts", response_model=list[ScriptOut])
def scripts(_: AuthenticatedSession = Depends(current_auth)) -> list[ScriptOut]:
    return [ScriptOut(**s.model_dump()) for s in simulator.load_scripts()]


@router.post("/workspaces/{workspace_id}/simulate/customer-message", response_model=SimulationOut)
def simulate_customer_message(
    body: CustomerMessageIn,
    ctx: WorkspaceContext = Depends(require_membership("integrations.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> SimulationOut:
    if body.script_id:
        script = simulator.get_script(body.script_id)
        alias, text, attachments = script.customer_alias, script.text, script.attachments
    elif body.customer_alias and (body.text or "").strip():
        alias, text, attachments = body.customer_alias, body.text, []
    else:
        raise AppError(
            "VALIDATION_FAILED",
            errors=[{"field": "script_id", "code": "required", "params": {}}],
        )
    result = simulator.simulate_customer_message(
        _factory(db),
        clock,
        settings,
        ctx.workspace_id,
        customer_alias=alias,
        text=text,
        attachments=attachments,
    )
    return SimulationOut(
        received=result.received, duplicates=result.duplicates, ignored=result.ignored
    )


@router.post("/workspaces/{workspace_id}/simulate/owner-native-reply", response_model=SimulationOut)
def simulate_native_reply(
    body: NativeReplyIn,
    ctx: WorkspaceContext = Depends(require_membership("integrations.manage")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_app_settings),
) -> SimulationOut:
    result = simulator.simulate_owner_native_reply(
        _factory(db),
        clock,
        settings,
        ctx.workspace_id,
        conversation_id=body.conversation_id,
        text=body.text,
    )
    return SimulationOut(
        received=result.received, duplicates=result.duplicates, ignored=result.ignored
    )


@router.get("/workspaces/{workspace_id}/failure-rules", response_model=Page[FailureRuleOut])
def list_failure_rules(
    ctx: WorkspaceContext = Depends(require_membership("integrations.manage")),
    db: Session = Depends(get_db),
) -> Page[FailureRuleOut]:
    return Page(
        items=[
            FailureRuleOut(
                id=r.id,
                operation=r.operation,
                mode=r.mode,
                remaining=r.remaining,
                retry_after_s=r.retry_after_s,
            )
            for r in simulator.list_failure_rules(db, ctx.workspace_id)
        ]
    )


@router.post(
    "/workspaces/{workspace_id}/failure-rules", response_model=FailureRuleOut, status_code=201
)
def add_failure_rule(
    body: FailureRuleIn,
    ctx: WorkspaceContext = Depends(require_membership("integrations.manage")),
    db: Session = Depends(get_db),
) -> FailureRuleOut:
    rule = simulator.set_failure_rule(
        db,
        ctx.workspace_id,
        operation=body.operation,
        mode=body.mode,
        remaining=body.remaining,
        retry_after_s=body.retry_after_s,
    )
    return FailureRuleOut(
        id=rule.id,
        operation=rule.operation,
        mode=rule.mode,
        remaining=rule.remaining,
        retry_after_s=rule.retry_after_s,
    )


@router.delete("/workspaces/{workspace_id}/failure-rules/{rule_id}", status_code=204)
def delete_failure_rule(
    rule_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("integrations.manage")),
    db: Session = Depends(get_db),
) -> Response:
    simulator.delete_failure_rule(db, ctx.workspace_id, rule_id)
    return Response(status_code=204)


@router.post("/jobs/run-due", response_model=RunDueOut)
def run_due(
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
    _: AuthenticatedSession = Depends(current_auth),
) -> RunDueOut:
    """Run what is due now, in this process (when no worker is running)."""
    return RunDueOut(ran=run_due_jobs(clock, session_factory=_factory(db)))


@router.get("/jobs", response_model=Page[JobOut])
def list_jobs(
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    auth: AuthenticatedSession = Depends(current_auth),
) -> Page[JobOut]:
    """The latest jobs of the workspaces the user belongs to (and system jobs)."""
    workspace_ids = [
        workspace.id for _, workspace in identity_repo.list_memberships(db, auth.user.id)
    ]
    stmt = select(Job).where((Job.workspace_id.in_(workspace_ids)) | (Job.workspace_id.is_(None)))
    if status:
        stmt = stmt.where(Job.status == status)
    rows = db.scalars(stmt.order_by(Job.created_at.desc()).limit(50))
    return Page(
        items=[
            JobOut(
                id=j.id,
                job_type=j.job_type,
                status=j.status,
                run_at=j.run_at.isoformat(),
                attempts=j.attempts,
                last_error_code=j.last_error_code,
            )
            for j in rows
        ]
    )
