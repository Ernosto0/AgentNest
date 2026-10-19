"""Paste-and-extract (workflows.md §A step 3, agent-runtime.md §6).

``start`` stores the pasted text **only** in the run's redacted input snapshot (never in a job
payload) and enqueues the job. The job asks the model for ``(key, value, verbatim excerpt)``
triples and then does the deterministic part: every item is re-checked against the text (the
excerpt must really be in it, the value must really be in the excerpt, the value is re-parsed)
and survivors become ``pasted_text`` **candidates**, never facts (INV-02, INV-03).
"""

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.injection import detect_injection
from app.ai.models import AgentRun
from app.ai.runner import create_queued_run, run_task
from app.ai.runtime import get_provider, runner_deps
from app.ai.schemas import (
    MAX_EXTRACT_CHARS,
    MAX_EXTRACT_ITEMS,
    CatalogKey,
    ExtractedItem,
    ExtractFactsInput,
    ExtractFactsOutput,
)
from app.ai.tasks.extract_fact_candidates import EXTRACT_FACT_CANDIDATES
from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import ActorRef, WorkspaceContext
from app.core.errors import AppError
from app.identity import repository as identity_repo
from app.identity import service as identity_service
from app.identity.models import User, Workspace
from app.identity.permissions import has_permission
from app.jobs import queue
from app.jobs.registry import JobContext, job_handler
from app.knowledge import candidates
from app.knowledge import repository as repo
from app.knowledge.models import FactCandidate
from app.knowledge.parsing import ParseAmbiguity, ParseError, parse_money, parse_phone
from app.knowledge.templates import TemplateItem, load_template
from app.knowledge.values import validate_value

_WS = re.compile(r"\s+")
MAX_REQUEST_ID_CHARS = 100


class ExtractFactCandidatesPayload(BaseModel):
    run_id: uuid.UUID


def _norm(text: str) -> str:
    """Whitespace-normalised text, for the verbatim checks (case and letters are kept)."""
    return _WS.sub(" ", text).strip()


def _validation(field: str, code: str, **params: Any) -> AppError:
    return AppError("VALIDATION_FAILED", errors=[{"field": field, "code": code, "params": params}])


# --- request --------------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractionStatus:
    run_id: uuid.UUID
    status: str
    candidates_created: int
    error_code: str | None
    injection_suspected: bool


def start(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    text: str,
    client_request_id: str,
) -> AgentRun:
    """Create the queued run (holding the text) and enqueue the job. Commits. Idempotent per
    ``(user, client_request_id)``."""
    if not has_permission(ctx.role, "knowledge.edit"):
        raise AppError("FORBIDDEN", permission="knowledge.edit")
    if ctx.actor.type != "user" or not ctx.actor.id:
        raise AppError("FORBIDDEN", permission="knowledge.edit")
    cleaned = text.strip()
    if not cleaned:
        raise _validation("text", "required")
    if len(cleaned) > MAX_EXTRACT_CHARS:
        raise _validation("text", "too_long", max=MAX_EXTRACT_CHARS)
    request_id = client_request_id.strip()
    if not request_id or len(request_id) > MAX_REQUEST_ID_CHARS:
        raise _validation("client_request_id", "invalid")

    existing = session.scalar(
        select(AgentRun).where(
            AgentRun.workspace_id == ctx.workspace_id,
            AgentRun.task == "extract_fact_candidates",
            AgentRun.input_snapshot["client_request_id"].astext == request_id,
            AgentRun.input_snapshot["user_id"].astext == ctx.actor.id,
        )
    )
    if existing is not None:
        return existing

    correlation_id = uuid.uuid4()
    flags = detect_injection(cleaned)
    run = create_queued_run(
        session,
        clock,
        get_provider(),
        ctx,
        "extract_fact_candidates",
        {
            "text": cleaned,
            "user_id": ctx.actor.id,
            "client_request_id": request_id,
            "injection_flags": flags,
        },
        correlation_id,
    )
    audit.record(
        session,
        ctx,
        "knowledge.extraction_requested",
        "agent_run",
        run.id,
        {"chars": len(cleaned), "injection_suspected": bool(flags)},
        correlation_id=correlation_id,
        clock=clock,
    )
    queue.enqueue(
        session,
        "extract_fact_candidates",
        ExtractFactCandidatesPayload(run_id=run.id),
        workspace_id=ctx.workspace_id,
        correlation_id=correlation_id,
        dedup_key=f"extract_fact_candidates:{run.id}",
        clock=clock,
    )
    session.commit()
    return run


