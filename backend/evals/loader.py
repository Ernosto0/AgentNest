"""YAML loading for eval datasets and the named fact fixtures."""

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.commands.resolver import FactSnapshot

EVALS_DIR = Path(__file__).parent
# What a case may carry besides its expectations (draft_reply uses most of them).
INPUT_KEYS = (
    "text",
    "conversation",
    "price_disclosure",
    "unusable",
    "languages",
    "automation",
    "attachments",
    "approved_answers",
    "handling_mode",
)
TASKS = ("interpret_command", "extract_fact_candidates", "draft_reply")


@dataclass(frozen=True)
class Fixture:
    name: str
    business_category: str
    default_locale: str
    currency: str
    timezone: str
    facts: tuple[FactSnapshot, ...]


@dataclass(frozen=True)
class Case:
    id: str
    locale: str
    hard: bool
    tags: tuple[str, ...]
    inputs: dict[str, Any]  # "text" and friends
    expect: dict[str, Any]


@dataclass(frozen=True)
class Dataset:
    task: str
    name: str
    version: int
    fixture: Fixture
    cases: tuple[Case, ...] = field(default=())


def load_fixture(name: str) -> Fixture:
    data = yaml.safe_load((EVALS_DIR / "fixtures" / f"{name}.yaml").read_text(encoding="utf-8"))
    workspace = data["workspace"]
    facts = tuple(
        FactSnapshot(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"eval:{name}:{raw['key']}"),
            key=raw["key"],
            label=raw["label"],
            category=raw["category"],
            value_type=raw["value_type"],
            value=raw["value"],
            status=raw.get("status", "verified"),
            version=raw.get("version", 1),
            allowed_values=tuple(raw.get("allowed_values", ())),
        )
        for raw in data["facts"]
    )
    return Fixture(
        name=name,
        business_category=workspace["business_category"],
        default_locale=workspace["default_locale"],
        currency=workspace["currency"],
        timezone=workspace["timezone"],
        facts=facts,
    )


def load_dataset(task: str, path: Path) -> Dataset:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    fixture = load_fixture(data.get("fixtures", {}).get("facts", "demo_gym"))
    cases: list[Case] = []
    seen: set[str] = set()
    for raw in data["cases"]:
        if raw["id"] in seen:
            raise ValueError(f"{path.name}: duplicate case id {raw['id']!r}")
        seen.add(raw["id"])
        cases.append(
            Case(
                id=raw["id"],
                locale=raw.get("locale", fixture.default_locale),
                hard=bool(raw.get("hard", False)),
                tags=tuple(raw.get("tags", ())),
                inputs={k: raw[k] for k in INPUT_KEYS if k in raw},
                expect=raw.get("expect", {}),
            )
        )
    return Dataset(
        task=task,
        name=data["dataset"],
        version=int(data.get("version", 1)),
        fixture=fixture,
        cases=tuple(cases),
    )


def load_datasets(task: str, only: str | None = None) -> list[Dataset]:
    if task not in TASKS:
        raise ValueError(f"unknown task {task!r}; expected one of {TASKS}")
    paths = sorted((EVALS_DIR / task).glob("*.yaml"))
    datasets = [load_dataset(task, p) for p in paths]
    return [d for d in datasets if only is None or d.name == only]
