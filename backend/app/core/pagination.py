"""List envelope shared by all modules (api-design.md §1)."""

from pydantic import BaseModel


class Page[T](BaseModel):
    """Cursor page. Lists so far are small and bounded, so ``next_cursor`` is always null."""

    items: list[T]
    next_cursor: str | None = None
