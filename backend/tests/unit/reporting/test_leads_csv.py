"""CSV cells round-trip safely through the stdlib reader, including Excel formulas."""

import csv
import io
import uuid
from datetime import UTC, datetime

import pytest

from app.reporting.leads import Lead, clean_question
from app.reporting.leads_csv import render_csv


@pytest.mark.parametrize(
    "value",
    [
        "=SUM(1,2)",
        "+123",
        "-123",
        "@name",
        "\tformula",
        "\rformula",
        "normal",
        "a=b",
        'quote " and, comma',
        None,
        "",
    ],
)
def test_roundtrip_and_formula_escape(value):
    row = Lead(
        uuid.uuid4(),
        uuid.uuid4(),
        value,
        datetime(2026, 3, 8, 21, tzinfo=UTC),
        value,
        "pricing",
        {},
        value,
    )
    result = render_csv([row], timezone="Europe/Istanbul", link_base="https://app.example/")
    cells = list(csv.reader(io.StringIO(result)))
    assert cells[0] == ["customer_handle", "last_question", "date", "conversation_link"]
    assert len(cells[1]) == 4
    assert cells[1][2] == "2026-03-09"
    assert cells[1][3] == f"https://app.example/w/{row.workspace_id}/inbox/{row.conversation_id}"
    if value and value[0] in "=+-@\t\r":
        assert cells[1][0].startswith("'") and cells[1][1].startswith("'")
    else:
        assert cells[1][:2] == [value or "", value or ""]
    assert result.endswith("\r\n")


def test_newlines_and_control_characters():
    row = Lead(
        uuid.uuid4(),
        uuid.uuid4(),
        "a\r\nb",
        datetime(2026, 3, 8, 21, tzinfo=UTC),
        'hello\n"world",\r\nend',
        "pricing",
        {},
    )
    cells = list(
        csv.reader(io.StringIO(render_csv([row], timezone="Europe/Istanbul", link_base="")))
    )
    assert cells[1][0] == "a b"
    assert "\n" not in cells[1][1] and "\r" not in cells[1][1]
    assert '"world",' in cells[1][1]
    assert clean_question("a\x00\x01\t\x7fb") == "a    b"
    assert clean_question("x" * 301) == "x" * 299 + "…"
    assert clean_question(None) is None
