"""Static permission matrix (security-and-privacy.md §3), complete from day one.

Server-enforced; the frontend only hides controls. Most permissions are first used by later
phases. Notes on the two permissions the matrix describes with a qualifier:
- ``knowledge.edit`` is granted to staff, but their edits become candidates (Phase 2 logic).
- ``reports.view`` is the full report. Staff get ``reports.view_inbox_metrics`` only.
"""

OWNER = "owner"
MANAGER = "manager"
STAFF = "staff"
ROLES = (OWNER, MANAGER, STAFF)

_ALL = frozenset(ROLES)
_OWNER_MANAGER = frozenset({OWNER, MANAGER})
_OWNER_ONLY = frozenset({OWNER})

# permission -> roles that hold it
PERMISSION_MATRIX: dict[str, frozenset[str]] = {
    "workspace.manage": _OWNER_ONLY,
    "members.manage": _OWNER_ONLY,
    "integrations.manage": _OWNER_ONLY,
    "automation.manage": _OWNER_ONLY,
    "agent.settings.edit": _OWNER_MANAGER,
    "agent.delegation.manage": _OWNER_ONLY,
    "agent.control": _OWNER_ONLY,
    "agent.activity.view": _OWNER_MANAGER,
    "comments.approve": _OWNER_MANAGER,
    "comments.moderate": _OWNER_MANAGER,
    "knowledge.edit": _ALL,
    "knowledge.verify": _OWNER_MANAGER,
    "commands.use": _ALL,
    "reply.write": _ALL,
    "reply.approve": _OWNER_MANAGER,
    "conversation.takeover": _ALL,
    "content.edit": _ALL,
    "content.approve": _OWNER_MANAGER,
    "approvals.view": _ALL,
    "reports.view": _OWNER_MANAGER,
    "reports.view_inbox_metrics": _ALL,
    "activity.view": _OWNER_MANAGER,
    "system_health.view": _OWNER_MANAGER,
    "data.export": _OWNER_ONLY,
    "data.delete": _OWNER_ONLY,
}


def has_permission(role: str | None, permission: str) -> bool:
    """True if ``role`` holds ``permission``. Unknown permissions raise (typos must not pass)."""
    if permission not in PERMISSION_MATRIX:
        raise KeyError(f"Unknown permission: {permission}")
    return role in PERMISSION_MATRIX[permission]


def permissions_for(role: str) -> frozenset[str]:
    return frozenset(p for p, roles in PERMISSION_MATRIX.items() if role in roles)
