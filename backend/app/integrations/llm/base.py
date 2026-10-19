"""The thin LLM provider interface (ADR-009): one method, structured output, no tools.

``context`` is an optional typed copy of the task input. Real providers ignore it; the
deterministic fake reads it so it never has to parse prompt text. Tasks never import a vendor
SDK; only ``app.ai`` imports this package.
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel


@dataclass(frozen=True)
class LLMMessage:
    """One conversation turn. Untrusted data is wrapped and labelled by the prompt builder."""

    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None


@dataclass(frozen=True)
class LLMResult:
    """What a provider call produced. ``raw_text`` is always re-validated by the runner."""

    raw_text: str
    usage: LLMUsage
    latency_ms: int
    provider: str
    model: str
    is_fake: bool
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str
    is_fake: bool

    def generate_structured(
        self,
        *,
        task: str,
        model: str,
        system: str,
        messages: list[LLMMessage],
        output_schema: type[BaseModel],
        max_output_tokens: int,
        timeout_s: float,
        context: object | None = None,
    ) -> LLMResult: ...
