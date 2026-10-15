"""Knowledge routes (api-design.md §2.3). Thin: validate, call the service, map to a model.

Every route is workspace-scoped through ``require_membership`` (INV-01): a fact or candidate
from another workspace is simply not found (404).
"""

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import current_auth, get_clock, require_membership
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.db import get_db
from app.core.pagination import Page
from app.identity.service import AuthenticatedSession
from app.knowledge import readiness as readiness_module
from app.knowledge import repository as repo
from app.knowledge import service
from app.knowledge.models import BusinessFact, FactCandidate
from app.knowledge.schemas import (
    CandidateOut,
    CandidateStatus,
    Category,
    FactCreate,
    FactOut,
    FactPatch,
    FactStatus,
    FactTransition,
    ReadinessLinkOut,
    ReadinessOut,
    RequirementOut,
    TemplateItemOut,
    VersionOut,
)

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["knowledge"])


def _fact_out(view: service.FactView) -> FactOut:
    fact = view.fact
    return FactOut(
        id=fact.id,
        key=fact.key,
        category=fact.category,
        label=fact.label,
        value_type=fact.value_type,
        value=fact.value,
        display=view.display,
        status=fact.status,
        state=view.state,
        criticality=fact.criticality,
        current_version=fact.current_version,
        valid_from=fact.valid_from,
        valid_until=fact.valid_until,
        last_verified_at=fact.last_verified_at,
        last_verified_by_name=view.last_verified_by_name,
        source_type=view.source_type,
        usable=view.usable,
        open_candidates_count=view.open_candidates_count,
    )


def _candidate_out(view: service.CandidateView) -> CandidateOut:
    candidate = view.candidate
    return CandidateOut(
        id=candidate.id,
        fact_key=candidate.fact_key,
        fact_id=candidate.fact_id,
        fact_label=view.fact_label,
        value_type=candidate.value_type,
        proposed_value=candidate.proposed_value,
        proposed_display=view.proposed_display,
        current_display=view.current_display,
        relation=candidate.relation,
        status=candidate.status,
        source_type=candidate.source_type,
        source_excerpt=candidate.source_excerpt,
        proposed_by_name=view.proposed_by_name,
        created_at=candidate.created_at,
        resolved_at=candidate.resolved_at,
    )


def _fact_response(
    db: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    auth: AuthenticatedSession,
    fact: BusinessFact,
) -> FactOut:
    return _fact_out(service.fact_view(db, clock, ctx, fact, ui_locale=auth.user.ui_locale))


# --- facts ----------------------------------------------------------------------------------


