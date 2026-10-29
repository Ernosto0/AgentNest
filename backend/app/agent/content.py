"""Owner-only content tools; existing content rules and ledger own publication."""

import json
import uuid
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.agent import delegation, owner_tasks
from app.agent.grounding import ReplyValidationArgs, validate_reply
from app.agent.models import ACTIVE_RUN_STATES, AgentAction, AgentEvent, AgentSession, OwnerTask
from app.agent.repository import admit_action, scoped_thread
from app.agent.tools.broker import BrokerContext, ToolInputError
from app.content import grounding, scheduling, service, transitions
from app.content.models import ContentItem, MediaAsset
from app.content.payload import approval_payload, approval_summary
from app.core.canonical import canonical_json, payload_hash
from app.core.clock import Clock
from app.core.config import get_settings
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity.permissions import has_permission
from app.knowledge import impact
from app.knowledge.models import BusinessFact, FactReference
from app.operations.models import Operation

CONTENT_ACTIONS = ("content.prepare", "content.schedule", "content.publish", "content.cancel")


def _references(
    db: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    item: ContentItem,
    claims: Sequence[tuple[uuid.UUID, int]],
) -> list[list[Any]]:
    """Bind noncritical placeholder sources as well as sources found by claim scanning."""
    from app.agent.knowledge import visible_predicate

    references = set(claims)
    references.update(
        (fact_id, version)
        for fact_id, version in db.execute(
            select(FactReference.fact_id, FactReference.fact_version).where(
                FactReference.workspace_id == item.workspace_id,
                FactReference.referrer_type == "content_item",
                FactReference.referrer_id == item.id,
            )
        )
    )
    for fact_id, version in references:
        if (
            db.scalar(
                select(BusinessFact.id).where(
                    BusinessFact.id == fact_id,
                    BusinessFact.workspace_id == item.workspace_id,
                    BusinessFact.current_version == version,
                    visible_predicate(db, clock, ctx),
                )
            )
            is None
        ):
            raise AppError("APPROVAL_STALE")
    return sorted([[str(fid), version] for fid, version in references])


def publication_current(db: Session, clock: Clock, item: ContentItem, action: AgentAction) -> bool:
    """Keep fact versions bound even if an edit preserves a fact's displayed value."""
    if not action.content_intent or item.version != action.version:
        return False
    from app.inbox.system import system_context

    ctx = system_context(db, item.workspace_id, "agent.content")
    if ctx is None:
        return False
    checked = grounding.check(
        db, clock, ctx, grounding.texts_of(item.caption, item.overlay_text_suggestions)
    )
    try:
        return (
            not checked.blocking
            and _references(db, clock, ctx, item, checked.references)
            == action.content_intent["fact_refs"]
        )
    except AppError:
        return False


