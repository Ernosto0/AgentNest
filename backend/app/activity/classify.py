"""How an Activity entry reads at a glance: its level, and whether it is routine detail.

Derived at read time from the audit row (action, actor type and a few whitelisted metadata
codes), so historical rows are classified exactly like new ones and ``audit_logs`` stays
insert-only (INV-12). One rule table drives both the per-row classification and the SQL
filters of the feed and the summary; a test checks that the two always agree.

- ``level`` describes what the recorded event *was*, not the current state of its record:
  ``failure`` (something did not happen or broke), ``warning`` (a problem, an uncertain outcome
  or a degraded connection), ``success`` (an effect completed) or ``info`` (everything else,
  including human decisions such as a rejection). An action this version does not know is
  ``info``.
- ``routine`` marks internal machinery that repeats a business event or only records progress
  (assistant step/session bookkeeping, ledger start/success, "being sent", a draft's ``sent``
  status beside ``reply.sent``). A routine entry is never a failure or warning and never a
  person's own action, so hiding routine entries can never hide a problem.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, get_args

from sqlalchemy import ColumnElement, and_, false, func, not_, or_

from app.audit.models import AuditLog

Level = Literal["failure", "warning", "success", "info"]
LEVELS: tuple[str, ...] = get_args(Level)
_PROBLEM: frozenset[str] = frozenset({"failure", "warning"})


@dataclass(frozen=True)
class Rule:
    level: Level = "info"
    routine: bool = False
    # Metadata fields read in order (the first present one counts) and the level each value maps
    # to. A value missing from the map keeps the base level.
    fields: tuple[str, ...] = ()
    by_value: Mapping[str, Level] = field(default_factory=dict)


_AGENT_STATES: Mapping[str, Level] = {
    "failed": "failure",
    "abandoned": "warning",
    "stale": "warning",
    "outcome_unknown": "warning",
    "succeeded": "success",
    "completed": "success",
}

RULES: dict[str, Rule] = {
    # Messages
    "comment.source_ingested": Rule(routine=True),
    "comment.media_changed": Rule(routine=True),
    "owner_question.expired": Rule("warning"),
    # Replies
    "reply_draft.needs_human": Rule("warning"),
    "reply_draft.queued": Rule(routine=True),
    "reply_draft.sending": Rule(routine=True),
    "reply_draft.outcome_unknown": Rule("warning"),
    "reply_draft.sent": Rule("success", routine=True),  # reply.sent is the business event
    "reply_draft.failed": Rule("failure"),
    "reply_draft.superseded": Rule(routine=True),
    "reply_draft.blocked": Rule("warning"),
    "reply.sent": Rule("success"),
    "reply.failed": Rule("failure"),
    "reply.outcome_unknown": Rule("warning"),
    "reply.outcome_unconfirmed": Rule("warning"),
    "reply.late_confirmation": Rule("success"),
    # Approvals
    "approval.approved": Rule("success"),
    "approval.granted": Rule("success"),
    # Content
    "content.on_hold": Rule("warning"),
    "content.publishing": Rule(routine=True),
    "content.retry_scheduled": Rule("warning"),
    "content.published": Rule("success"),
    "content.failed": Rule("failure"),
    "media.rejected": Rule("failure"),
    "media.deleted": Rule(routine=True),
    # Knowledge
    "fact.verified": Rule("success"),
    "fact_candidate.accepted": Rule("success"),
    # Commands
    "command.received": Rule(routine=True),
    "command.interpreted": Rule(routine=True),
    "command.executed": Rule("success"),
    "command.failed": Rule("failure"),
    # Accounts
    "social_account.connected": Rule("success"),
    "social_account.degraded": Rule("warning"),
    "social_account.needs_reauth": Rule("warning"),
    "social_account.token_refreshed": Rule("success", routine=True),
    "account.reconnected": Rule("success"),
    "calendar.connected": Rule("success"),
    "calendar.degraded": Rule("warning"),
    "calendar.needs_reauth": Rule("warning"),
    "calendar.appointment_booked": Rule("success"),
    # Members
    "member.joined": Rule("success"),
    # System and security
    "auth.login_failed": Rule("warning"),
    "auth.login_throttled": Rule("warning"),
    "auth.password_change_failed": Rule("warning"),
    "meta.deauthorized": Rule("warning"),
    "operation.started": Rule(routine=True),
    "operation.succeeded": Rule("success", routine=True),
    "operation.failed": Rule("failure"),
    "operation.outcome_unknown": Rule("warning"),
    "operation.reconciled": Rule("success", routine=True),
    "webhook.signature_invalid": Rule("warning"),
    "security.token_key_rotated": Rule("success"),
    "security.token_key_rotation_failed": Rule("failure"),
    "security.operator_alert_fired": Rule(
        "warning", fields=("severity",), by_value={"critical": "failure"}
    ),
    "security.operator_alert_resolved": Rule("success"),
    "security.alert_delivery_failed": Rule("failure"),
    # The account agent's own bookkeeping: routine unless it records a problem.
    "agent.event_recorded": Rule(routine=True),
    "agent.session_transition": Rule(routine=True, fields=("to",), by_value=_AGENT_STATES),
    "agent.thread_transition": Rule(routine=True, fields=("to",), by_value=_AGENT_STATES),
    "agent.step_transition": Rule(routine=True, fields=("to",), by_value=_AGENT_STATES),
    "agent.action_transition": Rule(routine=True, fields=("to", "status"), by_value=_AGENT_STATES),
    "memory.written": Rule(routine=True),
}


@dataclass(frozen=True)
class Classification:
    level: Level
    routine: bool


def _field_value(rule: Rule, metadata: Mapping[str, Any]) -> str | None:
    for name in rule.fields:
        value = metadata.get(name)
        if value is not None:
            return str(value)
    return None


def classify(action: str, actor_type: str, metadata: Mapping[str, Any] | None) -> Classification:
    rule = RULES.get(action, Rule())
    level: Level = rule.level
    if rule.fields:
        value = _field_value(rule, metadata or {})
        if value is not None and value in rule.by_value:
            level = rule.by_value[value]
    routine = rule.routine and actor_type != "user" and level not in _PROBLEM
    return Classification(level, routine)


# --- SQL -----------------------------------------------------------------------------------


def _field_expr(rule: Rule) -> ColumnElement[Any]:
    columns = [AuditLog.metadata_[name].astext for name in rule.fields]
    return columns[0] if len(columns) == 1 else func.coalesce(*columns)


def _rule_has_level(action: str, rule: Rule, wanted: frozenset[str]) -> ColumnElement[bool]:
    """``action = :a AND <the row's level is one of wanted>`` for a metadata-dependent rule."""
    value = _field_expr(rule)
    hits = [v for v, lvl in rule.by_value.items() if lvl in wanted]
    clauses: list[ColumnElement[bool]] = []
    if hits:
        clauses.append(value.in_(hits))
    if rule.level in wanted:
        clauses.append(or_(value.is_(None), value.not_in(list(rule.by_value))))
    if not clauses:
        return false()
    return and_(AuditLog.action == action, or_(*clauses))


