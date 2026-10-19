"""FactService: the use cases of business knowledge (workflow A, state-machines.md §2).

Public functions commit (one request = one transaction, ADR-003); the audit entry and the
version row are written in the same transaction (INV-12, INV-17). Internal ``_``-functions
never commit, so accepting a candidate is one atomic unit.

Lock order: candidate first, then fact. Time comes from the injected ``Clock`` (INV-19).
"""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Final

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity import repository as identity_repo
from app.identity.models import Workspace
from app.identity.permissions import has_permission
from app.knowledge import candidates, impact, usability
from app.knowledge import repository as repo
from app.knowledge.formatting import format_value
from app.knowledge.models import BusinessFact, FactCandidate, FactVersion
from app.knowledge.templates import Template, TemplateItem, load_template
from app.knowledge.transitions import apply_fact_event
from app.knowledge.values import clean_text, validate_value, values_equal


class _Unset:
    """Marks an argument that was not supplied (distinct from an explicit ``None``)."""

    def __repr__(self) -> str:
        return "UNSET"


UNSET: Final = _Unset()


# --- small helpers --------------------------------------------------------------------------


def _require(ctx: WorkspaceContext, permission: str) -> None:
    if not has_permission(ctx.role, permission):
        raise AppError("FORBIDDEN", permission=permission)


def _workspace(session: Session, ctx: WorkspaceContext) -> Workspace:
    workspace = identity_repo.get_workspace(session, ctx)
    if workspace is None:
        raise AppError("NOT_FOUND")
    return workspace


def _user_id(ctx: WorkspaceContext) -> uuid.UUID | None:
    return uuid.UUID(ctx.actor.id) if ctx.actor.type == "user" and ctx.actor.id else None


def _error(field: str, code: str, **params: Any) -> AppError:
    return AppError("VALIDATION_FAILED", errors=[{"field": field, "code": code, "params": params}])


@dataclass(frozen=True)
class _Spec:
    """What a key means for this workspace: derived from the template, never from the client."""

    category: str
    label: dict[str, str]
    value_type: str
    criticality: str
    allowed_values: tuple[str, ...]
    fixed: bool  # a fixed template key (staff may propose it); False for patterns and custom


def _slug_label(key: str) -> dict[str, str]:
    text = key.split(".", 1)[1].replace("_", " ").strip().capitalize()
    return {"tr": text, "en": text}


def _clean_label(label: dict[str, str] | None) -> dict[str, str] | None:
    if not label:
        return None
    tr, en = clean_text(label.get("tr") or ""), clean_text(label.get("en") or "")
    if not (tr or en):
        return None
    return {"tr": tr or en, "en": en or tr}


def _spec_for_key(
    template: Template,
    key: str,
    *,
    value_type: str | None,
    label: dict[str, str] | None,
    criticality: str | None,
    allow_missing_label: bool = False,
) -> _Spec:
    clean_label = _clean_label(label)
    if key.startswith("custom."):
        if value_type is None:
            raise _error("value_type", "required")
        if clean_label is None and not allow_missing_label:
            raise _error("label", "required")
        return _Spec(
            "custom",
            clean_label or _slug_label(key),
            value_type,
            criticality or "standard",
            (),
            False,
        )
    item: TemplateItem | None = template.find(key)
    if item is None:
        raise _error("key", "unknown_key")
    chosen = value_type or (item.value_types[0] if len(item.value_types) == 1 else None)
    if chosen is None:
        raise _error("value_type", "required")
    if chosen not in item.value_types:
        raise _error("value_type", "not_allowed", allowed=list(item.value_types))
    if item.key is not None:
        resolved_label = dict(item.label)
    elif clean_label is not None:
        resolved_label = clean_label
    elif allow_missing_label:
        resolved_label = _slug_label(key)
    else:
        raise _error("label", "required")
    return _Spec(
        item.category,
        resolved_label,
        chosen,
        item.criticality,
        item.allowed_values,
        item.key is not None,
    )


def _display(fact: BusinessFact, ctx: WorkspaceContext, locale: str | None = None) -> str:
    return format_value(fact.value_type, fact.value, locale or ctx.locale, ctx.locale)


def _window_text(valid_from: date | None, valid_until: date | None) -> str:
    start = valid_from.isoformat() if valid_from else ""
    end = valid_until.isoformat() if valid_until else ""
    return f"{start}..{end}"


