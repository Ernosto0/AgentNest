"""The pilot waitlist (global table, not workspace-scoped): one row per normalized email."""

from sqlalchemy import CheckConstraint, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin

WAITLIST_LOCALES = ("tr", "en")


class WaitlistEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A pilot request from the public landing page.

    Personal data: the email is never logged in plain text, and rows are removed by the retention
    job (``RETENTION_WAITLIST_DAYS``) or on request (``waitlist-delete`` CLI command).
    """

    __tablename__ = "waitlist_entries"
    __table_args__ = (
        UniqueConstraint("email_normalized"),
        CheckConstraint("locale IN ('tr', 'en')", name="locale"),
    )

    email: Mapped[str] = mapped_column(Text, nullable=False)
    email_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    business_name: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    instagram_handle: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(Text, nullable=False, default="tr", server_default="tr")