def level_clause(levels: set[str] | frozenset[str]) -> ColumnElement[bool]:
    """Rows whose level is one of ``levels``."""
    wanted = frozenset(levels)
    simple = [a for a, r in RULES.items() if not r.fields and r.level in wanted]
    clauses: list[ColumnElement[bool]] = []
    if simple:
        clauses.append(AuditLog.action.in_(simple))
    clauses.extend(_rule_has_level(a, r, wanted) for a, r in RULES.items() if r.fields)
    if "info" in wanted:
        clauses.append(AuditLog.action.not_in(list(RULES)))  # unknown actions read as info
    return or_(*clauses) if clauses else false()


def routine_clause() -> ColumnElement[bool]:
    """Rows that are routine detail (the complement is what "key activity" shows)."""
    clauses: list[ColumnElement[bool]] = []
    simple = [a for a, r in RULES.items() if r.routine and not r.fields]
    if simple:
        clauses.append(AuditLog.action.in_(simple))
    for action, rule in RULES.items():
        if rule.routine and rule.fields:
            clauses.append(_rule_has_level(action, rule, frozenset({"info", "success"})))
    return and_(AuditLog.actor_type != "user", or_(*clauses))


def not_routine_clause() -> ColumnElement[bool]:
    return not_(routine_clause())
