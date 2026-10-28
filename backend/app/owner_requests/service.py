"""Account-first information decisions and narrowly scoped continuation evidence."""

import hashlib
import uuid
from datetime import timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.agent.models import ACTIVE_RUN_STATES, AgentEvent, AgentSession, AgentThread
from app.agent.repository import scoped_account, scoped_thread
from app.audit.service import record
from app.core.canonical import payload_hash
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity import repository as members
from app.identity.permissions import has_permission
from app.inbox.models import Message
from app.owner_requests.models import OwnerAnswer, OwnerQuestion

RequiredInfo = Literal["availability", "exception", "service_detail", "business_policy", "other"]
Visibility = Literal["customer_reply", "private_business"]


def knowledge_fence(db: Session, workspace: uuid.UUID) -> str:
    """Content-free aggregate invalidation, without loading business bodies."""
    from app.knowledge.models import BusinessFact, FactCandidate

    parts = []
    for model in (BusinessFact, FactCandidate):
        row = db.execute(
            select(
                func.count(model.id),
                func.sum(
                    func.hashtextextended(func.concat(model.id, model.status, model.updated_at), 0)
                ),
            ).where(model.workspace_id == workspace)
        ).one()
        parts.append([row[0], str(row[1]) if row[1] is not None else None])
    return payload_hash(parts)


class AskOwner(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=500)
    required_info: RequiredInfo
    visibility: Visibility
    holding_response: bool = False


class ReusableKnowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Reusable information is a typed unverified text candidate; critical structured
    # values are subsequently edited/verified through the existing knowledge workflow.
    key: str = Field(pattern=r"^custom\.[a-z][a-z0-9_]{0,60}$")
    text: str = Field(min_length=1, max_length=500)


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    client_request_id: uuid.UUID
    body: str = Field(min_length=1, max_length=700)
    kind: Literal["answer", "proposal"] = "answer"
    reusable_knowledge: ReusableKnowledge | None = None


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    client_request_id: uuid.UUID


def question_scope(
    db: Session,
    ctx: WorkspaceContext,
    account: uuid.UUID,
    question: uuid.UUID,
    *,
    lock: bool = False,
) -> OwnerQuestion:
    from app.agent.repository import AgentScopeError

    try:
        scoped_account(db, ctx.workspace_id, account, lock=lock)
    except AgentScopeError as exc:
        raise AppError("NOT_FOUND") from exc
    ref = db.scalar(
        select(OwnerQuestion).where(
            OwnerQuestion.workspace_id == ctx.workspace_id,
            OwnerQuestion.social_account_id == account,
            OwnerQuestion.id == question,
        )
    )
    if ref is None:
        raise AppError("NOT_FOUND")
    if lock:
        scoped_thread(db, ctx.workspace_id, account, ref.thread_id, lock=True)
        db.refresh(ref, with_for_update=True)
    return ref


def audit(db: Session, clock: Clock, ctx: WorkspaceContext, q: OwnerQuestion, action: str) -> None:
    record(
        db,
        ctx,
        action,
        "owner_question",
        q.id,
        {"version": q.version, "state": q.state},
        clock=clock,
    )


def notify(db: Session, clock: Clock, ctx: WorkspaceContext, q: OwnerQuestion, kind: str) -> None:
    from app.integrations.instagram.models import SocialAccount
    from app.notifications.service import notify_permission_holders

    social = db.get(SocialAccount, q.social_account_id)
    notify_permission_holders(
        db,
        clock,
        ctx,
        permission="owner_questions.answer",
        type=kind,
        subject_type="owner_question",
        subject_id=q.id,
        params={"question_id": str(q.id)},
        dedup_key=f"{kind}:{q.id}",
        is_simulated=bool(social and social.provider_kind == "mock"),
    )


