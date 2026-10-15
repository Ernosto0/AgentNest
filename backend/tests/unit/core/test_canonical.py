import uuid
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.canonical import canonical_json, payload_hash


def test_key_order_does_not_change_the_hash() -> None:
    assert payload_hash({"a": 1, "b": [1, 2]}) == payload_hash({"b": [1, 2], "a": 1})


def test_nested_key_order_is_normalised() -> None:
    assert payload_hash({"x": {"b": 1, "a": 2}}) == payload_hash({"x": {"a": 2, "b": 1}})


def test_list_order_matters() -> None:
    assert payload_hash([1, 2]) != payload_hash([2, 1])


def test_canonical_form_has_no_whitespace_and_is_sorted() -> None:
    assert canonical_json({"b": 1, "a": "x"}) == '{"a":"x","b":1}'


def test_known_hash_vector_is_stable() -> None:
    # Guards against accidental changes of the canonical form (hashes are persisted).
    assert (
        payload_hash({"amount": Decimal("7000.00"), "currency": "TRY"})
        == "7269f1944b8e741a029f36ba78ce6807dfe4d1f5521f469658ca5ddf12c9b1e6"
    )


def test_decimals_are_strings_and_precision_is_preserved() -> None:
    assert canonical_json({"amount": Decimal("7000.00")}) == '{"amount":"7000.00"}'
    assert payload_hash({"a": Decimal("7000.00")}) != payload_hash({"a": Decimal("7000")})
    assert canonical_json({"a": Decimal("1E+3")}) == '{"a":"1000"}'


def test_unicode_is_utf8_not_escaped() -> None:
    assert canonical_json({"ad": "Gölkent İ ı ş ₺"}) == '{"ad":"Gölkent İ ı ş ₺"}'
    assert payload_hash({"ad": "İ"}) != payload_hash({"ad": "I"})


def test_hash_is_64_hex_chars() -> None:
    digest = payload_hash({})
    assert len(digest) == 64 and int(digest, 16) >= 0


def test_datetimes_are_normalised_to_utc() -> None:
    utc = datetime(2026, 10, 15, 16, 0, tzinfo=UTC)
    istanbul = utc.astimezone(timezone(timedelta(hours=3)))
    assert payload_hash({"at": utc}) == payload_hash({"at": istanbul})
    assert canonical_json({"at": utc}) == '{"at":"2026-10-15T16:00:00Z"}'


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(TypeError):
        payload_hash({"at": datetime(2026, 1, 1)})


def test_uuids_are_strings() -> None:
    value = uuid.UUID("12345678-1234-5678-1234-567812345678")
    assert canonical_json({"id": value}) == '{"id":"12345678-1234-5678-1234-567812345678"}'


def test_nan_is_rejected() -> None:
    with pytest.raises(ValueError):
        payload_hash({"x": float("nan")})


def test_unsupported_types_are_rejected() -> None:
    with pytest.raises(TypeError):
        payload_hash({"x": object()})
