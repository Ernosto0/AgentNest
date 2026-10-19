"""The scriptable deterministic provider (testing-strategy.md §3)."""

import json
from typing import Any

import pytest
from pydantic import BaseModel

from app.integrations.llm import FakeLLMProvider, LLMMessage, build_provider
from app.integrations.llm.errors import LLMConfigError, LLMTransientError
from app.integrations.llm.fake import fake_implementation


class Out(BaseModel):
    value: int


@fake_implementation("unit_test_task")
def _default(context: Any, schema: type[BaseModel]) -> BaseModel:
    return schema(value=len(str(context)))


def _call(provider: FakeLLMProvider, task: str = "unit_test_task", context: object = "abc") -> Any:
    return provider.generate_structured(
        task=task,
        model="m",
        system="s",
        messages=[LLMMessage("user", "u")],
        output_schema=Out,
        max_output_tokens=10,
        timeout_s=1,
        context=context,
    )


def test_default_implementation_receives_the_typed_context() -> None:
    result = _call(FakeLLMProvider())
    assert json.loads(result.raw_text) == {"value": 3}
    assert result.is_fake is True and result.provider == "fake"
    assert result.usage.input_tokens is None  # no tokens for the fake provider


def test_queue_overrides_once_in_fifo_order_then_falls_back() -> None:
    provider = FakeLLMProvider()
    provider.queue("unit_test_task", Out(value=1))
    provider.queue("unit_test_task", {"value": 2})
    provider.queue("unit_test_task", "not json at all")
    assert json.loads(_call(provider).raw_text) == {"value": 1}
    assert json.loads(_call(provider).raw_text) == {"value": 2}
    assert _call(provider).raw_text == "not json at all"
    assert json.loads(_call(provider).raw_text) == {"value": 3}  # queue empty: default again


def test_queued_exceptions_are_raised() -> None:
    provider = FakeLLMProvider()
    provider.queue("unit_test_task", LLMTransientError("down"))
    with pytest.raises(LLMTransientError):
        _call(provider)


def test_unknown_task_is_a_config_error_not_a_guess() -> None:
    with pytest.raises(LLMConfigError):
        _call(FakeLLMProvider(), task="never_registered")


def test_calls_are_recorded() -> None:
    provider = FakeLLMProvider()
    _call(provider)
    assert provider.calls[0].task == "unit_test_task"
    assert provider.calls[0].messages[0].content == "u"


def test_build_provider_follows_settings_without_silent_fallback() -> None:
    from app.core.config import Settings

    assert build_provider(Settings(_env_file=None, llm_provider="fake")).name == "fake"
    real = build_provider(Settings(_env_file=None, llm_provider="openai", openai_api_key="sk-x"))
    assert real.name == "openai" and real.is_fake is False
