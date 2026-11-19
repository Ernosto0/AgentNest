"""Account Agent proposals against an immutable, isolated practice snapshot.

The provider sees the production Agent prompt and tool schemas. This adapter deliberately
does not call ToolBroker.dispatch: its database handlers include live writes and effects.
Only bounded snapshot reads and pure production grounding/policy are executable here.
"""

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.agent.context import SYSTEM
from app.agent.delegation import ActionRule, Decision, decide
from app.agent.grounding import ReplyValidationArgs, validate_template_reply
from app.agent.policy import classify_request, evaluate_action_policy
from app.agent.tools.broker import BrokerContext, build_default_broker
from app.ai.prompt import json_section, untrusted_section
from app.ai.runner import RunnerDeps
from app.ai.step_runner import run_step
from app.inbox.context import DraftContext
from app.integrations.llm.base import LLMMessage
from app.integrations.llm.steps import LLMStepRequest, LLMToolObservation
from app.knowledge.render import placeholder_keys


@dataclass(frozen=True)
class PracticeSnapshot:
    context: DraftContext
    account_id: uuid.UUID
    config_version: int
    delegation_version: int | None
    rule: ActionRule
    persona_version: int
    personality: dict[str, Any]
    goals: str
    calendar_connected: bool = False
    active: bool = True
    quota_available: bool = True


@dataclass(frozen=True)
class PracticeResult:
    decision: str
    reasons: tuple[str, ...]
    text: str | None = None
    template: str | None = None
    rendered: tuple[dict[str, object], ...] = ()
    agent_run_ids: tuple[uuid.UUID, ...] = ()
    language: str | None = None
    # Tool outcomes contain simulated metadata, never real resource/action identifiers.
    simulations: tuple[str, ...] = field(default=())


def _facts(snapshot: PracticeSnapshot) -> list[dict[str, Any]]:
    return [
        {
            "id": str(fact.fact_id),
            "key": fact.key,
            "version": fact.version,
            "display": fact.display,
            "placeholder": fact.placeholder,
            "category": fact.category,
            "visibility": "public_business",
        }
        for fact in snapshot.context.facts
    ]


def _answers(snapshot: PracticeSnapshot) -> list[dict[str, Any]]:
    return [
        {
            "id": str(answer.id),
            "version": answer.version,
            "language": answer.language,
            "title": answer.title,
            "template": answer.answer_template,
        }
        for answer in snapshot.context.approved_answers
    ]


def request_for(snapshot: PracticeSnapshot) -> LLMStepRequest:
    context = snapshot.context
    broker_context = BrokerContext(
        context.ctx, snapshot.account_id, context.conversation_id, "dm", "customer"
    )
    tools = build_default_broker().available(
        broker_context, capabilities={"calendar_connected": snapshot.calendar_connected}
    )
    facts = _facts(snapshot)
    data: dict[str, Any] = {
        "surface": "dm",
        "reply_language": context.language.code,
        "persona_version": snapshot.persona_version,
        "personality": snapshot.personality,
        "goal_instructions": snapshot.goals[:500],
        "event_cursor": len(context.history),
        "turns": [
            {
                "id": str(uuid.uuid5(context.conversation_id, str(index))),
                "direction": "inbound" if role == "customer" else "outbound",
                "text": text[:500],
            }
            for index, (role, text) in enumerate(context.history[-8:])
        ],
        "knowledge": {"facts": facts[:4], "next_cursor": None},
        "approved_answers": {"answers": _answers(snapshot)[:2], "next_cursor": None},
        "customer_memory": {"memories": []},
        "owner_answers": [],
        "private_origin": None,
    }
    body = untrusted_section("untrusted_agent_context", json.dumps(data, ensure_ascii=False))
    body += "\n" + json_section(
        "source_references",
        [
            {"id": item["id"], "version": item["version"], "placeholder": item["placeholder"]}
            for item in facts[:4]
        ],
    )
    return LLMStepRequest(
        task="account_agent_step",
        model="fake",
        system=SYSTEM,
        messages=(LLMMessage("user", body),),
        tools=tools,
    )