def status_of(session: Session, ctx: WorkspaceContext, run_id: uuid.UUID) -> ExtractionStatus:
    run = session.scalar(
        select(AgentRun).where(
            AgentRun.workspace_id == ctx.workspace_id,
            AgentRun.id == run_id,
            AgentRun.task == "extract_fact_candidates",
        )
    )
    if run is None:
        raise AppError("NOT_FOUND")
    created = int(
        session.scalar(
            select(func.count())
            .select_from(FactCandidate)
            .where(
                FactCandidate.workspace_id == ctx.workspace_id,
                FactCandidate.agent_run_id == run.id,
                FactCandidate.relation != "same",  # an equal value is nothing to decide
            )
        )
        or 0
    )
    snapshot = run.input_snapshot or {}
    status = run.status
    # The runner marks the run succeeded when the model's output is valid; the candidates are
    # stored a moment later. Until then the run is not finished for the user (or the UI would
    # stop polling and report "nothing found"). Old runs have no snapshot left: finished.
    if status == "succeeded" and run.input_snapshot is not None and "stored_at" not in snapshot:
        status = "running"
    return ExtractionStatus(
        run_id=run.id,
        status=status,
        candidates_created=created,
        error_code=run.error_code,
        injection_suspected=bool(snapshot.get("injection_flags")),
    )


# --- the deterministic part -----------------------------------------------------------------


class FactLike(Protocol):
    @property
    def value_type(self) -> str: ...
    @property
    def value(self) -> dict[str, Any]: ...


def _parse_value(
    item: TemplateItem, fact: FactLike | None, raw: str, locale: str, currency: str
) -> dict[str, Any] | None:
    """Re-parse the value from the text the owner pasted. ``None`` drops the item: anything
    ambiguous or unsupported is left for the owner to enter by hand, never guessed."""
    text = raw.strip()
    language = locale if locale in ("tr", "en") else "tr"
    try:
        match item.value_type:
            case "money":
                parsed = parse_money(text, language, currency)
                if isinstance(parsed, ParseAmbiguity):
                    return None
                base = dict(fact.value) if fact is not None and fact.value_type == "money" else {}
                return validate_value(
                    "money",
                    {**base, "amount": f"{parsed.amount:.2f}", "currency": parsed.currency},
                    default_currency=currency,
                )
            case "phone":
                return validate_value("phone", {"e164": parse_phone(text)})
            case "email":
                return validate_value("email", {"email": text.lower()})
            case "url":
                return validate_value("url", {"url": text})
            case "text":
                return validate_value("text", {"text": text})
    except (ParseError, AppError):
        return None
    return None  # hours, addresses, lists, localized texts: entered by hand


def accept_items(
    items: list[ExtractedItem],
    pasted_text: str,
    catalog: dict[str, TemplateItem],
) -> list[tuple[ExtractedItem, TemplateItem]]:
    """Keep the items whose key is in the catalog, whose excerpt is a verbatim (whitespace-
    normalised) substring of the pasted text, whose value is inside the excerpt, and whose
    excerpt (and the line it sits in) is not an instruction. Everything else is dropped
    silently."""
    haystack = _norm(pasted_text)
    lines = [_norm(line) for line in pasted_text.splitlines()]
    kept: list[tuple[ExtractedItem, TemplateItem]] = []
    for item in items[:MAX_EXTRACT_ITEMS]:
        template = catalog.get(item.fact_key)
        excerpt, raw = _norm(item.source_excerpt), _norm(item.raw_value_text)
        if template is None or not excerpt or not raw:
            continue
        if excerpt not in haystack or raw not in excerpt:
            continue  # the anti-hallucination check
        if detect_injection(excerpt):
            continue  # instructions inside the text are never a source of facts (INV-03)
        # A short, innocent-looking excerpt may sit inside an injected line ("Ignore previous
        # instructions. Monthly membership 1 TL"): judge the whole line it came from.
        if any(detect_injection(line) for line in lines if excerpt in line):
            continue
        kept.append((item, template))
    return kept


@dataclass(frozen=True)
class PlannedCandidate:
    item: ExtractedItem
    template: TemplateItem
    fact: Any  # the live fact for the key, or ``None`` (a ``FactLike``)
    value: dict[str, Any]
    excerpt: str


def plan_candidates(
    output: ExtractFactsOutput,
    pasted_text: str,
    catalog: dict[str, TemplateItem],
    lookup: Callable[[str], Any],
    *,
    locale: str,
    currency: str,
) -> list[PlannedCandidate]:
    """The deterministic part, with no database: which items become candidates, and with
    which re-parsed value. ``lookup(key)`` returns the live fact for a key or ``None``."""
    planned: list[PlannedCandidate] = []
    for item, template in accept_items(output.items, pasted_text, catalog):
        fact = lookup(item.fact_key)
        if fact is not None and fact.value_type != template.value_type:
            continue
        value = _parse_value(template, fact, item.raw_value_text, locale, currency)
        if value is None:
            continue
        planned.append(PlannedCandidate(item, template, fact, value, _norm(item.source_excerpt)))
    return planned


