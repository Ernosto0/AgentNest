"""Typed tool dispatch. Model arguments never supply tenant identity or authority."""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.knowledge import answers_page, facts_page
from app.agent.models import AgentThread
from app.ai.injection import neutralise_untrusted
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.inbox.models import Message
from app.integrations.llm.steps import LLMToolDefinition

Capability = Literal["public_read", "private_read", "internal_write", "external_effect"]
Surface = Literal["dm", "comment", "owner_task"]
Source = Literal["customer", "owner_task"]


@dataclass(frozen=True)
class BrokerContext:
    workspace: WorkspaceContext
    account_id: uuid.UUID
    thread_id: uuid.UUID
    surface: Surface
    source: Source
    memory_generation: int | None = None


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    name: str
    version: str | None
    data: dict[str, Any]
    error: str | None = None

    def observation(self) -> dict[str, Any]:
        return {"ok": self.ok, "data": self.data, "error": self.error}


ToolHandler = Callable[[Session, Clock, BrokerContext, BaseModel], dict[str, Any]]


class ToolInputError(ValueError):
    """Typed input was structurally valid but exceeded a broker bound."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    description: str
    capability: Capability
    surfaces: frozenset[Surface]
    sources: frozenset[Source]
    arguments_schema: type[BaseModel]
    handler: ToolHandler


class ToolBroker:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name == "agent_decide" or spec.name in self._tools:
            raise ValueError("tool name is reserved or already registered")
        self._tools[spec.name] = spec

    def available(
        self, context: BrokerContext, *, capabilities: dict[str, bool] | None = None
    ) -> tuple[LLMToolDefinition, ...]:
        return tuple(
            LLMToolDefinition(spec.name, spec.description, spec.arguments_schema, spec.version)
            for spec in self._tools.values()
            if _allowed(spec, context)
            and (
                capabilities is None
                or spec.name != "comment.private_reply"
                or capabilities.get("comment_private_reply") is True
            )
        )

    def dispatch(
        self,
        session: Session,
        clock: Clock,
        context: BrokerContext,
        *,
        name: str,
        version: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        spec = self._tools.get(name)
        if spec is None:
            return ToolResult(False, name, None, {}, "UNKNOWN_TOOL")
        if version != spec.version:
            return ToolResult(False, name, spec.version, {}, "STALE_TOOL_SCHEMA")
        if not _allowed(spec, context):
            return ToolResult(False, name, spec.version, {}, "TOOL_FORBIDDEN")
        try:
            encoded = json.dumps(arguments, ensure_ascii=False)
        except (TypeError, ValueError):
            return ToolResult(False, name, spec.version, {}, "TOOL_ARGUMENT_INVALID")
        if len(encoded.encode("utf-8")) > 8192:
            return ToolResult(False, name, spec.version, {}, "TOOL_ARGUMENT_TOO_LARGE")
        try:
            parsed = spec.arguments_schema.model_validate(arguments)
        except ValidationError:
            return ToolResult(False, name, spec.version, {}, "TOOL_ARGUMENT_INVALID")
        # The caller supplies context from the server; the broker rechecks ownership before
        # any handler reads a domain record. A reference in arguments cannot change this scope.
        thread = session.scalar(
            select(AgentThread).where(
                AgentThread.workspace_id == context.workspace.workspace_id,
                AgentThread.social_account_id == context.account_id,
                AgentThread.id == context.thread_id,
                AgentThread.surface == context.surface,
            )
        )
        if thread is None:
            return ToolResult(False, name, spec.version, {}, "TOOL_SCOPE_INVALID")
        try:
            data = spec.handler(session, clock, context, parsed)
            output = json.dumps(data, ensure_ascii=False)
        except ToolInputError:
            return ToolResult(False, name, spec.version, {}, "TOOL_ARGUMENT_INVALID")
        except (ValueError, TypeError):
            return ToolResult(False, name, spec.version, {}, "TOOL_RESULT_INVALID")
        if len(output.encode("utf-8")) > 16384:
            return ToolResult(False, name, spec.version, {}, "TOOL_RESULT_TOO_LARGE")
        return ToolResult(True, name, spec.version, data)


def _allowed(spec: ToolSpec, context: BrokerContext) -> bool:
    if context.surface not in spec.surfaces or context.source not in spec.sources:
        return False
    return not (spec.capability == "private_read" and context.surface != "dm")


class KnowledgeReadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int
    cursor: str | None


def _knowledge_read(
    session: Session, clock: Clock, context: BrokerContext, args: BaseModel
) -> dict[str, Any]:
    request = KnowledgeReadArgs.model_validate(args)
    if not 1 <= request.limit <= 20:
        raise ToolInputError("invalid limit")
    return facts_page(
        session,
        clock,
        context.workspace,
        limit=request.limit,
        cursor=request.cursor,
    )


class AnswersReadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(ge=1, le=10)
    cursor: uuid.UUID | None
    language: Literal["tr", "en"]


def _answers_read(
    session: Session,
    clock: Clock,
    context: BrokerContext,
    args: BaseModel,
) -> dict[str, Any]:
    request = AnswersReadArgs.model_validate(args)
    return answers_page(
        session,
        clock,
        context.workspace,
        language=request.language,
        limit=request.limit,
        cursor=request.cursor,
    )


def _validate_reply(
    session: Session,
    clock: Clock,
    context: BrokerContext,
    args: BaseModel,
) -> dict[str, Any]:
    from app.agent.grounding import ReplyValidationArgs, validate_reply

    result = validate_reply(session, clock, context, ReplyValidationArgs.model_validate(args))
    return {
        "valid": result.valid,
        "text": result.text,
        "errors": list(result.errors),
        "facts": [{"id": str(fid), "version": version} for fid, version in result.facts],
        "customer_source": str(result.customer_source) if result.customer_source else None,
    }


class ThreadReadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int


def _thread_read(
    session: Session, _clock: Clock, context: BrokerContext, args: BaseModel
) -> dict[str, Any]:
    request = ThreadReadArgs.model_validate(args)
    if not 1 <= request.limit <= 10:
        raise ToolInputError("invalid limit")
    conversation_id = session.scalar(
        select(AgentThread.dm_conversation_id).where(
            AgentThread.workspace_id == context.workspace.workspace_id,
            AgentThread.social_account_id == context.account_id,
            AgentThread.id == context.thread_id,
            AgentThread.surface == "dm",
        )
    )
    if conversation_id is None:
        return {"messages": []}
    rows = session.scalars(
        select(Message)
        .where(
            Message.workspace_id == context.workspace.workspace_id,
            Message.social_account_id == context.account_id,
            Message.conversation_id == conversation_id,
            Message.is_deleted.is_(False),
        )
        .order_by(Message.provider_timestamp.desc(), Message.created_at.desc(), Message.id.desc())
        .limit(request.limit)
    ).all()
    from app.memory.service import source_visible

    identity_id = session.scalar(
        select(AgentThread.customer_identity_id).where(
            AgentThread.workspace_id == context.workspace.workspace_id,
            AgentThread.social_account_id == context.account_id,
            AgentThread.id == context.thread_id,
        )
    )
    rows = [row for row in rows if source_visible(session, identity_id, row)]
    return {
        "messages": [
            {
                "id": str(item.id),
                "direction": item.direction,
                "text": neutralise_untrusted((item.text or "")[:1000]),
            }
            for item in reversed(rows)
        ]
    }


def build_default_broker() -> ToolBroker:
    from app.agent.dm import send
    from app.agent.grounding import ReplyValidationArgs
    from app.memory.service import MemoryProposal, MemoryRead, private_context, write_proposal

    broker = ToolBroker()
    from app.comments.actions import ModerateArgs, PublicReplyArgs
    from app.comments.actions import propose as propose_public
    from app.comments.private_reply import PrivateReplyArgs
    from app.comments.private_reply import propose as propose_private
    from app.comments.service import PublicRead, public_context

    broker.register(
        ToolSpec(
            "public.thread",
            "v1",
            "Read bounded public post and current comment thread only.",
            "public_read",
            frozenset({"comment"}),
            frozenset({"customer"}),
            PublicRead,
            public_context,
        )
    )
    broker.register(
        ToolSpec(
            "comment.reply",
            "v1",
            "Propose one grounded public reply to a versioned comment.",
            "external_effect",
            frozenset({"comment"}),
            frozenset({"customer"}),
            PublicReplyArgs,
            propose_public,
        )
    )
    broker.register(
        ToolSpec(
            "comment.moderate",
            "v1",
            "Propose hide, unhide, or delete for a versioned public comment under delegation.",
            "external_effect",
            frozenset({"comment"}),
            frozenset({"customer"}),
            ModerateArgs,
            propose_public,
        )
    )
    broker.register(
        ToolSpec(
            "comment.private_reply",
            "v1",
            "Propose a one-shot private reply to an eligible source comment; no DM window opens.",
            "external_effect",
            frozenset({"comment"}),
            frozenset({"customer"}),
            PrivateReplyArgs,
            propose_private,
        )
    )

    from app.owner_requests.service import AskOwner, ask

    broker.register(
        ToolSpec(
            "owner.ask",
            "v1",
            "Ask the business for missing information; never approves an action.",
            "internal_write",
            frozenset({"dm"}),
            frozenset({"customer"}),
            AskOwner,
            ask,
        )
    )

    # This is the existing exact DM action path: its result is an action/approval
    # reference, never an information answer. It cannot approve its own proposal.
    def request_approval(
        db: Session, clock: Clock, ctx: BrokerContext, args: BaseModel
    ) -> dict[str, Any]:
        return send(db, clock, ctx, args, require_human=True)

    broker.register(
        ToolSpec(
            "approval.request",
            "v1",
            "Propose an exact grounded DM through current delegation and explicit approval policy.",
            "external_effect",
            frozenset({"dm"}),
            frozenset({"customer"}),
            ReplyValidationArgs,
            request_approval,
        )
    )

    def read_memory(
        db: Session, clock: Clock, ctx: BrokerContext, args: BaseModel
    ) -> dict[str, Any]:
        request = MemoryRead.model_validate(args)
        result = private_context(db, clock, ctx, request.relevant_to) or {"memories": []}
        result["memories"] = result["memories"][: request.limit]
        return result

    def write_memory(
        db: Session, clock: Clock, ctx: BrokerContext, args: BaseModel
    ) -> dict[str, Any]:
        return write_proposal(db, clock, ctx, MemoryProposal.model_validate(args))

    for name, schema, handler in (
        ("memory.read", MemoryRead, read_memory),
        ("memory.write", MemoryProposal, write_memory),
    ):
        broker.register(
            ToolSpec(
                name,
                "v1",
                "Private self-reported customer preferences/claims; never business authority.",
                "private_read" if name.endswith("read") else "internal_write",
                frozenset({"dm"}),
                frozenset({"customer"}),
                schema,
                handler,
            )
        )
    broker.register(
        ToolSpec(
            "dm.send",
            "v1",
            "Propose a grounded private reply and observe its durable action result.",
            "external_effect",
            frozenset({"dm"}),
            frozenset({"customer"}),
            ReplyValidationArgs,
            send,
        )
    )
    broker.register(
        ToolSpec(
            "knowledge.answers",
            "v1",
            "Read active business answer templates and versions.",
            "public_read",
            frozenset({"dm", "comment", "owner_task"}),
            frozenset({"customer", "owner_task"}),
            AnswersReadArgs,
            _answers_read,
        )
    )
    broker.register(
        ToolSpec(
            "reply.validate",
            "v1",
            "Validate a proposed reply with exact fact source versions.",
            "public_read",
            frozenset({"dm", "comment", "owner_task"}),
            frozenset({"customer", "owner_task"}),
            ReplyValidationArgs,
            _validate_reply,
        )
    )
    broker.register(
        ToolSpec(
            "knowledge.read",
            "v1",
            "Read verified, currently usable business facts with source keys and versions.",
            "public_read",
            frozenset({"dm", "comment", "owner_task"}),
            frozenset({"customer", "owner_task"}),
            KnowledgeReadArgs,
            _knowledge_read,
        )
    )
    broker.register(
        ToolSpec(
            "thread.read",
            "v1",
            "Read recent messages from the current private DM thread only.",
            "private_read",
            frozenset({"dm"}),
            frozenset({"customer", "owner_task"}),
            ThreadReadArgs,
            _thread_read,
        )
    )
    return broker
