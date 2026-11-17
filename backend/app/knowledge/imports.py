"""Source-independent candidate imports; all network work runs between transactions."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.injection import detect_injection
from app.ai.models import AgentRun
from app.ai.runner import create_queued_run, run_task
from app.ai.runtime import get_provider, runner_deps
from app.ai.schemas import MAX_EXTRACT_CHARS, ExtractFactsInput, ExtractFactsOutput
from app.ai.tasks.extract_fact_candidates import EXTRACT_FACT_CANDIDATES
from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import ActorRef, WorkspaceContext
from app.identity import service as identity_service
from app.identity.models import Workspace
from app.jobs.registry import JobContext
from app.knowledge import candidates, extraction
from app.knowledge import repository as repo
from app.knowledge.constants import STALE_CAPTION_DAYS
from app.knowledge.models import FactCandidate
from app.knowledge.templates import TemplateItem
from app.knowledge.values import values_equal

PROFILE_IMPORT_CAPTIONS = 12


@dataclass(frozen=True)
class ImportSegment:
    origin: str
    text: str
    posted_at: datetime | None = None
    url: str | None = None


class ImportRunPayload(BaseModel):
    run_id: uuid.UUID


@dataclass(frozen=True)
class GatherInput:
    session_factory: sessionmaker[Session]
    clock: Clock
    workspace_id: uuid.UUID
    snapshot: dict[str, Any]
    run_id: uuid.UUID | None = None


@dataclass(frozen=True)
class GatherResult:
    segments: list[ImportSegment]
    notes: dict[str, Any]
    simulated: bool = False


class ImportFailed(Exception):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


@dataclass(frozen=True)
class PreparedImport:
    text: str
    kept: list[ImportSegment]
    injection_flags: list[str]
    skipped_injection: int


def rank(segment: ImportSegment) -> tuple[bool, float]:
    return (
        segment.origin == "caption",
        -segment.posted_at.timestamp() if segment.posted_at else float("inf"),
    )


def prepare_segments(
    segments: list[ImportSegment], budget: int = MAX_EXTRACT_CHARS
) -> PreparedImport:
    blocks: list[str] = []
    kept: list[ImportSegment] = []
    flags: set[str] = set()
    skipped = 0
    usable: list[ImportSegment] = []
    for segment in sorted(segments, key=rank):
        text = segment.text.strip()
        if not text:
            continue
        # Inspect the whole segment, including instructions beyond the truncation boundary.
        found = detect_injection(text)
        if found:
            flags.update(found)
            skipped += 1
            continue
        usable.append(replace(segment, text=text[:700]))
    for segment in usable:
        # Origins are source-defined labels, never imported header text.
        origin = segment.origin if segment.origin in ("bio", "caption", "website_page") else "data"
        date = (
            f" {segment.posted_at.date().isoformat()}"
            if origin == "caption" and segment.posted_at
            else ""
        )
        block = f"[{origin}{date}]\n{segment.text}"
        if len("\n\n".join([*blocks, block])) > min(budget, MAX_EXTRACT_CHARS):
            break
        blocks.append(block)
        kept.append(segment)
    return PreparedImport("\n\n".join(blocks), kept, sorted(flags), skipped)


def attribute(excerpt: str, kept: list[ImportSegment]) -> ImportSegment | None:
    normalized = extraction._norm(excerpt)
    if not normalized:
        return None
    return next(
        (seg for seg in sorted(kept, key=rank) if normalized in extraction._norm(seg.text)), None
    )


@dataclass(frozen=True)
class ImportStoreResult:
    created: int
    duplicates: int
    stale: int


def store_import_candidates(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    run: AgentRun,
    output: ExtractFactsOutput,
    text: str,
    kept: list[ImportSegment],
    *,
    source_type: str,
    simulated: bool,
    catalog: dict[str, TemplateItem],
    locale: str,
    currency: str,
) -> ImportStoreResult:
    planned = extraction.plan_candidates(
        output,
        text,
        catalog,
        lambda key: repo.get_live_fact_by_key(session, ctx, key, lock=True),
        locale=locale,
        currency=currency,
    )
    selected: dict[str, tuple[extraction.PlannedCandidate, ImportSegment]] = {}
    duplicates = 0
    for entry in planned:
        seg = attribute(entry.excerpt, kept)
        if seg is None:
            continue
        key = entry.item.fact_key
        previous = selected.get(key)
        if previous is not None:
            duplicates += 1
            if rank(previous[1]) <= rank(seg):
                continue
        selected[key] = (entry, seg)
    created = stale = 0
    for key, (entry, seg) in selected.items():
        same_fact = (
            candidates.compute_relation(
                candidates.snapshot_of(entry.fact),
                entry.value,
                entry.template.value_type,
                source_type,
            )
            == "same"
        )
        existing = session.scalars(
            select(FactCandidate)
            .where(
                FactCandidate.workspace_id == ctx.workspace_id,
                FactCandidate.fact_key == key,
                (FactCandidate.status == "pending")
                | (
                    (FactCandidate.source_type == source_type)
                    & FactCandidate.status.in_(("accepted", "rejected"))
                ),
            )
            .with_for_update()
        )
        if same_fact or any(
            c.value_type == entry.template.value_type
            and values_equal(c.value_type, c.proposed_value, entry.value)
            for c in existing
        ):
            duplicates += 1
            continue
        candidates.propose_candidate(
            session,
            clock,
            ctx,
            key=key,
            value_type=entry.template.value_type,
            value=entry.value,
            source_type=source_type,
            source_excerpt=entry.excerpt,
            fact=entry.fact,
            agent_run_id=run.id,
            source_detail={
                "origin": seg.origin,
                "posted_at": seg.posted_at.isoformat() if seg.posted_at else None,
                "url": seg.url if seg.url and seg.url.startswith(("https://", "http://")) else None,
                "simulated": simulated,
            },
        )
        created += 1
        if (
            seg.origin == "caption"
            and seg.posted_at
            and (clock.now() - seg.posted_at).days > STALE_CAPTION_DAYS
        ):
            stale += 1
    return ImportStoreResult(created, duplicates, stale)


def fail_run_if_open(job: JobContext, error_code: str) -> None:
    if not isinstance(job.payload, ImportRunPayload) or job.workspace_id is None:
        return
    with job.session_factory() as session:
        run = session.scalar(
            select(AgentRun)
            .where(
                AgentRun.id == job.payload.run_id,
                AgentRun.workspace_id == job.workspace_id,
                AgentRun.task == "extract_fact_candidates",
            )
            .with_for_update()
        )
        if run is not None and (
            run.status in ("queued", "running")
            or (run.status == "succeeded" and "stored_at" not in (run.input_snapshot or {}))
        ):
            run.status, run.error_code, run.completed_at = "failed", error_code, job.clock.now()
        session.commit()


def run_import(
    job: JobContext, *, source_type: str, gather: Callable[[GatherInput], GatherResult]
) -> None:
    if not isinstance(job.payload, ImportRunPayload) or job.workspace_id is None:
        return
    run_id = job.payload.run_id
    with job.session_factory() as session:
        run = session.scalar(
            select(AgentRun).where(
                AgentRun.id == run_id,
                AgentRun.workspace_id == job.workspace_id,
                AgentRun.task == "extract_fact_candidates",
            )
        )
        if run is None or run.status == "succeeded":
            return
        snapshot = dict(run.input_snapshot or {})
        if snapshot.get("source") != source_type:
            return
        workspace = session.get(Workspace, job.workspace_id)
        if workspace is None:
            return
        ctx = identity_service.workspace_context(
            workspace, ActorRef.system(f"import.{source_type}"), None
        )
        catalog, keys = extraction.catalog_for(
            workspace.business_category, workspace.default_locale
        )
        locale, currency, correlation_id = (
            workspace.default_locale,
            workspace.currency,
            run.correlation_id,
        )
        session.commit()
    try:
        gathered = gather(
            GatherInput(job.session_factory, job.clock, job.workspace_id, snapshot, run_id)
        )
    except ImportFailed as exc:
        fail_run_if_open(job, exc.error_code)
        return
    prepared = prepare_segments(gathered.segments)
    with job.session_factory() as session:
        run = session.scalar(
            select(AgentRun)
            .where(AgentRun.id == run_id, AgentRun.workspace_id == job.workspace_id)
            .with_for_update()
        )
        if run is None or "stored_at" in (run.input_snapshot or {}):
            return
        run.input_snapshot = {
            **snapshot,
            **gathered.notes,
            "injection_flags": prepared.injection_flags,
            "segments": [
                {
                    "origin": s.origin,
                    "posted_at": s.posted_at.isoformat() if s.posted_at else None,
                    "chars": len(s.text),
                }
                for s in prepared.kept
            ],
        }
        if not prepared.kept:
            run.status, run.completed_at = "succeeded", job.clock.now()
            run.input_snapshot = {**run.input_snapshot, "stored_at": job.clock.now().isoformat()}
            _audit_completed(
                session,
                job,
                ctx,
                run,
                source_type,
                gathered.simulated,
                ImportStoreResult(0, 0, 0),
                prepared,
            )
        session.commit()
    if not prepared.kept:
        return
    outcome = run_task(
        runner_deps(job.session_factory, job.clock),
        ctx,
        replace(EXTRACT_FACT_CANDIDATES, store_output=False),
        ExtractFactsInput(
            text=prepared.text, catalog=keys, workspace_locale=locale, currency=currency
        ),
        correlation_id,
        job_id=job.job_id,
        agent_run_id=run_id,
    )
    if outcome.output is None:
        return
    with job.session_factory() as session:
        run = session.scalar(
            select(AgentRun)
            .where(AgentRun.id == run_id, AgentRun.workspace_id == job.workspace_id)
            .with_for_update()
        )
        if run is None or "stored_at" in (run.input_snapshot or {}):
            return
        result = store_import_candidates(
            session,
            job.clock,
            ctx,
            run,
            outcome.output,
            prepared.text,
            prepared.kept,
            source_type=source_type,
            simulated=gathered.simulated,
            catalog=catalog,
            locale=locale,
            currency=currency,
        )
        run.input_snapshot = {
            **(run.input_snapshot or {}),
            "stored_at": job.clock.now().isoformat(),
        }
        _audit_completed(session, job, ctx, run, source_type, gathered.simulated, result, prepared)
        session.commit()


def _audit_completed(
    session: Session,
    job: JobContext,
    ctx: WorkspaceContext,
    run: AgentRun,
    source: str,
    simulated: bool,
    result: ImportStoreResult,
    prepared: PreparedImport,
) -> None:
    audit.record(
        session,
        ctx,
        "knowledge.import_completed",
        "agent_run",
        run.id,
        {
            "source": source,
            "candidates": result.created,
            "duplicates": result.duplicates,
            "stale": result.stale,
            "skipped_injection": prepared.skipped_injection,
            "segments": len(prepared.kept),
        },
        correlation_id=run.correlation_id,
        clock=job.clock,
        is_simulated=simulated,
    )


def find_in_progress(
    session: Session, workspace_id: uuid.UUID, source_type: str, now: datetime
) -> AgentRun | None:
    return session.scalar(
        select(AgentRun)
        .where(
            AgentRun.workspace_id == workspace_id,
            AgentRun.task == "extract_fact_candidates",
            AgentRun.input_snapshot["source"].astext == source_type,
            AgentRun.status.in_(("queued", "running")),
            AgentRun.created_at >= now - timedelta(minutes=10),
        )
        .order_by(AgentRun.created_at.desc())
        .limit(1)
    )


def find_request(
    session: Session, workspace_id: uuid.UUID, source_type: str, request_id: str
) -> AgentRun | None:
    return session.scalar(
        select(AgentRun)
        .where(
            AgentRun.workspace_id == workspace_id,
            AgentRun.task == "extract_fact_candidates",
            AgentRun.input_snapshot["source"].astext == source_type,
            AgentRun.input_snapshot["client_request_id"].astext == request_id,
        )
        .order_by(AgentRun.created_at.desc())
        .limit(1)
    )


def create_import_run(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    source_type: str,
    snapshot_extra: dict[str, Any],
    client_request_id: str,
) -> AgentRun:
    existing = find_request(session, ctx.workspace_id, source_type, client_request_id)
    if existing is not None:
        return existing
    return create_queued_run(
        session,
        clock,
        get_provider(),
        ctx,
        "extract_fact_candidates",
        {
            **snapshot_extra,
            "source": source_type,
            "client_request_id": client_request_id,
            "user_id": ctx.actor.id,
        },
        uuid.uuid4(),
    )
