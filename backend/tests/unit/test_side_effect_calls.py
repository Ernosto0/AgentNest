"""INV-15: no code calls a side-effecting provider method outside the operations module.

``send_text_message`` and the other external effects (and the reconciliation lookup) may be
called only from ``app/operations`` (and defined in ``app/integrations/instagram``). Everything
else reaches the provider through the ledger. Enforced here by reading the source, as a second
line of defence beside the import contracts.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
FORBIDDEN_CALLS = {
    "send_text_message",
    "create_media_container",
    "publish_container",
    "refresh_token",
    "find_recent_outbound",
}
ALLOWED_DIRS = (APP / "operations", APP / "integrations" / "instagram")


def _calls(path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        (node.func.attr, node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in FORBIDDEN_CALLS
    ]


def _allowed(path: Path) -> bool:
    return any(directory in path.parents for directory in ALLOWED_DIRS)


def test_only_the_operations_module_calls_side_effecting_provider_methods() -> None:
    offenders = [
        f"{path.relative_to(APP)}:{line} calls {name}()"
        for path in sorted(APP.rglob("*.py"))
        if not _allowed(path)
        for name, line in _calls(path)
    ]
    assert offenders == []


def test_the_scan_sees_the_calls_it_is_meant_to_guard() -> None:
    """If the operations module stopped calling the provider, this scan would prove nothing."""
    names = {name for path in (APP / "operations").rglob("*.py") for name, _ in _calls(path)}
    assert {"send_text_message", "find_recent_outbound"} <= names


@pytest.mark.parametrize("name", sorted(FORBIDDEN_CALLS))
def test_the_guarded_methods_exist_on_the_provider_protocol(name: str) -> None:
    from app.integrations.instagram.base import InstagramProvider

    assert hasattr(InstagramProvider, name)
