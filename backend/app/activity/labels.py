"""Actor and resource labels of the Activity feed (plan H7).

Audit metadata holds no text (INV-12), so labels are resolved at read time from the records
themselves: one batched, workspace-scoped query per resource type (no N+1). A record that no
longer exists gets a neutral label. Message text is never read: a customer is shown by handle.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.models import AgentAction, AgentThread
from app.approvals.models import Approval
from app.audit.models import AuditLog
from app.content.models import ContentItem
from app.core.context import WorkspaceContext
from app.core.i18n import catalog_keys, t
from app.identity.models import User, WorkspaceMember
from app.inbox.models import Conversation, Message, ReplyDraft
from app.integrations.instagram.models import SocialAccount
from app.knowledge.models import ApprovedAnswer, BusinessFact, FactCandidate
from app.operations.models import Operation
from app.owner_requests.models import OwnerQuestion
from app.reporting import links
from app.reporting.models import DailyReport

_ACTOR_KEYS = {"system": "activity.actor.system", "agent": "activity.actor.agent"}


@dataclass(frozen=True)
class Actor:
    type: str
    label: str


@dataclass(frozen=True)
class Resource:
    type: str
    id: uuid.UUID
    label: str
    link: str | None


def _uuid_or_none(value: str | None) -> uuid.UUID | None:
    try:
        return uuid.UUID(value) if value else None
    except ValueError:
        return None


def _text(key: str, locale: str, fallback: str) -> str:
    return t(key if key in catalog_keys(locale) else fallback, locale)


def _gone(locale: str) -> str:
    return t("activity.resource.gone", locale)


def _pairs(session: Session, statement: Any) -> dict[Any, Any]:
    return {row[0]: row[1] for row in session.execute(statement)}


def _member_names(
    session: Session, ctx: WorkspaceContext, user_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Display names of the users who are members of this workspace (others are absent)."""
    if not user_ids:
        return {}
    return _pairs(
        session,
        select(User.id, User.display_name)
        .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.workspace_id == ctx.workspace_id, User.id.in_(user_ids)),
    )


def resolve_actors(
    session: Session, ctx: WorkspaceContext, rows: Sequence[AuditLog], locale: str
) -> dict[uuid.UUID, Actor]:
    """``{audit id: Actor}``. A user who is no longer a member reads "Eski uye"."""
    user_ids = {uid for r in rows if r.actor_type == "user" and (uid := _uuid_or_none(r.actor_id))}
    names = _member_names(session, ctx, user_ids)
    result: dict[uuid.UUID, Actor] = {}
    for row in rows:
        if row.actor_type == "user":
            uid = _uuid_or_none(row.actor_id)
            label = names.get(uid) if uid else None
            result[row.id] = Actor("user", label or t("activity.actor.former_member", locale))
        elif row.actor_type == "provider":
            result[row.id] = Actor("provider", t("activity.actor.provider", locale))
        else:
            key = _ACTOR_KEYS.get(row.actor_type, "activity.actor.system")
            result[row.id] = Actor(row.actor_type, t(key, locale))
    return result