def _snapshot(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    fact: BusinessFact,
    *,
    change_kind: str,
    source_type: str,
    source_ref: str | None,
    reason: str | None,
) -> FactVersion:
    """Append the immutable version row for the fact's *current* state (INV-17)."""
    return repo.add_version(
        session,
        FactVersion(
            workspace_id=ctx.workspace_id,
            fact_id=fact.id,
            version=fact.current_version,
            value=fact.value,
            status=fact.status,
            valid_from=fact.valid_from,
            valid_until=fact.valid_until,
            source_type=source_type,
            source_ref=source_ref,
            actor_type=ctx.actor.type,
            actor_id=ctx.actor.id,
            reason=clean_text(reason) if reason else None,
            change_kind=change_kind,
            created_at=clock.now(),
        ),
    )


def _audit(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    action: str,
    fact: BusinessFact,
    **metadata: Any,
) -> None:
    audit.record(
        session,
        ctx,
        action,
        "business_fact",
        fact.id,
        {"key": fact.key, "version": fact.current_version, **metadata},
        clock=clock,
    )


# --- create ---------------------------------------------------------------------------------


def _insert_fact(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    workspace: Workspace,
    *,
    key: str,
    spec: _Spec,
    value: dict[str, Any],
    verified: bool,
    valid_from: date | None,
    valid_until: date | None,
    source_type: str,
    source_ref: str | None,
    reason: str | None,
) -> BusinessFact:
    if valid_from and valid_until and valid_until < valid_from:
        raise _error("valid_until", "window_invalid")
    now = clock.now()
    status = apply_fact_event(None, "create_verified" if verified else "create_unverified")
    fact = BusinessFact(
        workspace_id=ctx.workspace_id,
        key=key,
        category=spec.category,
        label=spec.label,
        value_type=spec.value_type,
        value=value,
        status=status,
        criticality=spec.criticality,
        current_version=1,
        valid_from=valid_from,
        valid_until=valid_until,
        last_verified_at=now if verified else None,
        last_verified_by_user_id=_user_id(ctx) if verified else None,
    )
    try:
        with session.begin_nested():
            repo.add_fact(session, fact)
    except IntegrityError as exc:  # the partial unique index: a concurrent create won
        raise AppError("CONFLICT_STATE", reason="key_exists", key=key) from exc
    _snapshot(
        session,
        clock,
        ctx,
        fact,
        change_kind="created",
        source_type=source_type,
        source_ref=source_ref,
        reason=reason,
    )
    candidates.recompute_relations(session, ctx, key, fact)
    _audit(
        session,
        clock,
        ctx,
        "fact.created",
        fact,
        status=status,
        source_type=source_type,
        new_display=_display(fact, ctx),
    )
    return fact


def create_fact(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    key: str,
    value: dict[str, Any],
    value_type: str | None = None,
    label: dict[str, str] | None = None,
    criticality: str | None = None,
    valid_from: date | None = None,
    valid_until: date | None = None,
    reason: str | None = None,
) -> BusinessFact | FactCandidate:
    """Enter a new fact (``knowledge.edit``).

    A verifier creates a ``verified`` fact. Staff create a ``staff_proposal`` candidate for a
    fixed template key (``new`` relation) and cannot create pattern or custom keys or set a
    validity window; the caller answers 202 in that case.
    """
    _require(ctx, "knowledge.edit")
    workspace = _workspace(session, ctx)
    template = load_template(workspace.business_category)
    can_verify = has_permission(ctx.role, "knowledge.verify")
    spec = _spec_for_key(template, key, value_type=value_type, label=label, criticality=criticality)
    if not can_verify and (not spec.fixed or valid_from or valid_until):
        raise AppError("FORBIDDEN", permission="knowledge.verify")
    canonical = validate_value(
        spec.value_type,
        value,
        allowed_values=spec.allowed_values or None,
        default_currency=workspace.currency,
    )
    existing = repo.get_live_fact_by_key(session, ctx, key, lock=True)
    if existing is not None:
        raise AppError("CONFLICT_STATE", reason="key_exists", key=key)
    if not can_verify:
        candidate = candidates.propose_candidate(
            session,
            clock,
            ctx,
            key=key,
            value_type=spec.value_type,
            value=canonical,
            source_type="staff_proposal",
        )
        session.commit()
        return candidate
    fact = _insert_fact(
        session,
        clock,
        ctx,
        workspace,
        key=key,
        spec=spec,
        value=canonical,
        verified=True,
        valid_from=valid_from,
        valid_until=valid_until,
        source_type="owner_entry",
        source_ref=None,
        reason=reason,
    )
    session.commit()
    return fact


