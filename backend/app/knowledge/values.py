"""Value types of business facts (business-knowledge.md §2): validation and canonical form.

``validate_value`` is the only way raw input becomes a stored ``value``. It returns the
canonical JSON form (money amounts as 2-decimal strings, trimmed text, sorted hours), so two
equal values always serialise identically and ``values_equal`` is a plain comparison.
"""

import datetime as dt
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from app.core.errors import AppError

VALUE_TYPES = (
    "money",
    "weekly_hours",
    "text",
    "localized_text",
    "phone",
    "email",
    "address",
    "url",
    "boolean",
    "enum",
    "string_list",
)
MONEY_UNITS = ("month", "session", "package")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
_URL_RE = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.IGNORECASE)


def clean_text(value: str) -> str:
    """NFC, unified newlines, trimmed lines, no runs of blanks. Never changes letter case."""
    text = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


Text5000 = Annotated[str, StringConstraints(max_length=5000)]


class LocalizedStr(_Strict):
    """Optional tr/en strings; empty ones are dropped by ``clean_localized``."""

    tr: str | None = None
    en: str | None = None

    @field_validator("tr", "en")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = clean_text(value)
        if len(cleaned) > 5000:
            raise ValueError("too_long")
        return cleaned or None


# --- money --------------------------------------------------------------------------------


