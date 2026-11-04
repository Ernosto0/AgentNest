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
        className="group flex min-h-16 w-full items-center justify-between gap-4 rounded-2xl border border-border/80 bg-surface p-4 sm:p-5 text-left shadow-card-modern transition-all duration-150 hover:border-action/40 hover:shadow-card-hover hover:translate-y-[-1px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="font-heading font-bold text-primary text-base">
              {t(`approvals.action.${actionKey(approval.action)}`)}
            </span>
            <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold shadow-2xs ${statusTone}`}>
              {t(`approvals.status.${approval.status}`)}
            </span>
            {approval.is_simulated ? <SimulatedBadge /> : null}
          </div>
          <div className="text-sm break-words text-secondary font-medium">
            {[name, detail].filter(Boolean).join(" → ")}
          </div>
        </div>
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
  const [tab, setTab] = useState<Tab>("pending");
  const [openId, setOpenId] = useState<string | null>(null);

  const all = approvals.data ?? [];
  const shown = all.filter((a) => (tab === "pending" ? a.status === "pending" : a.status !== "pending"));
  const open = all.find((a) => a.id === openId) ?? null;

  return (
    <div className="flex flex-col gap-6 max-w-4xl">
      <div className="relative overflow-hidden rounded-2xl border border-border/90 bg-gradient-to-r from-surface via-surface to-surface-subtle/50 p-6 shadow-card-modern">
        <div className="absolute top-0 right-0 h-32 w-64 bg-gradient-to-bl from-amber-500/10 via-emerald-500/5 to-transparent pointer-events-none rounded-tr-2xl" />
        <h1 className="type-page text-primary font-heading font-extrabold text-2xl sm:text-3xl tracking-tight">{t("approvals.title")}</h1>
        <p className="mt-1 text-sm text-secondary max-w-xl">{t("approvals.intro")}</p>
      </div>

      <div
        role="tablist"
        aria-label={t("approvals.tabs.label")}
        className="flex gap-1.5 p-1 bg-surface-subtle/80 border border-border/80 rounded-xl shadow-2xs w-fit"
      >
        {(["pending", "history"] as const).map((name) => (
          <button
            key={name}
            role="tab"
            type="button"
            aria-selected={tab === name}
            onClick={() => setTab(name)}
            className={`min-h-9 rounded-lg px-4 text-xs font-semibold transition-all duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${
              tab === name
                ? "bg-surface text-primary shadow-xs font-bold ring-1 ring-border/50"
                : "text-secondary hover:bg-surface/50 hover:text-primary"
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
