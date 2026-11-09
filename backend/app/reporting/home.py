"""Exact current attention counts, independent of capped list previews."""

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, aliased

from app.agent.models import AgentAction
from app.comments.models import PublicComment, PublicCommentAction
from app.content.models import ContentItem
from app.core.context import WorkspaceContext
from app.identity.permissions import has_permission
from app.integrations.instagram.models import SocialAccount
from app.operations.models import Operation


def attention_counts(db: Session, ctx: WorkspaceContext) -> dict[str, int | None]:
    drafts = None
    if has_permission(ctx.role, "content.approve"):
        drafts = (
            db.scalar(
                select(func.count())
                .select_from(ContentItem)
                .where(
                    ContentItem.workspace_id == ctx.workspace_id,
                    ContentItem.status.in_(("draft", "pending_approval")),
                )
            )
            or 0
        )

    reply = aliased(PublicComment)
    received_reply = exists().where(
        reply.workspace_id == PublicComment.workspace_id,
        reply.social_account_id == PublicComment.social_account_id,
        reply.thread_id == PublicComment.thread_id,
        reply.parent_id == PublicComment.id,
        reply.is_owner.is_(True),
        reply.state == "visible",
    )
    # An accepted/queued/unknown effect is not delivery evidence. Only a succeeded
    # ledger operation or a received owner reply makes a comment answered.
    manual_reply = exists().where(
        Operation.workspace_id == PublicComment.workspace_id,
        Operation.social_account_id == PublicComment.social_account_id,
        Operation.subject_type == "public_comment",
        Operation.subject_id == PublicComment.id,
        Operation.operation_type == "comment_reply",
        Operation.status == "succeeded",
    )
    agent_reply = exists(
        select(PublicCommentAction.id)
        .join(
            AgentAction,
            AgentAction.id == PublicCommentAction.agent_action_id,
        )
        .join(Operation, Operation.id == AgentAction.operation_id)
        .where(
            PublicCommentAction.workspace_id == PublicComment.workspace_id,
            PublicCommentAction.social_account_id == PublicComment.social_account_id,
            PublicCommentAction.comment_id == PublicComment.id,
            PublicCommentAction.effect == "reply",
            AgentAction.workspace_id == PublicComment.workspace_id,
            AgentAction.social_account_id == PublicComment.social_account_id,
            Operation.workspace_id == PublicComment.workspace_id,
            Operation.social_account_id == PublicComment.social_account_id,
            Operation.operation_type == "comment_reply",
            Operation.status == "succeeded",
        )
    )
    comments = (
        db.scalar(
            select(func.count())
            .select_from(PublicComment)
            .join(
                SocialAccount,
                SocialAccount.id == PublicComment.social_account_id,
            )
            .where(
                PublicComment.workspace_id == ctx.workspace_id,
                SocialAccount.workspace_id == ctx.workspace_id,
                SocialAccount.status != "disconnected",
                PublicComment.is_owner.is_(False),
                PublicComment.state == "visible",
                ~received_reply,
                ~manual_reply,
                ~agent_reply,
            )
        )
        or 0
    )
    return {"drafts": drafts, "unanswered_comments": comments}
