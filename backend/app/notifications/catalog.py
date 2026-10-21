"""The notification catalog: the single source of every notification type (plan H8).

Each type has a severity, a recipient rule and the pattern of its ``dedup_key``. ``notify`` and
``notify_permission_holders`` refuse a type that is not listed here. The same list is written to
``frontend/src/features/notifications/catalog.json`` (``uv run python -m
app.notifications.catalog``) so a frontend test fails when ``describe.ts`` lacks a type; a backend
test fails when the file is out of date. The table for people is observability.md section 4.4.

Types of later sessions are added by the session that produces them.
"""

import json
from dataclasses import dataclass
from pathlib import Path

INFO = "info"
ATTENTION = "attention"
CRITICAL = "critical"
SEVERITIES = (INFO, ATTENTION, CRITICAL)


@dataclass(frozen=True)
class NotificationSpec:
    type: str
    severity: str
    recipients: str  # the permission that selects the recipients, or a rule in words
    dedup: str  # the shape of the dedup key (an unread duplicate per recipient is never created)


_SPECS = (
    NotificationSpec(
        "approval.requested", ATTENTION, "approval's required permission", "approval:{approval_id}"
    ),
    NotificationSpec(
        "approval.expired", INFO, "the requesting user", "approval-expired:{approval_id}"
    ),
    NotificationSpec(
        "content.on_hold",
        ATTENTION,
        "content.approve + author",
        "content.on_hold:{content_id}:v{version}",
    ),
    NotificationSpec(
        "content.published",
        INFO,
        "content.approve + author",
        "content.published:{content_id}:v{version}",
    ),
    NotificationSpec(
        "content.failed",
        ATTENTION,
        "content.approve + author",
        "content.failed:{content_id}:v{version}",
    ),
    NotificationSpec(
        "conversation.needs_human", ATTENTION, "reply.approve", "needs-human:{conversation_id}"
    ),
    NotificationSpec("reply.failed", ATTENTION, "reply.approve", "reply-failed:{draft_id}"),
    NotificationSpec(
        "knowledge.fact_changed",
        INFO,
        "knowledge.verify (not the changer)",
        "fact:{fact_id}:v{version}",
    ),
    NotificationSpec(
        "account.needs_reauth", CRITICAL, "integrations.manage", "account:{account_id}:needs_reauth"
    ),
    NotificationSpec(
        "account.permission_missing",
        ATTENTION,
        "integrations.manage",
        "account:{account_id}:permission_missing:{capability}",
    ),
    NotificationSpec("report.daily_ready", INFO, "reports.view", "report:{local_date}"),
)

CATALOG: dict[str, NotificationSpec] = {spec.type: spec for spec in _SPECS}

FRONTEND_FILE = (
    Path(__file__).resolve().parents[3]
    / "frontend"
    / "src"
    / "features"
    / "notifications"
    / "catalog.json"
)


def spec_for(type: str) -> NotificationSpec:
    """The catalog entry of ``type``; an unknown type is a programming error."""
    try:
        return CATALOG[type]
    except KeyError:
        raise ValueError(f"unknown notification type: {type}") from None


def frontend_document() -> dict[str, list[dict[str, str]]]:
    """What the frontend needs of the catalog: the types and their severities."""
    return {"types": [{"type": s.type, "severity": s.severity} for s in _SPECS]}


if __name__ == "__main__":
    text = json.dumps(frontend_document(), indent=2, ensure_ascii=False) + "\n"
    with FRONTEND_FILE.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
