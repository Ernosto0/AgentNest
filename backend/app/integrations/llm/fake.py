"""Deterministic offline provider (ADR-009, agent-runtime.md §9): the default for development,
demo and CI, so the core demo needs no credentials or network (INV-14).

Each task registers a rule-based implementation with ``@fake_implementation(task)``; the
implementation receives the typed task input (``context``) and returns a schema-valid output.
Tests can script the next call with ``queue(task, output | Exception)`` to simulate adversarial,
invalid or failing model output and prove the deterministic layers still hold.
"""

import json
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.integrations.llm.base import LLMMessage, LLMResult, LLMUsage
from app.integrations.llm.errors import LLMConfigError
from app.integrations.llm.steps import LLMStepRequest, LLMStepResult

# (typed task input, output schema) -> output model or a plain dict
FakeImplementation = Callable[[Any, type[BaseModel]], BaseModel | dict[str, Any]]

_IMPLEMENTATIONS: dict[str, FakeImplementation] = {}

# What a test may script: a model/dict (serialised), a raw string (e.g. broken JSON), or an
# exception to raise.
Scripted = BaseModel | dict[str, Any] | str | Exception


def fake_implementation(task: str) -> Callable[[FakeImplementation], FakeImplementation]:
    def decorator(func: FakeImplementation) -> FakeImplementation:
        _IMPLEMENTATIONS[task] = func
        return func

    return decorator


@dataclass(frozen=True)
class FakeCall:
    """A recorded call, so tests can assert what the runner sent."""

    task: str
    model: str
    system: str
    messages: tuple[LLMMessage, ...]
    context: object | None


class FakeLLMProvider:
    name = "fake"
    is_fake = True

    def __init__(self) -> None:
        self._queued: dict[str, deque[Scripted]] = defaultdict(deque)
        self._step_queue: deque[LLMStepResult | Exception] = deque()
        self.calls: list[FakeCall] = []
        self.step_calls: list[LLMStepRequest] = []

    def queue(self, task: str, item: Scripted) -> None:
        """Override the next call of ``task`` (calls are consumed in FIFO order)."""
        self._queued[task].append(item)

    def reset(self) -> None:
        self._queued.clear()
        self._step_queue.clear()
        self.calls.clear()
        self.step_calls.clear()

    def queue_step(self, item: LLMStepResult | Exception) -> None:
        """Script one model decision for coordinator and broker tests."""
        self._step_queue.append(item)

    def generate_step(self, request: LLMStepRequest) -> LLMStepResult:
        self.step_calls.append(request)
        if self._step_queue:
            item = self._step_queue.popleft()
            if isinstance(item, Exception):
                raise item
            return item
        # An unscripted offline agent yields visibly instead of inventing an effect.
        return LLMStepResult(
            kind="handoff",
            usage=LLMUsage(),
            latency_ms=0,
            provider=self.name,
            model="fake",
            is_fake=True,
            explanation="No scripted offline agent step is available.",
        )

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
    ) -> LLMResult:
        started = time.monotonic()
        self.calls.append(FakeCall(task, model, system, tuple(messages), context))
        scripted = self._queued[task].popleft() if self._queued[task] else None
        if isinstance(scripted, Exception):
            raise scripted
        if scripted is None:
            impl = _IMPLEMENTATIONS.get(task)
            if impl is None:
                raise LLMConfigError(f"the fake provider has no implementation for {task!r}")
            scripted = impl(context, output_schema)
        if isinstance(scripted, BaseModel):
            raw = scripted.model_dump_json()
        elif isinstance(scripted, dict):
            raw = json.dumps(scripted, ensure_ascii=False)
        else:
            raw = scripted
        return LLMResult(
            raw_text=raw,
            usage=LLMUsage(),
            latency_ms=int((time.monotonic() - started) * 1000),
            provider=self.name,
            model="fake",
            is_fake=True,
        )
