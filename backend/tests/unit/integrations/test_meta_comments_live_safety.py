"""Offline safety boundaries of the optional real comment probes."""

import pytest

from tests.contract import test_meta_comments_live as live


@pytest.mark.parametrize(("token", "account"), [("", ""), ("fake-token", ""), ("", "fake-id")])
def test_no_client_without_credentials(monkeypatch, token, account):
    monkeypatch.setenv("META_LIVE_ACCESS_TOKEN", token)
    monkeypatch.setenv("META_LIVE_IG_USER_ID", account)
    monkeypatch.setattr(live.httpx, "HTTPTransport", lambda: pytest.fail("network constructed"))
    with pytest.raises(pytest.skip.Exception):
        live.live_account.__wrapped__()


@pytest.mark.parametrize("missing", ["META_LIVE_COMMENT_EFFECT", "META_LIVE_COMMENT_SEND"])
def test_mutations_need_separate_opt_ins(monkeypatch, missing):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("META_LIVE_COMMENT_ID", "target")
    monkeypatch.setenv("META_LIVE_COMMENT_EFFECT", "private_reply")
    monkeypatch.setenv("META_LIVE_COMMENT_SEND", "YES_SEND_REAL_MESSAGE")
    monkeypatch.delenv(missing, raising=False)
    with pytest.raises(pytest.skip.Exception):
        live._inputs(mutation=True)


def test_limit_probes_need_extra_opt_in(monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("META_LIVE_COMMENT_ID", "target")
    monkeypatch.setenv("META_LIVE_COMMENT_EFFECT", "private_reply")
    monkeypatch.setenv("META_LIVE_COMMENT_SEND", "YES_SEND_REAL_MESSAGE")
    monkeypatch.delenv("META_LIVE_COMMENT_LIMIT_PROBES", raising=False)
    with pytest.raises(pytest.skip.Exception):
        live._inputs(mutation=True, repeat=True)


def test_records_never_contain_secrets_or_content(monkeypatch, tmp_path):
    path = tmp_path / "probes.jsonl"
    monkeypatch.setenv("META_LIVE_PROBE_RECORD", str(path))
    live._record(
        token="secret-token",
        text="private comment text",
        recipient_id="sensitive-id",
        http_status=200,
        count=1,
        error_code="secret-token",
    )
    data = path.read_text()
    assert "secret-token" not in data and "private comment text" not in data
    assert "sensitive-id" not in data and '"http_status": 200' in data


def test_failure_has_no_sensitive_exception_context():
    def fail():
        raise ValueError("secret-token")

    with pytest.raises(pytest.fail.Exception) as caught:
        live._probe(fail)
    assert "secret-token" not in str(caught.value)
    assert caught.value.__context__ is None


def test_ci_always_skips(monkeypatch):
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("META_LIVE_ACCESS_TOKEN", "fake-token")
    monkeypatch.setenv("META_LIVE_IG_USER_ID", "fake-id")
    with pytest.raises(pytest.skip.Exception):
        live.live_account.__wrapped__()
