"""The closed command registry (agent-runtime.md §3, ADR-007, INV-04).

Every command the system can run is listed here and nowhere else. There is **no** entry for
approve, reject, publish now, send a message, connect or disconnect accounts, change automation
policies or manage members: those are answered ``unsupported`` with a pointer into the app, and
a test pins that no such type can ever be added by accident.
"""

import builtins
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.ai.schemas import (
    QueryActivitySummary,
    QueryFact,
    QueryPendingApprovals,
    RegistryEntry,
    Unsupported,
    UpdateBrandVoice,
    UpdateFact,
)
from app.commands.executors import (
    query_activity_summary,
    query_fact,
    query_pending_approvals,
    unsupported,
    update_fact,
)
from app.commands.results import CommandResult, ExecContext
from app.knowledge.impact import ImpactReport

Executor = Callable[[ExecContext, dict[str, Any]], CommandResult]
# (summary shown on the card, what the change would touch) -> the stored confirmation summary
SummaryBuilder = Callable[[dict[str, Any], ImpactReport], dict[str, Any]]


def fact_change_summary(summary: dict[str, Any], impact: ImpactReport) -> dict[str, Any]:
    """Old and new value plus what the change would touch (workflows.md §B step 2.4)."""
    return {**summary, "impact": impact.to_dict()}


@dataclass(frozen=True)
class CommandSpec:
    type: str
    mutating: bool
    required_permission: str
    params_model: builtins.type[BaseModel]  # ``type`` is shadowed by the field above
    executor: Executor
    confirmation_summary_builder: SummaryBuilder | None
    description: str
    parameters: dict[str, str]
    approval_action: str | None = None  # set for every mutating command


REGISTRY: dict[str, CommandSpec] = {
    spec.type: spec
    for spec in (
        CommandSpec(
            type="query.fact",
            mutating=False,
            required_permission="commands.use",
            params_model=QueryFact,
            executor=query_fact.execute,
            confirmation_summary_builder=None,
            description="Answer a question about one business fact (a price, hours, a phone).",
            parameters={"fact_key": "a key from business_facts"},
        ),
        CommandSpec(
            type="query.pending_approvals",
            mutating=False,
            required_permission="approvals.view",
            params_model=QueryPendingApprovals,
            executor=query_pending_approvals.execute,
            confirmation_summary_builder=None,
            description="List what is waiting for the owner's approval. Never approves anything.",
            parameters={},
        ),
        CommandSpec(
            type="query.activity_summary",
            mutating=False,
            required_permission="reports.view",
            params_model=QueryActivitySummary,
            executor=query_activity_summary.execute,
            confirmation_summary_builder=None,
            description="Basic counts of what happened in a period.",
            parameters={"period": "today | yesterday | last_7_days"},
        ),
        CommandSpec(
            type="knowledge.update_fact",
            mutating=True,
            required_permission="knowledge.edit",
            params_model=UpdateFact,
            executor=update_fact.execute_update_fact,
            confirmation_summary_builder=fact_change_summary,
            description="Change the value of an existing business fact. The owner confirms first.",
            parameters={
                "fact_key": "a key from business_facts",
                "raw_value_text": "the new value exactly as typed",
                "normalized_value": "your reading of it (money: amount string + currency)",
                "reason": "optional reason",
            },
            approval_action="command.update_fact",
        ),
        CommandSpec(
            type="knowledge.update_brand_voice",
            mutating=True,
            required_permission="knowledge.edit",
            params_model=UpdateBrandVoice,
            executor=update_fact.execute_update_brand_voice,
            confirmation_summary_builder=fact_change_summary,
            description="Change the brand voice guidelines. The owner confirms first.",
            parameters={
                "instruction": "what the owner asked for",
                "proposed_guidelines": "the complete new guidelines text",
            },
            approval_action="command.update_brand_voice",
        ),
        CommandSpec(
            type="unsupported",
            mutating=False,
            required_permission="commands.use",
            params_model=Unsupported,
            executor=unsupported.execute,
            confirmation_summary_builder=None,
            description=(
                "Anything else, including approving, rejecting, publishing, sending messages, "
                "connecting accounts, automation settings and managing members."
            ),
            parameters={
                "reason": "publish | send_message | approve | manage_account | settings"
                " | members | other"
            },
        ),
    )
}


def describe_registry() -> list[RegistryEntry]:
    """The registry as the interpreter's prompt sees it (static text; ``clarify`` is added)."""
    entries = [
        RegistryEntry(type=s.type, description=s.description, parameters=s.parameters)
        for s in REGISTRY.values()
    ]
    entries.append(
        RegistryEntry(
            type="clarify",
            description="The instruction is ambiguous (for example which price). Do not guess.",
            parameters={
                "intent": "knowledge.update_fact | query.fact | knowledge.update_brand_voice",
                "candidate_fact_keys": "plausible keys from business_facts",
                "raw_value_text": "the value as typed, if any",
            },
        )
    )
    return entries
