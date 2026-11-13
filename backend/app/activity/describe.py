"""What an Activity entry says beyond its action name (api-design.md section 2.8).

Everything here is read from whitelisted metadata *codes* and mapped to catalog texts, so no
free text reaches the reader: operator alert summaries, exception strings, file names and
e-mail hashes are never shown. A value that does not look like a code is dropped rather than
displayed. Fact values are the one exception the audit catalog allows (``old_display`` /
``new_display`` are formatted business facts, never customer text); they are capped in length.
"""

import hashlib
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.activity.classify import RULES, Classification
from app.audit.models import AuditLog
from app.core.i18n import catalog_keys, format_local_datetime, t

_CODE = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")
_DISPLAY_MAX = 120

ALERT_ACTIONS = frozenset(
    {
        "security.operator_alert_fired",
        "security.operator_alert_resolved",
        "security.alert_delivery_failed",
    }
)

# Alert-key prefixes of operations/operator_alerts.py, most specific first.
_ALERT_KINDS: tuple[tuple[str, str], ...] = (
    ("agent_health:stuck_session:", "stuck_session"),
    ("agent_health:dead_job:", "agent_dead_job"),
    ("dead_job:", "dead_job"),
    ("backup:", "backup"),
    ("webhook:signature_failure_burst", "signature_burst"),
    ("account_needs_reauth:", "account_needs_reauth"),
    ("unresolved_operation:", "unresolved_operation"),
    ("capability_loss:", "capability_loss"),
    ("ai_budget_exhausted:", "ai_budget"),
    ("circuit_open:", "circuit_open"),
)


def alert_kind(metadata: Mapping[str, Any]) -> str:
    key = metadata.get("alert_key")
    if isinstance(key, str):
        for prefix, kind in _ALERT_KINDS:
            if key.startswith(prefix):
                return kind
    return "other"


def alert_condition(metadata: Mapping[str, Any], locale: str) -> str:
    return t(f"activity.alert.condition.{alert_kind(metadata)}", locale)


class _Texts:
    """Catalog lookups for one locale, with fallbacks."""

    def __init__(self, locale: str) -> None:
        self.locale = locale
        self.known = catalog_keys(locale)

    def has(self, key: str) -> bool:
        return key in self.known

    def get(self, key: str, fallback: str | None = None, **params: Any) -> str:
        if key in self.known or fallback is None:
            return t(key, self.locale, **params)
        return t(fallback, self.locale, **params)


def entry_text(row: AuditLog, texts: _Texts) -> str:
    """The headline: the action's template, or a more specific variant chosen by a code."""
    meta = row.metadata_ or {}
    if row.action in ALERT_ACTIONS:
        condition = alert_condition(meta, texts.locale)
        if row.action == "security.operator_alert_fired":
            refire = meta.get("is_refire") is True
            key = "activity.alert.repeated" if refire else "activity.alert.fired"
        elif row.action == "security.operator_alert_resolved":
            key = "activity.alert.resolved"
        else:
            key = "activity.alert.delivery_failed"
        return texts.get(key, condition=condition)
    rule = RULES.get(row.action)
    if rule is not None and rule.fields:
        for name in rule.fields:
            value = meta.get(name)
            if isinstance(value, str) and _CODE.match(value):
                variant = f"activity.{row.action}.{value}"
                if texts.has(variant):
                    return texts.get(variant)
                break
    return texts.get(f"activity.{row.action}", "activity.unknown")


# --- Details --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Detail:
    key: str
    label: str
    value: str


def _code(value: Any) -> str | None:
    return value if isinstance(value, str) and _CODE.match(value) else None


def _humanize(code: str) -> str:
    return code.replace("_", " ").replace(".", " · ")


def _state(texts: _Texts, value: Any) -> str | None:
    code = _code(value)
    if code is None:
        return None
    key = f"activity.state.{code}"
    return texts.get(key) if texts.has(key) else _humanize(code)


def _plain_code(texts: _Texts, value: Any) -> str | None:
    return _code(value)


def _int(texts: _Texts, value: Any) -> str | None:
    return str(value) if isinstance(value, int) and not isinstance(value, bool) else None


def _bool(texts: _Texts, value: Any) -> str | None:
    if not isinstance(value, bool):
        return None
    return texts.get("activity.detail.yes" if value else "activity.detail.no")


