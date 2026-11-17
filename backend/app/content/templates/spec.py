"""Strict template inputs and persisted, versioned render evidence."""

import unicodedata
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, field_validator

from app.knowledge.values import clean_text

RENDERER_VERSION = "1"
SIZES = {"story": (1080, 1920), "feed": (1080, 1350)}
FactKey = Annotated[
    str, StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
]
Language = Literal["tr", "en"]
CardFormat = Literal["story", "feed"]


class InputBase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    format: CardFormat
    language: Language | None = None


class PriceCard(InputBase):
    template: Literal["price_card"]
    fact_key: FactKey


class HoursCard(InputBase):
    template: Literal["hours_card"]
    fact_key: Literal["hours.weekly"] = "hours.weekly"


class ServicesList(InputBase):
    template: Literal["services_list"]
    fact_keys: list[FactKey] = Field(min_length=2, max_length=6)


class Announcement(InputBase):
    template: Literal["announcement"]
    headline: str = Field(min_length=1, max_length=180)
    body: str = Field(min_length=1, max_length=1600)
    date_line: str | None = Field(default=None, max_length=120)

    @field_validator("headline", "body", "date_line", mode="before")
    @classmethod
    def clean(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        return clean_text(
            "".join(c for c in value if not unicodedata.category(c).startswith("C") or c == "\n")
        )


TemplateInput = Annotated[
    PriceCard | HoursCard | ServicesList | Announcement, Field(discriminator="template")
]


class FactUse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    fact_id: uuid.UUID
    key: str
    version: int


class BrandRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    primary_color: str
    accent_color: str
    logo_media_asset_id: uuid.UUID | None


class RenderRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    renderer_version: str = RENDERER_VERSION
    template: str
    format: CardFormat
    language: Language
    facts: list[FactUse]
    inputs: dict[str, Any]
    brand: BrandRecord
    rendered_at: datetime

    def to_input(self) -> TemplateInput:
        data: dict[str, Any] = dict(
            self.inputs, template=self.template, format=self.format, language=self.language
        )
        if self.template in {"price_card", "hours_card"}:
            data["fact_key"] = self.facts[0].key
        elif self.template == "services_list":
            data["fact_keys"] = [f.key for f in self.facts]
        return TypeAdapter(TemplateInput).validate_python(data)

    def fact_references(self) -> tuple[tuple[uuid.UUID, int], ...]:
        return tuple((fact.fact_id, fact.version) for fact in self.facts)


LABELS = {
    "price_card": {"tr": "Fiyat kartı", "en": "Price card"},
    "hours_card": {"tr": "Çalışma saatleri", "en": "Opening hours"},
    "services_list": {"tr": "Hizmetler", "en": "Services"},
    "announcement": {"tr": "Duyuru", "en": "Announcement"},
}


def catalog() -> list[dict[str, Any]]:
    fields = {
        "price_card": [{"name": "fact_key", "kind": "fact_key", "accepted_value_types": ["money"]}],
        "hours_card": [
            {
                "name": "fact_key",
                "kind": "fact_key",
                "accepted_value_types": ["weekly_hours"],
                "key": "hours.weekly",
            }
        ],
        "services_list": [
            {
                "name": "fact_keys",
                "kind": "fact_key_list",
                "accepted_value_types": ["money"],
                "min_items": 2,
                "max_items": 6,
            }
        ],
        "announcement": [
            {"name": name, "kind": "text", "max_length": limit}
            for name, limit in (("headline", 180), ("body", 1600), ("date_line", 120))
        ],
    }
    return [
        {
            "id": key,
            "labels": labels,
            "formats": [
                {"id": fmt, "width": size[0], "height": size[1]} for fmt, size in SIZES.items()
            ],
            "fields": fields[key],
        }
        for key, labels in LABELS.items()
    ]
