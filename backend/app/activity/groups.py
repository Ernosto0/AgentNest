"""Which Activity group an audit action belongs to (plan H7, observability.md section 5).

``GROUPS`` is the single list of audit actions the feed knows. A test fails when an action of
the catalog, or one written by the code, is missing here or has no ``activity.<action>`` text in
both catalogs. Dynamic names are expanded: ``reply_draft.<status>``, ``approval.<result>``,
``content.<status>`` and ``social_account.<status>``.
"""

from typing import Literal, get_args

Group = Literal[
    "messages",
    "replies",
    "approvals",
    "content",
    "knowledge",
    "commands",
    "accounts",
    "members",
    "system",
]
GROUP_NAMES: tuple[str, ...] = get_args(Group)

_BY_GROUP: dict[str, tuple[str, ...]] = {
    "messages": (
        "message.received",
        "message.native_reply_recorded",
        "conversation.takeover",
        "conversation.release",
    ),
    "replies": (
        "reply_draft.created",
        "reply_draft.edited",
        "reply_draft.pending_approval",
        "reply_draft.needs_human",
        "reply_draft.queued",
        "reply_draft.sending",
        "reply_draft.outcome_unknown",
        "reply_draft.sent",
        "reply_draft.failed",
        "reply_draft.rejected",
        "reply_draft.expired",
        "reply_draft.superseded",
        "reply_draft.cancelled",
        "reply_draft.blocked",
        "reply.sent",
        "reply.failed",
        "reply.outcome_unknown",
        "reply.outcome_unconfirmed",
        "reply.late_confirmation",
    ),
    "approvals": (
        "approval.requested",
        "approval.approved",
        "approval.granted",
        "approval.rejected",
        "approval.expired",
        "approval.cancelled",
    ),
    "content": (
        "content.created",
        "content.generated",
        "content.updated",
        "content.submitted",
        "content.scheduled",
        "content.on_hold",
        "content.cancelled",
        "content.rejected",
        "content.publishing",
        "content.retry_scheduled",
        "content.published",
        "content.failed",
        "media.uploaded",
        "media.rejected",
    ),
    "knowledge": (
        "fact.created",
        "fact.updated",
        "fact.verified",
        "fact.archived",
        "fact.restored",
        "fact_candidate.created",
        "fact_candidate.accepted",
        "fact_candidate.rejected",
        "knowledge.extraction_requested",
        "approved_answer.created",
        "approved_answer.updated",
        "approved_answer.archived",
        "policy.updated",
        "policy.reviewed",
    ),
    "commands": (
        "command.received",
        "command.interpreted",
        "command.executed",
        "command.failed",
        "command.cancelled",
        "command.expired",
    ),
    "accounts": (
        "social_account.connected",
        "social_account.degraded",
        "social_account.needs_reauth",
        "social_account.disconnected",
        "social_account.token_refreshed",
        "account.reconnected",
    ),
    "members": (
        "member.invited",
        "member.invite_revoked",
        "member.joined",
        "member.role_changed",
        "member.removed",
    ),
    "system": (
        "auth.login",
        "auth.logout",
        "auth.login_failed",
        "workspace.created",
        "workspace.updated",
        "operation.started",
        "operation.succeeded",
        "operation.failed",
        "operation.outcome_unknown",
        "operation.reconciled",
        "webhook.signature_invalid",
        "report.generated",
        "retention.cleanup_ran",
        "demo.reset",
        "demo.failure_rule_set",
    ),
}

GROUPS: dict[str, str] = {
    action: group for group, actions in _BY_GROUP.items() for action in actions
}


def group_of(action: str) -> str:
    """The group of ``action``; an action the feed does not know yet is a system entry."""
    return GROUPS.get(action, "system")


def actions_in(group: str) -> tuple[str, ...]:
    return _BY_GROUP[group]
