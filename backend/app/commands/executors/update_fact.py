"""``knowledge.update_fact`` and ``knowledge.update_brand_voice`` (workflows.md §B step 3).

Runs inside the approval's decided-callback, i.e. in the same transaction as the decision, as
the **human who decided** (INV-04): an owner or manager writes a new verified version; staff
only propose a ``contest`` candidate. A fact that changed since the owner confirmed (version
moved, archived) is not overwritten: the command fails with ``FACT_CHANGED_MEANWHILE`` and the
owner asks again with the current value in front of them.
"""

import uuid
from typing import Any

from app.commands.results import CommandResult, ExecContext, knowledge_link
from app.knowledge import repository as knowledge_repo
from app.knowledge import service as knowledge_service
from app.knowledge.formatting import format_value
from app.knowledge.models import FactCandidate


def _execute(ec: ExecContext, resolution: dict[str, Any], keys: tuple[str, str]) -> CommandResult:
    applied_key, proposed_key = keys
    fact = knowledge_repo.get_fact(ec.session, ec.ctx, uuid.UUID(resolution["fact_id"]), lock=True)
    if (
        fact is None
        or fact.status == "archived"
        or fact.current_version != resolution["from_version"]
    ):
        return CommandResult("command.fact_changed_meanwhile", error_code="FACT_CHANGED_MEANWHILE")
    label = fact.label.get(ec.user_locale) or fact.label.get("tr") or fact.key
    workspace_locale = ec.ctx.locale
    old_display = format_value(fact.value_type, fact.value, ec.user_locale, workspace_locale)
    category, key, value_type = fact.category, fact.key, fact.value_type
    result = knowledge_service.apply_update(
        ec.session,
        ec.clock,
        ec.ctx,
        fact.id,
        expected_version=resolution["from_version"],
        value=resolution["new_value"],
        reason=resolution.get("reason"),
        source_type="owner_command",
        source_ref=str(ec.command.id),
    )
    links = [knowledge_link(category=category, key=key)]
    new_display = format_value(
        value_type, resolution["new_value"], ec.user_locale, workspace_locale
    )
    if isinstance(result, FactCandidate):  # staff: a proposal for an owner or manager to accept
        return CommandResult(proposed_key, {"label": label, "new_display": new_display}, links)
    return CommandResult(
        applied_key,
        {
            "label": label,
            "old_display": old_display,
            "new_display": new_display,
            "version": result.current_version,
        },
        links,
    )


def execute_update_fact(ec: ExecContext, resolution: dict[str, Any]) -> CommandResult:
    return _execute(ec, resolution, ("command.fact_updated", "command.fact_proposed"))


def execute_update_brand_voice(ec: ExecContext, resolution: dict[str, Any]) -> CommandResult:
    return _execute(ec, resolution, ("command.brand_voice_updated", "command.brand_voice_proposed"))