def insert_trusted_fact(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    key: str,
    value: dict[str, Any],
    verified: bool,
    value_type: str | None = None,
    label: dict[str, str] | None = None,
    criticality: str | None = None,
    valid_from: date | None = None,
    valid_until: date | None = None,
    source_type: str = "seed",
    reason: str | None = None,
) -> BusinessFact:
    """Create a fact without a user permission check, optionally ``unverified``.

    For trusted internal callers only (the demo seed, ``source_type="seed"``/``template_default``).
    The router never calls this.
    """
    workspace = _workspace(session, ctx)
    spec = _spec_for_key(
        load_template(workspace.business_category),
        key,
        value_type=value_type,
        label=label,
        criticality=criticality,
        allow_missing_label=True,
    )
    canonical = validate_value(
        spec.value_type,
        value,
        allowed_values=spec.allowed_values or None,
        default_currency=workspace.currency,
    )
    if repo.get_live_fact_by_key(session, ctx, key, lock=True) is not None:
        raise AppError("CONFLICT_STATE", reason="key_exists", key=key)
    fact = _insert_fact(
        session,
        clock,
        ctx,
        workspace,
        key=key,
        spec=spec,
        value=canonical,
        verified=verified,
        valid_from=valid_from,
        valid_until=valid_until,
        source_type=source_type,
        source_ref=None,
        reason=reason,
    )
    session.commit()
    return fact


# --- update / verify / archive / restore ----------------------------------------------------


def _check_version(fact: BusinessFact, expected_version: int) -> None:
    if fact.current_version != expected_version:
        raise AppError("FACT_VERSION_CONFLICT", current_version=fact.current_version)


def _verify_row(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    fact: BusinessFact,
    *,
    source_type: str,
    source_ref: str | None,
    reason: str | None,
) -> BusinessFact:
    fact.status = apply_fact_event(fact.status, "verify")
    fact.current_version += 1
    fact.last_verified_at = clock.now()
    fact.last_verified_by_user_id = _user_id(ctx)
    _snapshot(
        session,
        clock,
        ctx,
        fact,
        change_kind="verified",
        source_type=source_type,
        source_ref=source_ref,
        reason=reason,
    )
    candidates.recompute_relations(session, ctx, fact.key, fact)
    _audit(session, clock, ctx, "fact.verified", fact, source_type=source_type)
    return fact


def _propagate(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    fact: BusinessFact,
    change: impact.ChangeKind,
    *,
    old_version: int,
    old_display: str,
) -> None:
    """Let referrers react to the change and tell the other verifiers (workflow B step 3.4).

    Runs in the update's own transaction, so a failing handler undoes the whole change.
    """
    effects = impact.apply_change(session, clock, ctx, fact, change, old_version)
    impact.notify_fact_changed(
        session,
        clock,
        ctx,
        fact,
        change=change,
        old_display=old_display,
        new_display="" if change == "archived" else _display(fact, ctx),
        effects=effects,
    )


def _apply_change(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    fact: BusinessFact,
    *,
    value: dict[str, Any] | None,
    valid_from: date | None | _Unset,
    valid_until: date | None | _Unset,
    source_type: str,
    source_ref: str | None,
    reason: str | None,
) -> BusinessFact:
    """Verifier-level edit of a locked fact: one new version row and one audit entry."""
    new_from = fact.valid_from if isinstance(valid_from, _Unset) else valid_from
    new_until = fact.valid_until if isinstance(valid_until, _Unset) else valid_until
    if new_from and new_until and new_until < new_from:
        raise _error("valid_until", "window_invalid")
    value_changed = value is not None and not values_equal(fact.value_type, fact.value, value)
    window_changed = (new_from, new_until) != (fact.valid_from, fact.valid_until)
    if not value_changed and not window_changed:
        if fact.status == "unverified":  # re-entering the same value verifies it
            return _verify_row(
                session,
                clock,
                ctx,
                fact,
                source_type=source_type,
                source_ref=source_ref,
                reason=reason,
            )
        return fact  # nothing changed: no version, no audit entry
    old_display, old_window = _display(fact, ctx), _window_text(fact.valid_from, fact.valid_until)
    fact.status = apply_fact_event(fact.status, "edit")
    if value_changed and value is not None:
        fact.value = value
    fact.valid_from, fact.valid_until = new_from, new_until
    fact.current_version += 1
    fact.last_verified_at = clock.now()
    fact.last_verified_by_user_id = _user_id(ctx)
    _snapshot(
        session,
        clock,
        ctx,
        fact,
        change_kind="value_changed",
        source_type=source_type,
        source_ref=source_ref,
        reason=reason,
    )
    candidates.recompute_relations(session, ctx, fact.key, fact)
    _audit(
        session,
        clock,
        ctx,
        "fact.updated",
        fact,
        source_type=source_type,
        source_ref=source_ref,
        old_display=old_display,
        new_display=_display(fact, ctx),
        old_window=old_window,
        new_window=_window_text(fact.valid_from, fact.valid_until),
    )
    _propagate(
        session,
        clock,
        ctx,
        fact,
        "value_changed",
        old_version=fact.current_version - 1,
        old_display=old_display,
    )
    return fact


