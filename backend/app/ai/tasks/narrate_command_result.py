"""LLM Task: narrate_command_result (conversational speech for command outcomes).

Converts structured command results into natural assistant responses while enforcing strict
numeric grounding (INV-08).
"""

from typing import Any

from pydantic import BaseModel, Field

from app.ai.prompt import data_section, json_section
from app.ai.runner import TaskDefinition
from app.commands.narrator import narrate_fallback, validate_metrics_grounding
from app.integrations.llm.base import LLMMessage
from app.integrations.llm.fake import fake_implementation

TASK = "narrate_command_result"


class NarrateCommandResultInput(BaseModel):
    user_query: str
    user_locale: str
    message_key: str
    params: dict[str, Any]


class NarrateCommandResultOutput(BaseModel):
    reply_text: str = Field(description="Natural, conversational assistant response")


def build_messages(task_input: NarrateCommandResultInput) -> list[LLMMessage]:
    body = "\n\n".join(
        [
            json_section("command_params", task_input.params),
            json_section(
                "context", {"locale": task_input.user_locale, "message_key": task_input.message_key}
            ),
            data_section("owner_query", task_input.user_query),
        ]
    )
    return [LLMMessage("user", body)]


def post_validate(
    task_input: NarrateCommandResultInput, output: NarrateCommandResultOutput
) -> list[str]:
    """Ensure output never invents numbers outside params (INV-08)."""
    return validate_metrics_grounding(
        output.reply_text, task_input.params, user_query=task_input.user_query
    )


def snapshot(task_input: NarrateCommandResultInput) -> dict[str, Any]:
    return task_input.model_dump(mode="json")


NARRATE_COMMAND_RESULT: TaskDefinition[NarrateCommandResultInput, NarrateCommandResultOutput] = (
    TaskDefinition(
        name=TASK,
        output_schema=NarrateCommandResultOutput,
        max_output_tokens=300,
        timeout_s=15.0,
        build_messages=build_messages,
        post_validate=post_validate,
        snapshot=snapshot,
    )
)


@fake_implementation(TASK)
def _fake_narrate_command_result(
    task_input: NarrateCommandResultInput,
) -> NarrateCommandResultOutput:
    """Deterministic, natural-sounding fallback in tests and demo mode."""
    reply = narrate_fallback(
        message_key=task_input.message_key,
        params=task_input.params,
        user_locale=task_input.user_locale,
        user_query=task_input.user_query,
    )
    if not reply:
        # Generic fallback
        reply = f"Operation completed: {task_input.message_key}"
    return NarrateCommandResultOutput(reply_text=reply)
