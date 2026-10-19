"""``query.fact``: answer from the fact, rendered through the same renderer as customer text
(INV-02). A fact that is not usable (unverified, contested, expired) is described, never shown
as if it were current."""

import uuid
from typing import Any

from app.commands.results import CommandResult, ExecContext, knowledge_link
from app.core.errors import AppError
from app.knowledge import repository as knowledge_repo
from app.knowledge import service as knowledge_service
from app.knowledge.render import render


def execute(ec: ExecContext, resolution: dict[str, Any]) -> CommandResult:
    fact = knowledge_repo.get_fact(ec.session, ec.ctx, uuid.UUID(resolution["fact_id"]))
    if fact is None or fact.status == "archived":
        raise AppError("NOT_FOUND")
    view = knowledge_service.fact_view(ec.session, ec.clock, ec.ctx, fact, ui_locale=ec.user_locale)
    label = fact.label.get(ec.user_locale) or fact.label.get("tr") or fact.key
    links = [knowledge_link(category=fact.category, key=fact.key)]
    usable = knowledge_service.usable_facts(ec.session, ec.clock, ec.ctx)
    rendered = render(
        "{{fact:" + fact.key + "}}", usable, ec.user_locale, fallback_locale=ec.ctx.locale
    )
    if rendered.ok:
        return CommandResult(
            "command.fact_value", {"label": label, "display": rendered.text}, links
        )
    return CommandResult(
        "command.fact_not_usable",
        {"label": label, "state": view.state, "display": view.display},
        links,
    )