def apply_update(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    fact_id: uuid.UUID,
    *,
    expected_version: int,
    value: dict[str, Any] | _Unset = UNSET,
    valid_from: date | None | _Unset = UNSET,
    valid_until: date | None | _Unset = UNSET,
    reason: str | None = None,
    source_type: str = "owner_entry",
    source_ref: str | None = None,
) -> BusinessFact | FactCandidate:
    """Edit a fact (``knowledge.edit``) **without committing**: for callers that own a larger
    transaction (an approval decided-callback). Verifiers write a new verified version; staff
    edits become a ``contest`` candidate and cannot touch the window."""
    _require(ctx, "knowledge.edit")
    fact = repo.get_fact(session, ctx, fact_id, lock=True)
    if fact is None:
        raise AppError("NOT_FOUND")
    _check_version(fact, expected_version)
    if fact.status == "archived":
        raise AppError("CONFLICT_STATE", entity="fact", status=fact.status, event="edit")
    workspace = _workspace(session, ctx)
    template = load_template(workspace.business_category)
    item = template.find(fact.key)
    allowed = item.allowed_values if item is not None else ()
    canonical: dict[str, Any] | None = None
    if not isinstance(value, _Unset):
        canonical = validate_value(
            fact.value_type,
            value,
            allowed_values=allowed or None,
            default_currency=workspace.currency,
        )

    if not has_permission(ctx.role, "knowledge.verify"):
        if not isinstance(valid_from, _Unset) or not isinstance(valid_until, _Unset):
            raise AppError("FORBIDDEN", permission="knowledge.verify")
        if canonical is None:
            raise _error("value", "required")
        candidate = candidates.propose_candidate(
            session,
            clock,
            ctx,
            key=fact.key,
            value_type=fact.value_type,
            value=canonical,
            source_type="staff_proposal",
            fact=fact,
        )
        return candidate

    result = _apply_change(
        session,
        clock,
        ctx,
        fact,
        value=canonical,
        valid_from=valid_from,
        valid_until=valid_until,
        source_type=source_type,
        source_ref=source_ref,
        reason=reason,
    )
    return result


def update_fact(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    fact_id: uuid.UUID,
    *,
    expected_version: int,
    value: dict[str, Any] | _Unset = UNSET,
    valid_from: date | None | _Unset = UNSET,
    valid_until: date | None | _Unset = UNSET,
    reason: str | None = None,
    source_type: str = "owner_entry",
    source_ref: str | None = None,
) -> BusinessFact | FactCandidate:
    """Edit a fact (``knowledge.edit``) and commit. Verifiers write a new verified version;
    staff edits become a ``contest`` candidate (the caller answers 202) and cannot touch the
    window."""
    result = apply_update(
        session,
        clock,
        ctx,
        fact_id,
        expected_version=expected_version,
        value=value,
        valid_from=valid_from,
        valid_until=valid_until,
        reason=reason,
        source_type=source_type,
        source_ref=source_ref,
    )
    session.commit()
    return result


def verify_fact(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    fact_id: uuid.UUID,
    *,
    expected_version: int,
) -> BusinessFact:
    """Mark an unverified fact verified (``knowledge.verify``). Staff get 403, nothing changes."""
    _require(ctx, "knowledge.verify")
    fact = repo.get_fact(session, ctx, fact_id, lock=True)
    if fact is None:
        raise AppError("NOT_FOUND")
    _check_version(fact, expected_version)
    _verify_row(session, clock, ctx, fact, source_type="owner_entry", source_ref=None, reason=None)
    session.commit()
    return fact


