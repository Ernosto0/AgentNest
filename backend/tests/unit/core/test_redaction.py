"""AC-X7 (redaction part): known secret keys are masked in logs (INV-10)."""

import json
from collections.abc import Iterator
from typing import Any

import pytest

from app.core.config import Settings, get_settings
from app.core.logging import REDACTED, configure_logging, get_logger, redact_processor


def redact(**event: Any) -> dict[str, Any]:
    return dict(redact_processor(None, "info", {"event": "x", **event}))


@pytest.mark.parametrize(
    "key",
    [
        "token",
        "access_token",
        "csrf_token",
        "secret",
        "SECRET_KEY",
        "password",
        "new_password",
        "authorization",
        "Authorization",
        "cookie",
        "set_cookie",
        "api_key",
        "code",
    ],
)
def test_sensitive_keys_are_masked(key: str) -> None:
    assert redact(**{key: "value"})[key] == REDACTED


@pytest.mark.parametrize("key", ["error_code", "status", "request_id", "input_tokens", "user_id"])
def test_non_sensitive_keys_are_kept(key: str) -> None:
    assert redact(**{key: "value"})[key] == "value"


def test_boolean_and_null_flags_under_sensitive_looking_keys_stay_readable() -> None:
    # e.g. the startup log line "cookie_secure=true": a flag cannot hold a secret.
    result = redact(cookie_secure=True, token=None, secret_enabled=False)
    assert (result["cookie_secure"], result["token"], result["secret_enabled"]) == (
        True,
        None,
        False,
    )
    assert redact(cookie_secure="true")["cookie_secure"] == REDACTED  # strings still masked


def test_nested_structures_are_masked() -> None:
    result = redact(
        headers={"Authorization": "Bearer abc", "accept": "json"}, items=[{"token": "t"}]
    )
    assert result["headers"] == {"Authorization": REDACTED, "accept": "json"}
    assert result["items"] == [{"token": REDACTED}]


def test_bearer_values_are_masked_even_under_innocent_keys() -> None:
    assert redact(header="Bearer abc.def")["header"] == REDACTED


def test_the_event_text_itself_is_never_replaced() -> None:
    assert redact(token="t")["event"] == "x"


@pytest.fixture
def restore_logging() -> Iterator[None]:
    yield
    configure_logging(get_settings())  # undo the test's own configuration


@pytest.mark.usefixtures("restore_logging")
def test_json_logging_pipeline_redacts_end_to_end(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(
        Settings(_env_file=None, app_env="development", log_format="json", log_level="INFO")
    )
    get_logger("test").info("login_attempt", password="hunter2", user_id="u1")
    # Logs go to stderr so that stdout stays usable for machine-readable CLI output.
    captured = capsys.readouterr()
    assert captured.out == ""
    line = json.loads(captured.err.strip().splitlines()[-1])
    assert line["password"] == REDACTED
    assert line["user_id"] == "u1"
    assert line["event"] == "login_attempt"
    assert {"ts", "level", "logger", "env"} <= set(line)
    assert "hunter2" not in json.dumps(line)
