"""Module dependency rules from component-design.md §3, enforced by import-linter.

The contracts live in pyproject.toml. Rules for modules that do not exist yet (e.g. "only
`operations` may call side-effecting provider methods", INV-15) are added by the phase that
creates those modules.
"""

import pytest
from importlinter.cli import lint_imports

from app.core.db import BACKEND_DIR


def test_import_contracts_are_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(BACKEND_DIR)  # import-linter reads pyproject.toml from the cwd
    assert lint_imports() == 0


WEB_PUSH_CONTRACTS = (
    "web-push-registry-only",
    "web-push-library-only-in-sender",
    "web-push-no-customer-text",
)


def test_the_web_push_contracts_are_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    """F-01: only the registry imports the channel, only its sender imports pywebpush, and the
    channel cannot import any module that holds customer text. Checked on their own so that they
    stay enforced even while an unrelated contract is broken."""
    monkeypatch.chdir(BACKEND_DIR)
    assert lint_imports(limit_to_contracts=WEB_PUSH_CONTRACTS) == 0