def archive_fact(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    fact_id: uuid.UUID,
    *,
    expected_version: int,
    reason: str | None = None,
) -> BusinessFact:
    _require(ctx, "knowledge.verify")
    fact = repo.get_fact(session, ctx, fact_id, lock=True)
    if fact is None:
        raise AppError("NOT_FOUND")
    _check_version(fact, expected_version)
    old_display = _display(fact, ctx)
    fact.status = apply_fact_event(fact.status, "archive")
    fact.current_version += 1
    _snapshot(
        session,
        clock,
        ctx,
        fact,
        change_kind="archived",
        source_type="owner_entry",
        source_ref=None,
        reason=reason,
    )
    candidates.recompute_relations(session, ctx, fact.key, fact)
    _audit(session, clock, ctx, "fact.archived", fact, source_type="owner_entry")
    _propagate(
        session,
        clock,
        ctx,
        fact,
        "archived",
        old_version=fact.current_version - 1,
        old_display=old_display,
    )
    session.commit()
    return fact


def restore_fact(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    fact_id: uuid.UUID,
    *,
    expected_version: int,
) -> BusinessFact:
    """Bring an archived fact back as ``unverified``; it must be verified again."""
    _require(ctx, "knowledge.verify")
    fact = repo.get_fact(session, ctx, fact_id, lock=True)
    if fact is None:
        raise AppError("NOT_FOUND")
    _check_version(fact, expected_version)
    new_status = apply_fact_event(fact.status, "restore")
    if repo.get_live_fact_by_key(session, ctx, fact.key) is not None:
        raise AppError("CONFLICT_STATE", reason="key_exists", key=fact.key)
    try:
        with session.begin_nested():
            fact.status = new_status
            fact.current_version += 1
            session.flush()
    except IntegrityError as exc:
        raise AppError("CONFLICT_STATE", reason="key_exists", key=fact.key) from exc
    _snapshot(
        session,
        clock,
        ctx,
        fact,
        change_kind="restored",
        source_type="owner_entry",
        source_ref=None,
        reason=None,
    )
    candidates.recompute_relations(session, ctx, fact.key, fact)
    _audit(session, clock, ctx, "fact.restored", fact, source_type="owner_entry")
    session.commit()
    return fact


# --- candidates -----------------------------------------------------------------------------


def accept_candidate(
    session: Session, clock: Clock, ctx: WorkspaceContext, candidate_id: uuid.UUID
) -> BusinessFact:
    """Apply a pending candidate as a verified fact value (``knowledge.verify``)."""
    _require(ctx, "knowledge.verify")
    candidate = repo.get_candidate(session, ctx, candidate_id, lock=True)  # candidate first
    if candidate is None:
        raise AppError("NOT_FOUND")
    # Resolve first: applying the value would otherwise supersede this very candidate (it then
    # equals the fact). Raises CONFLICT_STATE unless it is still pending. All in one transaction.
    candidates.resolve(candidate, "accept", _user_id(ctx), clock.now())
    workspace = _workspace(session, ctx)
    fact = repo.get_live_fact_by_key(session, ctx, candidate.fact_key, lock=True)  # then fact
    ref = str(candidate.id)
    if fact is None:
        spec = _spec_for_key(
            load_template(workspace.business_category),
            candidate.fact_key,
            value_type=candidate.value_type,
            label=None,
            criticality=None,
            allow_missing_label=True,
        )
        fact = _insert_fact(
            session,
            clock,
            ctx,
            workspace,
            key=candidate.fact_key,
            spec=spec,
            value=candidate.proposed_value,
            verified=True,
            valid_from=None,
            valid_until=None,
            source_type="candidate_accepted",
            source_ref=ref,
            reason=None,
        )
    else:
        if fact.value_type != candidate.value_type:
            raise AppError("CONFLICT_STATE", reason="value_type_changed", key=fact.key)
        fact = _apply_change(
            session,
            clock,
            ctx,
            fact,
            value=candidate.proposed_value,
            valid_from=UNSET,
            valid_until=UNSET,
            source_type="candidate_accepted",
            source_ref=ref,
            reason=None,
        )
    audit.record(
        session,
        ctx,
        "fact_candidate.accepted",
        "fact_candidate",
        candidate.id,
        {
            "key": candidate.fact_key,
            "relation": candidate.relation,
            "source_type": candidate.source_type,
            "fact_version": fact.current_version,
        },
        clock=clock,
    )
    session.commit()
    return fact


