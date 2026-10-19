"""OpenAI adapter (ADR-009 amendment): Responses API with structured outputs, no tools.

- ``responses.parse(text_format=<Pydantic model>)`` sends a strict JSON schema, so the model's
  output is constrained to the task schema. The runner still re-validates ``raw_text``.
- ``store=False``: nothing is retained by OpenAI for later retrieval (agent-runtime.md §8).
- No ``tools``: tasks are single proposal calls (ADR-007).
- This is the only module that imports the ``openai`` SDK.
"""

import time
from typing import Any

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


def _retry_after(exc: openai.RateLimitError) -> float | None:
    value = exc.response.headers.get(_RETRY_AFTER)
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None
