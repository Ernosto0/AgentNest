"""The only place where social-account states change (state-machines.md §7).

Pure: maps ``(current, target)`` to the target or raises ``CONFLICT_STATE``. Entering
``needs_reauth``, ``degraded`` or ``disconnected`` is announced by the caller (operations).
"""

from app.core.errors import AppError

_ALLOWED: dict[str | None, frozenset[str]] = {
    None: frozenset({"connected"}),
    "connected": frozenset({"needs_reauth", "degraded", "disconnected"}),
    "degraded": frozenset({"connected", "needs_reauth", "disconnected"}),
    "needs_reauth": frozenset({"connected", "disconnected"}),
}


def apply_account_transition(
    current: str | None, target: str, *, reauthorized: bool = False
) -> str:
    if reauthorized and target == "connected" and current in ("connected", "disconnected"):
        return target
    if target in _ALLOWED.get(current, frozenset()):
        return target
    raise AppError("CONFLICT_STATE", entity="social_account", status=current, target=target)