def reject_candidate(
    session: Session, clock: Clock, ctx: WorkspaceContext, candidate_id: uuid.UUID
) -> FactCandidate:
    """Reject a pending candidate. If it was a ``contest`` the fact is usable again."""
    _require(ctx, "knowledge.verify")
    candidate = repo.get_candidate(session, ctx, candidate_id, lock=True)
    if candidate is None:
        raise AppError("NOT_FOUND")
    candidates.resolve(candidate, "reject", _user_id(ctx), clock.now())
    audit.record(
        session,
        ctx,
        "fact_candidate.rejected",
        "fact_candidate",
        candidate.id,
        {
            "key": candidate.fact_key,
            "relation": candidate.relation,
            "source_type": candidate.source_type,
        },
        clock=clock,
    )
    session.commit()
    return candidate


# --- reads ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class UsableFact:
    """A usable fact, pre-rendered for LLM tasks (Phase 3 renders placeholders from these)."""

    fact_id: uuid.UUID
    key: str
    category: str
    label: dict[str, str]
    value_type: str
    value: dict[str, Any]
    display: str
    version: int
    criticality: str
    placeholder: str


def usable_facts(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    categories: tuple[str, ...] | None = None,
    on_date: date | None = None,
    locale: str | None = None,
) -> list[UsableFact]:
    """Only verified, live, in-window, uncontested facts (INV-02). ``on_date`` is a date in
    the workspace timezone; it defaults to today there."""
    today = on_date or usability.local_today(clock.now(), ctx.timezone)
    contested = repo.contested_keys(session, ctx)
    result: list[UsableFact] = []
    for fact in repo.list_facts(session, ctx, status="verified"):
        if categories is not None and fact.category not in categories:
            continue
        if not usability.is_usable(
            status=fact.status,
            valid_from=fact.valid_from,
            valid_until=fact.valid_until,
            today=today,
            contested=fact.key in contested,
        ):
            continue
        result.append(
            UsableFact(
                fact_id=fact.id,
                key=fact.key,
                category=fact.category,
                label=fact.label,
                value_type=fact.value_type,
                value=fact.value,
                display=_display(fact, ctx, locale),
                version=fact.current_version,
                criticality=fact.criticality,
                placeholder="{{fact:" + fact.key + "}}",
            )
        )
    return result


@dataclass(frozen=True)
class FactView:
    fact: BusinessFact
    state: str
    usable: bool
    display: str
    open_candidates_count: int
    source_type: str | None
    last_verified_by_name: str | None


def fact_views(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    facts: list[BusinessFact] | tuple[BusinessFact, ...],
    *,
    ui_locale: str,
) -> list[FactView]:
    """Facts with computed state, usability and display (in the user's UI locale)."""
    today = usability.local_today(clock.now(), ctx.timezone)
    contested = repo.contested_keys(session, ctx)
    counts = repo.pending_candidate_counts(session, ctx)
    sources: dict[uuid.UUID, str] = {}
    for fact in facts:
        version = repo.get_version(session, ctx, fact.id, fact.current_version)
        if version is not None:
            sources[fact.id] = version.source_type
    verifier_ids = [f.last_verified_by_user_id for f in facts if f.last_verified_by_user_id]
    names = identity_repo.member_names(session, ctx, verifier_ids)
    views = []
    for fact in facts:
        is_contested = fact.key in contested
        views.append(
            FactView(
                fact=fact,
                state=usability.display_state(
                    status=fact.status,
                    valid_from=fact.valid_from,
                    valid_until=fact.valid_until,
                    today=today,
                    contested=is_contested,
                ),
                usable=usability.is_usable(
                    status=fact.status,
                    valid_from=fact.valid_from,
                    valid_until=fact.valid_until,
                    today=today,
                    contested=is_contested,
                ),
                display=_display(fact, ctx, ui_locale),
                open_candidates_count=counts.get(fact.key, 0),
                source_type=sources.get(fact.id),
                last_verified_by_name=names.get(fact.last_verified_by_user_id)
                if fact.last_verified_by_user_id
                else None,
            )
        )
    return views