def ask(db: Session, clock: Clock, context: Any, args: BaseModel) -> dict[str, Any]:
    request = AskOwner.model_validate(args)
    scoped_account(db, context.workspace.workspace_id, context.account_id, lock=True)
    thread = scoped_thread(
        db, context.workspace.workspace_id, context.account_id, context.thread_id, lock=True
    )
    if context.surface != "dm" or thread.handling_mode != "agent":
        raise ValueError("private DM required")
    from app.memory.service import resolve_identity, source_visible

    identity = resolve_identity(db, clock, thread)
    goal = db.scalar(
        select(AgentSession).where(
            AgentSession.thread_id == thread.id, AgentSession.status.in_(ACTIVE_RUN_STATES)
        )
    )
    event = db.scalar(
        select(AgentEvent).where(
            AgentEvent.thread_id == thread.id,
            AgentEvent.cursor == thread.event_cursor,
            AgentEvent.kind == "customer_message",
        )
    )
    message = db.get(Message, uuid.UUID(event.source_id)) if event and event.source_id else None
    if (
        not event
        or not identity
        or not goal
        or not message
        or message.is_deleted
        or message.conversation_id != thread.dm_conversation_id
        or not source_visible(db, identity.id, message)
    ):
        raise ValueError("missing current customer source")
    # Model wording and visibility never choose the dedup identity. An attempted
    # visibility change returns the original question, never a second private record.
    key = hashlib.sha256(
        f"{thread.id}:{goal.id}:{event.id}:{request.required_info}".encode()
    ).hexdigest()
    existing = db.scalar(
        select(OwnerQuestion).where(
            OwnerQuestion.workspace_id == thread.workspace_id, OwnerQuestion.continuation_key == key
        )
    )
    if existing:
        return question_result(existing)
    q = OwnerQuestion(
        workspace_id=thread.workspace_id,
        social_account_id=thread.social_account_id,
        thread_id=thread.id,
        session_id=goal.id,
        customer_identity_id=identity.id,
        source_message_id=message.id,
        source_cursor=thread.event_cursor,
        source_hash=payload_hash({"text": message.text}),
        knowledge_fence=knowledge_fence(db, thread.workspace_id),
        ownership_generation=thread.ownership_generation,
        deletion_generation=thread.deletion_generation,
        required_info=request.required_info,
        visibility=request.visibility,
        continuation_key=key,
        body=request.question,
        state="pending",
        version=1,
        created_at=clock.now(),
        expires_at=clock.now() + timedelta(days=7),
    )
    db.add(q)
    db.flush()
    notify(db, clock, context.workspace, q, "owner_question.requested")
    audit(db, clock, context.workspace, q, "owner_question.created")
    if request.holding_response:
        from app.agent.context import assemble
        from app.agent.dm import send
        from app.agent.grounding import ReplyValidationArgs
        from app.inbox.context import MESSAGING_WINDOW
        from app.inbox.models import Conversation
        from app.operations.send import SEND_MARGIN

        conversation = db.get(Conversation, thread.dm_conversation_id)
        language = assemble(db, clock, context).language
        if (
            conversation
            and conversation.last_inbound_at
            and language in {"tr", "en"}
            and clock.now() < conversation.last_inbound_at + MESSAGING_WINDOW - SEND_MARGIN
        ):
            template = (
                "Bu talebiniz için işletmeden bilgi istedim."
                if language == "tr"
                else "I've asked the business for information about your request."
            )
            holding = send(
                db,
                clock,
                context,
                ReplyValidationArgs(template=template, language=language),
                semantic_slot=f"holding:{q.id}",
            )
            if holding.get("action_id"):
                q.holding_action_id = uuid.UUID(holding["action_id"])
    return question_result(q)


def question_result(q: OwnerQuestion) -> dict[str, Any]:
    return {
        "question_id": str(q.id),
        "state": q.state,
        "version": q.version,
        "wait_for": "owner",
        "approval_id": None,
    }


def event_and_wake(db: Session, clock: Clock, q: OwnerQuestion, kind: str) -> None:
    """Caller holds account/thread. Accept information even during takeover or pause.

    Unlike customer admission this event is evidence, never a messaging permission.
    Recovery can rediscover the persisted answer even if its wake was lost.
    """
    from app.agent.jobs import wake

    thread = db.get(AgentThread, q.thread_id)
    if thread is None:
        raise AppError("NOT_FOUND")
    thread.event_cursor += 1
    thread.thread_version += 1
    thread.last_activity_at = clock.now()
    db.add(
        AgentEvent(
            workspace_id=q.workspace_id,
            social_account_id=q.social_account_id,
            thread_id=q.thread_id,
            cursor=thread.event_cursor,
            kind=kind,
            source_kind="owner_question",
            source_key=f"{q.id}:{q.version}",
            source_id=str(q.id),
            source_version=q.version,
            created_at=clock.now(),
        )
    )
    db.flush()
    wake(db, clock, q.workspace_id, q.thread_id, f"owner:{q.id}:{q.version}")


