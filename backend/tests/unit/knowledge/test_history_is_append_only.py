"""INV-17: ``fact_versions`` has no update or delete path in the code base."""

import re
from pathlib import Path

KNOWLEDGE = Path(__file__).parents[3] / "app" / "knowledge"


def test_no_module_updates_or_deletes_fact_versions() -> None:
    forbidden = re.compile(
        r"(update|delete)\(\s*FactVersion\b|session\.delete\(\s*\w*version|FactVersion\)\s*\.\s*(update|delete)",
        re.IGNORECASE,
    )
    offenders = [
        path.name for path in KNOWLEDGE.glob("*.py") if forbidden.search(path.read_text("utf-8"))
    ]
    assert offenders == []


def test_the_repository_only_adds_and_reads_versions() -> None:
    source = (KNOWLEDGE / "repository.py").read_text("utf-8")
    version_functions = re.findall(r"^def (\w*version\w*)\(", source, re.MULTILINE)
    assert sorted(version_functions) == ["add_version", "get_version", "list_versions"]


def test_the_service_never_assigns_attributes_on_a_version_row() -> None:
    source = (KNOWLEDGE / "service.py").read_text("utf-8")
    assert not re.search(r"\bversion_row\.\w+\s*=|\bversion\.\w+\s*=", source)