def dispatch_snapshot_tool(
    snapshot: PracticeSnapshot, request: LLMStepRequest, name: str, arguments: dict[str, Any]
) -> tuple[dict[str, Any], PracticeResult | None]:
    """Schema-check a proposal and handle it without any Session or live tool handler."""
    try:
        argument_bytes = len(json.dumps(arguments, ensure_ascii=False).encode("utf-8"))
    except (ValueError, TypeError):
        return {"ok": False, "error": "TOOL_ARGUMENT_INVALID"}, None
    if argument_bytes > 8192:
        return {"ok": False, "error": "TOOL_ARGUMENT_TOO_LARGE"}, None
    schema = next((tool.arguments_schema for tool in request.tools if tool.name == name), None)
    if schema is None:
        return {"ok": False, "error": "TOOL_FORBIDDEN", "is_simulated": True}, None
    try:
        parsed = schema.model_validate(arguments)
    except (ValidationError, ValueError):
        return {"ok": False, "error": "TOOL_ARGUMENT_INVALID", "is_simulated": True}, None
    context = snapshot.context
    payload: dict[str, Any] = {"is_simulated": True}
    if name in {"reply.validate", "dm.send", "approval.request"}:
        proposal = ReplyValidationArgs.model_validate(parsed)
        if proposal.language != context.language.code:
            return {"valid": False, "errors": ["REPLY_LANGUAGE_MISMATCH"]}, None
        grounded = validate_template_reply(proposal, context.facts)
        payload.update(valid=grounded.valid, text=grounded.text, errors=list(grounded.errors))
        if not grounded.valid or name == "reply.validate":
            return payload, None
        classification = classify_request(
            action_type="dm.send",
            surface="dm",
            inbound_text=context.customer_text,
            template=proposal.template,
            used_fact_keys=placeholder_keys(proposal.template),
            prices_shared=context.price_disclosure == "share",
            workspace_escalation_keywords=context.escalation_keywords,
        )
        base = decide(
            rule=snapshot.rule,
            source="customer",
            requester_allowed=True,
            account_active=snapshot.active,
            capability_available=bool(context.account_capabilities.get("messaging")),
            target_owned=True,
            visibility_allowed=True,
            claims_valid=True,
            quota_available=snapshot.quota_available,
        )
        evaluated = evaluate_action_policy(snapshot.rule, classification, base_decision=base)
        if name == "approval.request" and evaluated.kind == "automatic":
            evaluated = Decision("ask", "explicit_approval_requested")
        decision = {
            "automatic": "auto",
            "ask": "approval_required",
            "off": "blocked",
            "blocked": "blocked",
        }.get(evaluated.kind, "human_required")
        return payload, PracticeResult(
            decision,
            (evaluated.reason,),
            grounded.text if decision in {"auto", "approval_required"} else None,
            proposal.template,
            grounded.rendered,
            language=proposal.language,
        )
    if name == "knowledge.read":
        limit = getattr(parsed, "limit", 4)
        if not 1 <= limit <= 20:
            return {"ok": False, "error": "TOOL_ARGUMENT_INVALID"}, None
        facts = _facts(snapshot)
        cursor = getattr(parsed, "cursor", None)
        payload.update(
            facts=[f for f in facts if cursor is None or f["key"] > cursor][:limit],
            next_cursor=None,
        )
    elif name == "knowledge.answers":
        payload.update(
            answers=[
                a for a in _answers(snapshot) if a["language"] == getattr(parsed, "language", None)
            ][: getattr(parsed, "limit", 2)],
            next_cursor=None,
        )
    elif name == "thread.read":
        payload["messages"] = json.loads(
            # The history itself is copied; no real thread is looked up by model arguments.
            json.dumps(
                [
                    {
                        "direction": "inbound" if role == "customer" else "outbound",
                        "text": text[:1000],
                    }
                    for role, text in context.history[-getattr(parsed, "limit", 8) :]
                ]
            )
        )
    elif name == "memory.read":
        payload["memories"] = []
    elif name == "memory.write":
        payload.update(status="simulated", persisted=False)
    elif name == "owner.ask":
        return payload, PracticeResult(
            "human_required",
            ("SANDBOX_OWNER_INPUT_REQUIRED",),
            language=context.language.code,
            simulations=(name,),
        )
    elif name.startswith("calendar."):
        # A practice chat has no real customer or live availability. Never read the
        # production calendar or accept live appointment IDs as simulated evidence.
        return {**payload, "status": "simulated", "verified": False}, PracticeResult(
            "human_required",
            ("SANDBOX_CALENDAR_SIMULATED",),
            language=context.language.code,
            simulations=(name,),
        )
    else:
        return {"ok": False, "error": "TOOL_FORBIDDEN", "is_simulated": True}, None
    return payload, None


def run_practice(
    deps: RunnerDeps, snapshot: PracticeSnapshot, *, job_id: uuid.UUID | None = None
) -> PracticeResult:
    """Use the production provider's bounded Agent step API, never legacy draft_reply."""
    from dataclasses import replace

    from app.agent.coordinator import _fit_request_budget

    if snapshot.context.language.code is None:
        return PracticeResult("human_required", ("LANGUAGE_UNSUPPORTED",))
    if not snapshot.active:
        return PracticeResult("blocked", ("AGENT_INACTIVE",))
    request = request_for(snapshot)
    run_ids: list[uuid.UUID] = []
    observations: list[LLMToolObservation] = []
    started = time.monotonic()
    calls = 0
    for _ in range(8):
        if calls >= 8 or time.monotonic() - started >= 120:
            break
        fitted = _fit_request_budget(replace(request, observations=tuple(observations)))
        if fitted is None:
            return PracticeResult(
                "human_required", ("AGENT_CONTEXT_LIMIT",), agent_run_ids=tuple(run_ids)
            )
        outcome = run_step(
            deps,
            snapshot.context.ctx,
            None,
            fitted,
            job_id=job_id,
            test_turn_id=snapshot.context.conversation_id,
            allow_repair=calls < 7,
        )
        calls += 1 + outcome.repair_attempts
        run_ids.append(outcome.agent_run_id)
        step = outcome.result
        if step is None:
            return PracticeResult(
                "human_required",
                (outcome.error_code or "LLM_UNAVAILABLE",),
                agent_run_ids=tuple(run_ids),
            )
        if step.kind != "tool" or not step.tool_name:
            return PracticeResult(
                "human_required", ("AGENT_HANDOFF",), agent_run_ids=tuple(run_ids)
            )
        data, result = dispatch_snapshot_tool(
            snapshot, request, step.tool_name, step.tool_arguments
        )
        if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > 16384:
            data = {"ok": False, "error": "TOOL_RESULT_TOO_LARGE"}
        if result is not None:
            return replace(result, agent_run_ids=tuple(run_ids))
        observations.append(
            LLMToolObservation(
                step.call_id or str(uuid.uuid4()), step.tool_name, step.tool_arguments, data
            )
        )
    return PracticeResult("human_required", ("AGENT_STEP_LIMIT",), agent_run_ids=tuple(run_ids))