@dataclass(frozen=True)
class CandidateView:
    candidate: FactCandidate
    fact_label: dict[str, str]
    proposed_display: str
    current_display: str | None
    proposed_by_name: str | None


def candidate_views(
    session: Session,
    ctx: WorkspaceContext,
    items: list[FactCandidate] | tuple[FactCandidate, ...],
    *,
    ui_locale: str,
) -> list[CandidateView]:
    workspace = _workspace(session, ctx)
    template = load_template(workspace.business_category)
    live = {f.key: f for f in repo.list_facts(session, ctx) if f.status != "archived"}
    proposer_ids = [
        uuid.UUID(c.proposed_by_actor_id)
        for c in items
        if c.proposed_by_actor_type == "user" and c.proposed_by_actor_id
    ]
    names = identity_repo.member_names(session, ctx, proposer_ids)
    views = []
    for candidate in items:
        fact = live.get(candidate.fact_key)
        item = template.find(candidate.fact_key)
        label = (
            fact.label
            if fact
            else (dict(item.label) if item and item.key else _slug_label(candidate.fact_key))
        )
        proposer = (
            names.get(uuid.UUID(candidate.proposed_by_actor_id))
            if candidate.proposed_by_actor_type == "user" and candidate.proposed_by_actor_id
            else None
        )
        views.append(
            CandidateView(
                candidate=candidate,
                fact_label=label,
                proposed_display=format_value(
                    candidate.value_type, candidate.proposed_value, ui_locale, ctx.locale
                ),
                current_display=_display(fact, ctx, ui_locale) if fact else None,
                proposed_by_name=proposer,
            )
        )
    return views


def fact_view(
    session: Session, clock: Clock, ctx: WorkspaceContext, fact: BusinessFact, *, ui_locale: str
) -> FactView:
    return fact_views(session, clock, ctx, [fact], ui_locale=ui_locale)[0]


def candidate_view(
    session: Session, ctx: WorkspaceContext, candidate: FactCandidate, *, ui_locale: str
) -> CandidateView:
    return candidate_views(session, ctx, [candidate], ui_locale=ui_locale)[0]


@dataclass(frozen=True)
class VersionView:
    version: FactVersion
    display: str
    actor_name: str | None


def version_views(
    session: Session, ctx: WorkspaceContext, fact_id: uuid.UUID, *, ui_locale: str
) -> list[VersionView]:
    """Version history of a fact, newest first (the immutable snapshots, INV-17)."""
    fact = repo.get_fact(session, ctx, fact_id)
    if fact is None:
        raise AppError("NOT_FOUND")
    versions = repo.list_versions(session, ctx, fact_id)
    user_ids = [uuid.UUID(v.actor_id) for v in versions if v.actor_type == "user" and v.actor_id]
    names = identity_repo.member_names(session, ctx, user_ids)
    return [
        VersionView(
            version=v,
            display=format_value(fact.value_type, v.value, ui_locale, ctx.locale),
            actor_name=names.get(uuid.UUID(v.actor_id))
            if v.actor_type == "user" and v.actor_id
            else None,
        )
        for v in versions
    ]


@dataclass(frozen=True)
class ChecklistItem:
    item: TemplateItem
    status: str  # missing | present (patterns) | unverified | verified | contested | expired | ...
    facts: tuple[BusinessFact, ...]


def template_checklist(
    session: Session, clock: Clock, ctx: WorkspaceContext
) -> list[ChecklistItem]:
    """Template items compared with the workspace's live facts (drives the checklist)."""
    workspace = _workspace(session, ctx)
    template = load_template(workspace.business_category)
    today = usability.local_today(clock.now(), ctx.timezone)
    contested = repo.contested_keys(session, ctx)
    live = [f for f in repo.list_facts(session, ctx) if f.status != "archived"]
    by_key = {f.key: f for f in live}
    result: list[ChecklistItem] = []
    for item in template.items:
        if item.key is not None:
            fact = by_key.get(item.key)
            if fact is None:
                result.append(ChecklistItem(item, "missing", ()))
                continue
            state = usability.display_state(
                status=fact.status,
                valid_from=fact.valid_from,
                valid_until=fact.valid_until,
                today=today,
                contested=fact.key in contested,
            )
            result.append(ChecklistItem(item, state, (fact,)))
        else:
            matching = tuple(f for f in live if item.matches(f.key))
            result.append(ChecklistItem(item, "present" if matching else "missing", matching))
    return result
