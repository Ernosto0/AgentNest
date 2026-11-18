"""Offline checks of the manual WhatsApp harness: it needs three explicit inputs and never
falls back to the application's own WhatsApp settings."""

import pytest

from tests.contract.test_whatsapp_live import _probe, live_inputs

_NAMES = ("WHATSAPP_LIVE_ACCESS_TOKEN", "WHATSAPP_LIVE_PHONE_NUMBER_ID", "WHATSAPP_LIVE_TO")


@pytest.mark.parametrize("missing", _NAMES)
def test_live_harness_requires_all_three_inputs(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    for name in _NAMES:
        monkeypatch.setenv(name, "synthetic")
    monkeypatch.setenv(missing, "")
    with pytest.raises(pytest.skip.Exception, match="WHATSAPP_LIVE_ACCESS_TOKEN"):
        live_inputs.__wrapped__()


def test_the_harness_ignores_the_application_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "app-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
    with pytest.raises(pytest.skip.Exception):
        live_inputs.__wrapped__()


def test_probe_failure_cannot_retain_sensitive_exception() -> None:
    def fail() -> None:
        raise RuntimeError("synthetic-secret-token")

    with pytest.raises(pytest.fail.Exception) as caught:
        _probe(fail)
    assert "synthetic-secret" not in str(caught.value)
    assert caught.value.__context__ is None
