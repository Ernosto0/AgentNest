"""Task ``extract_fact_candidates`` (agent-runtime.md §6): task definition plus its fake.

The model proposes ``(fact_key, raw value, verbatim excerpt)`` triples from pasted text. They
only ever become *candidates* for the owner to accept (INV-02): `knowledge.extraction` drops
anything whose excerpt is not really in the text. The fake extracts money, phone and e-mail
lines with regexes, skipping lines that look like instructions.
"""

import re
from typing import Any

from app.ai.injection import detect_injection
from app.ai.prompt import json_section, untrusted_section
from app.ai.runner import TaskDefinition
from app.ai.schemas import (
    MAX_EXTRACT_ITEMS,
    CatalogKey,
    ExtractedItem,
    ExtractFactsInput,
    ExtractFactsOutput,
    NormalizedMoney,
    NormalizedText,
)
from app.ai.tasks.matching import EMAIL, PHONE, amount_text, match_facts
from app.integrations.llm.base import LLMMessage
from app.integrations.llm.fake import fake_implementation
from app.knowledge.parsing import Money, ParseAmbiguity, ParseError, parse_money

TASK = "extract_fact_candidates"
MAX_RAW_CHARS = 200
MAX_EXCERPT_CHARS = 500


def build_messages(task_input: ExtractFactsInput) -> list[LLMMessage]:
    parameters = {"workspace_locale": task_input.workspace_locale, "currency": task_input.currency}
    body = "\n\n".join(
        [
            json_section("fact_catalog", [k.model_dump() for k in task_input.catalog]),
            json_section("task_parameters", parameters),
            untrusted_section("untrusted_pasted_text", task_input.text),
        ]
    )
    return [LLMMessage("user", body)]


def post_validate(task_input: ExtractFactsInput, output: ExtractFactsOutput) -> list[str]:
    problems: list[str] = []
    if len(output.items) > MAX_EXTRACT_ITEMS:
        problems.append(f"at most {MAX_EXTRACT_ITEMS} items are allowed")
    for index, item in enumerate(output.items):
        if len(item.raw_value_text) > MAX_RAW_CHARS or len(item.source_excerpt) > MAX_EXCERPT_CHARS:
            problems.append(f"items.{index}: raw_value_text or source_excerpt is too long")
    return problems


EXTRACT_FACT_CANDIDATES: TaskDefinition[ExtractFactsInput, ExtractFactsOutput] = TaskDefinition(
    name=TASK,
    output_schema=ExtractFactsOutput,
    max_output_tokens=2000,
    timeout_s=60,
    build_messages=build_messages,
    post_validate=post_validate,
    # No snapshot of its own: the endpoint stored the (redacted) pasted text on the run.
)

# --- the fake -------------------------------------------------------------------------------


def _money_reading(raw: str, locale: str, currency: str) -> NormalizedMoney | None:
    try:
        parsed = parse_money(raw, locale if locale in ("tr", "en") else "tr", currency)
    except ParseError:
        return None
    money: Money = parsed.alternatives[0] if isinstance(parsed, ParseAmbiguity) else parsed
    return NormalizedMoney(kind="money", amount=str(money.amount), currency=money.currency)


@fake_implementation(TASK)
def fake_extract_fact_candidates(
    task_input: ExtractFactsInput, schema: Any = None
) -> ExtractFactsOutput:
    """One item per line that names a known fact with a value (money, phone or e-mail)."""
    items: list[ExtractedItem] = []
    by_type: dict[str, list[CatalogKey]] = {}
    for key in task_input.catalog:
        by_type.setdefault(key.value_type, []).append(key)

    for line in re.split(r"[\r\n]+", task_input.text):
        excerpt = " ".join(line.split())
        if not excerpt or detect_injection(excerpt):  # instructions are never a source
            continue
        raw = amount_text(excerpt)
        if raw is not None:
            targets = [k for k in match_facts(excerpt, by_type.get("money", [])) if k.key]
            if len(targets) == 1:
                items.append(
                    ExtractedItem(
                        fact_key=targets[0].key,
                        raw_value_text=raw,
                        normalized_value=_money_reading(
                            raw, task_input.workspace_locale, task_input.currency
                        ),
                        source_excerpt=excerpt[:MAX_EXCERPT_CHARS],
                    )
                )
                continue
        phone = PHONE.search(excerpt)
        if phone and "contact.phone" in {k.key for k in task_input.catalog}:
            value = phone.group().strip()
            items.append(
                ExtractedItem(
                    fact_key="contact.phone",
                    raw_value_text=value,
                    normalized_value=NormalizedText(kind="text", text=value),
                    source_excerpt=excerpt[:MAX_EXCERPT_CHARS],
                )
            )
            continue
        email = EMAIL.search(excerpt)
        if email and "contact.email" in {k.key for k in task_input.catalog}:
            items.append(
                ExtractedItem(
                    fact_key="contact.email",
                    raw_value_text=email.group(),
                    normalized_value=NormalizedText(kind="text", text=email.group()),
                    source_excerpt=excerpt[:MAX_EXCERPT_CHARS],
                )
            )
    return ExtractFactsOutput(items=items[:MAX_EXTRACT_ITEMS])
