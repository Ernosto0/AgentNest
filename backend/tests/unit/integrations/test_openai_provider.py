"""OpenAI adapter against a stubbed HTTP transport: no network, no key (ADR-009)."""

import json
from collections.abc import Callable
from typing import Any, Literal

import httpx2 as httpx
import pytest
from pydantic import BaseModel

from app.integrations.llm.base import LLMMessage
from app.integrations.llm.errors import (
    LLMConfigError,
    LLMInvalidOutput,
    LLMRefusal,
    LLMTransientError,
)
from app.integrations.llm.openai_provider import OpenAIProvider


class Answer(BaseModel):
    kind: Literal["ok", "no"]
    note: str


def _response_body(output: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "status": "completed",
        "model": "gpt-6-luna-2026",
        "output": output,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "usage": {
            "input_tokens": 120,
            "input_tokens_details": {"cached_tokens": 64},
            "output_tokens": 30,
            "output_tokens_details": {"reasoning_tokens": 5},
            "total_tokens": 150,
        },
    }
    body.update(overrides)
    return body


def _message(text: str) -> dict[str, Any]:
    return {
        "type": "message",
        "id": "msg_1",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def _provider(
    handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any
) -> tuple[OpenAIProvider, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = httpx.Client(transport=httpx.MockTransport(record))
    return OpenAIProvider("sk-test", http_client=client, **kwargs), seen


def _call(provider: OpenAIProvider) -> Any:
    return provider.generate_structured(
        task="interpret_command",
        model="gpt-6-luna",
        system="SYSTEM RULES",
        messages=[LLMMessage("user", "<task_parameters>x</task_parameters>")],
        output_schema=Answer,
        max_output_tokens=800,
        timeout_s=5,
    )


def test_request_is_strict_unstored_and_toolless_and_usage_is_captured() -> None:
    provider, seen = _provider(
        lambda _: httpx.Response(200, json=_response_body([_message('{"kind":"ok","note":"x"}')]))
    )
    result = _call(provider)

    assert Answer.model_validate_json(result.raw_text) == Answer(kind="ok", note="x")
    assert (result.usage.input_tokens, result.usage.output_tokens) == (120, 30)
    assert result.usage.cached_input_tokens == 64
    assert result.provider == "openai" and result.is_fake is False

    assert len(seen) == 1 and seen[0].url.path.endswith("/responses")
    body = json.loads(seen[0].content)
    assert body["store"] is False  # data minimisation
    assert not body.get("tools")  # tasks have no tools (ADR-007)
    assert body["instructions"] == "SYSTEM RULES"
    assert body["max_output_tokens"] == 800
    assert body["reasoning"] == {"effort": "low"}
    fmt = body["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True
    assert fmt["schema"]["additionalProperties"] is False
    assert sorted(fmt["schema"]["required"]) == ["kind", "note"]
    assert seen[0].headers["authorization"] == "Bearer sk-test"


def test_reasoning_effort_can_be_switched_off() -> None:
    provider, seen = _provider(
        lambda _: httpx.Response(200, json=_response_body([_message('{"kind":"ok","note":"x"}')])),
        reasoning_effort="",
    )
    _call(provider)
    assert "reasoning" not in json.loads(seen[0].content)


@pytest.mark.parametrize("status", [500, 502, 503])
def test_server_errors_are_transient(status: int) -> None:
    provider, _ = _provider(lambda _: httpx.Response(status, json={"error": {"message": "boom"}}))
    with pytest.raises(LLMTransientError):
        _call(provider)


def test_rate_limit_is_transient_and_keeps_retry_after() -> None:
    provider, seen = _provider(
        lambda _: httpx.Response(
            429, headers={"retry-after": "42"}, json={"error": {"message": "slow down"}}
        )
    )
    with pytest.raises(LLMTransientError) as info:
        _call(provider)
    assert info.value.retry_after_seconds == 42
    assert len(seen) == 1  # the SDK must not retry on its own: the job owns the backoff


def test_timeout_and_connection_errors_are_transient() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("t", request=request)

    provider, _ = _provider(boom)
    with pytest.raises(LLMTransientError):
        _call(provider)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("c", request=request)

    provider, _ = _provider(down)
    with pytest.raises(LLMTransientError):
        _call(provider)


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_credential_and_request_errors_are_config_errors(status: int) -> None:
    provider, _ = _provider(lambda _: httpx.Response(status, json={"error": {"message": "no"}}))
    with pytest.raises(LLMConfigError):
        _call(provider)


def test_a_refusal_is_not_retried_and_not_an_output() -> None:
    refusal = {
        "type": "message",
        "id": "msg_1",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "refusal", "refusal": "I can't help with that."}],
    }
    provider, _ = _provider(lambda _: httpx.Response(200, json=_response_body([refusal])))
    with pytest.raises(LLMRefusal):
        _call(provider)


def test_truncated_json_is_invalid_output() -> None:
    body = _response_body(
        [_message('{"kind":"ok","no')],
        status="incomplete",
        incomplete_details={"reason": "max_output_tokens"},
    )
    provider, _ = _provider(lambda _: httpx.Response(200, json=body))
    with pytest.raises(LLMInvalidOutput):  # the SDK cannot parse the cut-off text
        _call(provider)


def test_incomplete_response_without_output_is_invalid_output() -> None:
    body = _response_body(
        [], status="incomplete", incomplete_details={"reason": "max_output_tokens"}
    )
    provider, _ = _provider(lambda _: httpx.Response(200, json=body))
    with pytest.raises(LLMInvalidOutput, match="max_output_tokens"):
        _call(provider)


def test_malformed_json_is_invalid_output() -> None:
    provider, _ = _provider(
        lambda _: httpx.Response(200, json=_response_body([_message('{"kind": "maybe"}')]))
    )
    with pytest.raises(LLMInvalidOutput):
        _call(provider)
