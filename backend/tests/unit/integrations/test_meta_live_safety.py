"""Offline safety checks for the manual harness; never construct a network client."""

import pytest

from tests.contract.test_meta_live import _probe, live_account


@pytest.mark.parametrize(
    ("token", "ig_id"), [("", ""), ("synthetic-token", ""), ("", "synthetic-id")]
)
def test_live_harness_requires_both_inputs(
    monkeypatch: pytest.MonkeyPatch, token: str, ig_id: str
) -> None:
    monkeypatch.setenv("META_LIVE_ACCESS_TOKEN", token)
    monkeypatch.setenv("META_LIVE_IG_USER_ID", ig_id)
    with pytest.raises(pytest.skip.Exception, match="both explicit live credentials"):
        live_account.__wrapped__()


def test_probe_failure_cannot_retain_sensitive_exception() -> None:
    def fail() -> None:
        raise RuntimeError("synthetic-secret-and-presigned-url")

    with pytest.raises(pytest.fail.Exception) as caught:
        _probe(fail)
    assert "synthetic-secret" not in str(caught.value)
    assert caught.value.__context__ is None
    assert caught.value.pytrace is False
