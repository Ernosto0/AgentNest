import { useTranslation } from "react-i18next";
import { ErrorMessage } from "@/components/ErrorMessage";
import { Skeleton } from "@/components/Feedback";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { useReplyUsage } from "./hooks";
import { SettingRow, SettingsPanel, SettingsSection } from "./SettingsParts";

const STATE_TONE = {
  normal: "text-secondary",
  warning: "text-attention",
  grace: "text-attention",
  paused: "text-danger",
} as const;

const BAR_TONE = {
  normal: "bg-action",
  warning: "bg-attention",
  grace: "bg-attention",
  paused: "bg-danger",
} as const;

/**
 * Settings, "Plan and AI replies": the plan, how many AI reply drafts this period has used, when
 * the period ends and what the state means for the owner. Owners and managers only; nobody else
 * sees the section (or its navigation entry) and nothing is fetched for them.
 */
export function Usage() {
  const { t, i18n } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const usage = useReplyUsage();
  if (role !== "owner" && role !== "manager") return null;

  const number = new Intl.NumberFormat(i18n.language);
  const data = usage.data;
  const percent = data ? Math.min(100, Math.round((data.used / data.quota) * 100)) : 0;
  const date = (iso: string) =>
    new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeZone: workspace.timezone }).format(new Date(iso));

  return (
    <SettingsSection id="usage" title={t("usage.title")} description={t("usage.description")}>
      {usage.isPending ? <Skeleton label={t("common.loading")} rows={3} /> : null}
      {usage.isError ? <ErrorMessage error={usage.error} /> : null}
      {data ? (
        <SettingsPanel data-testid="usage-meter" data-state={data.state}>
          <SettingRow
            className="border-t-0"
            label={t("usage.plan")}
            description={data.quota_override !== null ? t("usage.customQuota") : undefined}
          >
            <p className="text-body font-semibold text-primary">
              {t(`usage.plans.${data.plan}`)}
              <span className="ml-2 rounded-full bg-surface-subtle px-2.5 py-0.5 text-xs font-bold text-secondary">{t(`usage.status.${data.status}`)}</span>
            </p>
          </SettingRow>
          <div className="flex min-w-0 flex-col gap-3 border-t border-border/70 px-4 py-4 sm:px-5">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <p className="text-body font-semibold text-primary">{t("usage.repliesThisPeriod")}</p>
              <p className="text-body font-semibold text-primary tabular-nums">
                {t("usage.used", { used: number.format(data.used), quota: number.format(data.quota) })}
              </p>
            </div>
            <div
              role="progressbar"
              aria-label={t("usage.repliesThisPeriod")}
              aria-valuenow={Math.min(data.used, data.quota)}
              aria-valuemin={0}
              aria-valuemax={data.quota}
              className="h-2 overflow-hidden rounded-full bg-surface-subtle"
            >
              <div className={`h-full rounded-full transition-[width] duration-normal ${BAR_TONE[data.state]}`} style={{ width: `${percent}%` }} />
            </div>
            <p role={data.state === "paused" ? "alert" : "status"} data-testid="usage-state" className={`text-metadata font-medium ${STATE_TONE[data.state]}`}>
              {t(`usage.state.${data.state}`)}
            </p>
          </div>
          <SettingRow label={t("usage.periodEnds")}>
            <p className="text-body text-primary">{date(data.period_end)}</p>
          </SettingRow>
          <p className="border-t border-border/70 px-4 py-3 text-metadata text-secondary sm:px-5">{t("usage.rule")}</p>
        </SettingsPanel>
      ) : null}
    </SettingsSection>
  );
}
