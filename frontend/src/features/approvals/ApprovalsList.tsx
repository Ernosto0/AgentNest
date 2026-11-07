import { useSearchParams } from "react-router-dom";
import { ApprovalSummary } from "./ApprovalSummary";
import { useTranslation } from "react-i18next";
import type { Approval } from "@/api/types";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { PageHeader } from "@/components/Layout";
import { ChevronRightIcon } from "@/components/icons";
import { useApprovals } from "@/features/commands/hooks";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { ApprovalDetailSheet } from "./ApprovalDetailSheet";

type Tab = "pending" | "history";

function Row({ approval, onOpen }: { approval: Approval; onOpen: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        data-approval-id={approval.id}
        className="group flex min-h-16 w-full items-center justify-between gap-4 bg-surface p-4 sm:p-5 text-left transition-colors hover:bg-surface-subtle focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus"
      >
        <ApprovalSummary approval={approval} />
        <div className="flex shrink-0 items-center pl-2 text-secondary/50 group-hover:translate-x-0.5 group-hover:text-primary transition-transform">
          <ChevronRightIcon className="text-xl" />
        </div>
      </button>
    </li>
  );
}

/** Everything that needs a decision, and what was decided. Generic: new actions need no screen. */
export function ApprovalsList() {
  const { t } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const approvals = useApprovals(workspace.id);
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "history" ? "history" : "pending";
  const openId = params.get("approval");
  const setTab = (next: Tab) => { const query = new URLSearchParams(params); query.set("tab", next); query.delete("approval"); setParams(query); };
  const setOpenId = (id: string | null) => { const query = new URLSearchParams(params); if (id) query.set("approval", id); else query.delete("approval"); setParams(query); };

  const all = approvals.data ?? [];
  const shown = all.filter((a) => (tab === "pending" ? a.status === "pending" : a.status !== "pending"));
  const open = all.find((a) => a.id === openId) ?? null;

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader title={t("approvals.title")} description={t("approvals.intro")} />

      <div
        role="tablist"
        aria-label={t("approvals.tabs.label")}
        className="flex gap-1 border-b border-border"
      >
        {(["pending", "history"] as const).map((name) => (
          <button
            key={name}
            role="tab"
            type="button"
            aria-selected={tab === name}
            onClick={() => setTab(name)}
            className={`min-h-11 border-b-2 px-4 text-body font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${
              tab === name
                ? "border-action text-action"
                : "border-transparent text-secondary hover:bg-surface-subtle hover:text-primary"
            }`}
          >
            {t(`approvals.tabs.${name}`)}
          </button>
        ))}
      </div>

      {approvals.isError ? <ErrorMessage error={approvals.error} /> : null}
      {approvals.isPending ? <p className="text-sm text-secondary">{t("common.loading")}</p> : null}
      {approvals.data && shown.length === 0 ? (
        <EmptyState
          title={tab === "pending" ? t("approvals.empty") : t("approvals.emptyHistory")}
          description={tab === "pending" ? t("approvals.emptyHint") : undefined}
        />
      ) : null}
      {shown.length > 0 ? (
        <ul className="overflow-hidden rounded-panel border border-border bg-surface divide-y divide-border" aria-label={t("approvals.tabs.label")}>
          {shown.map((approval) => (
            <Row key={approval.id} approval={approval} onOpen={() => setOpenId(approval.id)} />
          ))}
        </ul>
      ) : null}
      {open ? <ApprovalDetailSheet approval={open} onClose={() => setOpenId(null)} /> : null}
    </div>
  );
}
