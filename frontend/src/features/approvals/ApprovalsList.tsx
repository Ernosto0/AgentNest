import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Approval } from "@/api/types";
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

  const isPending = approval.status === "pending";
  const statusTone = isPending
    ? "text-attention bg-attention-subtle border border-attention/30"
    : approval.status === "approved"
      ? "text-success bg-success-subtle border border-success/30"
      : approval.status === "rejected"
        ? "text-danger bg-danger-subtle border border-danger/30"
        : "text-secondary bg-surface-subtle border border-border";

  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        data-approval-id={approval.id}
        className="group flex min-h-14 w-full items-center justify-between gap-4 rounded-2xl border border-border/80 bg-surface p-4 text-left shadow-2xs transition-all duration-150 hover:border-action/40 hover:bg-surface hover:shadow-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-heading font-semibold text-primary">
              {t(`approvals.action.${actionKey(approval.action)}`)}
            </span>
            <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold shadow-2xs ${statusTone}`}>
              {t(`approvals.status.${approval.status}`)}
            </span>
            {approval.is_simulated ? <SimulatedBadge /> : null}
          </div>
          <div className="text-sm break-words text-secondary">
            {[name, detail].filter(Boolean).join(" → ")}
          </div>
        </div>
        <div className="flex shrink-0 items-center pl-2 text-secondary group-hover:translate-x-0.5 group-hover:text-primary transition-transform">
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
  const [tab, setTab] = useState<Tab>("pending");
  const [openId, setOpenId] = useState<string | null>(null);

  const all = approvals.data ?? [];
  const shown = all.filter((a) => (tab === "pending" ? a.status === "pending" : a.status !== "pending"));
  const open = all.find((a) => a.id === openId) ?? null;

  return (
    <div className="flex flex-col gap-6 max-w-4xl">
      <div>
        <h1 className="type-page text-primary">{t("approvals.title")}</h1>
        <p className="mt-1 text-sm text-secondary">{t("approvals.intro")}</p>
      </div>

      <div
        role="tablist"
        aria-label={t("approvals.tabs.label")}
        className="flex gap-2 p-1.5 bg-surface-subtle/80 border border-border/80 rounded-xl shadow-2xs w-fit"
      >
        {(["pending", "history"] as const).map((name) => (
          <button
            key={name}
            role="tab"
            type="button"
            aria-selected={tab === name}
            onClick={() => setTab(name)}
            className={`min-h-10 rounded-lg px-4 text-sm font-semibold transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${
              tab === name
                ? "bg-action text-on-action shadow-xs font-bold"
                : "text-secondary hover:bg-surface hover:text-primary"
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
        <ul className="flex flex-col gap-3" aria-label={t("approvals.tabs.label")}>
          {shown.map((approval) => (
            <Row key={approval.id} approval={approval} onOpen={() => setOpenId(approval.id)} />
          ))}
        </ul>
      ) : null}
      {open ? <ApprovalDetailSheet approval={open} onClose={() => setOpenId(null)} /> : null}
    </div>
  );
}
