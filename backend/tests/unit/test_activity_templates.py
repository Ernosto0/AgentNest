"""Template coverage of the Activity feed (plan H7): every action of the audit catalog in
observability.md section 5, and every action the code writes, has an ``activity.<action>`` text
in both languages and a group."""

import re
from pathlib import Path

from app.activity.groups import GROUP_NAMES, GROUPS
from app.core.i18n import catalog_keys, t

BACKEND = Path(__file__).resolve().parents[2]
CATALOG_DOC = BACKEND.parent / "docs" / "architecture" / "observability.md"
APP = BACKEND / "app"

_ACTION = re.compile(r"`([a-z_]+\.[a-z_]+(?:/[a-z_]+)*)`")
_LITERAL = re.compile(r'"([a-z_]+\.[a-z_]+)"')
# The resource-type prefixes of audit actions; a literal with another prefix is not an action.
_PREFIXES = (
    "auth",
    "workspace",
    "member",
    "fact",
    "fact_candidate",
    "knowledge",
    "approved_answer",
    "policy",
    "command",
    "approval",
    "message",
    "reply_draft",
    "reply",
    "conversation",
    "content",
    "media",
    "operation",
    "social_account",
    "account",
    "webhook",
    "report",
    "retention",
    "demo",
)


def catalog_actions() -> set[str]:
    """The actions in the audit action catalog table (``a.b/c`` means ``a.b`` and ``a.c``)."""
    lines = CATALOG_DOC.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("| Area | Actions |"))
    actions: set[str] = set()
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        for token in _ACTION.findall(line):
            head, *rest = token.split("/")
            actions.add(head)
            prefix = head.split(".")[0]
            actions.update(f"{prefix}.{name}" for name in rest)
    return actions


def written_actions() -> set[str]:
    """Literal action names inside ``audit.record(...)`` calls (and the one-line wrappers)."""
    found: set[str] = set()
    for path in APP.rglob("*.py"):
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if "audit.record(" not in line and "_audit(" not in line:
                continue
            for window in lines[i : i + 8]:
                found.update(m for m in _LITERAL.findall(window) if m.split(".")[0] in _PREFIXES)
    return found


def test_the_catalog_is_found_and_not_trivially_small() -> None:
    assert len(catalog_actions()) > 70


def test_every_catalog_action_has_a_group_and_a_text_in_both_languages() -> None:
    missing_group = sorted(a for a in catalog_actions() if a not in GROUPS)
    assert not missing_group, f"no Activity group: {missing_group}"
    for locale in ("tr", "en"):
        known = catalog_keys(locale)
        missing = sorted(a for a in catalog_actions() if f"activity.{a}" not in known)
        assert not missing, f"no {locale} text: {missing}"


def test_every_action_the_code_writes_is_known_to_the_feed() -> None:
    written = written_actions()
    assert {"reply.sent", "fact.updated", "content.created", "member.joined"} <= written
    unknown = sorted(a for a in written if a not in GROUPS)
    assert not unknown, f"written by the code but not in app/activity/groups.py: {unknown}"


def test_every_known_action_has_texts_that_differ_between_languages_or_are_names() -> None:
    for action in GROUPS:
        tr, en = t(f"activity.{action}", "tr"), t(f"activity.{action}", "en")
        assert not tr.startswith("activity.") and not en.startswith("activity."), action
        assert tr.strip() and en.strip()


def test_every_group_is_used() -> None:
    assert set(GROUPS.values()) == set(GROUP_NAMES)
