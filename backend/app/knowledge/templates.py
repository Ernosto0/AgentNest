"""Category templates (business-knowledge.md §3): which facts a business is expected to have.

Templates live in code as YAML. They are validated when the application starts (unique keys,
valid types, enum values), so a typo fails fast instead of surfacing as a missing checklist
item. Items are *not* materialised as rows: missing items are computed by comparing the
template with the existing facts.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.knowledge.constants import CATEGORIES, CRITICALITIES, KEY_RE
from app.knowledge.values import VALUE_TYPES

TEMPLATE_DIR = Path(__file__).parent / "templates"
# business_category -> extra template file (every workspace also gets ``common``)
CATEGORY_FILES = {"gym": "gym", "pilates_studio": "pilates_studio", "other": None}


class TemplateError(Exception):
    """A template file is invalid. Raised at startup."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Labelled(_Strict):
    tr: str = Field(min_length=1)
    en: str = Field(min_length=1)


class TemplateItemModel(_Strict):
    # Exactly one of ``key`` (fixed item) and ``key_pattern`` (``service.*``: owner-named slots).
    key: str | None = None
    key_pattern: str | None = None
    category: str
    label: Labelled
    value_types: list[str] = Field(min_length=1)
    criticality: Literal["critical", "standard"]
    required_for: Literal["drafts", "ready"] | None = None
    # ``contact``: at least one of the group is needed; ``location``: address or online_only.
    required_group: Literal["contact", "location"] | None = None
    # ``price_disclosure=share`` / ``price_disclosure=do_not_share``
    required_when: Literal["price_disclosure=share", "price_disclosure=do_not_share"] | None = None
    description: Labelled
    allowed_values: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "TemplateItemModel":
        if (self.key is None) == (self.key_pattern is None):
            raise ValueError("exactly one of key and key_pattern is required")
        identifier = self.key or self.key_pattern or ""
        probe = identifier.removesuffix(".*") + (".x" if identifier.endswith(".*") else "")
        if self.key_pattern is not None and not self.key_pattern.endswith(".*"):
            raise ValueError(f"{identifier}: key_pattern must end with '.*'")
        if not KEY_RE.match(probe):
            raise ValueError(f"{identifier}: invalid key")
        if probe.split(".")[0] != self.category or self.category not in CATEGORIES:
            raise ValueError(f"{identifier}: key prefix must equal category {self.category}")
        if self.criticality not in CRITICALITIES:
            raise ValueError(f"{identifier}: invalid criticality")
        unknown = [v for v in self.value_types if v not in VALUE_TYPES]
        if unknown:
            raise ValueError(f"{identifier}: unknown value types {unknown}")
        if self.key is not None and len(self.value_types) != 1:
            raise ValueError(f"{identifier}: a fixed item has exactly one value type")
        if ("enum" in self.value_types) != bool(self.allowed_values):
            raise ValueError(f"{identifier}: enum items (only) need allowed_values")
        if self.key_pattern is not None and (self.required_group or self.required_when):
            raise ValueError(f"{identifier}: pattern items cannot use groups or conditions")
        return self


class TemplateFile(_Strict):
    items: list[TemplateItemModel]


@dataclass(frozen=True)
class TemplateItem:
    """One expected fact (``key``) or a family of owner-named facts (``pattern``)."""

    key: str | None
    pattern: str | None
    category: str
    label: dict[str, str]
    value_types: tuple[str, ...]
    criticality: str
    required_for: str | None
    required_group: str | None
    required_when: str | None
    description: dict[str, str]
    allowed_values: tuple[str, ...]

    @property
    def identifier(self) -> str:
        return self.key or self.pattern or ""

    @property
    def value_type(self) -> str:
        return self.value_types[0]

    def matches(self, key: str) -> bool:
        if self.key is not None:
            return self.key == key
        prefix = (self.pattern or "").removesuffix("*")
        return bool(prefix) and key.startswith(prefix) and len(key) > len(prefix)


@dataclass(frozen=True)
class Template:
    business_category: str
    items: tuple[TemplateItem, ...]

    def find(self, key: str) -> TemplateItem | None:
        """The fixed item for ``key``, else the pattern item it falls under."""
        for item in self.items:
            if item.key == key:
                return item
        for item in self.items:
            if item.pattern is not None and item.matches(key):
                return item
        return None


def _load_file(name: str) -> list[TemplateItem]:
    path = TEMPLATE_DIR / f"{name}.yaml"
    try:
        parsed = TemplateFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise TemplateError(f"{path.name}: {exc}") from exc
    return [
        TemplateItem(
            key=item.key,
            pattern=item.key_pattern,
            category=item.category,
            label=item.label.model_dump(),
            value_types=tuple(item.value_types),
            criticality=item.criticality,
            required_for=item.required_for,
            required_group=item.required_group,
            required_when=item.required_when,
            description=item.description.model_dump(),
            allowed_values=tuple(item.allowed_values),
        )
        for item in parsed.items
    ]


@lru_cache
def load_template(business_category: str) -> Template:
    if business_category not in CATEGORY_FILES:
        raise TemplateError(f"unknown business category {business_category}")
    names = ["common"]
    extra = CATEGORY_FILES[business_category]
    if extra is not None:
        names.append(extra)
    items: list[TemplateItem] = []
    for name in names:
        items.extend(_load_file(name))
    seen: set[str] = set()
    for item in items:
        if item.identifier in seen:
            raise TemplateError(f"{business_category}: duplicate template item {item.identifier}")
        seen.add(item.identifier)
    return Template(business_category=business_category, items=tuple(items))


def validate_templates() -> None:
    """Load every template (raises ``TemplateError``); called when the app starts."""
    for category in CATEGORY_FILES:
        load_template(category)
