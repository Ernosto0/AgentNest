"""Request and response bodies for ``POST /api/v1/waitlist``."""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

# One @, a dotted domain, no spaces or control characters. Delivery is not verified here.
_EMAIL = re.compile(
    r"^[^@\s<>\"',;:()\[\]\\]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$"
)

Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]


def normalize_email(value: str) -> str:
    return value.strip().lower()


class WaitlistRequest(BaseModel):
    """Email is required. The landing form also sends optional context for the operator."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    business_name: Short | None = None
    category: Short | None = None
    instagram_handle: Short | None = None
    city: Short | None = None
    locale: Literal["tr", "en"] = "tr"

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        value = normalize_email(value)
        if ".." in value or not _EMAIL.match(value):
            raise ValueError("not a valid email address")
        return value

    @field_validator("business_name", "category", "instagram_handle", "city")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if any(ord(ch) < 32 for ch in value):
            raise ValueError("control characters are not allowed")
        return value or None


class WaitlistResponse(BaseModel):
    status: Literal["received"] = "received"
