"""Identifier helpers. Primary keys are application-generated UUID4 values."""

import uuid


def new_id() -> uuid.UUID:
    return uuid.uuid4()


def parse_uuid(value: str) -> uuid.UUID | None:
    """Parse a UUID string, returning ``None`` instead of raising."""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None