def store_candidates(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    run: AgentRun,
    output: ExtractFactsOutput,
    pasted_text: str,
    *,
    catalog: dict[str, TemplateItem],
    locale: str,
    currency: str,
) -> int:
    """Create ``pasted_text`` candidates for the planned items (in the caller's transaction)."""
    planned = plan_candidates(
        output,
        pasted_text,
        catalog,
        lambda key: repo.get_live_fact_by_key(session, ctx, key, lock=True),
        locale=locale,
        currency=currency,
    )
    for entry in planned:
        candidates.propose_candidate(
            session,
            clock,
            ctx,
            key=entry.item.fact_key,
            value_type=entry.template.value_type,
            value=entry.value,
            source_type="pasted_text",
            source_excerpt=entry.excerpt,
            fact=entry.fact,
            agent_run_id=run.id,
        )
    return len(planned)


def catalog_for(
    business_category: str, locale: str
) -> tuple[dict[str, TemplateItem], list[CatalogKey]]:
    """The fixed template keys the model may extract (labels and hints in ``locale``)."""
    template = load_template(business_category)
    fixed = {item.key: item for item in template.items if item.key is not None}
    keys = [
        CatalogKey(
            key=key,
            label=item.label.get(locale) or item.label.get("tr") or key,
            value_type=item.value_type,
            description=item.description.get(locale) or item.description.get("tr") or "",
        )
        for key, item in sorted(fixed.items())
    ]
    return fixed, keys


# --- the job --------------------------------------------------------------------------------


def _fail_run_if_open(job: JobContext, error_code: str) -> None:
    payload = job.payload
    if not isinstance(payload, ExtractFactCandidatesPayload):
        return
    with job.session_factory() as session:
        run = session.get(AgentRun, payload.run_id, with_for_update=True)
        unfinished = run is not None and (
            run.status in ("queued", "running")
            or (run.status == "succeeded" and "stored_at" not in (run.input_snapshot or {}))
        )
        if run is not None and unfinished:
            run.status = "failed"
            run.error_code = "LLM_UNAVAILABLE" if error_code == "LLM_UNAVAILABLE" else error_code
            run.completed_at = job.clock.now()
        session.commit()


@job_handler(
    "extract_fact_candidates",
    ExtractFactCandidatesPayload,
    max_attempts=2,  # agent-runtime.md §2
    timeout=150,
    on_dead=_fail_run_if_open,
    backoff=(10, 60),
)
def extract_fact_candidates(job: JobContext) -> None:
    payload = job.payload
    if not isinstance(payload, ExtractFactCandidatesPayload) or job.workspace_id is None:
        return
    with job.session_factory() as session:  # [T1] gather
        run = session.get(AgentRun, payload.run_id)
        if run is None or run.workspace_id != job.workspace_id or run.status == "succeeded":
            return
        snapshot = dict(run.input_snapshot or {})
        text, user_id = str(snapshot.get("text", "")), snapshot.get("user_id")
        user = session.get(User, uuid.UUID(user_id)) if user_id else None
        workspace = session.get(Workspace, job.workspace_id)
        found = identity_repo.get_membership(session, job.workspace_id, user.id) if user else None
        if not text or user is None or workspace is None or found is None:
            run.status = "failed"
            run.error_code = "FORBIDDEN" if found is None else "VALIDATION_FAILED"
            run.completed_at = job.clock.now()
            session.commit()
            return
        ctx = identity_service.workspace_context(workspace, ActorRef.user(user.id), found[0].role)
        catalog, keys = catalog_for(workspace.business_category, user.ui_locale)
        task_input = ExtractFactsInput(
            text=text,
            catalog=keys,
            workspace_locale=workspace.default_locale,
            currency=workspace.currency,
        )
        locale, currency = workspace.default_locale, workspace.currency
        correlation_id = run.correlation_id
        session.commit()

    outcome = run_task(  # no transaction is open during the model call
        runner_deps(job.session_factory, job.clock),
        ctx,
        EXTRACT_FACT_CANDIDATES,
        task_input,
        correlation_id,
        job_id=job.job_id,
        agent_run_id=payload.run_id,
    )
    if outcome.output is None:
        return  # the run is already recorded as failed; the UI offers manual entry
    with job.session_factory() as session:  # [T2] store
        run = session.get(AgentRun, payload.run_id, with_for_update=True)
        if run is None:
            return
        store_candidates(
            session,
            job.clock,
            ctx,
            run,
            outcome.output,
            text,
            catalog=catalog,
            locale=locale,
            currency=currency,
        )
        run.input_snapshot = {
            **(run.input_snapshot or {}),
            "stored_at": job.clock.now().isoformat(),
        }
        session.commit()
