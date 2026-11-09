import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { DailyReport, ReportMetric } from "@/api/types";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { formatValue } from "@/features/reports/format";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { FOCUS, PanelLink } from "./DashboardPanel";

/** Period metrics for today; snapshot counts ("now") live in the attention panel instead. */
const PULSE_KEYS = ["inbound_messages", "replies_sent", "content_published", "integration_errors"] as const;
/** For these a rise is bad news. */
const LOWER_IS_BETTER = new Set<string>(["integration_errors"]);

const LG_COLS: Record<number, string> = {
  1: "lg:grid-cols-1",
  2: "lg:grid-cols-2",
  3: "lg:grid-cols-3",
  4: "lg:grid-cols-4",
};

type Trend = { text: string; tone: "up-good" | "up-bad" | "down-good" | "neutral"; arrow: "▲" | "▼" | "" };

/**
 * Today at a glance (user-journeys §1): the day's own numbers, each a link to its evidence.
 * Missing values stay "unavailable"; only real zeros render as 0.
 */
export function TodayPulse({
  report,
  yesterday,
  pending,
  failed,
}: {
  report: DailyReport | undefined;
  yesterday: DailyReport | undefined;
  pending: boolean;
  failed: boolean;
}) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const metrics = new Map<string, ReportMetric>((report?.metrics ?? []).map((m) => [m.key, m]));
  const previous = new Map<string, ReportMetric>((yesterday?.metrics ?? []).map((m) => [m.key, m]));
  const shown = PULSE_KEYS.map((key) => metrics.get(key)).filter((m): m is ReportMetric => m !== undefined);
  const quiet = report !== undefined && report.summary.empty;
  const asOf = report
    ? new Date(report.period_end).toLocaleTimeString(i18n.language, {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: workspace.timezone,
      })
    : "";

  const trendFor = (metric: ReportMetric): Trend | null => {
    const before = previous.get(metric.key)?.value;
    if (metric.value === null || before === undefined || before === null) return null;
    const vs = t("home.numbers.vsYesterday");
    if (metric.value === before) return { text: `${t("home.numbers.same")} ${vs}`, tone: "neutral", arrow: "" };
    // Growth from zero has no meaningful percentage: say what yesterday was instead.
    if (before === 0) {
      return { text: t("home.numbers.yesterdayValue", { value: formatValue(0, i18n.language) }), tone: "neutral", arrow: "" };
    }
    const diff = metric.value - before;
    const pct = Math.round(Math.abs(diff / before) * 100);
    const worse = LOWER_IS_BETTER.has(metric.key);
    if (diff > 0) return { text: `${t("home.numbers.more", { pct })} ${vs}`, tone: worse ? "up-bad" : "up-good", arrow: "▲" };
    return { text: `${t("home.numbers.less", { pct })} ${vs}`, tone: worse ? "down-good" : "neutral", arrow: "▼" };
  };

  const toneClass = {
    "up-good": "text-success",
    "down-good": "text-success",
    "up-bad": "text-danger",
    neutral: "text-secondary",
  } as const;

  return (
    <section
      aria-labelledby="home-numbers-title"
      data-testid="home-numbers"
      className="min-w-0 overflow-hidden rounded-2xl border border-border bg-surface"
    >
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-5 pt-3 sm:px-6">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 id="home-numbers-title" className="font-heading text-[1.0625rem] font-semibold tracking-tight text-primary">
            {t("home.numbers.title")}
          </h2>
          {report ? (
            <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-metadata text-secondary">
              {report.is_partial ? (
                <>
                  <span>{t("home.numbers.asOf", { time: asOf })}</span>
                  <span aria-hidden="true" className="text-secondary/50">·</span>
                  <span>{t("home.numbers.partialNote")}</span>
                </>
              ) : null}
              {report.has_simulated_data ? <SimulatedBadge compact /> : null}
            </span>
          ) : null}
        </div>
        <PanelLink to={`/w/${workspace.id}/more/reports`}>{t("home.numbers.openReport")}</PanelLink>
      </div>

      {quiet ? (
        <p data-testid="numbers-empty" className="px-5 pb-1 text-metadata text-secondary sm:px-6">
          {t("home.numbers.empty")}
        </p>
      ) : null}

      {pending ? (
        <div role="status" className="grid grid-cols-2 gap-px border-t border-border bg-border lg:grid-cols-4">
          <span className="sr-only">{t("common.loading")}</span>
          {PULSE_KEYS.map((key) => (
            <div key={key} aria-hidden="true" className="flex flex-col gap-2.5 bg-surface px-5 py-4 sm:px-6">
              <div className="h-2.5 w-20 rounded-full bg-surface-subtle motion-safe:animate-pulse" />
              <div className="h-7 w-12 rounded-lg bg-surface-subtle motion-safe:animate-pulse" />
            </div>
          ))}
        </div>
      ) : failed && !report ? (
        <p role="status" className="border-t border-border px-5 py-4 text-body text-secondary sm:px-6">
          {t("home.loadFailed")}
        </p>
      ) : shown.length > 0 ? (
        <dl className={`mt-3 grid grid-cols-2 gap-px border-t border-border bg-border ${LG_COLS[shown.length] ?? "lg:grid-cols-4"}`}>
          {shown.map((metric, index) => {
            const label = t(`reports.metrics.${metric.key}`);
            const value = metric.value === null ? t("core.unavailable") : formatValue(metric.value, i18n.language);
            const trend = trendFor(metric);
            const alarming = LOWER_IS_BETTER.has(metric.key) && (metric.value ?? 0) > 0;
            const lastOdd = shown.length % 2 === 1 && index === shown.length - 1;
            return (
              <div
                key={metric.key}
                data-testid={`number-${metric.key}`}
                className={`group relative flex min-w-0 flex-col gap-1 px-5 py-4 transition-colors sm:px-6 ${
                  alarming ? "bg-danger-subtle" : "bg-surface"
                } ${metric.link.route ? "hover:bg-surface-subtle" : ""} ${lastOdd ? "col-span-2 lg:col-span-1" : ""}`}
              >
                <dt className={`text-metadata font-medium ${alarming ? "text-danger" : "text-secondary"}`}>{label}</dt>
                <dd className="font-heading text-[1.75rem] leading-9 font-bold tracking-tight text-primary tabular-nums">
                  {metric.link.route ? (
                    <Link
                      to={metric.link.route}
                      aria-label={`${label}: ${value}`}
                      className={`rounded-control after:absolute after:inset-0 after:content-[''] ${FOCUS}`}
                    >
                      {value}
                    </Link>
                  ) : (
                    value
                  )}
                </dd>
                {trend ? (
                  <dd className={`text-xs font-medium ${toneClass[trend.tone]}`}>
                    {trend.arrow ? <span aria-hidden="true" className="mr-1 text-[0.625rem]">{trend.arrow}</span> : null}
                    {trend.text}
                  </dd>
                ) : null}
              </div>
            );
          })}
        </dl>
      ) : (
        <div className="h-3" aria-hidden="true" />
      )}
    </section>
  );
}
