"""The closed registry (INV-04) and the command state machine (state-machines.md §3)."""

import pytest

from app.ai.schemas import INTERPRETATION_TYPES, InterpretCommandOutput
from app.commands.registry import REGISTRY, describe_registry
from app.commands.transitions import COMMAND_EVENTS, TERMINAL, apply_command_event
from app.core.errors import AppError
from app.identity.permissions import PERMISSION_MATRIX

FORBIDDEN_WORDS = ("approve", "reject", "publish", "send", "schedule", "connect", "disconnect")


@pytest.mark.invariant("INV-04")
def test_no_command_type_can_approve_publish_or_send() -> None:
    types = set(REGISTRY) | INTERPRETATION_TYPES
    for command_type in types:
        for word in FORBIDDEN_WORDS:
            assert word not in command_type, (command_type, word)
    assert {s.type for s in REGISTRY.values() if s.mutating} == {
        "knowledge.update_fact",
        "knowledge.update_brand_voice",
    }


@pytest.mark.invariant("INV-04")
def test_the_output_schema_cannot_express_an_approval() -> None:
    schema = InterpretCommandOutput.model_json_schema()
    tags = {
        d["properties"]["type"]["const"]
        for d in schema["$defs"].values()
        if "type" in d.get("properties", {})
    }
    assert tags == INTERPRETATION_TYPES


def test_the_registry_and_the_output_union_list_the_same_types() -> None:
    assert set(REGISTRY) | {"clarify"} == INTERPRETATION_TYPES
    assert {e.type for e in describe_registry()} == INTERPRETATION_TYPES


def test_every_entry_is_well_formed() -> None:
    for spec in REGISTRY.values():
        assert spec.required_permission in PERMISSION_MATRIX, spec.type
        assert spec.params_model.model_fields["type"].annotation is not None
        assert spec.description and callable(spec.executor)
        if spec.mutating:  # state changes always go through a confirmation approval
            assert spec.confirmation_summary_builder is not None, spec.type
            assert spec.approval_action is not None, spec.type
        else:
            assert spec.confirmation_summary_builder is None and spec.approval_action is None


def test_the_registry_description_is_static_and_workspace_independent() -> None:
    assert describe_registry() == describe_registry()
    assert all(e.description for e in describe_registry())


# --- state machine ---------------------------------------------------------------------------

ALLOWED = {
    (None, "submit"): "interpreting",
    ("interpreting", "complete"): "completed",
    ("interpreting", "ask_confirmation"): "awaiting_confirmation",
    ("interpreting", "clarify"): "needs_clarification",
    ("interpreting", "unsupported"): "unsupported",
    ("interpreting", "fail"): "failed",
    ("needs_clarification", "answer"): "interpreting",
    ("needs_clarification", "cancel"): "cancelled",
    ("needs_clarification", "expire"): "expired",
    ("awaiting_confirmation", "approved"): "executing",
    ("awaiting_confirmation", "cancel"): "cancelled",
    ("awaiting_confirmation", "expire"): "expired",
    ("executing", "complete"): "completed",
    ("executing", "fail"): "failed",
}


@pytest.mark.parametrize(("key", "expected"), sorted(ALLOWED.items(), key=str))
def test_every_documented_transition(key: tuple[str | None, str], expected: str) -> None:
    assert apply_command_event(*key) == expected


def test_everything_else_is_refused() -> None:
    states = {
        None,
        "interpreting",
        "needs_clarification",
        "awaiting_confirmation",
        "executing",
    } | TERMINAL
    for state in states:
        for event in COMMAND_EVENTS:
            if (state, event) in ALLOWED:
                continue
            with pytest.raises(AppError) as info:
                apply_command_event(state, event)
            assert info.value.code == "CONFLICT_STATE", (state, event)


def test_terminal_states_are_final() -> None:
    for state in TERMINAL:
        assert not [k for k in ALLOWED if k[0] == state]
