"""Closed vocabularies of the knowledge module (data-model.md §3.3, state-machines.md §2)."""

import re

CATEGORIES = (
    "identity",
    "contact",
    "location",
    "hours",
    "service",
    "pricing",
    "promotion",
    "policy",
    "booking",
    "faq",
    "brand",
    "escalation",
    "schedule",
    "custom",
)
CRITICALITIES = ("critical", "standard")
FACT_STATUSES = ("unverified", "verified", "archived")
SOURCE_TYPES = ("owner_entry", "owner_command", "candidate_accepted", "seed", "template_default")
CHANGE_KINDS = ("created", "value_changed", "verified", "archived", "restored")
CANDIDATE_SOURCES = ("staff_proposal", "pasted_text", "instagram_profile", "website")
CANDIDATE_RELATIONS = ("new", "same", "discrepancy", "contest")
CANDIDATE_STATUSES = ("pending", "accepted", "rejected", "superseded")
# Tier 2 (staff) can contest a verified value; tier 3 (pasted text, profile, website) cannot.
STAFF_SOURCES = frozenset({"staff_proposal"})

KEY_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$"
KEY_RE = re.compile(KEY_PATTERN)

APPROVED_ANSWER_STATUSES = ("active", "needs_review", "archived")
APPROVED_ANSWER_INTENTS = (
    "greeting",
    "pricing",
    "hours",
    "location_contact",
    "services",
    "booking",
    "promotions",
    "faq",
)