class Read(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["content", "media"]
    cursor: uuid.UUID | None = None
    limit: int = Field(default=5, ge=1, le=10)


class Prepare(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content_type: Literal["feed_image", "story_image"]
    title: str = Field(min_length=1, max_length=150)
    media_asset_id: uuid.UUID | None
    caption: ReplyValidationArgs | None


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content_id: uuid.UUID
    expected_version: int = Field(ge=1)


class Schedule(Target):
    local_date: date
    local_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class Clarify(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=500)


def _task(db: Session, context: BrokerContext) -> OwnerTask:
    thread = scoped_thread(
        db, context.workspace.workspace_id, context.account_id, context.thread_id, lock=True
    )
    task = owner_tasks.for_thread(db, thread)
    current = owner_tasks.current_context(db, task)
    if context.source != "owner_task" or current != context.workspace:
        raise ToolInputError("owner task authority required")
    return task


def clarify(db: Session, clock: Clock, context: BrokerContext, args: BaseModel) -> dict[str, Any]:
    task = _task(db, context)
    question = Clarify.model_validate(args).question.strip()
    if not question or len(task.answers) >= 8:
        raise ToolInputError("question limit or blank question")
    task.clarification = task.clarification or question
    task.updated_at = clock.now()
    return {"status": "needs_clarification", "question": task.clarification}


def read(db: Session, clock: Clock, context: BrokerContext, args: BaseModel) -> dict[str, Any]:
    task = _task(db, context)
    if not has_permission(context.workspace.role, "content.edit"):
        return {"error": "FORBIDDEN"}
    request = Read.model_validate(args)
    model = ContentItem if request.kind == "content" else MediaAsset
    query = select(model).where(model.workspace_id == context.workspace.workspace_id)
    if model is ContentItem:
        query = query.where(
            or_(
                ContentItem.social_account_id.is_(None),
                ContentItem.social_account_id == context.account_id,
            )
        )
    else:
        query = query.where(MediaAsset.status == "ready")
    if request.cursor:
        query = query.where(model.id > request.cursor)
    rows = cast(
        list[ContentItem | MediaAsset],
        list(db.scalars(query.order_by(model.id).limit(request.limit + 1)).all()),
    )
    refs = dict(task.read_refs)
    items = []
    for row in rows[: request.limit]:
        if isinstance(row, ContentItem):
            refs[f"content:{row.id}"] = row.version
            items.append(
                {
                    "id": str(row.id),
                    "version": row.version,
                    "selected": task.read_refs.get("selected_content_id") == str(row.id),
                    "title": row.title[:150],
                    "caption": (row.caption or "")[:900],
                    "status": row.status,
                    "media_asset_id": str(row.media_asset_id) if row.media_asset_id else None,
                }
            )
        else:
            refs[f"media:{row.id}"] = row.sha256
            items.append(
                {
                    "id": str(row.id),
                    "sha256": row.sha256,
                    "selected": task.read_refs.get("selected_media_id") == str(row.id),
                    "filename": (row.original_filename or "")[:150],
                    "width": row.width,
                    "height": row.height,
                }
            )
    # Bounded durable read receipts prevent guessed IDs/aliases becoming selected assets.
    if len(refs) > 200:
        selections = {
            key: value for key, value in refs.items() if not key.startswith(("content:", "media:"))
        }
        receipts = [
            (key, value) for key, value in refs.items() if key.startswith(("content:", "media:"))
        ]
        refs = {**selections, **dict(receipts[-(200 - len(selections)) :])}
    task.read_refs = refs
    return {
        "items": items,
        "next_cursor": str(rows[request.limit - 1].id) if len(rows) > request.limit else None,
    }


def _item(db: Session, context: BrokerContext, request: Target) -> ContentItem:
    task = _task(db, context)
    item = service.get_item(db, context.workspace, request.content_id, lock=True)
    if item.social_account_id not in (None, context.account_id):
        raise ToolInputError("wrong account")
    if not _selected(db, task, "content", item.id):
        raise ToolInputError("ambiguous content selection; ask the requester to select content")
    if (
        item.version != request.expected_version
        or task.read_refs.get(f"content:{item.id}") != item.version
    ):
        raise ToolInputError("read current content version first")
    return item


def _selected(db: Session, task: OwnerTask, kind: str, selected: uuid.UUID) -> bool:
    if task.read_refs.get(f"selected_{kind}_id") == str(selected):
        return True
    text = task.request_text + " " + " ".join(answer["text"] for answer in task.answers)
    if str(selected) in text:
        return True
    if kind == "media":
        count = db.scalar(
            select(func.count(MediaAsset.id)).where(
                MediaAsset.workspace_id == task.workspace_id, MediaAsset.status == "ready"
            )
        )
    else:
        count = db.scalar(
            select(func.count(ContentItem.id)).where(
                ContentItem.workspace_id == task.workspace_id,
                or_(
                    ContentItem.social_account_id.is_(None),
                    ContentItem.social_account_id == task.social_account_id,
                ),
            )
        )
    return count == 1


def _action(
    db: Session,
    clock: Clock,
    context: BrokerContext,
    kind: str,
    target: str,
    intent: dict[str, Any],
    *,
    version: int = 1,
    exact_hash: str | None = None,
) -> AgentAction:
    task = _task(db, context)
    thread = scoped_thread(db, task.workspace_id, task.social_account_id, task.thread_id)
    goal = db.scalar(
        select(AgentSession).where(
            AgentSession.thread_id == thread.id, AgentSession.status.in_(ACTIVE_RUN_STATES)
        )
    )
    event = db.scalar(
        select(AgentEvent).where(
            AgentEvent.thread_id == thread.id, AgentEvent.cursor == thread.event_cursor
        )
    )
    if goal is None or event is None:
        raise ToolInputError("no active owner task")
    action = admit_action(
        db,
        workspace_id=task.workspace_id,
        account_id=context.account_id,
        thread_id=thread.id,
        session_id=goal.id,
        source_event_id=event.id,
        action_type=kind,
        target_ref=target,
        semantic_slot=f"{kind}:v{version}",
        payload_hash=exact_hash or payload_hash(intent),
        clock=clock,
    )
    if action.content_intent is None:
        action.content_intent = intent
        action.version = version
        action.ownership_generation = thread.ownership_generation
        decision = delegation.authorize_action(
            db,
            clock,
            context.workspace,
            action.id,
            source="owner_task",
            requester_user_id=task.requester_user_id,
            target_owned=True,
            visibility_allowed=True,
            claims_valid=True,
            quota_available=True,
        )
        if decision.kind not in {"automatic", "ask"}:
            action.status, action.outcome_code = "cancelled", decision.reason
    return action


def prepare(db: Session, clock: Clock, context: BrokerContext, args: BaseModel) -> dict[str, Any]:
    request = Prepare.model_validate(args)
    task = _task(db, context)
    if request.media_asset_id is None:
        return {
            "status": "needs_clarification",
            "reason": "select_existing_media",
            "use_tool": "task.clarify",
        }
    asset = db.scalar(
        select(MediaAsset).where(
            MediaAsset.workspace_id == task.workspace_id,
            MediaAsset.id == request.media_asset_id,
            MediaAsset.status == "ready",
        )
    )
    if asset is None or task.read_refs.get(f"media:{asset.id}") != asset.sha256:
        raise ToolInputError("read and select ready media first")
    if not _selected(db, task, "media", asset.id):
        return {
            "status": "needs_clarification",
            "reason": "ambiguous_media",
            "use_tool": "task.clarify",
        }
    if request.content_type == "feed_image" and request.caption is None:
        return {
            "status": "needs_clarification",
            "reason": "caption_required",
            "use_tool": "task.clarify",
        }
    if request.content_type == "story_image" and request.caption is not None:
        raise ToolInputError("stories have no caption")
    if request.caption:
        if request.caption.owner_answer or request.caption.customer_clarification:
            raise ToolInputError("private source cannot authorize published content")
        checked = validate_reply(db, clock, context, request.caption)
        if not checked.valid:
            return {"valid": False, "errors": list(checked.errors)}
    intent = {
        "request": request.model_dump(mode="json"),
        "media_sha256": asset.sha256,
        "rendered_caption": checked.text if request.caption else None,
    }
    action = _action(db, clock, context, "content.prepare", str(task.id), intent)
    if action.status == "authorized":
        execute(db, clock, action)
    return result(db, action)


def _publish_intent(
    db: Session,
    clock: Clock,
    context: BrokerContext,
    item: ContentItem,
    schedule: service.ScheduleRequest,
) -> dict[str, Any]:
    checked = service._check(
        db,
        clock,
        get_settings(),
        context.workspace,
        item,
        schedule,
        needs_approval=False,
        account_id=context.account_id,
    )
    ready = service._require_valid(checked, context.workspace.locale)
    references = _references(db, clock, context.workspace, item, ready.claims.references)
    payload = approval_payload(
        item,
        version=item.version,
        social_account_id=context.account_id,
        media_sha256=ready.media.sha256,
        scheduled_at=ready.resolved.scheduled_at,
        fact_versions=references,
    )
    return {
        "payload": json.loads(canonical_json(payload)),
        "schedule_input": ready.resolved.input,
        "fact_refs": references,
        "deadline": (
            ready.resolved.scheduled_at + service._max_delay(db, context.workspace)
        ).isoformat(),
    }


def _deadline(db: Session, clock: Clock, action: AgentAction) -> None:
    if action.content_intent is None:
        raise AppError("APPROVAL_STALE")
    deadline = datetime.fromisoformat(action.content_intent["deadline"])
    action.execute_before = deadline
    if action.policy_grant:
        action.policy_grant = {**action.policy_grant, "execute_before": deadline.isoformat()}
    if action.approval_id:
        from app.approvals.models import Approval

        approval = db.get(Approval, action.approval_id)
        if approval:
            approval.execute_before = deadline
            instant = datetime.fromisoformat(
                action.content_intent["payload"]["scheduled_at"].replace("Z", "+00:00")
            )
            approval.expires_at = min(
                clock.now() + timedelta(hours=24), instant if instant > clock.now() else deadline
            )


def schedule(db: Session, clock: Clock, context: BrokerContext, args: BaseModel) -> dict[str, Any]:
    request = Schedule.model_validate(args)
    item = _item(db, context, request)
    if item.status != "draft":
        raise ToolInputError("draft required")
    intent = _publish_intent(
        db,
        clock,
        context,
        item,
        service.ScheduleRequest(local_date=request.local_date, local_time=request.local_time),
    )
    action = _action(
        db,
        clock,
        context,
        "content.schedule",
        str(item.id),
        intent,
        version=item.version,
        exact_hash=payload_hash(intent["payload"]),
    )
    action.payload_ref = item.id
    _deadline(db, clock, action)
    if action.status == "authorized":
        execute(db, clock, action)
    if action.outcome_code and action.outcome_code.startswith("publication:"):
        publication = db.get(AgentAction, uuid.UUID(action.outcome_code.split(":", 1)[1]))
        if publication is not None:
            return {"schedule_action_id": str(action.id), **result(db, publication)}
    return result(db, action)


def publish(db: Session, clock: Clock, context: BrokerContext, args: BaseModel) -> dict[str, Any]:
    request = Target.model_validate(args)
    item = _item(db, context, request)
    if item.status != "draft":
        raise ToolInputError("draft required")
    intent = _publish_intent(db, clock, context, item, service.ScheduleRequest(publish_now=True))
    action = _publication(db, clock, context, item, intent)
    return result(db, action)


def _publication(
    db: Session, clock: Clock, context: BrokerContext, item: ContentItem, intent: dict[str, Any]
) -> AgentAction:
    action = _action(
        db,
        clock,
        context,
        "content.publish",
        str(item.id),
        intent,
        version=item.version,
        exact_hash=payload_hash(intent["payload"]),
    )
    action.payload_ref = item.id
    _deadline(db, clock, action)
    if action.status == "authorized":
        execute(db, clock, action)
    return action


def cancel(db: Session, clock: Clock, context: BrokerContext, args: BaseModel) -> dict[str, Any]:
    request = Target.model_validate(args)
    item = _item(db, context, request)
    intent = {"content_id": str(item.id), "version": item.version}
    action = _action(
        db, clock, context, "content.cancel", str(item.id), intent, version=item.version
    )
    action.payload_ref = item.id
    if action.status == "authorized":
        execute(db, clock, action)
    return result(db, action)


def execute(db: Session, clock: Clock, action: AgentAction) -> None:
    """Also called inside an explicit approval decision. Never commits or calls a provider."""
    delegation.fence_action(db, clock, action.workspace_id, action.id)
    thread = scoped_thread(db, action.workspace_id, action.social_account_id, action.thread_id)
    task = owner_tasks.for_thread(db, thread)
    ctx = owner_tasks.current_context(db, task)
    if ctx is None or not has_permission(
        ctx.role, delegation.REQUESTER_PERMISSIONS[action.action_type]
    ):
        raise AppError("APPROVAL_STALE")
    context = BrokerContext(ctx, action.social_account_id, thread.id, "owner_task", "owner_task")
    intent = action.content_intent
    if intent is None:
        raise AppError("APPROVAL_STALE")
    if action.action_type == "content.prepare":
        request = Prepare.model_validate(intent["request"])
        asset = db.get(MediaAsset, request.media_asset_id)
        if (
            asset is None
            or asset.workspace_id != ctx.workspace_id
            or asset.status != "ready"
            or asset.sha256 != intent["media_sha256"]
            or payload_hash(intent) != action.payload_hash
        ):
            raise AppError("APPROVAL_STALE")
        rendered = validate_reply(db, clock, context, request.caption) if request.caption else None
        if rendered and not rendered.valid:
            raise AppError("APPROVAL_STALE")
        if (rendered.text if rendered else None) != intent["rendered_caption"]:
            raise AppError("APPROVAL_STALE")
        item = ContentItem(
            workspace_id=ctx.workspace_id,
            social_account_id=context.account_id,
            content_type=request.content_type,
            status="draft",
            version=1,
            title=request.title,
            caption=rendered.text if rendered else None,
            media_asset_id=asset.id,
            created_by_user_id=task.requester_user_id,
            is_simulated=False,
            validation={},
            overlay_text_suggestions=[],
            created_at=clock.now(),
            updated_at=clock.now(),
        )
        from app.integrations.instagram.models import SocialAccount

        social = db.get(SocialAccount, context.account_id)
        item.is_simulated = bool(social and social.is_simulated)
        db.add(item)
        db.flush()
        claims = grounding.check(db, clock, ctx, grounding.texts_of(item.caption, []))
        item.validation = claims.report
        impact.replace_references(
            db,
            ctx,
            "content_item",
            item.id,
            sorted(set(claims.references) | set(rendered.facts if rendered else ())),
        )
        action.payload_ref = item.id
        task.read_refs = {
            **task.read_refs,
            f"content:{item.id}": item.version,
            "selected_content_id": str(item.id),
        }
    else:
        item = service.get_item(db, ctx, uuid.UUID(action.target_ref), lock=True)
        if item.version != action.version or item.social_account_id not in (
            None,
            context.account_id,
        ):
            raise AppError("APPROVAL_STALE")
        if action.action_type == "content.cancel":
            if (
                payload_hash({"content_id": str(item.id), "version": item.version})
                != action.payload_hash
            ):
                raise AppError("APPROVAL_STALE")
            service.apply_cancel(db, clock, ctx, item.id, expected_version=action.version)
        else:
            payload = intent["payload"]
            instant = datetime.fromisoformat(payload["scheduled_at"].replace("Z", "+00:00"))
            # Check current facts, media, account, content and quota against the exact receipt.
            checked = service._check(
                db,
                clock,
                get_settings(),
                ctx,
                item,
                None,
                needs_approval=False,
                account_id=context.account_id,
            )
            if not checked.result.ok or checked.media is None:
                raise AppError("APPROVAL_STALE")
            if scheduling.quota_forecast_exceeded(
                service._post_times(db, ctx, context.account_id, item.id, instant),
                instant,
                get_settings().publish_daily_limit,
            ):
                raise AppError("APPROVAL_STALE")
            current = approval_payload(
                item,
                version=item.version,
                social_account_id=context.account_id,
                media_sha256=checked.media.sha256,
                scheduled_at=instant,
                fact_versions=intent["fact_refs"],
            )
            if (
                payload_hash(current) != action.payload_hash
                or _references(db, clock, ctx, item, checked.claims.references)
                != intent["fact_refs"]
            ):
                raise AppError("APPROVAL_STALE")
            if action.action_type == "content.schedule":
                publication = _publication(db, clock, context, item, intent)
                action.outcome_code = f"publication:{publication.id}"
            else:
                if item.status != "draft":
                    raise AppError("APPROVAL_STALE")
                if action.policy_grant:
                    item.approval_id = delegation.record_effect_grant(
                        db,
                        clock,
                        ctx,
                        action_id=action.id,
                        subject_type="content_item",
                        subject_id=item.id,
                        subject_version=item.version,
                        payload=current,
                        summary=approval_summary(item, instant),
                        required_permission="content.approve",
                        expires_at=datetime.fromisoformat(intent["deadline"]),
                    )
                else:
                    item.approval_id = action.approval_id
                item.social_account_id = context.account_id
                item.origin, item.agent_action_id = "agent", action.id
                transitions.apply(
                    db,
                    clock,
                    ctx,
                    item,
                    "schedule",
                    social_account_id=context.account_id,
                    is_simulated=checked.account.is_simulated if checked.account else False,
                    scheduled_at=instant,
                    schedule_input=intent["schedule_input"],
                    validation=service.stored_report(checked),
                )
                impact.replace_references(
                    db,
                    ctx,
                    "content_item",
                    item.id,
                    [(uuid.UUID(fid), ver) for fid, ver in intent["fact_refs"]],
                )
                service.enqueue_publish(db, clock, item)
                action.status = "queued"
                return
    action.status = "succeeded"
    from app.audit.service import record

    record(
        db,
        ctx,
        "agent.content_applied",
        "agent_action",
        action.id,
        {"action_type": action.action_type, "content_id": str(action.payload_ref)},
        is_simulated=item.is_simulated,
        clock=clock,
    )


def result(db: Session, action: AgentAction) -> dict[str, Any]:
    item = db.get(ContentItem, action.payload_ref) if action.payload_ref else None
    if (
        item
        and action.action_type == "content.publish"
        and action.status not in {"proposed", "waiting_approval"}
    ):
        op = db.scalar(
            select(Operation).where(
                Operation.workspace_id == item.workspace_id,
                Operation.idempotency_key == f"publish:{item.id}:v{action.version}",
            )
        )
        if op:
            action.operation_id = op.id
            action.status = {
                "succeeded": "succeeded",
                "failed": "failed",
                "cancelled": "cancelled",
                "in_progress": "in_progress",
                "outcome_unknown": "outcome_unknown",
            }.get(op.status, "queued")
        elif (
            item.agent_action_id != action.id
            or item.origin != "agent"
            or item.version != action.version
            or item.status
            in {
                "cancelled",
                "on_hold",
                "failed",
                "draft",
            }
        ):
            action.status = "cancelled"
    return {
        "action_id": str(action.id),
        "action_type": action.action_type,
        "status": action.status,
        "outcome_code": action.outcome_code,
        "approval_id": str(action.approval_id) if action.status == "waiting_approval" else None,
        "content_id": str(item.id) if item else None,
        "content_status": item.status if item else None,
        "is_simulated": item.is_simulated if item else None,
    }