@router.get("/facts", response_model=Page[FactOut])
def list_facts(
    category: Category | None = None,
    status: FactStatus | None = None,
    ctx: WorkspaceContext = Depends(require_membership()),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> Page[FactOut]:
    facts = repo.list_facts(db, ctx, category=category, status=status)
    views = service.fact_views(db, clock, ctx, list(facts), ui_locale=auth.user.ui_locale)
    return Page(items=[_fact_out(v) for v in views])


@router.get("/facts/template", response_model=list[TemplateItemOut])
def get_template(
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> list[TemplateItemOut]:
    return [
        TemplateItemOut(
            identifier=entry.item.identifier,
            key=entry.item.key,
            pattern=entry.item.pattern,
            category=entry.item.category,
            label=entry.item.label,
            description=entry.item.description,
            value_types=list(entry.item.value_types),
            criticality=entry.item.criticality,
            required_for=entry.item.required_for,
            required_group=entry.item.required_group,
            required_when=entry.item.required_when,
            allowed_values=list(entry.item.allowed_values),
            status=entry.status,
            fact_ids=[f.id for f in entry.facts],
        )
        for entry in service.template_checklist(db, clock, ctx)
    ]


@router.post("/facts", response_model=FactOut | CandidateOut, status_code=201)
def create_fact(
    body: FactCreate,
    response: Response,
    ctx: WorkspaceContext = Depends(require_membership("knowledge.edit")),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> FactOut | CandidateOut:
    """A verifier gets the verified fact (201); staff get a pending candidate (202)."""
    result = service.create_fact(
        db,
        clock,
        ctx,
        key=body.key,
        value=body.value,
        value_type=body.value_type,
        label=body.label.model_dump() if body.label else None,
        criticality=body.criticality,
        valid_from=body.valid_from,
        valid_until=body.valid_until,
        reason=body.reason,
    )
    if isinstance(result, FactCandidate):
        response.status_code = 202
        return _candidate_out(
            service.candidate_view(db, ctx, result, ui_locale=auth.user.ui_locale)
        )
    return _fact_response(db, clock, ctx, auth, result)


@router.patch("/facts/{fact_id}", response_model=FactOut | CandidateOut)
def patch_fact(
    fact_id: uuid.UUID,
    body: FactPatch,
    response: Response,
    ctx: WorkspaceContext = Depends(require_membership("knowledge.edit")),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> FactOut | CandidateOut:
    sent = body.model_fields_set
    result = service.update_fact(
        db,
        clock,
        ctx,
        fact_id,
        expected_version=body.expected_version,
        value=body.value if body.value is not None else service.UNSET,
        valid_from=body.valid_from if "valid_from" in sent else service.UNSET,
        valid_until=body.valid_until if "valid_until" in sent else service.UNSET,
        reason=body.reason,
    )
    if isinstance(result, FactCandidate):
        response.status_code = 202
        return _candidate_out(
            service.candidate_view(db, ctx, result, ui_locale=auth.user.ui_locale)
        )
    return _fact_response(db, clock, ctx, auth, result)


@router.post("/facts/{fact_id}/verify", response_model=FactOut)
def verify_fact(
    fact_id: uuid.UUID,
    body: FactTransition,
    ctx: WorkspaceContext = Depends(require_membership("knowledge.verify")),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> FactOut:
    fact = service.verify_fact(db, clock, ctx, fact_id, expected_version=body.expected_version)
    return _fact_response(db, clock, ctx, auth, fact)


@router.post("/facts/{fact_id}/archive", response_model=FactOut)
def archive_fact(
    fact_id: uuid.UUID,
    body: FactTransition,
    ctx: WorkspaceContext = Depends(require_membership("knowledge.verify")),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> FactOut:
    fact = service.archive_fact(
        db, clock, ctx, fact_id, expected_version=body.expected_version, reason=body.reason
    )
    return _fact_response(db, clock, ctx, auth, fact)


@router.post("/facts/{fact_id}/restore", response_model=FactOut)
def restore_fact(
    fact_id: uuid.UUID,
    body: FactTransition,
    ctx: WorkspaceContext = Depends(require_membership("knowledge.verify")),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> FactOut:
    fact = service.restore_fact(db, clock, ctx, fact_id, expected_version=body.expected_version)
    return _fact_response(db, clock, ctx, auth, fact)


@router.get("/facts/{fact_id}/versions", response_model=Page[VersionOut])
def list_versions(
    fact_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership()),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
) -> Page[VersionOut]:
    views = service.version_views(db, ctx, fact_id, ui_locale=auth.user.ui_locale)
    return Page(
        items=[
            VersionOut(
                version=v.version.version,
                value=v.version.value,
                display=v.display,
                status=v.version.status,
                valid_from=v.version.valid_from,
                valid_until=v.version.valid_until,
                source_type=v.version.source_type,
                source_ref=v.version.source_ref,
                actor_type=v.version.actor_type,
                actor_name=v.actor_name,
                reason=v.version.reason,
                change_kind=v.version.change_kind,
                created_at=v.version.created_at,
            )
            for v in views
        ]
    )


# --- candidates -----------------------------------------------------------------------------


@router.get("/fact-candidates", response_model=Page[CandidateOut])
def list_candidates(
    status: CandidateStatus | None = "pending",
    ctx: WorkspaceContext = Depends(require_membership()),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
) -> Page[CandidateOut]:
    items = repo.list_candidates(db, ctx, status=status)
    views = service.candidate_views(db, ctx, list(items), ui_locale=auth.user.ui_locale)
    return Page(items=[_candidate_out(v) for v in views])


@router.post("/fact-candidates/{candidate_id}/accept", response_model=FactOut)
def accept_candidate(
    candidate_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("knowledge.verify")),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> FactOut:
    fact = service.accept_candidate(db, clock, ctx, candidate_id)
    return _fact_response(db, clock, ctx, auth, fact)


@router.post("/fact-candidates/{candidate_id}/reject", response_model=CandidateOut)
def reject_candidate(
    candidate_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_membership("knowledge.verify")),
    auth: AuthenticatedSession = Depends(current_auth),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> CandidateOut:
    candidate = service.reject_candidate(db, clock, ctx, candidate_id)
    return _candidate_out(service.candidate_view(db, ctx, candidate, ui_locale=auth.user.ui_locale))


# --- readiness ------------------------------------------------------------------------------


@router.get("/readiness", response_model=ReadinessOut)
def get_readiness(
    ctx: WorkspaceContext = Depends(require_membership()),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> ReadinessOut:
    report = readiness_module.readiness(db, clock, ctx)
    return ReadinessOut(
        level=report.level,
        requirements=[
            RequirementOut(
                code=r.code,
                required_for=r.required_for,
                satisfied=r.satisfied,
                status=r.status,
                link=ReadinessLinkOut(
                    target=r.link.target,
                    category=r.link.category,
                    key=r.link.key,
                ),
                missing_keys=list(r.missing_keys),
            )
            for r in report.requirements
        ],
    )
