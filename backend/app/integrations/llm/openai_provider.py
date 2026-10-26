"""OpenAI adapter: legacy structured tasks and isolated Responses function steps.

- ``responses.parse(text_format=<Pydantic model>)`` sends a strict JSON schema, so the model's
  output is constrained to the task schema. The runner still re-validates ``raw_text``.
- ``store=False``: nothing is retained by OpenAI for later retrieval (agent-runtime.md §8).
- Legacy tasks send no tools; account-agent steps use only registered strict functions.
- This is the only module that imports the ``openai`` SDK.
"""

import json
import time
from typing import Any, cast

import httpx2 as httpx
import openai
from pydantic import BaseModel, ValidationError

from app.integrations.llm.base import LLMMessage, LLMResult, LLMUsage
from app.integrations.llm.errors import (
    LLMConfigError,
    LLMInvalidOutput,
    LLMRefusal,
    LLMTransientError,
)
from app.integrations.llm.steps import LLMStepRequest, LLMStepResult
from app.integrations.llm.strict_schema import strict_tool_schema

_RETRY_AFTER = "retry-after"


class OpenAIProvider:
    name = "openai"
    is_fake = False

    def __init__(
        self,
        api_key: str,
        *,
        reasoning_effort: str = "low",
        http_client: httpx.Client | None = None,
    ) -> None:
        # max_retries=0: retry policy belongs to the job (backoff 10 s / 60 s / 300 s), not here.
        self._client = openai.OpenAI(api_key=api_key, max_retries=0, http_client=http_client)
        self._reasoning_effort = reasoning_effort

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
        context: object | None = None,  # only the fake provider reads this
    ) -> LLMResult:
        started = time.monotonic()
        extra: dict[str, Any] = {}
        if self._reasoning_effort:
            extra["reasoning"] = {"effort": self._reasoning_effort}
        try:
            response = self._client.responses.parse(
                model=model,
                instructions=system,
                input=[{"role": m.role, "content": m.content} for m in messages],
                text_format=output_schema,
                max_output_tokens=max_output_tokens,
                store=False,
                timeout=timeout_s,
                **extra,
            )
        except openai.APITimeoutError as exc:
            raise LLMTransientError("timeout") from exc
        except openai.APIConnectionError as exc:
            raise LLMTransientError("connection error") from exc
        except openai.RateLimitError as exc:
            raise LLMTransientError("rate limited", retry_after_seconds=_retry_after(exc)) from exc
        except openai.InternalServerError as exc:
            raise LLMTransientError(f"server error {exc.status_code}") from exc
        except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            raise LLMConfigError("authentication or permission error") from exc
        except openai.ContentFilterFinishReasonError as exc:
            raise LLMRefusal("content filtered") from exc
        except openai.LengthFinishReasonError as exc:
            raise LLMInvalidOutput("output truncated at max_output_tokens") from exc
        except openai.APIStatusError as exc:  # remaining 4xx: the request itself was rejected
            raise LLMConfigError(f"request rejected ({exc.status_code})") from exc
        except ValidationError as exc:  # the SDK could not parse the text into the schema
            raise LLMInvalidOutput(f"unparseable output: {exc.error_count()} errors") from exc

        if response.status == "incomplete":
            raise LLMInvalidOutput(
                f"incomplete response: {getattr(response.incomplete_details, 'reason', None)}",
                raw_text=response.output_text or None,
            )
        for item in response.output:
            for part in getattr(item, "content", None) or []:
                if getattr(part, "type", None) == "refusal":
                    raise LLMRefusal("model refused")
        raw = response.output_text
        if not raw:
            raise LLMInvalidOutput("empty output")
        usage = response.usage
        cached = getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", None)
        return LLMResult(
            raw_text=raw,
            usage=LLMUsage(
                input_tokens=usage.input_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
                cached_input_tokens=cached,
            ),
            latency_ms=int((time.monotonic() - started) * 1000),
            provider=self.name,
            model=response.model or model,
            is_fake=False,
            metadata={"response_id": response.id},
        )

    def generate_step(self, request: LLMStepRequest) -> LLMStepResult:
        """Choose exactly one native function call, with no provider-side conversation state."""
        from typing import Literal

        from pydantic import ConfigDict

        class _Control(BaseModel):
            model_config = ConfigDict(extra="forbid")

            kind: Literal["wait", "complete", "handoff"]
            reason: str
            wait_for: str | None

        if len(request.tools) > 32 or len(request.observations) > 12:
            raise LLMConfigError("step tool or observation limit exceeded")

        tools: list[dict[str, Any]] = []
        for item in request.tools:
            tools.append(
                {
                    "type": "function",
                    "name": item.name,
                    "description": item.description,
                    "parameters": strict_tool_schema(item.arguments_schema),
                    "strict": True,
                }
            )
        tools.append(
            {
                "type": "function",
                "name": "agent_decide",
                "description": (
                    "Wait, finish this goal, or hand it to a human. Give a brief reason."
                ),
                "parameters": strict_tool_schema(_Control),
                "strict": True,
            }
        )
        model_input: list[dict[str, Any]] = [
            {"role": item.role, "content": item.content} for item in request.messages
        ]
        for observation in request.observations:
            encoded_result = json.dumps(observation.result, ensure_ascii=False)
            if len(encoded_result.encode("utf-8")) > 16384:
                raise LLMConfigError("tool observation exceeds limit")
            model_input.extend(
                [
                    {
                        "type": "function_call",
                        "name": observation.name,
                        "arguments": json.dumps(observation.arguments, ensure_ascii=False),
                        "call_id": observation.call_id,
                    },
                    {
                        "type": "function_call_output",
                        "call_id": observation.call_id,
                        "output": encoded_result,
                    },
                ]
            )
        started = time.monotonic()
        extra: dict[str, Any] = {}
        if self._reasoning_effort:
            extra["reasoning"] = {"effort": self._reasoning_effort}
        try:
            response = self._client.responses.create(
                model=request.model,
                instructions=request.system,
                input=cast(Any, model_input),
                tools=cast(Any, tools),
                tool_choice="required",
                parallel_tool_calls=False,
                max_output_tokens=request.max_output_tokens,
                store=False,
                timeout=request.timeout_s,
                **extra,
            )
        except openai.APITimeoutError as exc:
            raise LLMTransientError("timeout") from exc
        except openai.APIConnectionError as exc:
            raise LLMTransientError("connection error") from exc
        except openai.RateLimitError as exc:
            raise LLMTransientError("rate limited", retry_after_seconds=_retry_after(exc)) from exc
        except openai.InternalServerError as exc:
            raise LLMTransientError(f"server error {exc.status_code}") from exc
        except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            raise LLMConfigError("authentication or permission error") from exc
        except openai.APIStatusError as exc:
            raise LLMConfigError(f"request rejected ({exc.status_code})") from exc

        usage = response.usage
        captured = LLMUsage(
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            cached_input_tokens=getattr(
                getattr(usage, "input_tokens_details", None), "cached_tokens", None
            ),
        )
        if response.status == "incomplete":
            raise LLMInvalidOutput("incomplete step response", usage=captured)
        for item in response.output:
            for part in getattr(item, "content", None) or []:
                if getattr(part, "type", None) == "refusal":
                    raise LLMRefusal("model refused")
        calls = [item for item in response.output if item.type == "function_call"]
        if len(calls) != 1:
            raise LLMInvalidOutput(
                "step response must contain exactly one function call", usage=captured
            )
        call = calls[0]
        if len(call.arguments.encode("utf-8")) > 8192:
            raise LLMInvalidOutput("step arguments exceed 8192 bytes", usage=captured)
        try:
            arguments = json.loads(call.arguments)
        except ValueError as exc:
            raise LLMInvalidOutput("invalid function arguments", usage=captured) from exc
        if not isinstance(arguments, dict):
            raise LLMInvalidOutput("function arguments must be an object", usage=captured)
        common = {
            "usage": captured,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "provider": self.name,
            "model": response.model or request.model,
            "is_fake": False,
            "call_id": call.call_id,
            "metadata": {"response_id": response.id},
        }
        if call.name == "agent_decide":
            try:
                decision = _Control.model_validate(arguments)
            except ValidationError as exc:
                raise LLMInvalidOutput("invalid control decision", usage=captured) from exc
            if len(decision.reason) > 500 or (
                decision.wait_for is not None and len(decision.wait_for) > 100
            ):
                raise LLMInvalidOutput("control decision exceeds bounds", usage=captured)
            return LLMStepResult(
                kind=decision.kind,
                explanation=decision.reason,
                wait_for=decision.wait_for,
                **common,
            )
        reason = arguments.get("reason")
        explanation = (
            reason[:500]
            if isinstance(reason, str)
            else next(
                (item.description[:500] for item in request.tools if item.name == call.name),
                f"Call {call.name}",
            )
        )
        return LLMStepResult(
            kind="tool",
            tool_name=call.name,
            tool_arguments=arguments,
            explanation=explanation,
            **common,
        )


def _retry_after(exc: openai.RateLimitError) -> float | None:
    value = exc.response.headers.get(_RETRY_AFTER)
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None
