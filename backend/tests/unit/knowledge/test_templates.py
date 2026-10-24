"""Template loader and its startup validation (P2-02)."""

from pathlib import Path

import pytest

from app.knowledge import templates
from app.knowledge.constants import CATEGORIES
from app.knowledge.templates import CATEGORY_FILES, TemplateError, load_template, validate_templates
from app.knowledge.values import VALUE_TYPES


@pytest.mark.parametrize("category", sorted(CATEGORY_FILES))
def test_every_shipped_template_loads_and_is_consistent(category: str) -> None:
    validate_templates()
    template = load_template(category)
    identifiers = [item.identifier for item in template.items]
    assert len(identifiers) == len(set(identifiers))
    for item in template.items:
        assert item.category in CATEGORIES
        assert set(item.value_types) <= set(VALUE_TYPES)
        assert item.label["tr"] and item.label["en"]
        assert item.description["tr"] and item.description["en"]


def test_other_category_uses_the_common_template_only() -> None:
    other = {i.identifier for i in load_template("other").items}
    fitness = {i.identifier for i in load_template("fitness").items}
    assert "pricing.membership_monthly" not in other
    assert {
        "identity.business_name",
        "hours.weekly",
        "service.*",
        "pricing.*",
        "promotion.*",
        "faq.*",
    } <= other
    assert other < fitness


def test_find_resolves_fixed_keys_before_patterns() -> None:
    template = load_template("fitness")
    assert template.find("pricing.membership_monthly").key == "pricing.membership_monthly"  # type: ignore[union-attr]
    assert template.find("service.reformer").pattern == "service.*"  # type: ignore[union-attr]
    assert template.find("promotion.trial_session").pattern == "promotion.*"  # type: ignore[union-attr]
    assert template.find("service") is None
    assert template.find("nonsense.key") is None


@pytest.mark.parametrize("category", sorted(CATEGORY_FILES))
def test_required_items_match_what_readiness_expects(category: str) -> None:
    template = load_template(category)
    drafts = {i.identifier for i in template.items if i.required_for == "drafts"}
    assert drafts == {
        "identity.business_name",
        "contact.phone",
        "contact.whatsapp",
        "contact.email",
        "location.address",
        "hours.weekly",
    }
    ready_prices = {i.identifier for i in template.items if i.required_when == "price_disclosure=share"}
    assert ready_prices == {"pricing.*"}


def _write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, yaml_text: str) -> None:
    (tmp_path / "common.yaml").write_text(yaml_text, encoding="utf-8")
    monkeypatch.setattr(templates, "TEMPLATE_DIR", tmp_path)
    templates.load_template.cache_clear()


ITEM = """
items:
  - key: identity.business_name
    category: identity
    label: {tr: A, en: B}
    value_types: [text]
    criticality: critical
    description: {tr: A, en: B}
"""


@pytest.mark.parametrize(
    "yaml_text",
    [
        ITEM + ITEM.split("items:")[1],  # duplicate key
        ITEM.replace("value_types: [text]", "value_types: [colour]"),  # unknown type
        ITEM.replace("category: identity", "category: pricing"),  # prefix != category
        ITEM.replace("identity.business_name", "BadKey"),  # invalid key
        ITEM.replace("value_types: [text]", "value_types: [enum]"),  # enum needs allowed_values
        ITEM.replace("criticality: critical", "criticality: huge"),
        ITEM.replace("key: identity.business_name", "key_pattern: identity"),
        ITEM.replace("label: {tr: A, en: B}", "label: {tr: A}"),
    ],
)
def test_broken_templates_fail_loudly(
    yaml_text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, monkeypatch, yaml_text)
    try:
        with pytest.raises(TemplateError):
            load_template("other")
    finally:
        templates.load_template.cache_clear()
