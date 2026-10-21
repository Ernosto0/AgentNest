"""The notification catalog (plan H8), dedup per type and read-all (P6-04)."""

import ast
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.content import notifications as content_notifications
from app.notifications import catalog
from app.notifications import service as notifications
from app.notifications.models import Notification
from tests.helpers.env import Env

APP = Path(__file__).resolve().parents[3] / "app"


def _string_constants(tree: ast.Module) -> dict[str, str]:
    return {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for target in node.targets
        if isinstance(target, ast.Name)
    }


def produced_types() -> set[str]:
    """Every literal ``type=`` handed to ``notify`` / ``notify_permission_holders`` in the code
    (a module-level constant is resolved; the content kinds are checked separately)."""
    found: set[str] = set()
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = _string_constants(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if name not in ("notify", "notify_permission_holders"):
                continue
            for keyword in node.keywords:
                if keyword.arg != "type":
                    continue
                if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    found.add(keyword.value.value)
                elif isinstance(keyword.value, ast.Name) and keyword.value.id in constants:
                    found.add(constants[keyword.value.id])
    return found


def test_every_type_produced_in_code_is_in_the_catalog() -> None:
    produced = produced_types()
    assert {"approval.requested", "account.needs_reauth", "report.daily_ready"} <= produced
    assert produced <= set(catalog.CATALOG)
    assert set(content_notifications.KINDS) <= set(catalog.CATALOG)
    for kind, severity in content_notifications.SEVERITY.items():
        assert catalog.CATALOG[kind].severity == severity


def test_the_frontend_copy_of_the_catalog_is_current() -> None:
    on_disk = json.loads(catalog.FRONTEND_FILE.read_text(encoding="utf-8"))
    assert on_disk == catalog.frontend_document(), "run: uv run python -m app.notifications.catalog"
    assert {s.severity for s in catalog.CATALOG.values()} <= set(catalog.SEVERITIES)


def test_an_unknown_type_is_refused(env: Env) -> None:
    ctx = env.ctx(env.owner)
    with pytest.raises(ValueError, match="unknown notification type"):
        notifications.notify(
            env.session, env.clock, ctx, recipient_user_id=env.owner.user.id, type="x.y"
        )
    with pytest.raises(ValueError, match="unknown notification type"):
        notifications.notify_permission_holders(
            env.session, env.clock, ctx, permission="nobody.has.this", type="x.y"
        )
    assert env.session.scalars(select(Notification)).all() == []


def test_a_severity_that_contradicts_the_catalog_is_refused(env: Env) -> None:
    with pytest.raises(ValueError, match="severity"):
        notifications.notify(
            env.session,
            env.clock,
            env.ctx(env.owner),
            recipient_user_id=env.owner.user.id,
            type="account.needs_reauth",
            severity="info",
        )


@pytest.mark.parametrize("type_", sorted(catalog.CATALOG))
def test_dedup_holds_per_type_until_read(env: Env, type_: str) -> None:
    ctx = env.ctx(env.owner)
    kwargs = {"recipient_user_id": env.owner.user.id, "type": type_, "dedup_key": f"k:{type_}"}
    first = notifications.notify(env.session, env.clock, ctx, **kwargs)  # type: ignore[arg-type]
    assert first is not None and first.severity == catalog.CATALOG[type_].severity
    assert notifications.notify(env.session, env.clock, ctx, **kwargs) is None  # type: ignore[arg-type]
    # Another type with the same key is a different notification.
    other = next(t for t in catalog.CATALOG if t != type_)
    assert (
        notifications.notify(
            env.session,
            env.clock,
            ctx,
            recipient_user_id=env.owner.user.id,
            type=other,
            dedup_key=f"k:{type_}",
        )
        is None
    )  # the unread duplicate is decided by the key and recipient, not by the type
    notifications.mark_read(env.session, env.clock, ctx, env.owner.user.id, first.id)
    assert notifications.notify(env.session, env.clock, ctx, **kwargs) is not None  # type: ignore[arg-type]


def test_read_all_touches_only_the_callers_notifications(env: Env) -> None:
    for role in (env.owner, env.manager):
        notifications.notify(
            env.session,
            env.clock,
            env.ctx(role),
            recipient_user_id=role.user.id,
            type="report.daily_ready",
            dedup_key="report:2026-10-20",
        )
    env.session.commit()
    assert env.call(env.owner, "POST", "/notifications/read-all").status_code == 204
    assert env.call(env.owner, "GET", "/notifications").json()["unread_count"] == 0
    assert env.call(env.manager, "GET", "/notifications").json()["unread_count"] == 1
