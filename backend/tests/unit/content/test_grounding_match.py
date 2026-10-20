"""The whole-token matcher that decides whether a typed value is a verified fact's value."""

import pytest

from app.content.grounding import occurs_as_token


@pytest.mark.parametrize(
    ("needle", "haystack"),
    [
        ("6.000 ₺", "6.000 ₺ / ay"),
        ("6.000 ₺", "Aylık: 6.000 ₺"),
        ("07:00", "Pzt 07:00–23:00, Sal–Cum kapalı"),
        ("23:00", "Pzt 07:00–23:00, Sal–Cum kapalı"),
        ("+905550000000", "+905550000000"),
        ("ÜCRETSİZ", "İlk deneme seansı ücretsiz."),  # case and diacritics do not matter
    ],
)
def test_a_value_that_is_a_token_of_the_display_matches(needle: str, haystack: str) -> None:
    assert occurs_as_token(needle, haystack)


@pytest.mark.parametrize(
    ("needle", "haystack"),
    [
        ("500 ₺", "6.500 ₺ / ay"),  # the tail of a bigger number
        ("6.000 ₺", "16.000 ₺ / ay"),
        ("6 ₺", "6.000 ₺ / ay"),
        ("07:00", "107:00"),
        ("23", "23:00"),  # a piece of a time
        ("ay", "aylık"),  # a piece of a word
        ("", "6.000 ₺"),
    ],
)
def test_a_piece_of_a_longer_token_does_not(needle: str, haystack: str) -> None:
    assert not occurs_as_token(needle, haystack)
