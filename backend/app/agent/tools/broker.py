"""Typed tool dispatch. Model arguments never supply tenant identity or authority."""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.models import AgentThread
from app.ai.injection import neutralise_untrusted
from app.core.clock import Clock
from app.core.context import WorkspaceContext
from app.inbox.models import Message
from app.integrations.llm.steps import LLMToolDefinition
from app.knowledge import service as knowledge_service

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

    def available(self, context: BrokerContext) -> tuple[LLMToolDefinition, ...]:
        return tuple(
            LLMToolDefinition(spec.name, spec.description, spec.arguments_schema, spec.version)
            for spec in self._tools.values()
            if _allowed(spec, context)
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
    facts = knowledge_service.usable_facts(session, clock, context.workspace)
    facts.sort(key=lambda item: item.key)
    if request.cursor is not None:
        facts = [fact for fact in facts if fact.key > request.cursor]
    page = facts[: request.limit + 1]
    return {
        "facts": [
            {
                "id": str(fact.fact_id),
                "key": fact.key,
                "version": fact.version,
                "display": neutralise_untrusted(fact.display),
                "placeholder": fact.placeholder,
            }
            for fact in page[: request.limit]
        ],
        "next_cursor": page[request.limit - 1].key if len(page) > request.limit else None,
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
        )
        .order_by(Message.provider_timestamp.desc(), Message.id.desc())
        .limit(request.limit)
    ).all()
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
    broker = ToolBroker()
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