def decide(
    db: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account: uuid.UUID,
    question: uuid.UUID,
    request: AnswerRequest | CancelRequest,
) -> OwnerAnswer:
    q = question_scope(db, ctx, account, question, lock=True)
    cancel = isinstance(request, CancelRequest)
    kind = request.kind if isinstance(request, AnswerRequest) else "cancel"
    permission = "owner_questions.propose" if kind == "proposal" else "owner_questions.answer"
    if not has_permission(ctx.role, permission) or ctx.actor.type != "user" or not ctx.actor.id:
        raise AppError("FORBIDDEN")
    if (
        isinstance(request, AnswerRequest)
        and request.reusable_knowledge
        and (kind != "answer" or q.visibility != "customer_reply")
    ):
        raise AppError("VALIDATION_FAILED")
    digest = payload_hash(request.model_dump(mode="json"))
    previous = db.scalar(
        select(OwnerAnswer).where(
            OwnerAnswer.question_id == q.id,
            OwnerAnswer.client_request_id == request.client_request_id,
        )
    )
    if previous:
        if previous.request_hash != digest or str(previous.author_user_id) != ctx.actor.id:
            raise AppError("VERSION_CONFLICT")
        return previous
    if kind == "proposal" and q.state != "pending":
        raise AppError("OWNER_QUESTION_CLOSED")
    if q.expires_at <= clock.now() or q.state in {"expired", "cancelled"} or q.body is None:
        raise AppError("OWNER_QUESTION_CLOSED")
    if q.version != request.expected_version:
        raise AppError("VERSION_CONFLICT")
    q.version += 1
    answer = OwnerAnswer(
        workspace_id=q.workspace_id,
        social_account_id=account,
        thread_id=q.thread_id,
        question_id=q.id,
        version=q.version,
        kind=kind,
        body=request.body if isinstance(request, AnswerRequest) else None,
        author_user_id=uuid.UUID(ctx.actor.id),
        author_role=ctx.role or "",
        client_request_id=request.client_request_id,
        request_hash=digest,
        created_at=clock.now(),
        expires_at=q.expires_at,
    )
    db.add(answer)
    db.flush()
    if kind != "proposal":
        retire_proposals(db, clock, q, ctx)
        q.state = "cancelled" if cancel else "answered"
        q.answer_id = answer.id if not cancel else None
        q.knowledge_fence = knowledge_fence(db, q.workspace_id)
        event_and_wake(db, clock, q, "owner_question_cancelled" if cancel else "owner_answer")
    if isinstance(request, AnswerRequest) and request.reusable_knowledge:
        from app.knowledge.candidates import propose_candidate
        from app.knowledge.models import BusinessFact
        from app.knowledge.values import validate_value

        reusable = request.reusable_knowledge
        value = validate_value("text", {"text": reusable.text})
        fact = db.scalar(
            select(BusinessFact).where(
                BusinessFact.workspace_id == ctx.workspace_id, BusinessFact.key == reusable.key
            )
        )
        candidate = propose_candidate(
            db,
            clock,
            ctx,
            key=reusable.key,
            value_type="text",
            value=value,
            source_type="owner_answer",
            fact=fact,
        )
        candidate.owner_answer_id = answer.id
        answer.candidate_id = candidate.id
        db.flush()
        q.knowledge_fence = knowledge_fence(db, q.workspace_id)
    audit(
        db,
        clock,
        ctx,
        q,
        "owner_question.proposed" if kind == "proposal" else "owner_question.decided",
    )
    db.flush()
    return answer