def resolve_resources(
    session: Session, ctx: WorkspaceContext, rows: Sequence[AuditLog], locale: str
) -> dict[uuid.UUID, Resource]:
    """``{audit id: Resource}`` for the rows that name a resource."""
    ws = ctx.workspace_id
    ids: dict[str, set[uuid.UUID]] = defaultdict(set)
    for row in rows:
        if row.resource_type and row.resource_id:
            ids[row.resource_type].add(row.resource_id)

    agent_routes: dict[uuid.UUID, str] = {}
    if ids["agent_action"]:
        for agent_action, thread in session.execute(
            select(AgentAction, AgentThread)
            .join(
                AgentThread,
                (AgentThread.id == AgentAction.thread_id)
                & (AgentThread.workspace_id == AgentAction.workspace_id),
            )
            .where(
                AgentAction.workspace_id == ws,
                AgentAction.id.in_(ids["agent_action"]),
                AgentThread.workspace_id == ws,
            )
        ):
            if thread.surface == "dm" and thread.dm_conversation_id:
                agent_routes[agent_action.id] = f"/w/{ws}/inbox/{thread.dm_conversation_id}"
            elif thread.surface == "comment" and thread.public_thread_id:
                agent_routes[agent_action.id] = (
                    f"/w/{ws}/more/agent/comments/{thread.public_thread_id}?account={agent_action.social_account_id}"
                )
            else:
                agent_routes[agent_action.id] = (
                    f"/w/{ws}/more/agent?account={agent_action.social_account_id}"
                )
    question_routes: dict[uuid.UUID, str] = {}
    if ids["owner_question"]:
        question_routes = {
            q.id: f"/w/{ws}/more/agent/questions/{q.id}?account={q.social_account_id}"
            for q in session.scalars(
                select(OwnerQuestion).where(
                    OwnerQuestion.workspace_id == ws, OwnerQuestion.id.in_(ids["owner_question"])
                )
            )
        }

    # Customers: a conversation, a message or a reply draft all lead to a conversation.
    conversation_of: dict[uuid.UUID, uuid.UUID] = {}
    if ids["message"]:
        conversation_of.update(
            _pairs(
                session,
                select(Message.id, Message.conversation_id).where(
                    Message.workspace_id == ws, Message.id.in_(ids["message"])
                ),
            )
        )
    if ids["reply_draft"]:
        conversation_of.update(
            _pairs(
                session,
                select(ReplyDraft.id, ReplyDraft.conversation_id).where(
                    ReplyDraft.workspace_id == ws, ReplyDraft.id.in_(ids["reply_draft"])
                ),
            )
        )
    conversation_ids = set(conversation_of.values()) | ids["conversation"]
    handles: dict[uuid.UUID, str | None] = {}
    if conversation_ids:
        handles = _pairs(
            session,
            select(Conversation.id, Conversation.customer_handle).where(
                Conversation.workspace_id == ws, Conversation.id.in_(conversation_ids)
            ),
        )

    titles: dict[uuid.UUID, str] = {}
    if ids["content_item"]:
        titles = _pairs(
            session,
            select(ContentItem.id, ContentItem.title).where(
                ContentItem.workspace_id == ws, ContentItem.id.in_(ids["content_item"])
            ),
        )
    answers: dict[uuid.UUID, str] = {}
    if ids["approved_answer"]:
        answers = _pairs(
            session,
            select(ApprovedAnswer.id, ApprovedAnswer.title).where(
                ApprovedAnswer.workspace_id == ws, ApprovedAnswer.id.in_(ids["approved_answer"])
            ),
        )
    approval_actions: dict[uuid.UUID, str] = {}
    if ids["approval"]:
        approval_actions = _pairs(
            session,
            select(Approval.id, Approval.action).where(
                Approval.workspace_id == ws, Approval.id.in_(ids["approval"])
            ),
        )
    operation_types: dict[uuid.UUID, str] = {}
    if ids["operation"]:
        operation_types = _pairs(
            session,
            select(Operation.id, Operation.operation_type).where(
                Operation.workspace_id == ws, Operation.id.in_(ids["operation"])
            ),
        )
    accounts: dict[uuid.UUID, str | None] = {}
    if ids["social_account"]:
        accounts = _pairs(
            session,
            select(SocialAccount.id, SocialAccount.username).where(
                SocialAccount.workspace_id == ws, SocialAccount.id.in_(ids["social_account"])
            ),
        )
    report_dates: dict[uuid.UUID, Any] = {}
    if ids["daily_report"]:
        report_dates = _pairs(
            session,
            select(DailyReport.id, DailyReport.local_date).where(
                DailyReport.workspace_id == ws, DailyReport.id.in_(ids["daily_report"])
            ),
        )
    members = _member_names(session, ctx, ids["user"])
    # Facts, and the facts that candidates are about.
    candidate_facts: dict[uuid.UUID, uuid.UUID | None] = {}
    if ids["fact_candidate"]:
        candidate_facts = _pairs(
            session,
            select(FactCandidate.id, FactCandidate.fact_id).where(
                FactCandidate.workspace_id == ws, FactCandidate.id.in_(ids["fact_candidate"])
            ),
        )
    fact_ids = ids["business_fact"] | {f for f in candidate_facts.values() if f is not None}
    facts: dict[uuid.UUID, tuple[dict[str, str], str]] = {}
    if fact_ids:
        facts = {
            row.id: (row.label, row.category)
            for row in session.execute(
                select(BusinessFact.id, BusinessFact.label, BusinessFact.category).where(
                    BusinessFact.workspace_id == ws, BusinessFact.id.in_(fact_ids)
                )
            )
        }

    def fact_label(fact_id: uuid.UUID) -> str | None:
        found = facts.get(fact_id)
        if found is None:
            return None
        labels = found[0]
        return labels.get(locale) or labels.get("tr") or next(iter(labels.values()), None)

    def conversation_resource(row: AuditLog, conversation_id: uuid.UUID | None) -> Resource:
        if not row.resource_type or row.resource_id is None:
            raise ValueError("an audit row without a resource")
        if conversation_id is None or conversation_id not in handles:
            return Resource(row.resource_type, row.resource_id, _gone(locale), None)
        label = handles[conversation_id] or t("activity.resource.customer", locale)
        route = links.conversation_link(ws, conversation_id)["route"]
        return Resource(row.resource_type, row.resource_id, label, route)

    result: dict[uuid.UUID, Resource] = {}
    for row in rows:
        kind, rid = row.resource_type, row.resource_id
        if not kind or rid is None:
            continue
        if kind in ("message", "reply_draft"):
            result[row.id] = conversation_resource(row, conversation_of.get(rid))
        elif kind == "conversation":
            result[row.id] = conversation_resource(row, rid)
        elif kind == "agent_action":
            result[row.id] = Resource(
                kind,
                rid,
                _text("activity.resource.agent_action", locale, "activity.resource.other"),
                agent_routes.get(rid),
            )
        elif kind == "owner_question":
            result[row.id] = Resource(
                kind, rid, t("report.item.owner_question", locale), question_routes.get(rid)
            )
        elif kind == "content_item":
            title = titles.get(rid)
            route = links.content_link(ws, rid)["route"] if title is not None else None
            result[row.id] = Resource(kind, rid, title or _gone(locale), route)
        elif kind == "approved_answer":
            title = answers.get(rid)
            route = f"/w/{ws}/more/knowledge/answers" if title is not None else None
            result[row.id] = Resource(kind, rid, title or _gone(locale), route)
        elif kind == "approval":
            action = approval_actions.get(rid)
            if action is None:
                result[row.id] = Resource(kind, rid, _gone(locale), None)
            else:
                label = _text(
                    f"report.item.approval.{action}", locale, "report.item.approval.other"
                )
                result[row.id] = Resource(kind, rid, label, links.approval_link(ws, rid)["route"])
        elif kind == "operation":
            op_type = operation_types.get(rid)
            if op_type is None:
                result[row.id] = Resource(kind, rid, _gone(locale), None)
            else:
                label = _text(
                    f"activity.resource.operation.{op_type}", locale, "activity.resource.operation"
                )
                result[row.id] = Resource(kind, rid, label, None)
        elif kind == "social_account":
            if rid not in accounts:
                result[row.id] = Resource(kind, rid, _gone(locale), None)
            else:
                label = accounts[rid] or t("activity.resource.social_account", locale)
                result[row.id] = Resource(kind, rid, label, f"/w/{ws}/more/automation")
        elif kind == "daily_report":
            day = report_dates.get(rid)
            if day is None:
                result[row.id] = Resource(kind, rid, _gone(locale), None)
            else:
                route = f"/w/{ws}/more/reports?date={day.isoformat()}"
                result[row.id] = Resource(kind, rid, day.isoformat(), route)
        elif kind == "user":
            name = members.get(rid)
            result[row.id] = Resource(
                kind, rid, name or t("activity.actor.former_member", locale), None
            )
        elif kind == "business_fact":
            fact_text = fact_label(rid)
            if fact_text is None:
                result[row.id] = Resource(kind, rid, _gone(locale), None)
            else:
                category = facts[rid][1]
                result[row.id] = Resource(
                    kind, rid, fact_text, f"/w/{ws}/more/knowledge/{category}"
                )
        elif kind == "fact_candidate":
            if rid not in candidate_facts:
                result[row.id] = Resource(kind, rid, _gone(locale), None)
            else:
                fact_id = candidate_facts[rid]
                label = (fact_label(fact_id) if fact_id else None) or t(
                    "activity.resource.fact_candidate", locale
                )
                result[row.id] = Resource(kind, rid, label, f"/w/{ws}/more/knowledge/suggestions")
        else:
            # owner_command, media_asset, agent_run, workspace, ...: a neutral name, no screen.
            label = _text(f"activity.resource.{kind}", locale, "activity.resource.other")
            result[row.id] = Resource(kind, rid, label, None)
    return result
