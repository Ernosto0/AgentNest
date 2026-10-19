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
  if (!draft.data) return <p className="text-sm text-slate-600">{t("common.loading")}</p>;
  return (
    <div className="flex flex-col gap-2 rounded-lg bg-slate-50 p-3" data-testid="reply-approval-body">
      <DraftText draft={draft.data} />
      <ReasonChips reasons={draft.data.decision_reasons} />
      <Link
        to={`/w/${workspace.id}/inbox/${draft.data.conversation_id}`}
        className="text-sm font-medium text-indigo-800 underline"
      >
        {t("convo.openConversation")}
      </Link>
    </div>
  );
}