class MoneyValue(_Strict):
    amount: Decimal
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
    unit: (
        Literal["month", "session", "package", "item", "hour", "person", "day", "year"] | None
    ) = None
    conditions: LocalizedStr | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def _amount_input(cls, value: Any) -> Any:
        if isinstance(value, bool | float):
            raise ValueError("amount_must_be_decimal_string")  # floats never carry money
        if isinstance(value, str):
            try:
                return Decimal(value.strip())
            except InvalidOperation as exc:
                raise ValueError("invalid_amount") from exc
        return value

    @field_validator("amount")
    @classmethod
    def _amount_range(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0:
            raise ValueError("amount_negative")
        if value != value.quantize(Decimal("0.01")):
            raise ValueError("too_many_decimals")
        if value >= Decimal("100000000"):
            raise ValueError("amount_too_large")
        return value.quantize(Decimal("0.01"))

    @model_validator(mode="after")
    def _drop_empty_conditions(self) -> "MoneyValue":
        if self.conditions is not None and not (self.conditions.tr or self.conditions.en):
            self.conditions = None
        return self


# --- weekly hours -------------------------------------------------------------------------


def time_to_minutes(value: str) -> int:
    if value == "24:00":
        return 1440
    match = _TIME_RE.match(value)
    if match is None:
        raise ValueError("invalid_time")
    return int(match.group(1)) * 60 + int(match.group(2))


def _normalise_ranges(ranges: list[tuple[str, str]]) -> list[tuple[str, str]]:
    parsed: list[tuple[int, int, str, str]] = []
    for opens, closes in ranges:
        start, end = time_to_minutes(opens), time_to_minutes(closes)
        if start >= end:
            raise ValueError("range_not_increasing")  # overnight ranges are not supported
        parsed.append((start, end, opens, closes))
    parsed.sort()
    for previous, current in zip(parsed, parsed[1:], strict=False):
        if current[0] < previous[1]:
            raise ValueError("ranges_overlap")
    return [(opens, closes) for _, _, opens, closes in parsed]


class HoursException(_Strict):
    date: dt.date
    closed: bool = True
    ranges: list[tuple[str, str]] = Field(default_factory=list)
    note: LocalizedStr | None = None

    @model_validator(mode="after")
    def _consistent(self) -> "HoursException":
        if self.closed and self.ranges:
            raise ValueError("closed_with_ranges")
        if not self.closed and not self.ranges:
            raise ValueError("open_without_ranges")
        self.ranges = _normalise_ranges(self.ranges)
        if self.note is not None and not (self.note.tr or self.note.en):
            self.note = None
        return self


class WeeklyHoursValue(_Strict):
    mon: list[tuple[str, str]] = Field(default_factory=list)
    tue: list[tuple[str, str]] = Field(default_factory=list)
    wed: list[tuple[str, str]] = Field(default_factory=list)
    thu: list[tuple[str, str]] = Field(default_factory=list)
    fri: list[tuple[str, str]] = Field(default_factory=list)
    sat: list[tuple[str, str]] = Field(default_factory=list)
    sun: list[tuple[str, str]] = Field(default_factory=list)
    exceptions: list[HoursException] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalise(self) -> "WeeklyHoursValue":
        for day in WEEKDAYS:
            setattr(self, day, _normalise_ranges(getattr(self, day)))
        dates = [exception.date for exception in self.exceptions]
        if len(dates) != len(set(dates)):
            raise ValueError("duplicate_exception_date")
        self.exceptions = sorted(self.exceptions, key=lambda exception: exception.date)
        return self


# --- simple types -------------------------------------------------------------------------


class TextValue(_Strict):
    text: Text5000

    @field_validator("text")
    @classmethod
    def _clean(cls, value: str) -> str:
        cleaned = clean_text(value)
        if not cleaned:
            raise ValueError("required")
        return cleaned


class LocalizedTextValue(LocalizedStr):
    @model_validator(mode="after")
    def _at_least_one(self) -> "LocalizedTextValue":
        if not (self.tr or self.en):
            raise ValueError("required")
        return self


def format_phone_display(e164: str) -> str:
    """Turkish mobile/landline numbers as ``0555 000 00 00``; others stay in E.164."""
    if e164.startswith("+90") and len(e164) == 13:
        national = "0" + e164[3:]
        return f"{national[:4]} {national[4:7]} {national[7:9]} {national[9:]}"
    return e164


class PhoneValue(_Strict):
    e164: str
    display: str | None = None

    @field_validator("e164")
    @classmethod
    def _e164(cls, value: str) -> str:
        value = value.strip()
        if not _E164_RE.match(value):
            raise ValueError("invalid_phone")
        return value

    @model_validator(mode="after")
    def _display(self) -> "PhoneValue":
        self.display = format_phone_display(self.e164)  # always derived: one canonical form
        return self


class EmailValue(_Strict):
    email: str

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL_RE.match(value) or len(value) > 320:
            raise ValueError("invalid_email")
        return value


class AddressValue(_Strict):
    lines: list[Annotated[str, StringConstraints(min_length=1, max_length=200)]] = Field(
        min_length=1, max_length=4
    )
    district: str | None = None
    city: str
    maps_url: str | None = None

    @field_validator("lines", mode="before")
    @classmethod
    def _lines(cls, value: Any) -> Any:
        if isinstance(value, list):
            if not all(isinstance(item, str) for item in value):
                raise ValueError("invalid_line")  # never drop input silently
            return [clean_text(item) for item in value if clean_text(item)]
        return value

    @field_validator("district", "city")
    @classmethod
    def _text(cls, value: str | None) -> str | None:
        cleaned = clean_text(value) if value is not None else None
        return cleaned or None

    @field_validator("maps_url")
    @classmethod
    def _maps(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not _URL_RE.match(value):
            raise ValueError("invalid_url")
        return value

    @model_validator(mode="after")
    def _city_required(self) -> "AddressValue":
        if not self.city:
            raise ValueError("city_required")
        return self


class UrlValue(_Strict):
    url: str

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        value = value.strip()
        if not _URL_RE.match(value) or len(value) > 2000:
            raise ValueError("invalid_url")
        return value


class BooleanValue(_Strict):
    value: bool


class EnumValue(_Strict):
    value: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]


class StringListValue(_Strict):
    items: list[str]

    @field_validator("items")
    @classmethod
    def _items(cls, value: list[str]) -> list[str]:
        cleaned = [clean_text(item) for item in value]
        unique = list(dict.fromkeys(item for item in cleaned if item))
        if len(unique) > 50 or any(len(item) > 100 for item in unique):
            raise ValueError("too_many_or_too_long")
        return unique


MODELS: dict[str, type[BaseModel]] = {
    "money": MoneyValue,
    "weekly_hours": WeeklyHoursValue,
    "text": TextValue,
    "localized_text": LocalizedTextValue,
    "phone": PhoneValue,
    "email": EmailValue,
    "address": AddressValue,
    "url": UrlValue,
    "boolean": BooleanValue,
    "enum": EnumValue,
    "string_list": StringListValue,
}


def _field_errors(exc: ValidationError) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        code = error["msg"].removeprefix("Value error, ")
        if error["type"] == "missing":
            code = "required"
        errors.append(
            {"field": f"value.{location}" if location else "value", "code": code, "params": {}}
        )
    return errors


def validate_value(
    value_type: str,
    raw: Any,
    *,
    allowed_values: tuple[str, ...] | None = None,
    default_currency: str | None = None,
) -> dict[str, Any]:
    """Validate ``raw`` for ``value_type`` and return its canonical JSON form.

    Raises ``AppError("VALIDATION_FAILED")`` with ``value.<path>`` field errors.
    """
    model = MODELS.get(value_type)
    if model is None:
        raise AppError(
            "VALIDATION_FAILED",
            errors=[{"field": "value_type", "code": "unknown_value_type", "params": {}}],
        )
    if not isinstance(raw, dict):
        raise AppError(
            "VALIDATION_FAILED", errors=[{"field": "value", "code": "invalid_type", "params": {}}]
        )
    if value_type == "money" and default_currency and "currency" not in raw:
        raw = {**raw, "currency": default_currency}
    try:
        parsed = model.model_validate(raw)
    except ValidationError as exc:
        raise AppError("VALIDATION_FAILED", errors=_field_errors(exc)) from exc
    result: dict[str, Any] = parsed.model_dump(mode="json")
    if (
        value_type == "enum"
        and allowed_values is not None
        and result["value"] not in allowed_values
    ):
        raise AppError(
            "VALIDATION_FAILED",
            errors=[
                {
                    "field": "value.value",
                    "code": "not_allowed",
                    "params": {"allowed": list(allowed_values)},
                }
            ],
        )
    compacted: dict[str, Any] = _compact(result)
    return compacted


def _compact(value: Any) -> Any:
    """Drop ``None`` entries so absent and null optional fields store identically."""
    if isinstance(value, dict):
        return {k: _compact(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_compact(item) for item in value]
    return value


def values_equal(value_type: str, a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Equality of two values in canonical form (re-validated so legacy shapes compare too)."""
    return validate_value(value_type, a) == validate_value(value_type, b)
