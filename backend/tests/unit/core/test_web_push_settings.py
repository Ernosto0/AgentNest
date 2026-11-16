"""F-01: VAPID keys, the Web Push settings checks and the key generator command."""

import base64

import pytest

from app.cli import main
from app.core.config import ConfigError, Settings
from app.core.security import generate_vapid_keys, vapid_keys_match

TOKEN_KEYS = "k1:" + base64.b64encode(b"7" * 32).decode()


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("WEB_PUSH_VAPID_PUBLIC_KEY", "WEB_PUSH_VAPID_PRIVATE_KEY", "WEB_PUSH_SUBJECT"):
        monkeypatch.delenv(name, raising=False)


def settings(**values: object) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_a_generated_pair_has_the_documented_shape_and_matches() -> None:
    public, private = generate_vapid_keys()
    assert len(base64.urlsafe_b64decode(public + "==")) == 65  # uncompressed P-256 point
    assert base64.urlsafe_b64decode(public + "==")[0] == 4
    assert len(base64.urlsafe_b64decode(private + "==")) == 32
    assert "=" not in public + private and "+" not in public + private
    assert vapid_keys_match(public, private)
    assert generate_vapid_keys() != (public, private)


def test_a_mismatched_or_malformed_pair_is_rejected() -> None:
    public, _ = generate_vapid_keys()
    _, other_private = generate_vapid_keys()
    assert not vapid_keys_match(public, other_private)
    for bad in ("", "!!!", "AAAA", public):
        assert not vapid_keys_match(public, bad)
    assert not vapid_keys_match("not-a-key", other_private)


def test_the_generated_pair_works_with_the_push_library() -> None:
    from py_vapid import Vapid

    public, private = generate_vapid_keys()
    claims = Vapid.from_string(private).sign(
        {"sub": "mailto:ops@example.com", "aud": "https://fcm.googleapis.com"}
    )
    assert claims["Authorization"].startswith("vapid ")
    assert f"k={public}" in claims["Authorization"]


def test_push_is_off_by_default_and_all_three_values_turn_it_on() -> None:
    assert settings().web_push_enabled is False
    public, private = generate_vapid_keys()
    on = settings(
        web_push_vapid_public_key=public,
        web_push_vapid_private_key=private,
        web_push_subject="mailto:ops@example.com",
        token_encryption_keys=TOKEN_KEYS,
        token_encryption_active_key_id="k1",
    )
    assert on.web_push_enabled is True


def test_a_partial_or_wrong_configuration_refuses_to_start() -> None:
    public, private = generate_vapid_keys()
    _, other_private = generate_vapid_keys()
    keys = {"token_encryption_keys": TOKEN_KEYS, "token_encryption_active_key_id": "k1"}
    with pytest.raises(ConfigError, match="must be set together"):
        settings(web_push_vapid_public_key=public, **keys)
    with pytest.raises(ConfigError, match="must be set together"):
        settings(web_push_subject="mailto:a@b.c", **keys)
    with pytest.raises(ConfigError, match="matching pair"):
        settings(
            web_push_vapid_public_key=public,
            web_push_vapid_private_key=other_private,
            web_push_subject="mailto:a@b.c",
            **keys,
        )
    with pytest.raises(ConfigError, match="WEB_PUSH_SUBJECT must start"):
        settings(
            web_push_vapid_public_key=public,
            web_push_vapid_private_key=private,
            web_push_subject="ops@example.com",
            **keys,
        )
    with pytest.raises(ConfigError, match="TOKEN_ENCRYPTION_KEYS must be set"):
        settings(
            web_push_vapid_public_key=public,
            web_push_vapid_private_key=private,
            web_push_subject="mailto:a@b.c",
        )


def test_the_private_key_is_never_in_the_loggable_configuration() -> None:
    public, private = generate_vapid_keys()
    cfg = settings(
        web_push_vapid_public_key=public,
        web_push_vapid_private_key=private,
        web_push_subject="mailto:ops@example.com",
        token_encryption_keys=TOKEN_KEYS,
        token_encryption_active_key_id="k1",
    )
    shown = str(cfg.public_dict()) + repr(cfg.web_push_vapid_private_key) + repr(cfg)
    assert private not in shown
    assert cfg.public_dict()["web_push_vapid_public_key"] == public


def test_generate_vapid_keys_command_prints_env_lines_only_on_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["generate-vapid-keys"]) == 0
    captured = capsys.readouterr()
    lines = captured.out.strip().splitlines()
    assert [line.split("=", 1)[0] for line in lines] == [
        "WEB_PUSH_VAPID_PUBLIC_KEY",
        "WEB_PUSH_VAPID_PRIVATE_KEY",
    ]
    public, private = (line.split("=", 1)[1] for line in lines)
    assert vapid_keys_match(public, private)
    assert "WEB_PUSH_SUBJECT" in captured.err and private not in captured.err
