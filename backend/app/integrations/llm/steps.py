"""Provider-neutral, bounded account-agent step contract.

The model chooses one registered tool or an explicit control decision. Its output is a
proposal; the application broker and coordinator own all reads, authority and effects.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

from app.integrations.llm.base import LLMMessage, LLMUsage

StepKind = Literal["tool", "wait", "complete", "handoff"]


@dataclass(frozen=True)
class LLMToolDefinition:
    name: str
    description: str
    arguments_schema: type[BaseModel]
    version: str


@dataclass(frozen=True)
class LLMToolObservation:
    """A previous call and bounded result to feed into the next model step."""

    call_id: str
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


@dataclass(frozen=True)
class LLMStepRequest:
    task: str
    model: str
    system: str
    messages: tuple[LLMMessage, ...]
    tools: tuple[LLMToolDefinition, ...]
    observations: tuple[LLMToolObservation, ...] = ()
    max_output_tokens: int = 800
    timeout_s: float = 30.0
    context: object | None = None  # deterministic fake only; real providers ignore it


@dataclass(frozen=True)
class LLMStepResult:
    kind: StepKind
    usage: LLMUsage
    latency_ms: int
    provider: str
    model: str
    is_fake: bool
    tool_name: str | None = None
    tool_arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str | None = None
    explanation: str = ""
    wait_for: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
