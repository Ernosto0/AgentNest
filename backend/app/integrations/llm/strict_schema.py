"""Strict JSON schemas for the small, closed tool argument models we own."""

from copy import deepcopy
from typing import Any

from pydantic import BaseModel


def strict_tool_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = deepcopy(model.model_json_schema())
    _close(schema)
    return schema


def _close(node: Any) -> None:
    if isinstance(node, list):
        for item in node:
            _close(item)
        return
    if not isinstance(node, dict):
        return
    if node.get("type") == "object":
        if node.get("additionalProperties", False) is not False:
            raise ValueError("tool argument objects must be closed")
        node["additionalProperties"] = False
        properties = node.get("properties", {})
        node["required"] = list(properties)
    node.pop("default", None)
    for item in node.values():
        _close(item)
