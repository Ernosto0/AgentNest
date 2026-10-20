"""AI drafts: the generate request and the phases of the ``generate_content`` job
(workflows.md section E step 1, plan.md G5 to G7).

    [T1] ``request``: the draft, the queued ``agent_runs`` row and the job, in one transaction
    [T1] ``prepare``: read the draft and the usable facts (read-only)
         the model PROPOSES a draft (``run_task``, with **no transaction open**)
    [T3] ``store``: re-check the draft, render the placeholders, validate the claims, save

The stored caption is the *rendered* text (G6): ``caption_template`` goes through ``render`` with
the usable facts, the hashtags are appended by code, and the claim validator then checks the
result. Issues (an invented price, a promise no fact backs) are stored inline; they do not stop
the draft because a person reviews it, but they block submission. A generation that is late,
because the owner edited or submitted the draft meanwhile, is discarded (nothing of the owner's
is overwritten). An LLM failure leaves the manual draft as it is.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.models import AgentRun
from app.ai.runner import create_queued_run
from app.ai.runtime import get_provider
from app.ai.schemas import (
    MAX_HASHTAGS,
    CommercialClaim,
    ContentProposal,
    DraftContentInput,
    DraftFact,
)
from app.ai.tasks.draft_content import TASK, clean_hashtag
from app.audit import service as audit
from app.content import grounding, service, transitions
from app.content.models import ContentItem
from app.content.payload import GenerateContentPayload, generate_job_key
from app.content.schemas import empty_validation
from app.core.clock import Clock
from app.core.context import ActorRef, WorkspaceContext
from app.identity import service as identity_service
from app.identity.models import Workspace
from app.inbox.context import INTERNAL_CATEGORIES, INTERNAL_KEYS
from app.jobs.queue import enqueue
from app.knowledge import impact
from app.knowledge import service as knowledge_service
from app.knowledge.render import RenderedSpan, RenderError, RenderResult, render
from app.knowledge.service import UsableFact

SUBJECT_TYPE = transitions.SUBJECT_TYPE
GENERATED_BY = "generate_content"
# Why a run ended without a draft (``agent_runs.error_code``), besides the runner's own.
CONTENT_CHANGED = "CONTENT_CHANGED"  # the draft was edited or submitted before the job started
INITIAL_TITLE_CHARS = 60

APPLIED = "applied"
DISCARDED = "discarded"
FAILED = "failed"


def initial_title(objective: str) -> str:
    """The internal label of a draft until the model proposes one (and the owner has not
    renamed it): the objective on one line."""
    line = " ".join(objective.split())
    if len(line) <= INITIAL_TITLE_CHARS:
        return line
    return line[: INITIAL_TITLE_CHARS - 1].rstrip() + "…"


# --- the request -----------------------------------------------------------------------------


def stage_request(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    content_type: str,
    objective: str,
    notes: str | None,
    client_request_id: str,
) -> tuple[ContentItem, bool]:
    """A draft with a queued generation, **without committing** (the caller owns the
    transaction: the command executor runs inside the command's). Returns ``(item, created)``;
    the same ``client_request_id`` by the same author returns the first draft and ``False``
    (G7)."""
    user_id = service.author_id(ctx)
    existing = service.existing_for_request(session, ctx, user_id, client_request_id)
    if existing is not None:
        return existing, False

    now = clock.now()
    correlation_id = uuid.uuid4()
    try:
        # The run and the draft are one unit: if the unique key says we lost a race, the run
        # this attempt inserted goes with it.
        with session.begin_nested():
            run = create_queued_run(
                session,
                clock,
                get_provider(),
                ctx,
                TASK,
                {
                    "content_type": content_type,
                    "objective_chars": len(objective),
                    "notes": notes,
                },
                correlation_id,
            )
            item = ContentItem(
                workspace_id=ctx.workspace_id,
                content_type=content_type,
                status="draft",
                version=1,
                title=initial_title(objective),
                objective=objective,
                overlay_text_suggestions=[],
                validation=empty_validation(),
                agent_run_id=run.id,
                created_by_user_id=user_id,
                client_request_id=client_request_id,
                is_simulated=False,  # set from the target account at submit
                created_at=now,
                updated_at=now,
            )
            session.add(item)
            session.flush()
    except IntegrityError:  # the same request arrived twice at once
        winner = service.existing_for_request(session, ctx, user_id, client_request_id)
        if winner is None:
            raise
        return winner, False
    audit.record(
        session,
        ctx,
        "content.created",
        "content_item",
        item.id,
        {"content_type": content_type, "version": 1, "source": "ai", "agent_run_id": run.id},
        is_simulated=False,
        correlation_id=correlation_id,
        clock=clock,
    )
    enqueue(
        session,
        "generate_content",
        GenerateContentPayload(content_id=item.id, version=item.version),
        workspace_id=ctx.workspace_id,
        correlation_id=correlation_id,
        dedup_key=generate_job_key(item.id),
        clock=clock,
    )
    return item, True


def request(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    *,
    content_type: str,
    objective: str,
    notes: str | None,
    client_request_id: str,
) -> tuple[ContentItem, bool]:
    """``stage_request`` and commit (``POST /content-items/generate``)."""
    result = stage_request(
        session,
        clock,
        ctx,
        content_type=content_type,
        objective=objective,
        notes=notes,
        client_request_id=client_request_id,
    )
    session.commit()
    return result


# --- phase 1: what the model is shown ---------------------------------------------------------


def offer(usable: Iterable[UsableFact]) -> list[UsableFact]:
    """The facts the model may quote and the renderer will accept: the usable ones except the
    internal settings, and without prices when the business does not share them (an unknown
    policy counts as ``do_not_share``)."""
    facts = list(usable)
    policy = next((f for f in facts if f.key == "policy.price_disclosure"), None)
    share = policy is not None and policy.value.get("value") == "share"
    return [
        f
        for f in facts
        if f.category not in INTERNAL_CATEGORIES
        and f.key not in INTERNAL_KEYS
        and (share or f.category != "pricing")
    ]


def offered_facts(session: Session, clock: Clock, ctx: WorkspaceContext) -> list[UsableFact]:
    return offer(knowledge_service.usable_facts(session, clock, ctx, locale=ctx.locale))


def _label(fact: UsableFact, language: str) -> str:
    return fact.label.get(language) or fact.label.get("tr") or fact.label.get("en") or fact.key


def build_input(
    offered: Iterable[UsableFact],
    *,
    content_type: str,
    objective: str,
    notes: str | None,
    language: str,
    brand_voice: str | None,
) -> DraftContentInput:
    """What the model is shown (pure, so the evals build exactly the same input)."""
    return DraftContentInput(
        content_type=content_type,
        objective=objective,
        notes=notes,
        language=language,
        facts=[
            DraftFact(
                key=f.key,
                label=_label(f, language),
                value_type=f.value_type,
                value_display=f.display,
                placeholder=f.placeholder,
            )
            for f in offered
        ],
        brand_voice=brand_voice,
    )


def _brand_voice(session: Session, clock: Clock, ctx: WorkspaceContext) -> str | None:
    usable = knowledge_service.usable_facts(
        session, clock, ctx, categories=("brand",), locale=ctx.locale
    )
    voice = next((f for f in usable if f.key == "brand.voice_guidelines"), None)
    if voice is None:
        return None
    text = voice.value.get(ctx.locale) or voice.value.get("tr") or voice.value.get("en")
    return str(text) if text else None


@dataclass(frozen=True)
class Prepared:
    ctx: WorkspaceContext
    item_id: uuid.UUID
    version: int  # the version the generation was asked for
    initial_title: str
    run_id: uuid.UUID
    correlation_id: uuid.UUID | None
    task_input: DraftContentInput
    # The output of a run that succeeded before a crash kept it from being stored: no second
    # model call is needed (and none is paid for).
    proposal: ContentProposal | None


def _mark_stored(run: AgentRun, clock: Clock, **extra: Any) -> None:
    run.input_snapshot = {
        **(run.input_snapshot or {}),
        "stored_at": clock.now().isoformat(),
        **extra,
    }


def prepare(
    session: Session, clock: Clock, workspace_id: uuid.UUID, payload: GenerateContentPayload
) -> Prepared | None:
    """Read what the model needs. ``None``: nothing to do (replayed job, draft gone or already
    changed; a run that never started is closed as ``CONTENT_CHANGED``)."""
    workspace = session.get(Workspace, workspace_id)
    item = session.scalar(
        select(ContentItem).where(
            ContentItem.workspace_id == workspace_id, ContentItem.id == payload.content_id
        )
    )
    if workspace is None or item is None or item.agent_run_id is None:
        return None
    run = session.scalar(
        select(AgentRun)
        .where(AgentRun.workspace_id == workspace_id, AgentRun.id == item.agent_run_id)
        .with_for_update()
    )
    if run is None or "stored_at" in (run.input_snapshot or {}):
        return None  # a replay: this generation is over

    proposal: ContentProposal | None = None
    if run.status == "succeeded" and run.output:
        try:
            proposal = ContentProposal.model_validate(run.output)
        except ValidationError:
            proposal = None
    stale = item.status != "draft" or item.version != payload.version
    if stale and proposal is None:
        run.status, run.error_code = "failed", CONTENT_CHANGED
        run.completed_at = clock.now()
        return None

    ctx = identity_service.workspace_context(workspace, ActorRef.system(GENERATED_BY), None)
    snapshot = run.input_snapshot or {}
    facts = offered_facts(session, clock, ctx)
    task_input = build_input(
        facts,
        content_type=item.content_type,
        objective=item.objective or "",
        notes=str(snapshot["notes"]) if snapshot.get("notes") else None,
        language=ctx.locale,
        brand_voice=_brand_voice(session, clock, ctx),
    )
    return Prepared(
        ctx=ctx,
        item_id=item.id,
        version=payload.version,
        initial_title=initial_title(item.objective or ""),
        run_id=run.id,
        correlation_id=run.correlation_id,
        task_input=task_input,
        proposal=proposal,
    )


# --- phase 3: render, validate, save ---------------------------------------------------------


@dataclass(frozen=True)
class Rendered:
    caption: str | None
    overlay: list[str]
    used: tuple[tuple[uuid.UUID, int], ...]
    used_keys: frozenset[str]
    # The rendered spans of each text by field name, indexing the stored text (the evals check
    # them against the validator independently of the matcher).
    spans: dict[str, tuple[RenderedSpan, ...]]


@dataclass(frozen=True)
class Assembled:
    rendered: Rendered
    checked: grounding.Grounding
    unbacked: tuple[str, ...]


def _shift(spans: tuple[RenderedSpan, ...], by: int) -> tuple[RenderedSpan, ...]:
    return tuple(replace(s, start=s.start - by, end=s.end - by) for s in spans)


def _render_all(
    proposal: ContentProposal, facts: list[UsableFact], language: str, content_type: str
) -> Rendered | list[RenderError]:
    """The caption (feed) or the suggestions (story) with every placeholder replaced, hashtags
    appended by code. All or nothing: a placeholder that cannot be rendered fails the draft."""
    templates: dict[str, str] = {}
    if content_type == "feed_image" and proposal.caption_template:
        templates["caption"] = proposal.caption_template
    elif content_type == "story_image":
        for index, suggestion in enumerate(proposal.overlay_text_suggestions):
            templates[f"overlay_text_suggestions.{index}"] = suggestion
    results: dict[str, RenderResult] = {}
    errors: list[RenderError] = []
    for name, template in templates.items():
        result = render(template, facts, language)
        results[name] = result
        errors.extend(result.errors)
    if errors:
        return errors

    used: dict[tuple[uuid.UUID, int], None] = {}
    keys: set[str] = set()
    spans: dict[str, tuple[RenderedSpan, ...]] = {}
    texts: dict[str, str] = {}
    for name, result in results.items():
        used.update(dict.fromkeys(result.used))
        keys.update(result.used_keys)
        texts[name] = result.text.strip()
        spans[name] = _shift(result.spans, len(result.text) - len(result.text.lstrip()))
    caption: str | None = None
    if "caption" in texts:
        tags: list[str] = []
        for raw in proposal.hashtags:
            tag = clean_hashtag(raw)
            if tag and tag not in tags:
                tags.append(tag)
        suffix = "\n\n" + " ".join(f"#{t}" for t in tags[:MAX_HASHTAGS]) if tags else ""
        caption = texts["caption"] + suffix
    overlay = [t for name, t in texts.items() if name.startswith("overlay_text_suggestions.")]
    return Rendered(caption, overlay, tuple(used), frozenset(keys), spans)


def _unbacked(claims: list[CommercialClaim], rendered_keys: frozenset[str]) -> list[str]:
    """The commercial claims that no fact the text really renders backs (code decides, not the
    model: a ``fact_key`` the model names but the text does not use backs nothing)."""
    return [c.claim for c in claims if c.fact_key is None or c.fact_key not in rendered_keys]


def assemble(
    proposal: ContentProposal, usable: Iterable[UsableFact], *, language: str, content_type: str
) -> Assembled | list[RenderError]:
    """The model's proposal as the text to store: render, append the hashtags, validate the
    claims (pure; the job and the evals run exactly this).

    Rendering and grounding use the **offered** facts only: a value the model typed is grounded
    by a fact it was allowed to quote, so a price the business does not share never passes as
    "equal to a verified fact" just because the model typed it.
    """
    offered = offer(usable)
    rendered = _render_all(proposal, offered, language, content_type)
    if isinstance(rendered, list):
        return rendered
    unbacked = _unbacked(proposal.commercial_claims, rendered.used_keys)
    checked = grounding.analyse(
        offered,
        language,
        grounding.texts_of(rendered.caption, rendered.overlay),
        rendered=rendered.used,
        unbacked_claims=unbacked,
    )
    return Assembled(rendered, checked, tuple(unbacked))


def _audit(
    session: Session,
    clock: Clock,
    prepared: Prepared,
    item: ContentItem | None,
    result: str,
    **details: Any,
) -> None:
    audit.record(
        session,
        prepared.ctx,
        "content.generated",
        "content_item",
        prepared.item_id,
        {
            "result": result,
            "agent_run_id": prepared.run_id,
            "content_type": prepared.task_input.content_type,
            "version": item.version if item is not None else prepared.version,
            **details,
        },
        correlation_id=prepared.correlation_id,
        clock=clock,
    )


def record_failure(session: Session, clock: Clock, prepared: Prepared, error_code: str) -> None:
    """The model produced nothing usable (the runner has marked the run failed): the draft stays
    a manual draft. Audit only."""
    _audit(session, clock, prepared, None, FAILED, error_code=error_code)


def store(session: Session, clock: Clock, prepared: Prepared, proposal: ContentProposal) -> str:
    """Save ``proposal`` on the draft unless it has moved on. No commit. Returns ``APPLIED``,
    ``DISCARDED`` or ``FAILED`` (a placeholder could not be rendered)."""
    ctx = prepared.ctx
    run = session.scalar(
        select(AgentRun)
        .where(AgentRun.workspace_id == ctx.workspace_id, AgentRun.id == prepared.run_id)
        .with_for_update()
    )
    item = service.get_item(session, ctx, prepared.item_id, lock=True)
    if run is None:
        return DISCARDED

    # Still the draft that was asked for? An edit made while the model ran (a new version), or
    # a submission, means the owner took over: their text is never overwritten (G7).
    if item.status != "draft" or item.version != prepared.version:
        _mark_stored(run, clock, discarded=True)
        _audit(session, clock, prepared, item, DISCARDED)
        return DISCARDED

    usable = knowledge_service.usable_facts(session, clock, ctx, locale=ctx.locale)  # fresh
    assembled = assemble(proposal, usable, language=ctx.locale, content_type=item.content_type)
    if isinstance(assembled, list):
        codes = sorted({e.code for e in assembled})
        run.status, run.error_code = "failed", codes[0]
        run.validation_errors = [{"code": e.code, "key": e.key} for e in assembled]
        run.completed_at = clock.now()
        _audit(session, clock, prepared, item, FAILED, error_code=codes[0])
        return FAILED

    rendered, checked = assembled.rendered, assembled.checked
    changes: dict[str, Any] = {
        "caption": rendered.caption,
        "overlay_text_suggestions": rendered.overlay,
        "validation": checked.report,
    }
    if item.title == prepared.initial_title and proposal.title.strip():
        changes["title"] = proposal.title.strip()  # the owner has not renamed it
    if item.visual_notes is None and proposal.visual_notes.strip():
        changes["visual_notes"] = proposal.visual_notes.strip()
    transitions.apply(session, clock, ctx, item, "edit", **changes)
    impact.replace_references(session, ctx, SUBJECT_TYPE, item.id, checked.references)
    _mark_stored(run, clock)
    _audit(
        session,
        clock,
        prepared,
        item,
        APPLIED,
        blocking_issues=len(checked.blocking),
        references=len(checked.references),
    )
    return APPLIED
