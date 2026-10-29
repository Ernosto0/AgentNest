"""Offline safety checks for the manual harness; never construct a network client."""

import pytest

from tests.contract.test_meta_live import _comment_probe_inputs, _probe, live_account


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


@pytest.mark.parametrize("effect", ["read", "reply", "private_reply", "hide", "unhide", "delete"])
def test_comment_probes_cannot_bypass_pending_evidence(monkeypatch, effect):
    monkeypatch.setenv("META_LIVE_COMMENT_MEDIA_ID", "explicit-test-media")
    monkeypatch.setenv("META_LIVE_COMMENT_ID", "explicit-test-comment")
    monkeypatch.setenv("META_LIVE_COMMENT_EFFECT", effect)
    with pytest.raises(pytest.skip.Exception, match="evidence remains pending"):
        _comment_probe_inputs(effect)


def test_comment_probe_never_selects_arbitrary_target(monkeypatch):
    monkeypatch.delenv("META_LIVE_COMMENT_MEDIA_ID", raising=False)
    monkeypatch.delenv("META_LIVE_COMMENT_ID", raising=False)
    with pytest.raises(pytest.skip.Exception, match="exact media and comment"):
        _comment_probe_inputs("delete")


def test_comment_mutation_requires_separate_exact_effect_opt_in(monkeypatch):
    monkeypatch.setenv("META_LIVE_COMMENT_MEDIA_ID", "explicit-test-media")
    monkeypatch.setenv("META_LIVE_COMMENT_ID", "explicit-test-comment")
    monkeypatch.setenv("META_LIVE_COMMENT_EFFECT", "hide")
    with pytest.raises(pytest.skip.Exception, match="separate exact effect"):
        _comment_probe_inputs("delete")
