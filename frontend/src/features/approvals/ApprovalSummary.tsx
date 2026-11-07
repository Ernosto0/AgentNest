import { useTranslation } from "react-i18next";
import type { Approval } from "@/api/types";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { actionKey } from "./format";

/** Shared decision wording. Approval is a decision, while delivery remains in the action record. */
export function ApprovalSummary({ approval }: { approval: Approval }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const summary = approval.summary as { label?: string; title?: string; new_formatted?: string; scheduled_at?: string; when?: string | null };
  const detail = summary.new_formatted ?? (summary.scheduled_at ? new Date(summary.scheduled_at).toLocaleString(i18n.language, { dateStyle: "short", timeStyle: "short", timeZone: workspace.timezone }) : summary.when);
  return <span className="flex min-w-0 flex-col gap-2 text-left">
    <span className="flex flex-wrap items-center gap-2"><strong className="font-semibold">{t(`approvals.action.${actionKey(approval.action)}`)}</strong><span className={`rounded-control px-2 py-1 text-metadata ${approval.status === "pending" ? "bg-attention-subtle text-attention" : "bg-surface-subtle text-secondary"}`}>{t(`approvals.status.${approval.status}`)}</span>{approval.is_simulated ? <SimulatedBadge /> : null}</span>
    <span className="break-words text-body text-secondary">{[summary.label ?? summary.title, detail].filter(Boolean).join(" → ")}</span>
  </span>;
}
