"""Stage a draft and a durable render job inside the human decision transaction."""

import uuid
from typing import Any

from app.commands.resolver import content_link
from app.commands.results import CommandResult, ExecContext
from app.content.templates.staging import stage_price_card
from app.knowledge import repository
from app.knowledge.service import usable_facts


def execute(ec: ExecContext, resolution: dict[str, Any]) -> CommandResult:
    fact = repository.get_fact(ec.session, ec.ctx, uuid.UUID(resolution["fact_id"]), lock=True)
    if (
        fact is None
        or fact.current_version != resolution["fact_version"]
        or fact.key != resolution["fact_key"]
    ):
        return CommandResult("command.fact_changed_meanwhile", error_code="FACT_CHANGED_MEANWHILE")
    label = fact.label.get(ec.user_locale) or fact.label.get("tr") or fact.key
    if fact.value_type != "money" or not any(
        f.fact_id == fact.id for f in usable_facts(ec.session, ec.clock, ec.ctx)
    ):
        return CommandResult(
            "command.price_card_fact_unusable",
            {"label": label},
            error_code="TEMPLATE_FACT_NOT_USABLE",
        )
    item = stage_price_card(
        ec.session,
        ec.clock,
        ec.ctx,
        command_id=ec.command.id,
        label=label,
        fact_key=fact.key,
        format=resolution["format"],
        language=resolution["language"],
    )
    return CommandResult(
        "command.price_card_started", {"title": item.title, "label": label}, [content_link(item.id)]
    )