def current_message(db: Session, thread: AgentThread) -> Message | None:
    return db.scalar(
        select(Message)
        .where(
            Message.workspace_id == thread.workspace_id,
            Message.social_account_id == thread.social_account_id,
            Message.conversation_id == thread.dm_conversation_id,
            Message.direction == "inbound",
            Message.sender_kind == "customer",
            Message.is_deleted.is_(False),
        )
        .order_by(Message.provider_timestamp.desc(), Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )


def evidence(
    db: Session, clock: Clock, context: Any, answer_id: uuid.UUID, version: int
) -> tuple[OwnerQuestion, OwnerAnswer, Message] | None:
    if context.surface != "dm":
        return None
    thread = scoped_thread(
        db, context.workspace.workspace_id, context.account_id, context.thread_id
    )
    q = db.scalar(
        select(OwnerQuestion)
        .join(OwnerAnswer, OwnerAnswer.question_id == OwnerQuestion.id)
        .where(
            OwnerAnswer.id == answer_id,
            OwnerAnswer.version == version,
            OwnerQuestion.workspace_id == thread.workspace_id,
            OwnerQuestion.social_account_id == thread.social_account_id,
            OwnerQuestion.thread_id == thread.id,
            OwnerQuestion.customer_identity_id == thread.customer_identity_id,
            OwnerQuestion.answer_id == answer_id,
        )
    )
    a = db.get(OwnerAnswer, answer_id) if q else None
    if (
        not q
        or not a
        or q.state != "answered"
        or not q.body
        or not a.body
        or q.visibility != "customer_reply"
        or a.kind != "answer"
        or q.expires_at <= clock.now()
        or a.expires_at <= clock.now()
        or q.ownership_generation != thread.ownership_generation
        or q.deletion_generation != thread.deletion_generation
        or q.knowledge_fence != knowledge_fence(db, q.workspace_id)
    ):
        return None
    # Role at answer time AND current membership are required. Staff proposals and
    # removed/demoted authors cannot become customer-facing authority.
    from app.identity.models import User

    membership = members.get_membership(db, q.workspace_id, a.author_user_id)
    author = membership[0] if membership else None
    user = db.get(User, a.author_user_id)
    if (
        a.author_role not in {"owner", "manager"}
        or author is None
        or user is None
        or not user.is_active
        or author.role not in {"owner", "manager"}
    ):
        return None
    original = db.get(Message, q.source_message_id) if q.source_message_id else None
    latest = current_message(db, thread)
    from app.memory.service import source_visible

    if (
        not original
        or original.is_deleted
        or payload_hash({"text": original.text}) != q.source_hash
        or not latest
        or original.conversation_id != thread.dm_conversation_id
        or not source_visible(db, thread.customer_identity_id, original)
        or not source_visible(db, thread.customer_identity_id, latest)
    ):
        return None
    # A changed request cannot consume this exception. A customer may reopen the
    # same request after the window by repeating it exactly; the old answer remains
    # bounded by its original expiry and current ownership/deletion evidence.
    if latest.id != original.id and (not original.text or latest.text != original.text):
        return None
    return q, a, latest


def private_answers(db: Session, clock: Clock, context: Any) -> list[dict[str, Any]]:
    if context.surface != "dm":
        return []
    rows = db.scalars(
        select(OwnerAnswer)
        .join(OwnerQuestion, OwnerQuestion.answer_id == OwnerAnswer.id)
        .where(
            OwnerQuestion.workspace_id == context.workspace.workspace_id,
            OwnerQuestion.social_account_id == context.account_id,
            OwnerQuestion.thread_id == context.thread_id,
            OwnerQuestion.state == "answered",
            OwnerQuestion.visibility == "customer_reply",
            OwnerQuestion.expires_at > clock.now(),
        )
        .order_by(OwnerAnswer.created_at.desc())
        .limit(3)
    )
    return [
        {"id": str(a.id), "version": a.version, "text": a.body}
        for a in rows
        if evidence(db, clock, context, a.id, a.version)
    ]


def redact(
    db: Session,
    clock: Clock,
    workspace: uuid.UUID,
    account: uuid.UUID,
    source_message: uuid.UUID | None = None,
) -> int:
    """Only new derived question/answer caches. Sent business outcomes stay immutable."""
    scoped_account(db, workspace, account, lock=True)
    query = select(OwnerQuestion).where(
        OwnerQuestion.workspace_id == workspace, OwnerQuestion.social_account_id == account
    )
    if source_message:
        query = query.where(OwnerQuestion.source_message_id == source_message)
    count = 0
    for q in db.scalars(query):
        retire_proposals(db, clock, q, None, clear_bodies=True)
        q.body, q.source_message_id = None, None
        q.source_hash = ""
        q.state, q.version = "cancelled", q.version + 1
        for a in db.scalars(select(OwnerAnswer).where(OwnerAnswer.question_id == q.id)):
            a.body = None
        count += 1
    db.flush()
    return count


def recover_questions(factory: Any, clock: Clock, batch: int = 100) -> None:
    """Bounded expiry selection precedes locking; account first, then thread/question.

    Resolved owner waits are found separately by coordinator recovery, so thousands
    of unanswered people cannot starve an already committed answer.
    """
    from app.core.context import ActorRef
    from app.identity.models import Workspace

    with factory() as db:
        ids = list(
            db.scalars(
                select(OwnerQuestion.id)
                .where(
                    OwnerQuestion.state.in_(("pending", "answered")),
                    OwnerQuestion.expires_at <= clock.now(),
                )
                .order_by(OwnerQuestion.expires_at, OwnerQuestion.id)
                .limit(batch)
            )
        )
    for question_id in ids:
        with factory() as db:
            ref = db.get(OwnerQuestion, question_id)
            if ref is None:
                continue
            ws = db.get(Workspace, ref.workspace_id)
            if ws is None:
                continue
            ctx = WorkspaceContext(
                ws.id,
                ActorRef.system("owner_questions"),
                None,
                ws.timezone,
                ws.default_locale,
                ws.is_demo,
            )
            q = question_scope(db, ctx, ref.social_account_id, ref.id, lock=True)
            if q.state not in {"pending", "answered"} or q.expires_at > clock.now():
                continue
            q.state, q.version, q.body = "expired", q.version + 1, None
            retire_proposals(db, clock, q, ctx, clear_bodies=True)
            for a in db.scalars(select(OwnerAnswer).where(OwnerAnswer.question_id == q.id)):
                a.body = None
            event_and_wake(db, clock, q, "owner_question_expired")
            notify(db, clock, ctx, q, "owner_question.expired")
            audit(db, clock, ctx, q, "owner_question.expired")
            db.commit()


def retire_proposals(
    db: Session,
    clock: Clock,
    q: OwnerQuestion,
    ctx: WorkspaceContext | None,
    *,
    clear_bodies: bool = False,
) -> None:
    """No approval locks here. Unsubmitted domain intents cancel now; cleanup later.

    In-flight/unknown operations retain their reservation and outcome evidence.
    Historical customer messages and manual drafts are never changed.
    """
    from app.agent.jobs import enqueue_cleanup
    from app.agent.models import AgentAction
    from app.agent.transitions import transition_action
    from app.inbox import drafts
    from app.inbox.models import ReplyDraft
    from app.inbox.system import system_context

    answer_ids = select(cast(OwnerAnswer.id, String)).where(OwnerAnswer.question_id == q.id)
    actions = list(
        db.scalars(
            select(AgentAction)
            .join(ReplyDraft, ReplyDraft.id == AgentAction.payload_ref)
            .where(
                AgentAction.workspace_id == q.workspace_id,
                AgentAction.social_account_id == q.social_account_id,
                AgentAction.thread_id == q.thread_id,
                AgentAction.action_type == "dm.send",
                or_(
                    AgentAction.id == q.holding_action_id,
                    ReplyDraft.validation["agent_proposal"]["owner_answer"]["id"].astext.in_(
                        answer_ids
                    ),
                ),
            )
            .with_for_update(of=AgentAction)
        )
    )
    mutation_ctx = ctx or system_context(db, q.workspace_id, "owner_questions")
    touched = False
    for action in actions:
        draft = db.get(ReplyDraft, action.payload_ref) if action.payload_ref else None
        if draft is None:
            continue
        if action.status in {"proposed", "waiting_approval", "authorized", "queued"}:
            transition_action(
                db,
                workspace_id=q.workspace_id,
                action_id=action.id,
                expected_status=action.status,
                expected_version=action.version,
                next_status="cancelled",
                clock=clock,
            )
            db.refresh(action)
            action.outcome_code = "APPROVAL_STALE"
            touched = True
        if draft.status in {"queued", "pending_approval", "needs_human"} and mutation_ctx:
            drafts.transition(
                db,
                clock,
                mutation_ctx,
                draft,
                "expire" if draft.status == "needs_human" else "cancel",
                reason="APPROVAL_STALE",
            )
        if clear_bodies:
            draft.validation = {"privacy_redacted": True}
            draft.template, draft.suggestion_text = None, None
            if draft.status not in {"sending", "outcome_unknown"}:
                draft.text = None
    if touched:
        enqueue_cleanup(
            db, clock, q.workspace_id, q.social_account_id, f"question:{q.id}:{q.version}"
        )
