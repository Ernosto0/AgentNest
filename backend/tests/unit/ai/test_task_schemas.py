"""Task output models must be valid OpenAI strict-mode schemas, checked offline (ADR-009).

A schema the provider rejects would only show up in a manual run with a real key. This walks
the exact schema the SDK would send and fails on anything strict mode does not accept.
"""

from typing import Any

import pytest
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel

from app.ai.schemas import (
    ContentProposal,
    ExtractFactsOutput,
    InterpretCommandOutput,
    NormalizedMoney,
    QueryFact,
    ReplyProposal,
    Unsupported,
    UpdateFact,
)

OUTPUT_MODELS: list[type[BaseModel]] = [
    InterpretCommandOutput,
    ExtractFactsOutput,
    ReplyProposal,
    ContentProposal,
]

# Keywords strict mode rejects or that this codebase deliberately keeps out of provider schemas
# (limits are enforced by post-validators instead).
FORBIDDEN = {
    "oneOf", "allOf", "not", "if", "then", "else", "discriminator", "default",
    "minLength", "maxLength", "pattern", "format", "minItems", "maxItems",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "patternProperties", "propertyNames", "unevaluatedProperties",
}  # fmt: skip


def _walk(node: Any, path: str = "$") -> list[str]:
    problems: list[str] = []
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            props = node.get("properties", {})
            if node.get("additionalProperties") is not False:
                problems.append(f"{path}: object must set additionalProperties=false")
            if sorted(node.get("required", [])) != sorted(props):
                problems.append(f"{path}: every property must be required")
        for key, value in node.items():
            if key in FORBIDDEN:
                problems.append(f"{path}: forbidden keyword {key!r}")
            problems += _walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            problems += _walk(item, f"{path}[{index}]")
    return problems


@pytest.mark.parametrize("model", OUTPUT_MODELS, ids=lambda m: m.__name__)
def test_provider_schema_is_strict_mode_compatible(model: type[BaseModel]) -> None:
    schema = to_strict_json_schema(model)
    assert schema["type"] == "object", "structured outputs need an object at the root"
    assert _walk(schema) == []


def test_the_walker_actually_catches_problems() -> None:
    bad = {
        "type": "object",
        "properties": {"a": {"type": "string", "maxLength": 3}, "b": {"oneOf": []}},
        "required": ["a"],
    }
    problems = _walk(bad)
    assert len(problems) >= 4  # open object, missing required, maxLength, oneOf


def test_the_interpretation_is_a_union_of_closed_types() -> None:
    schema = to_strict_json_schema(InterpretCommandOutput)
    defs = schema["$defs"]
    tags = {d["properties"]["type"]["const"] for d in defs.values() if "type" in d["properties"]}
    assert tags == {
        "query.activity_summary",
        "query.pending_approvals",
        "query.fact",
        "knowledge.update_fact",
        "knowledge.update_brand_voice",
        "query.content_status",
        "query.explain_failure",
        "content.create_draft",
        "content.cancel_scheduled",
        "clarify",
        "unsupported",
    }
    assert not {"approve", "publish", "send_message", "reject"} & tags  # INV-04


# --- the model's output is a proposal: unknown types never become executable ----------------


@pytest.mark.parametrize(
    "bad_type",
    ["approvals.approve", "approve", "content.publish_now", "message.send", "", "QUERY.FACT", None],
)
def test_a_type_outside_the_registry_becomes_unsupported(bad_type: object) -> None:
    parsed = InterpretCommandOutput.model_validate(
        {"interpretation": {"type": bad_type, "approval_id": "x"}}
    )
    assert parsed.interpretation == Unsupported(type="unsupported", reason="other")


def test_a_valid_type_with_bad_fields_is_not_silently_rewritten() -> None:
    with pytest.raises(ValueError):
        InterpretCommandOutput.model_validate({"interpretation": {"type": "query.fact"}})


def test_known_types_parse_to_their_models() -> None:
    parsed = InterpretCommandOutput.model_validate_json(
        '{"interpretation": {"type": "knowledge.update_fact", "fact_key": "pricing.x.y",'
        ' "raw_value_text": "7.000 TL", "reason": null,'
        ' "normalized_value": {"kind": "money", "amount": "7000.00", "currency": "TRY"}}}'
    )
    assert parsed.interpretation == UpdateFact(
        type="knowledge.update_fact",
        fact_key="pricing.x.y",
        raw_value_text="7.000 TL",
        reason=None,
        normalized_value=NormalizedMoney(kind="money", amount="7000.00", currency="TRY"),
    )
    assert InterpretCommandOutput.model_validate(
        {"interpretation": {"type": "query.fact", "fact_key": "a.b"}}
    ).interpretation == QueryFact(type="query.fact", fact_key="a.b")
