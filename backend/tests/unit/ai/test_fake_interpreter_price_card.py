"""Price-card grammar is a proposal with no value or publication authority."""

import pytest

from app.ai.schemas import Clarify, ContentMakePriceCard, Unsupported
from tests.unit.ai.test_fake_interpreter import interpret


@pytest.mark.parametrize(
    ("text", "locale"),
    [
        ("aylik uyelik icin fiyat karti yap", "tr"),
        ("make a price card for monthly membership", "en"),
    ],
)
def test_price_card_names_the_fact_only(text, locale):
    result = interpret(text, locale)
    assert isinstance(result, ContentMakePriceCard)
    assert result.fact_key == "pricing.membership_monthly"
    assert set(result.model_dump()) == {"type", "fact_key", "format"}


def test_ambiguous_price_card_keeps_feed_format():
    result = interpret("feed fiyat karti yap")
    assert isinstance(result, Clarify)
    assert result.intent == "content.make_price_card" and result.format == "feed"


@pytest.mark.parametrize("text", ["make a price card and publish it", "fiyat karti yap ve onayla"])
def test_combined_publication_or_approval_is_unsupported(text):
    assert isinstance(interpret(text), Unsupported)
