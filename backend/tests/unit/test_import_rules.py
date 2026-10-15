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
