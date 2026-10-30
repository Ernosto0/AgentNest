"""The permission matrix, written out independently of the implementation.

Source of truth: docs/architecture/security-and-privacy.md §3. A change to the matrix must
change this table too, which makes the change visible in review.
"""

import pytest

from app.identity.permissions import PERMISSION_MATRIX, ROLES, has_permission, permissions_for

# permission -> (owner, manager, staff)
EXPECTED: dict[str, tuple[bool, bool, bool]] = {
    "owner_questions.answer": (True, True, False),
    "owner_questions.propose": (True, True, True),
    "memory.correct": (True, True, False),
    "memory.forget": (True, True, False),
    "workspace.manage": (True, False, False),
    "members.manage": (True, False, False),
    "integrations.manage": (True, False, False),
    "automation.manage": (True, False, False),
    "agent.settings.edit": (True, True, False),
    "agent.delegation.manage": (True, False, False),
    "agent.control": (True, False, False),
    "agent.activity.view": (True, True, False),
    "comments.view": (True, True, True),
    "comments.approve": (True, True, False),
    "comments.moderate": (True, True, False),
    "knowledge.edit": (True, True, True),
    "knowledge.verify": (True, True, False),
    "commands.use": (True, True, True),
    "reply.write": (True, True, True),
    "reply.approve": (True, True, False),
    "conversation.takeover": (True, True, True),
    "content.edit": (True, True, True),
    "content.approve": (True, True, False),
    "approvals.view": (True, True, True),
    "reports.view": (True, True, False),
    "reports.view_inbox_metrics": (True, True, True),
    "activity.view": (True, True, False),
    "system_health.view": (True, True, False),
    "data.export": (True, False, False),
    "data.delete": (True, False, False),
}


def test_matrix_matches_the_documented_table_exactly() -> None:
    assert set(PERMISSION_MATRIX) == set(EXPECTED)
    for permission, flags in EXPECTED.items():
        for role, allowed in zip(ROLES, flags, strict=True):
            assert has_permission(role, permission) is allowed, (permission, role)


def test_owner_holds_every_permission() -> None:
    assert permissions_for("owner") == set(PERMISSION_MATRIX)


def test_roles_are_strictly_nested() -> None:
    assert permissions_for("staff") < permissions_for("manager") < permissions_for("owner")


def test_staff_cannot_approve_verify_or_manage() -> None:
    for permission in (
        "reply.approve",
        "content.approve",
        "knowledge.verify",
        "workspace.manage",
        "members.manage",
        "integrations.manage",
        "automation.manage",
    ):
        assert not has_permission("staff", permission)


def test_unknown_permissions_raise_instead_of_denying_silently() -> None:
    with pytest.raises(KeyError):
        has_permission("owner", "workspace.manag")


def test_no_role_and_unknown_roles_hold_nothing() -> None:
    for permission in PERMISSION_MATRIX:
        assert not has_permission(None, permission)
        assert not has_permission("superuser", permission)  # there is no global superuser
