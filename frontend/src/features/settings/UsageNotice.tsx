import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AlertIcon, CriticalIcon } from "@/components/icons";
import { FOCUS } from "@/features/home/DashboardPanel";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useReplyUsage } from "./hooks";

/**
 * A small notice on Today when the AI reply allowance is at 80% or more, and a clear one when
 * drafting is paused. Silent while usage is normal, for staff, and while loading or on error:
 * it must never get in the way of the page.
 */
export function UsageNotice() {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const usage = useReplyUsage().data;
  if (!usage || usage.state === "normal") return null;

  const paused = usage.state === "paused";
  const number = new Intl.NumberFormat(i18n.language);
  return (
    <div
      role={paused ? "alert" : "status"}
      data-testid="usage-notice"
      data-state={usage.state}
      className={`flex flex-wrap items-center gap-x-4 gap-y-3 rounded-2xl border px-4 py-3 sm:px-5 ${
        paused ? "border-danger/30 bg-danger-subtle" : "border-attention/30 bg-attention-subtle"
      }`}
    >
      <span
        aria-hidden="true"
        className={`flex size-8 shrink-0 items-center justify-center rounded-lg text-base text-on-action ${paused ? "bg-danger" : "bg-attention"}`}
      >
        {paused ? <CriticalIcon /> : <AlertIcon />}
      </span>
      <div className="min-w-0 flex-1 basis-64">
        <p className="font-medium text-primary">{t(`usage.state.${usage.state}`)}</p>
        <p className="text-metadata text-secondary tabular-nums">
          {t("usage.used", { used: number.format(usage.used), quota: number.format(usage.quota) })}
        </p>
      </div>
      <Link
        to={`/w/${workspace.id}/more/settings#usage`}
        className={`inline-flex min-h-10 items-center rounded-control border border-border bg-surface px-4 text-body font-semibold text-primary hover:bg-surface-subtle ${FOCUS}`}
      >
        {t("usage.details")}
      </Link>
    </div>
  );
}
