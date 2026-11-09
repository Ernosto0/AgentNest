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

const SM_COLS: Record<number, string> = {
  1: "sm:grid-cols-1",
  2: "sm:grid-cols-2",
  3: "sm:grid-cols-3",
  4: "sm:grid-cols-4",
};

type Trend = { text: string; tone: "good" | "bad" | "neutral"; arrow: "▲" | "▼" | "" };

/**
 * Today at a glance (user-journeys §1): the day's own numbers in one compact row, each a link to
 * its evidence. A comparison appears only when it says something: unchanged values stay quiet,
 * and growth from zero names yesterday's value instead of a percentage. Missing values stay
 * "unavailable"; real zeros are shown, but muted.
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
    if (metric.value === null || before === undefined || before === null || metric.value === before) return null;
    if (before === 0) {
      return { text: t("home.numbers.yesterdayValue", { value: formatValue(0, i18n.language) }), tone: "neutral", arrow: "" };
    }
    const diff = metric.value - before;
    const pct = Math.round(Math.abs(diff / before) * 100);
    const worse = LOWER_IS_BETTER.has(metric.key);
    const vs = t("home.numbers.vsYesterday");
    if (diff > 0) return { text: `${t("home.numbers.more", { pct })} ${vs}`, tone: worse ? "bad" : "good", arrow: "▲" };
    return { text: `${t("home.numbers.less", { pct })} ${vs}`, tone: worse ? "good" : "neutral", arrow: "▼" };
  };
  const trends = new Map(shown.map((m) => [m.key, trendFor(m)]));
  const anyTrend = [...trends.values()].some(Boolean);
  const toneClass = { good: "text-success", bad: "text-danger", neutral: "text-secondary" } as const;

  return (
    <section
      aria-labelledby="home-numbers-title"
      data-testid="home-numbers"
      className="flex min-w-0 flex-col overflow-hidden rounded-2xl border border-border bg-surface lg:flex-row"
    >
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-x-4 gap-y-1 px-5 pt-3 pb-2.5 lg:w-64 lg:shrink-0 lg:flex-col lg:flex-nowrap lg:justify-center lg:gap-1 lg:border-r lg:border-border lg:py-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <h2 id="home-numbers-title" className="font-heading text-base font-semibold tracking-tight text-primary">
              {t("home.numbers.title")}
            </h2>
            {report?.is_partial ? <span className="text-xs text-secondary">{t("home.numbers.asOf", { time: asOf })}</span> : null}
          </div>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
            {quiet ? (
              <p data-testid="numbers-empty" className="text-xs text-secondary">
                {t("home.numbers.empty")}
              </p>
            ) : report?.is_partial && anyTrend ? (
              <p className="text-xs text-secondary">{t("home.numbers.partialNote")}</p>
            ) : null}
            {report?.has_simulated_data ? <SimulatedBadge compact /> : null}
          </div>
        </div>
        <PanelLink to={`/w/${workspace.id}/more/reports`} className="-my-2.5 lg:my-0 lg:-mb-2.5">
          {t("home.numbers.openReport")}
        </PanelLink>
      </div>

      {pending ? (
        <div role="status" className="grid flex-1 grid-cols-2 gap-px border-t border-border bg-border sm:grid-cols-4 lg:border-t-0">
          <span className="sr-only">{t("common.loading")}</span>
          {PULSE_KEYS.map((key) => (
            <div key={key} aria-hidden="true" className="flex flex-col gap-2 bg-surface px-5 py-3.5">
              <div className="h-2.5 w-20 rounded-full bg-surface-subtle motion-safe:animate-pulse" />
              <div className="h-6 w-10 rounded-md bg-surface-subtle motion-safe:animate-pulse" />
            </div>
          ))}
        </div>
      ) : failed && !report ? (
        <p role="status" className="flex flex-1 items-center border-t border-border px-5 py-3.5 text-body text-secondary lg:border-t-0">
          {t("home.loadFailed")}
        </p>
      ) : shown.length > 0 ? (
        <dl className={`grid flex-1 grid-cols-2 gap-px border-t border-border bg-border lg:border-t-0 ${SM_COLS[shown.length] ?? "sm:grid-cols-4"}`}>
          {shown.map((metric, index) => {
            const label = t(`reports.metrics.${metric.key}`);
            const value = metric.value === null ? t("core.unavailable") : formatValue(metric.value, i18n.language);
            const trend = trends.get(metric.key) ?? null;
            const alarming = LOWER_IS_BETTER.has(metric.key) && (metric.value ?? 0) > 0;
            const muted = metric.value === 0 || metric.value === null;
            const lastOdd = shown.length % 2 === 1 && index === shown.length - 1;
            return (
              <div
                key={metric.key}
                data-testid={`number-${metric.key}`}
                className={`group relative flex min-w-0 flex-col justify-center px-5 py-3 transition-colors ${
                  alarming ? "bg-danger-subtle" : "bg-surface"
                } ${metric.link.route ? "hover:bg-surface-subtle/70" : ""} ${lastOdd ? "col-span-2 sm:col-span-1" : ""}`}
              >
                <dt className={`truncate text-xs font-medium ${alarming ? "text-danger" : "text-secondary"}`}>{label}</dt>
                <dd
                  className={`font-heading text-[1.625rem] leading-8 font-bold tracking-tight tabular-nums ${
                    muted ? "text-secondary/70" : "text-primary"
                  }`}
                >
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
                  <dd className={`truncate text-[0.6875rem] font-medium ${toneClass[trend.tone]}`}>
                    {trend.arrow ? <span aria-hidden="true" className="mr-1 text-[0.5625rem]">{trend.arrow}</span> : null}
                    {trend.text}
                  </dd>
                ) : null}
              </div>
            );
          })}
        </dl>
      ) : null}
    </section>
  );
}
