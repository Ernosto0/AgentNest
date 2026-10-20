import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Approval } from "@/api/types";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ChevronRightIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useApprovals } from "@/features/commands/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { ApprovalDetailSheet } from "./ApprovalDetailSheet";
import { actionKey } from "./format";

type Tab = "pending" | "history";

function Row({ approval, onOpen }: { approval: Approval; onOpen: () => void }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const summary = approval.summary as {
    label?: string;
    title?: string;
    new_formatted?: string;
    scheduled_at?: string;
    when?: string | null;
  };
  // A fact change shows the new value; a content approval shows its title and the time.
  const name = summary.label ?? summary.title;
  const detail =
    summary.new_formatted ??
    (summary.scheduled_at
      ? new Date(summary.scheduled_at).toLocaleString(i18n.language, {
          dateStyle: "short",
          timeStyle: "short",
          timeZone: workspace.timezone,
        })
      : summary.when);
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        data-approval-id={approval.id}
        className="flex min-h-14 w-full items-center justify-between gap-3 rounded-xl bg-white px-4 py-3 text-left ring-1 ring-slate-200 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
      >
        <span className="min-w-0">
          <span className="block font-medium">{t(`approvals.action.${actionKey(approval.action)}`)}</span>
          <span className="block text-sm break-words text-slate-600">
            {[name, detail].filter(Boolean).join(" → ")}
          </span>
          <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-600">
            <span>{t(`approvals.status.${approval.status}`)}</span>
            {approval.is_simulated ? <SimulatedBadge /> : null}
          </span>
        </span>
        <ChevronRightIcon className="shrink-0 text-xl text-slate-400" />
      </button>
    </li>
  );
}

/** Everything that needs a decision, and what was decided. Generic: new actions need no screen. */
export function ApprovalsList() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const approvals = useApprovals(workspace.id);
  const [tab, setTab] = useState<Tab>("pending");
  const [openId, setOpenId] = useState<string | null>(null);

  const all = approvals.data ?? [];
  const shown = all.filter((a) => (tab === "pending" ? a.status === "pending" : a.status !== "pending"));
  const open = all.find((a) => a.id === openId) ?? null;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold">{t("approvals.title")}</h1>
        <p className="mt-1 text-slate-600">{t("approvals.intro")}</p>
      </div>

      <div role="tablist" aria-label={t("approvals.tabs.label")} className="flex gap-2">
        {(["pending", "history"] as const).map((name) => (
          <button
            key={name}
            role="tab"
            type="button"
            aria-selected={tab === name}
            onClick={() => setTab(name)}
            className={`min-h-11 rounded-lg px-4 font-medium focus-visible:outline-2 focus-visible:outline-indigo-600 ${
              tab === name ? "bg-indigo-700 text-white" : "bg-white text-slate-800 ring-1 ring-slate-300"
            }`}
          >
            {t(`approvals.tabs.${name}`)}
          </button>
        ))}
      </div>

      {approvals.isError ? <ErrorMessage error={approvals.error} /> : null}
      {approvals.isPending ? <p>{t("common.loading")}</p> : null}
      {approvals.data && shown.length === 0 ? (
        <EmptyState
          title={tab === "pending" ? t("approvals.empty") : t("approvals.emptyHistory")}
          description={tab === "pending" ? t("approvals.emptyHint") : undefined}
        />
      ) : null}
      {shown.length > 0 ? (
        <Card className="p-0">
          <ul className="flex flex-col gap-3 p-3" aria-label={t("approvals.tabs.label")}>
            {shown.map((approval) => (
              <Row key={approval.id} approval={approval} onOpen={() => setOpenId(approval.id)} />
            ))}
          </ul>
        </Card>
      ) : null}
      {open ? <ApprovalDetailSheet approval={open} onClose={() => setOpenId(null)} /> : null}
    </div>
  );
}