def _severity(texts: _Texts, value: Any) -> str | None:
    code = _code(value)
    if code is None:
        return None
    return texts.get(f"activity.detail.severity.{code}", "activity.detail.severity.other")


def _role(texts: _Texts, value: Any) -> str | None:
    code = _code(value)
    if code is None:
        return None
    key = f"activity.detail.role.{code}"
    return texts.get(key) if texts.has(key) else code


def _operation(texts: _Texts, value: Any) -> str | None:
    code = _code(value)
    if code is None:
        return None
    key = f"activity.resource.operation.{code}"
    return texts.get(key) if texts.has(key) else code


def _display(texts: _Texts, value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = " ".join(value.split())
    return text if len(text) <= _DISPLAY_MAX else text[: _DISPLAY_MAX - 1] + "…"


def _date(texts: _Texts, value: Any) -> str | None:
    try:
        return date.fromisoformat(value).isoformat() if isinstance(value, str) else None
    except ValueError:
        return None


Formatter = Callable[[_Texts, Any], str | None]

# Shown in this order. Anything not listed (IDs, summaries, errors, file names) is not shown.
_DETAILS: tuple[tuple[str, str, Formatter], ...] = (
    ("severity", "severity", _severity),
    ("notification_count", "notification_count", _int),
    ("old_display", "old_value", _display),
    ("new_display", "new_value", _display),
    ("from", "from", _state),
    ("was", "from", _state),
    ("to", "to", _state),
    ("status", "to", _state),
    ("from_role", "from_role", _role),
    ("to_role", "to_role", _role),
    ("role", "role", _role),
    ("reason", "reason", _plain_code),
    ("error_code", "reason", _plain_code),
    ("code", "reason", _plain_code),
    ("operation_type", "operation_type", _operation),
    ("action_type", "type", _plain_code),
    ("command_type", "type", _plain_code),
    ("key", "fact_key", _plain_code),
    ("version", "version", _int),
    ("fact_version", "version", _int),
    ("delegation_version", "version", _int),
    ("local_date", "local_date", _date),
    ("scheduled", "scheduled", _bool),
    ("is_partial", "partial", _bool),
    ("retryable", "retryable", _bool),
    ("source_type", "source", _plain_code),
    ("source", "source", _plain_code),
    ("via", "source", _plain_code),
    ("channel", "channel", _plain_code),
    ("outcome", "outcome", _state),
    ("decision", "outcome", _state),
    ("result", "outcome", _state),
    ("revoked_count", "count", _int),
    ("messages_count", "count", _int),
)
_INSTANTS = ("start_at", "end_at", "scheduled_at")


def entry_details(row: AuditLog, texts: _Texts, timezone: str) -> list[Detail]:
    meta = row.metadata_ or {}
    found: list[Detail] = []
    used_labels: set[str] = set()
    for key, label, formatter in _DETAILS:
        if key not in meta or label in used_labels:
            continue
        value = formatter(texts, meta[key])
        if value is None:
            continue
        used_labels.add(label)
        found.append(Detail(key, texts.get(f"activity.detail.{label}"), value))
    for key in _INSTANTS:
        raw = meta.get(key)
        if not isinstance(raw, str):
            continue
        try:
            instant = datetime.fromisoformat(raw)
        except ValueError:
            continue
        if instant.tzinfo is None:
            continue
        found.append(
            Detail(
                key,
                texts.get(f"activity.detail.{key}"),
                format_local_datetime(instant, timezone, texts.locale),
            )
        )
    return found


# --- Grouping --------------------------------------------------------------------------------


def collapse_key(row: AuditLog, classification: Classification) -> str:
    """Entries with the same key describe the same kind of thing and may be shown as one group.

    - an operator alert: the same alert condition (its key), fired and re-fired alike;
    - routine detail: the same action by the same actor, whatever the record;
    - anything else: the same action on the same record by the same actor.

    The key is opaque; the client only compares keys of adjacent entries.
    """
    meta = row.metadata_ or {}
    if row.action in ALERT_ACTIONS:
        parts = [row.action, str(meta.get("alert_key") or row.resource_id or "")]
    elif classification.routine:
        parts = [row.action, row.actor_type, row.actor_id or ""]
    else:
        parts = [
            row.action,
            row.actor_type,
            row.actor_id or "",
            row.resource_type or "",
            str(row.resource_id or ""),
        ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def texts_for(locale: str) -> _Texts:
    return _Texts(locale)
