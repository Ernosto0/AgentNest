"""Verified facts of a small gym, for tests that draft replies (a slice of the demo seed)."""

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.identity.models import Workspace
from app.knowledge.models import BusinessFact
from tests.factories import create_fact, money

WEEK = {day: [["07:00", "23:00"]] for day in ("mon", "tue", "wed", "thu", "fri")} | {
    "sat": [["09:00", "21:00"]],
    "sun": [["10:00", "18:00"]],
    "exceptions": [],
}

MONTHLY = "pricing.membership_monthly"
QUARTER = "pricing.membership_3_months"
STUDENT = "pricing.student_monthly"
HOURS = "hours.weekly"
ADDRESS = "location.address"
PHONE = "contact.phone"
BOOKING = "booking.instructions"
DISCLOSURE = "policy.price_disclosure"
ANSWER_TEXT = "policy.price_answer_text"
KEYWORDS = "escalation.keywords"
VOICE = "brand.voice_guidelines"
TRIAL = "promotion.trial_session"
FITNESS = "service.fitness"


def seed_gym_facts(
    session: Session,
    workspace: Workspace,
    clock: Clock,
    *,
    price_disclosure: str | None = "share",
    extra: dict[str, dict[str, Any]] | None = None,
) -> dict[str, BusinessFact]:
    """Create the facts and return them by key. ``price_disclosure=None`` omits the policy."""
    facts: dict[str, BusinessFact] = {}

    def add(key: str, value: dict[str, Any], **kwargs: Any) -> None:
        facts[key] = create_fact(session, workspace, key, value, clock=clock, **kwargs)

    add(MONTHLY, money("6000"))
    add(QUARTER, money("16500", unit="package"))
    add(STUDENT, money("4500"), verified=False)
    add(HOURS, WEEK)
    add(ADDRESS, {"lines": ["Örnek Mah. Demo Sok. No: 1"], "district": "Bucak", "city": "Burdur"})
    add(PHONE, {"e164": "+905550000000"})
    add(
        BOOKING,
        {
            "tr": "Bize arayarak veya DM ile ulaşın; deneme seansı için rezervasyon gerekir.",
            "en": "Call or DM us; trial sessions need booking.",
        },
    )
    add(
        TRIAL,
        {"tr": "İlk deneme seansı ücretsiz.", "en": "The first trial session is free."},
        label={"tr": "Deneme seansı", "en": "Trial session"},
        value_type="localized_text",
        valid_until=date(2027, 12, 31),
    )
    add(
        FITNESS,
        {"tr": "Modern ekipmanlı fitness salonu.", "en": "A gym floor with modern equipment."},
        label={"tr": "Fitness", "en": "Fitness"},
        value_type="localized_text",
    )
    add(VOICE, {"tr": "Sıcak ve kısa yazın.", "en": "Warm and short."})
    add(KEYWORDS, {"items": ["avukat", "tüketici hakem", "sakatlandım"]})
    if price_disclosure is not None:
        add(DISCLOSURE, {"value": price_disclosure})
    for key, value in (extra or {}).items():
        add(key, value)
    session.commit()
    return facts
