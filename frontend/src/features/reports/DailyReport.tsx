import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import type { ReportMetric } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { dayLabel, isLocalDay, shiftDay, todayIn } from "./dates";
import { formatValue } from "./format";
import { useDailyReport, useGenerateReport } from "./hooks";

const LINK =
  "font-semibold text-indigo-700 underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-indigo-600";

function hasValue(metric: ReportMetric): metric is ReportMetric & { value: number } {
  return typeof metric.value === "number" && metric.value !== 0;
}

/** The daily report (J5): what happened on one local day, and the records behind every number. */
export function DailyReport() {
  const { t, i18n } = useTranslation();
  const { workspace, role } = useCurrentWorkspace();
  const [params, setParams] = useSearchParams();
  const today = todayIn(workspace.timezone);
  const requested = params.get("date");
  // Nothing after today: a later date falls back to today.
  const day = isLocalDay(requested) && requested < today ? requested : today;
  const report = useDailyReport(workspace.id, day === today ? null : day);
  const generate = useGenerateReport(workspace.id);
  const canGenerate = role === "owner" || role === "manager";

  const go = (target: string) => setParams(target === today ? {} : { date: target }, { replace: true });

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold">{t("reports.title")}</h1>
        <p className="mt-1 text-slate-600">{t("reports.intro")}</p>
      </div>

      <div className="flex items-center justify-between gap-2" role="group" aria-label={t("reports.dateLabel")}>
        <Button variant="secondary" onClick={() => go(shiftDay(day, -1))} aria-label={t("reports.previousDay")}>
          ‹
        </Button>
        <div className="flex flex-col items-center text-center">
          <p className="font-semibold" data-testid="report-day">
            {dayLabel(day, i18n.language)}
          </p>
          {day !== today ? (
            <button
              type="button"
              onClick={() => go(today)}
              className="min-h-11 text-sm font-medium text-indigo-700 underline underline-offset-2"
            >
              {t("reports.backToToday")}
            </button>
          ) : (
            <p className="text-sm text-slate-600">{t("reports.today")}</p>
          )}
        </div>
        <Button
          variant="secondary"
          disabled={day >= today}
          onClick={() => go(shiftDay(day, 1))}
          aria-label={t("reports.nextDay")}
        >
          ›
        </Button>
      </div>

      {report.isError ? <ErrorMessage error={report.error} /> : null}
      {report.isPending ? <p>{t("common.loading")}</p> : null}
      {report.data ? <ReportBody report={report.data} /> : null}
      {generate.isError ? <ErrorMessage error={generate.error} /> : null}

      {canGenerate && report.data ? (
        <Button variant="secondary" disabled={generate.isPending} onClick={() => generate.mutate(day)}>
          {generate.isPending ? t("common.saving") : t("reports.regenerate")}
        </Button>
      ) : null}
    </div>
  );
}

function ReportBody({ report }: { report: NonNullable<ReturnType<typeof useDailyReport>["data"]> }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const asOf = new Date(report.period_end).toLocaleTimeString(i18n.language, {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: workspace.timezone,
  });
  // The server decides which sections are worth showing (all-zero ones are left out of its
  // summary); the rows are the metrics with something to say.
  const sections = report.summary.sections.map((section) => ({
    ...section,
    metrics: report.metrics.filter((metric) => metric.section === section.section && hasValue(metric)),
  }));

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        {report.is_partial ? (
          <p className="text-sm text-slate-700" data-testid="report-as-of">
            {t("reports.asOf", { time: asOf })}
          </p>
        ) : null}
        {report.has_simulated_data ? <SimulatedBadge /> : null}
      </div>

      {report.summary.empty ? (
        <EmptyState title={report.summary.text} description={t("reports.emptyHint")} />
      ) : (
        sections.map((section) => (
          <Card key={section.section} aria-labelledby={`report-section-${section.section}`}>
            <h2 id={`report-section-${section.section}`} className="text-lg font-semibold">
              {section.title}
            </h2>
            <ul className="mt-2 divide-y divide-slate-100">
              {section.metrics.map((metric) => (
                <MetricRow key={metric.key} metric={metric as ReportMetric & { value: number }} />
              ))}
            </ul>
          </Card>
        ))
      )}
    </>
  );
}

function MetricRow({ metric }: { metric: ReportMetric & { value: number } }) {
  const { t, i18n } = useTranslation();
  const label = t(`reports.metrics.${metric.key}`);
  const number = formatValue(metric.value, i18n.language);
  const shown = metric.key === "median_first_response_minutes" ? t("reports.minutes", { value: number }) : number;
  const drill = metric.link.route;
  const screen = metric.screen_link?.route;
  return (
    <li className="flex min-h-12 items-center justify-between gap-3 py-2">
      <span className="text-slate-800">{label}</span>
      <span className="flex flex-wrap items-center justify-end gap-3">
        {screen ? (
          <Link to={screen} className="text-sm text-indigo-700 underline underline-offset-2">
            {t("reports.openScreen")}
          </Link>
        ) : null}
        {drill ? (
          <Link to={drill} className={LINK} aria-label={`${label}: ${shown}`}>
            {shown}
          </Link>
        ) : (
          <span className="font-semibold">{shown}</span>
        )}
      </span>
    </li>
  );
}
