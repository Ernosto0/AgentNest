"""CLI commands (P1-10)."""

import base64
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.cli import main
from app.core.config import Settings
from app.core.security import verify_password
from app.identity.models import User


def test_generate_key_secret_is_long_random_and_unique(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["generate-key"]) == 0
    first = capsys.readouterr().out.strip()
    assert main(["generate-key"]) == 0
    second = capsys.readouterr().out.strip()
    assert len(first.encode()) >= 32
    assert first != second


def test_generate_key_token_encryption_has_the_documented_format(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["generate-key", "--kind", "token-encryption", "--key-id", "k7"]) == 0
    key_id, _, material = capsys.readouterr().out.strip().partition(":")
    assert key_id == "k7"
    assert len(base64.b64decode(material, validate=True)) == 32


def test_export_openapi_to_a_file_is_utf8_lf_and_deterministic(tmp_path: Path) -> None:
    one, two = tmp_path / "one.json", tmp_path / "two.json"
    assert main(["export-openapi", "-o", str(one)]) == 0
    assert main(["export-openapi", "--output", str(two)]) == 0

    raw = one.read_bytes()
    assert raw == two.read_bytes()  # CI diffs the committed copy against a fresh export
    assert not raw.startswith((b"\xef\xbb\xbf", b"\xff\xfe"))  # no BOM / UTF-16 (PowerShell '>')
    assert b"\r\n" not in raw and raw.endswith(b"\n")
    spec = json.loads(raw.decode("utf-8"))
    assert {"/api/v1/auth/login", "/api/v1/meta", "/api/v1/workspaces/{workspace_id}"} <= set(
        spec["paths"]
    )


def test_export_openapi_to_stdout_is_pure_json(capfdbinary: pytest.CaptureFixture[bytes]) -> None:
    assert main(["export-openapi"]) == 0
    out = capfdbinary.readouterr().out
    assert json.loads(out.decode("utf-8"))["openapi"].startswith("3.")


def test_export_openapi_needs_no_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://nobody:x@127.0.0.1:1/none")
    get_settings.cache_clear()
    try:
        assert main(["export-openapi", "-o", str(tmp_path / "api.json")]) == 0
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


@pytest.mark.commits
def test_create_user_command(session_factory: sessionmaker[Session]) -> None:
    code = main(
        [
            "create-user",
            "--email",
            " New@Example.Test ",
            "--display-name",
            "New Person",
            "--password",
            "a-long-enough-password",
            "--locale",
            "en",
        ]
    )
    assert code == 0
    with session_factory() as session:
        user = session.scalars(select(User).where(User.email == "new@example.test")).one()
    assert (user.display_name, user.ui_locale) == ("New Person", "en")
    assert verify_password(user.password_hash, "a-long-enough-password")


@pytest.mark.commits
def test_create_user_rejects_weak_passwords_and_duplicates(
    session_factory: sessionmaker[Session], capsys: pytest.CaptureFixture[str]
) -> None:
    args = ["create-user", "--email", "dup@example.test", "--display-name", "D"]
    assert main([*args, "--password", "short"]) == 1
    assert "password: too_short" in capsys.readouterr().err
    assert main([*args, "--password", "a-long-enough-password"]) == 0
    assert main([*args, "--password", "a-long-enough-password"]) == 1
    assert "email: already_exists" in capsys.readouterr().err
    with session_factory() as session:
        assert len(session.scalars(select(User)).all()) == 1


@pytest.fixture
def unsafe_production(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """APP_ENV=production with demo tools on and no secret key (AC-X6)."""
    from app.core.config import get_settings

    for name in ("SECRET_KEY", "DATABASE_URL", "COOKIE_SECURE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEMO_TOOLS_ENABLED", "true")
    monkeypatch.setattr(
        "app.core.config.Settings.model_config", {**Settings.model_config, "env_file": None}
    )
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


@pytest.mark.usefixtures("unsafe_production")
def test_cli_refuses_to_start_on_an_unsafe_production_configuration(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["generate-key"]) == 1
    err = capsys.readouterr().err
    assert "Refusing to start" in err
    assert "SECRET_KEY" in err
    assert "DEMO_TOOLS_ENABLED" in err


@pytest.mark.usefixtures("unsafe_production")
def test_api_and_worker_refuse_to_start_on_an_unsafe_production_configuration() -> None:
    from app.core.config import ConfigError
    from app.main import create_app
    from app.worker import main as worker_main

    with pytest.raises(ConfigError, match="DEMO_TOOLS_ENABLED"):
        create_app()
    with pytest.raises(ConfigError, match="SECRET_KEY"):
        worker_main()


def test_unknown_command_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as info:
        main(["frobnicate"])
    assert info.value.code == 2
