import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ErrorMessage } from "@/components/ErrorMessage";
import { useApproval } from "@/features/inbox/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { ApprovalDetailSheet } from "./ApprovalDetailSheet";
import { ApprovalSummary } from "./ApprovalSummary";

export function LinkedApproval({ id }: { id: string }) {
  const { workspace } = useCurrentWorkspace();
  const { t } = useTranslation();
  const approval = useApproval(workspace.id, id);
  const [open, setOpen] = useState(false);
  if (approval.error) return <ErrorMessage error={approval.error} />;
  if (!approval.data) return <span>{t("common.loading")}</span>;
  return <>
    <button type="button" className="min-h-11 rounded-control p-2 hover:bg-surface focus-visible:outline-2 focus-visible:outline-focus" onClick={() => setOpen(true)}><ApprovalSummary approval={approval.data} /></button>
    {open ? <ApprovalDetailSheet approval={approval.data} onClose={() => setOpen(false)} /> : null}
  </>;
}
