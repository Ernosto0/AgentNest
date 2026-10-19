"""Command routes (api-design.md §2.4). Thin: validate, call the service, map to a model.

Commands are private to the member who typed them: someone else's command id is a 404.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_clock, require_membership
from app.approvals import repository as approvals_repo
from app.approvals.views import approval_out
from app.commands import service
from app.commands.models import OwnerCommand
from app.commands.schemas import (
    ClarificationAnswer,
    ClarificationOptionOut,
    ClarificationOut,
    CommandCreate,
    CommandOut,
    CommandResultOut,
)
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.pagination import Page

router = APIRouter(prefix="/workspaces/{workspace_id}/commands", tags=["commands"])


def _out(db: Session, clock: Clock, ctx: WorkspaceContext, command: OwnerCommand) -> CommandOut:
    approval = None
    if command.approval_id is not None:
        found = approvals_repo.get_approval(db, ctx, command.approval_id)
        approval = approval_out(db, clock, ctx, found) if found is not None else None
    clarification = None
    if command.clarification:
        data = command.clarification
        clarification = ClarificationOut(
            question_key=data["question_key"],
            params=data.get("params", {}),
            options=[ClarificationOptionOut(id=o["id"], label=o["label"]) for o in data["options"]],
        )
    return CommandOut(
        id=command.id,
        status=command.status,
        raw_text=command.raw_text,
        command_type=command.command_type,
        result=CommandResultOut(**command.result) if command.result else None,
        clarification=clarification,
        approval=approval,
        error_code=command.error_code,
        created_at=command.created_at,
        expires_at=command.expires_at,
        completed_at=command.completed_at,
    )


@router.post("", response_model=CommandOut, status_code=202)
def submit_command(
    body: CommandCreate,
    ctx: WorkspaceContext = Depends(require_membership("commands.use")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> CommandOut:
    command = service.submit(
        db, clock, ctx, text=body.text, client_request_id=body.client_request_id
    )
    return _out(db, clock, ctx, command)


@router.get("", response_model=Page[CommandOut])
def list_commands(
    limit: int = 20,
    ctx: WorkspaceContext = Depends(require_membership("commands.use")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> Page[CommandOut]:
    commands = service.list_commands(db, clock, ctx, limit=limit)
    return Page(items=[_out(db, clock, ctx, c) for c in commands])


@router.get("/{command_id}", response_model=CommandOut)
def get_command(
    command_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("commands.use")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> CommandOut:
    return _out(db, clock, ctx, service.get_command(db, clock, ctx, command_id))


@router.post("/{command_id}/clarification", response_model=CommandOut, status_code=202)
def answer_clarification(
    command_id: uuid.UUID,
    body: ClarificationAnswer,
    ctx: WorkspaceContext = Depends(require_membership("commands.use")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> CommandOut:
    command = service.answer_clarification(db, clock, ctx, command_id, body.option_id)
    return _out(db, clock, ctx, command)


@router.post("/{command_id}/cancel", response_model=CommandOut)
def cancel_command(
    command_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("commands.use")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> CommandOut:
    return _out(db, clock, ctx, service.cancel(db, clock, ctx, command_id))
