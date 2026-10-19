"""CommandService: the owner's natural-language commands (workflows.md §B, state-machines.md §3).

The flow: ``submit`` stores the command and enqueues ``interpret_command`` (202). The job runs
the LLM task with **no transaction open**, then ``finish_interpretation`` resolves the proposal
deterministically and either answers (read-only), asks (clarification), refuses
(``unsupported``) or asks the owner to confirm exactly what will change (an approval bound to a
payload hash). A confirmation is decided only through the approvals API; its callback
(``on_approval_decided``, same transaction as the decision) executes as the human who decided.

Nothing here can approve, publish or send, and nothing the model says reaches an executor
without passing ``resolver.resolve`` and a permission check of the human (INV-04).
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.schemas import (
    MAX_CATALOG_FACTS,
    MAX_COMMAND_CHARS,
    FactCatalogEntry,
    InterpretCommandInput,
    InterpretCommandOutput,
)
from app.approvals import service as approvals
from app.approvals.models import Approval
from app.audit import service as audit
from app.commands import repository as repo
from app.commands import resolver
from app.commands.models import OwnerCommand
from app.commands.payloads import InterpretCommandPayload
from app.commands.registry import REGISTRY, CommandSpec, describe_registry
from app.commands.resolver import FactSnapshot
from app.commands.results import CommandResult, ExecContext
from app.commands.transitions import apply_command_event
from app.core.canonical import payload_hash
from app.core.clock import Clock
from app.core.context import ActorRef, WorkspaceContext
from app.core.errors import AppError
from app.identity import repository as identity_repo
from app.identity import service as identity_service
from app.identity.models import User, Workspace
from app.identity.permissions import has_permission
from app.jobs import queue
from app.knowledge import impact
from app.knowledge import repository as knowledge_repo
from app.knowledge.formatting import format_value
from app.knowledge.models import BusinessFact
from app.knowledge.templates import load_template

CONFIRMATION_TTL = timedelta(minutes=30)
CLARIFICATION_TTL = timedelta(minutes=30)
SUBJECT_VERSION = 1  # a command is never edited: its confirmation binds version 1
MAX_REQUEST_ID_CHARS = 100


def _validation(field: str, code: str, **params: Any) -> AppError:
    return AppError("VALIDATION_FAILED", errors=[{"field": field, "code": code, "params": params}])


def _user_id(ctx: WorkspaceContext) -> uuid.UUID:
    if ctx.actor.type != "user" or not ctx.actor.id:
        raise AppError("FORBIDDEN", permission="commands.use")
    return uuid.UUID(ctx.actor.id)


# --- submit ---------------------------------------------------------------------------------


def submit(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    text: str,
    client_request_id: str,
    channel: str = "web",
) -> OwnerCommand:
    """Store the command and enqueue its interpretation. Commits. Idempotent per
    ``(user, client_request_id)``: a resubmission returns the existing command."""
    if not has_permission(ctx.role, "commands.use"):
        raise AppError("FORBIDDEN", permission="commands.use")
    user_id = _user_id(ctx)
    cleaned = text.strip()
    if not cleaned:
        raise _validation("text", "required")
    if len(cleaned) > MAX_COMMAND_CHARS:
        raise _validation("text", "too_long", max=MAX_COMMAND_CHARS)
    request_id = client_request_id.strip()
    if not request_id or len(request_id) > MAX_REQUEST_ID_CHARS:
        raise _validation("client_request_id", "invalid")

    existing = repo.get_by_client_request_id(session, user_id, request_id)
    if existing is not None:
        return _reuse(existing, ctx)

    command = OwnerCommand(
        workspace_id=ctx.workspace_id,
        user_id=user_id,
        channel=channel,
        client_request_id=request_id,
        raw_text=cleaned,
        status=apply_command_event(None, "submit"),
        correlation_id=uuid.uuid4(),
        created_at=clock.now(),
    )
    try:
        with session.begin_nested():
            session.add(command)
    except IntegrityError:  # a concurrent identical request won the race
        existing = repo.get_by_client_request_id(session, user_id, request_id)
        if existing is None:
            raise
        return _reuse(existing, ctx)
    audit.record(
        session,
        ctx,
        "command.received",
        "owner_command",
        command.id,
        {"channel": channel},
        correlation_id=command.correlation_id,
        clock=clock,
    )
    queue.enqueue(
        session,
        "interpret_command",
        InterpretCommandPayload(command_id=command.id),
        workspace_id=ctx.workspace_id,
        correlation_id=command.correlation_id,
        dedup_key=f"interpret_command:{command.id}",
        clock=clock,
    )
    session.commit()
    return command


def _reuse(existing: OwnerCommand, ctx: WorkspaceContext) -> OwnerCommand:
    if existing.workspace_id != ctx.workspace_id:
        raise AppError("CONFLICT_STATE", reason="client_request_id_reused")
    return existing


# --- reads ----------------------------------------------------------------------------------


def _expire_waiting(session: Session, clock: Clock, ctx: WorkspaceContext) -> None:
    """Lazy expiry: confirmations through their approvals (callback), clarifications here."""
    approvals.expire_due_in_workspace(session, clock, ctx)
    user_id = _user_id(ctx)
    changed = False
    for command in repo.list_commands(session, ctx, user_id, limit=100):
        if (
            command.status == "needs_clarification"
            and command.expires_at is not None
            and command.expires_at <= clock.now()
        ):
            _expire_clarification(session, clock, ctx, command)
            changed = True
    if changed:
        session.commit()


def _expire_clarification(
    session: Session, clock: Clock, ctx: WorkspaceContext | None, command: OwnerCommand
) -> None:
    command.status = apply_command_event(command.status, "expire")
    command.completed_at = clock.now()
    audit.record(
        session,
        ctx,
        "command.expired",
        "owner_command",
        command.id,
        {"was": "needs_clarification"},
        correlation_id=command.correlation_id,
        clock=clock,
        workspace_id=command.workspace_id,
    )


def get_command(
    session: Session, clock: Clock, ctx: WorkspaceContext, command_id: uuid.UUID
) -> OwnerCommand:
    """The requester's own command (anyone else's is a 404), after lazy expiry."""
    user_id = _user_id(ctx)
    _expire_waiting(session, clock, ctx)
    command = repo.get_command(session, ctx, command_id, user_id=user_id)
    if command is None:
        raise AppError("NOT_FOUND")
    session.refresh(command)  # the callbacks above may have changed it
    return command


def list_commands(
    session: Session, clock: Clock, ctx: WorkspaceContext, *, limit: int = 20
) -> list[OwnerCommand]:
    user_id = _user_id(ctx)
    _expire_waiting(session, clock, ctx)
    return list(repo.list_commands(session, ctx, user_id, limit=limit))


# --- interpretation (called by the job) ----------------------------------------------------


@dataclass(frozen=True)
class Interpretation:
    """Everything the job needs to run the LLM task, gathered in one short transaction."""

    ctx: WorkspaceContext
    task_input: InterpretCommandInput
    correlation_id: uuid.UUID
    user_locale: str


def _requester_context(
    session: Session, command: OwnerCommand
) -> tuple[WorkspaceContext, Workspace, User] | None:
    user = session.get(User, command.user_id)
    found = identity_repo.get_membership(session, command.workspace_id, command.user_id)
    if user is None or found is None or not user.is_active:
        return None
    member, workspace = found
    ctx = identity_service.workspace_context(workspace, ActorRef.user(user.id), member.role)
    return ctx, workspace, user


def _snapshots(session: Session, ctx: WorkspaceContext, workspace: Workspace) -> list[FactSnapshot]:
    template = load_template(workspace.business_category)
    result = []
    for fact in knowledge_repo.list_facts(session, ctx):
        if fact.status == "archived":
            continue
        item = template.find(fact.key)
        result.append(
            FactSnapshot(
                id=fact.id,
                key=fact.key,
                label=dict(fact.label),
                category=fact.category,
                value_type=fact.value_type,
                value=dict(fact.value),
                status=fact.status,
                version=fact.current_version,
                allowed_values=item.allowed_values if item is not None else (),
            )
        )
    return result


def _catalog(
    facts: list[BusinessFact] | list[FactSnapshot], locale: str, workspace_locale: str
) -> list[FactCatalogEntry]:
    entries = [
        FactCatalogEntry(
            key=f.key,
            label=f.label.get(locale) or f.label.get("tr") or f.key,
            category=f.category,
            value_type=f.value_type,
            status=f.status,
            current_value_display=format_value(f.value_type, f.value, locale, workspace_locale),
        )
        for f in facts
    ]
    return sorted(entries, key=lambda e: e.key)[:MAX_CATALOG_FACTS]


def prepare_interpretation(
    session: Session, clock: Clock, workspace_id: uuid.UUID, command_id: uuid.UUID
) -> Interpretation | None:
    """Context for the LLM call, or ``None`` when there is nothing to do (the command is gone
    or no longer interpreting). A requester who lost access fails the command."""
    command = session.get(OwnerCommand, command_id)
    if command is None or command.workspace_id != workspace_id:
        return None
    if command.status != "interpreting":
        return None  # cancelled, already resolved, or a retried job after success
    found = _requester_context(session, command)
    if found is None:
        _fail(session, clock, None, command, "FORBIDDEN")
        session.commit()
        return None
    ctx, workspace, user = found
    locale = identity_service_locale(user)
    snapshots = _snapshots(session, ctx, workspace)
    task_input = InterpretCommandInput(
        text=command.raw_text,
        user_locale=locale,
        workspace_locale=workspace.default_locale,
        timezone=workspace.timezone,
        now_local=clock.now()
        .astimezone(ZoneInfo(workspace.timezone))
        .isoformat(timespec="seconds"),
        currency=workspace.currency,
        fact_catalog=_catalog(snapshots, locale, workspace.default_locale),
        registry=describe_registry(),
    )
    return Interpretation(ctx, task_input, command.correlation_id, locale)


def identity_service_locale(user: User) -> str:
    return user.ui_locale if user.ui_locale in ("tr", "en") else "tr"


def finish_interpretation(
    session: Session,
    clock: Clock,
    workspace_id: uuid.UUID,
    command_id: uuid.UUID,
    *,
    output: InterpretCommandOutput | None,
    error_code: str | None,
    agent_run_id: uuid.UUID | None,
) -> None:
    """Apply the task outcome to the command. Commits.

    The command is re-read under a lock: if it was cancelled while the model was running, the
    result is discarded (agent-runtime.md §2).
    """
    command = session.get(OwnerCommand, command_id, with_for_update=True)
    if command is None or command.workspace_id != workspace_id or command.status != "interpreting":
        session.rollback()
        return
    found = _requester_context(session, command)
    if found is None:
        _fail(session, clock, None, command, "FORBIDDEN")
        session.commit()
        return
    ctx, workspace, user = found
    command.agent_run_id = agent_run_id
    if output is None:
        _fail(session, clock, ctx, command, error_code or "LLM_UNAVAILABLE")
        session.commit()
        return
    interpretation = output.interpretation
    outcome = resolver.resolve(
        interpretation,
        _snapshots(session, ctx, workspace),
        user_locale=identity_service_locale(user),
        workspace_locale=workspace.default_locale,
        currency=workspace.currency,
    )
    command.interpreted = interpretation.model_dump(mode="json")
    command.command_type = interpretation.type
    _apply_outcome(session, clock, ctx, command, outcome, identity_service_locale(user))
    session.commit()


def fail_after_dead_job(
    session: Session,
    clock: Clock,
    workspace_id: uuid.UUID,
    command_id: uuid.UUID,
    error_code: str,
) -> None:
    """The interpretation job ran out of attempts: tell the owner instead of leaving the command
    on "interpreting" forever. Commits."""
    command = session.get(OwnerCommand, command_id, with_for_update=True)
    if command is None or command.workspace_id != workspace_id or command.status != "interpreting":
        session.rollback()
        return
    _fail(
        session,
        clock,
        None,
        command,
        "LLM_UNAVAILABLE" if error_code == "LLM_UNAVAILABLE" else "INTERNAL_ERROR",
    )
    session.commit()


# --- outcomes -------------------------------------------------------------------------------


def _fail(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext | None,
    command: OwnerCommand,
    error_code: str,
    result: CommandResult | None = None,
) -> None:
    command.status = apply_command_event(command.status, "fail")
    command.error_code = error_code
    command.result = (
        result or CommandResult("command.failed", {"error_code": error_code})
    ).to_json()
    command.completed_at = clock.now()
    audit.record(
        session,
        ctx,
        "command.failed",
        "owner_command",
        command.id,
        {"error_code": error_code, "command_type": command.command_type},
        correlation_id=command.correlation_id,
        clock=clock,
        workspace_id=command.workspace_id,
    )


def _complete(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    command: OwnerCommand,
    result: CommandResult,
) -> None:
    command.status = apply_command_event(command.status, "complete")
    command.result = result.to_json()
    command.completed_at = clock.now()
    audit.record(
        session,
        ctx,
        "command.executed",
        "owner_command",
        command.id,
        {"command_type": command.command_type, "message_key": result.message_key},
        correlation_id=command.correlation_id,
        clock=clock,
    )


def _audit_interpreted(
    session: Session, clock: Clock, ctx: WorkspaceContext, command: OwnerCommand, outcome: str
) -> None:
    audit.record(
        session,
        ctx,
        "command.interpreted",
        "owner_command",
        command.id,
        {"command_type": command.command_type, "outcome": outcome},
        correlation_id=command.correlation_id,
        clock=clock,
    )


def _check_permission(spec: CommandSpec, ctx: WorkspaceContext) -> bool:
    return has_permission(ctx.role, spec.required_permission)


def _apply_outcome(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    command: OwnerCommand,
    outcome: resolver.Outcome,
    user_locale: str,
) -> None:
    exec_ctx = ExecContext(session, clock, ctx, command, user_locale)

    if isinstance(outcome, resolver.UnsupportedOutcome):
        command.status = apply_command_event(command.status, "unsupported")
        command.command_type = "unsupported"
        command.resolution = {"reason": outcome.reason}
        result = REGISTRY["unsupported"].executor(exec_ctx, command.resolution)
        command.result = result.to_json()
        command.completed_at = clock.now()
        _audit_interpreted(session, clock, ctx, command, "unsupported")
    elif isinstance(outcome, resolver.NeedsClarification):
        command.status = apply_command_event(command.status, "clarify")
        command.clarification = {
            "kind": outcome.kind,
            "question_key": outcome.question_key,
            "params": outcome.params,
            "options": [{"id": o.id, "label": o.label, "value": o.value} for o in outcome.options],
            "pending": outcome.pending,
        }
        command.expires_at = clock.now() + CLARIFICATION_TTL
        _audit_interpreted(session, clock, ctx, command, "needs_clarification")
    elif isinstance(outcome, resolver.Rejected):
        _audit_interpreted(session, clock, ctx, command, "rejected")
        _fail(session, clock, ctx, command, outcome.error_code, outcome.result)
    elif isinstance(outcome, resolver.Completed):
        _audit_interpreted(session, clock, ctx, command, "completed")
        _complete(session, clock, ctx, command, outcome.result)
    elif isinstance(outcome, resolver.Execute):
        spec = REGISTRY[outcome.command_type]
        command.command_type = outcome.command_type
        command.resolution = outcome.resolution
        _audit_interpreted(session, clock, ctx, command, "execute")
        if not _check_permission(spec, ctx):
            _fail(
                session,
                clock,
                ctx,
                command,
                "FORBIDDEN",
                CommandResult(
                    "command.forbidden",
                    {"permission": spec.required_permission},
                    error_code="FORBIDDEN",
                ),
            )
            return
        try:
            result = spec.executor(exec_ctx, outcome.resolution)
        except AppError as exc:
            _fail(session, clock, ctx, command, exc.code)
            return
        if result.error_code:
            _fail(session, clock, ctx, command, result.error_code, result)
        else:
            _complete(session, clock, ctx, command, result)
    elif isinstance(outcome, resolver.Confirm):
        _request_confirmation(session, clock, ctx, command, outcome)


def _request_confirmation(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    command: OwnerCommand,
    outcome: resolver.Confirm,
) -> None:
    spec = REGISTRY[outcome.command_type]
    command.command_type = outcome.command_type
    if not _check_permission(spec, ctx):
        _fail(
            session,
            clock,
            ctx,
            command,
            "FORBIDDEN",
            CommandResult(
                "command.forbidden",
                {"permission": spec.required_permission},
                error_code="FORBIDDEN",
            ),
        )
        return
    if spec.confirmation_summary_builder is None or spec.approval_action is None:
        raise RuntimeError(f"mutating command {spec.type!r} needs a summary builder and an action")
    summary = spec.confirmation_summary_builder(
        outcome.summary, impact.analyze_impact(session, ctx, outcome.fact_id)
    )
    expires_at = clock.now() + CONFIRMATION_TTL
    approval = approvals.request(
        session,
        clock,
        ctx,
        kind="confirmation",
        action=spec.approval_action,
        subject_type="owner_command",
        subject_id=command.id,
        subject_version=SUBJECT_VERSION,
        payload=outcome.payload,
        summary=summary,
        # Whoever holds this may decide it; the requester may too (ADR-014). Execution then
        # follows the *decider's* role: owners and managers write, staff only propose.
        required_permission="knowledge.verify",
        expires_at=expires_at,
    )
    command.status = apply_command_event(command.status, "ask_confirmation")
    command.resolution = outcome.payload
    command.approval_id = approval.id
    command.expires_at = expires_at
    _audit_interpreted(session, clock, ctx, command, "awaiting_confirmation")


# --- clarification and cancel ---------------------------------------------------------------


def answer_clarification(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    command_id: uuid.UUID,
    option_id: str,
) -> OwnerCommand:
    """The owner picked one of the offered options. Commits.

    Resolution continues deterministically from the stored question (no new model call), so a
    client can only choose something the system actually asked about.
    """
    user_id = _user_id(ctx)
    _expire_waiting(session, clock, ctx)
    command = repo.get_command(session, ctx, command_id, user_id=user_id, lock=True)
    if command is None:
        raise AppError("NOT_FOUND")
    session.refresh(command)
    command.status = apply_command_event(command.status, "answer")  # CONFLICT_STATE otherwise
    found = _requester_context(session, command)
    if found is None:
        raise AppError("FORBIDDEN", permission="commands.use")
    requester_ctx, workspace, user = found
    locale = identity_service_locale(user)
    outcome = resolver.resolve_choice(
        command.clarification or {},
        option_id,
        _snapshots(session, requester_ctx, workspace),
        user_locale=locale,
        workspace_locale=workspace.default_locale,
        currency=workspace.currency,
    )
    if outcome is None:
        session.rollback()
        raise _validation("option_id", "invalid")
    command.clarification = None
    command.expires_at = None
    _apply_outcome(session, clock, requester_ctx, command, outcome, locale)
    session.commit()
    return command


def cancel(
    session: Session, clock: Clock, ctx: WorkspaceContext, command_id: uuid.UUID
) -> OwnerCommand:
    """Withdraw a command that is waiting for an answer or a confirmation. Commits."""
    user_id = _user_id(ctx)
    _expire_waiting(session, clock, ctx)
    command = repo.get_command(session, ctx, command_id, user_id=user_id, lock=True)
    if command is None:
        raise AppError("NOT_FOUND")
    session.refresh(command)
    was = command.status
    command.status = apply_command_event(command.status, "cancel")  # CONFLICT_STATE otherwise
    command.completed_at = clock.now()
    if was == "awaiting_confirmation":
        approvals.cancel_for_subject(session, clock, ctx, "owner_command", command.id, "WITHDRAWN")
    audit.record(
        session,
        ctx,
        "command.cancelled",
        "owner_command",
        command.id,
        {"was": was},
        correlation_id=command.correlation_id,
        clock=clock,
    )
    session.commit()
    return command


def expire_clarifications(session: Session, clock: Clock, *, limit: int = 100) -> int:
    """Expiry job: clarifications nobody answered within 30 minutes (any workspace). Commits."""
    due = repo.due_clarifications(session, clock.now(), limit=limit)
    for command in due:
        _expire_clarification(session, clock, None, command)
    session.commit()
    return len(due)


# --- the approval subject -------------------------------------------------------------------


def subject_version(session: Session, ctx: WorkspaceContext, command_id: uuid.UUID) -> int | None:
    """The version a confirmation must still match: ``None`` once the command moved on."""
    command = repo.get_command(session, ctx, command_id)
    if command is None or command.status != "awaiting_confirmation":
        return None
    return SUBJECT_VERSION


def subject_status(session: Session, ctx: WorkspaceContext, command_id: uuid.UUID) -> str | None:
    command = repo.get_command(session, ctx, command_id)
    return command.status if command else None


def on_approval_decided(
    session: Session, clock: Clock, ctx: WorkspaceContext, approval: Approval
) -> None:
    """Decided-callback (same transaction as the decision, workflows.md §D).

    Approved: re-check the binding and run the executor as the human who decided. Rejected:
    the command is cancelled. Expired: the command expires. A stale fact does *not* raise: the
    command fails with ``FACT_CHANGED_MEANWHILE`` and the decision stands. Anything unexpected
    raises, which rolls the whole decision back.
    """
    command = repo.get_command(session, ctx, approval.subject_id, lock=True)
    if command is None or command.status != "awaiting_confirmation":
        return
    if approval.status == "rejected":
        command.status = apply_command_event(command.status, "cancel")
        command.completed_at = clock.now()
        audit.record(
            session, ctx, "command.cancelled", "owner_command", command.id,
            {"was": "awaiting_confirmation", "reason": "rejected"},
            correlation_id=command.correlation_id, clock=clock,
        )  # fmt: skip
        return
    if approval.status == "expired":
        command.status = apply_command_event(command.status, "expire")
        command.completed_at = clock.now()
        audit.record(
            session, ctx, "command.expired", "owner_command", command.id,
            {"was": "awaiting_confirmation"},
            correlation_id=command.correlation_id, clock=clock,
        )  # fmt: skip
        return
    if approval.status != "approved":
        return

    # Execution re-checks the binding: the payload stored with the command is exactly what the
    # approved hash covers, and the approval is still executable (INV-04, INV-16).
    if command.resolution is None or payload_hash(command.resolution) != approval.payload_hash:
        raise AppError("APPROVAL_STALE")
    approvals.assert_executable(session, clock, ctx, approval.id, SUBJECT_VERSION)
    spec = REGISTRY.get(command.command_type or "")
    if spec is None or not spec.mutating or not _check_permission(spec, ctx):
        raise AppError("FORBIDDEN", permission=spec.required_permission if spec else "commands.use")

    command.status = apply_command_event(command.status, "approved")
    decider = session.get(User, uuid.UUID(ctx.actor.id)) if ctx.actor.id else None
    locale = identity_service_locale(decider) if decider is not None else "tr"
    result = spec.executor(ExecContext(session, clock, ctx, command, locale), command.resolution)
    if result.error_code:
        _fail(session, clock, ctx, command, result.error_code, result)
    else:
        _complete(session, clock, ctx, command, result)
