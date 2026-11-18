"""Minimal in-memory CSV with Excel formula protection for customer-supplied cells."""

import csv
import io
from collections.abc import Sequence
from zoneinfo import ZoneInfo

from app.reporting.leads import Lead, clean_question


def _cell(value: str | None) -> str:
    value = value or ""
    escape = bool(value and value[0] in "=+-@\t\r")
    value = value.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return ("'" if escape else "") + value


def render_csv(rows: Sequence[Lead], *, timezone: str, link_base: str) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(("customer_handle", "last_question", "date", "conversation_link"))
    for row in rows:
        raw = row.raw_question if row.raw_question is not None else row.last_question
        question = clean_question(raw) or ""
        # Detect leading tab/CR in the original, before the list's control sanitization.
        if raw and raw[0] in "\t\r":
            question = "'" + question
        writer.writerow(
            (
                _cell(row.customer_handle),
                _cell(question),
                row.last_question_at.astimezone(ZoneInfo(timezone)).date().isoformat(),
                f"{link_base.rstrip('/')}/w/{row.workspace_id}/inbox/{row.conversation_id}",
            )
        )
    return output.getvalue()
