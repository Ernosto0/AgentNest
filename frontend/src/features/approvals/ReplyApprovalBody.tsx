import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { Approval } from "@/api/types";
import { DraftText, ReasonChips } from "@/features/inbox/DraftParts";
import { useReplyDraft } from "@/features/inbox/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";

/** The reply an authorization covers, shown with its sources (the approval carries only ids). */
export function ReplyApprovalBody({ approval }: { approval: Approval }) {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const draft = useReplyDraft(workspace.id, approval.subject.id);

  if (!draft.data) return <p className="text-sm text-secondary">{t("common.loading")}</p>;

  return (
    <div
      className="flex flex-col gap-3.5 rounded-panel border border-border bg-surface p-4 shadow-xs"
      data-testid="reply-approval-body"
    >
      <div className="rounded-control border border-border bg-surface-subtle p-3.5 shadow-2xs">
        <DraftText draft={draft.data} />
      </div>
      <ReasonChips reasons={draft.data.decision_reasons} />
      <div>
        <Link
          to={`/w/${workspace.id}/inbox/${draft.data.conversation_id}`}
          className="inline-flex min-h-11 items-center font-medium text-action underline underline-offset-2 hover:text-action-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          {t("convo.openConversation")}
        </Link>
      </div>
    </div>
  );
}
