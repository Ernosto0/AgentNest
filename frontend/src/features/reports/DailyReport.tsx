import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import type { ReportMetric } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ClockIcon, AlertIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { dayLabel, isLocalDay, shiftDay, todayIn } from "./dates";
import { formatValue } from "./format";
import { useDailyReport, useGenerateReport } from "./hooks";

const LINK =
  "type-metric font-semibold text-action underline underline-offset-4 hover:text-action-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

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
  const snapshot = params.get("snapshot_id");
  const report = useDailyReport(workspace.id, day === today ? null : day, snapshot);
  const generate = useGenerateReport(workspace.id);
  const canGenerate = role === "owner" || role === "manager";

  const go = (target: string) => setParams(target === today ? {} : { date: target }, { replace: true });

  return (
    <div className="flex flex-col gap-6 max-w-4xl">
      <div className="relative overflow-hidden rounded-2xl border border-border/90 bg-gradient-to-r from-surface via-surface to-surface-subtle/50 p-6 shadow-card-modern">
        <div className="absolute top-0 right-0 h-32 w-64 bg-gradient-to-bl from-emerald-500/10 via-teal-500/5 to-transparent pointer-events-none rounded-tr-2xl" />
        <h1 className="type-page text-primary font-heading font-extrabold text-2xl sm:text-3xl tracking-tight">{t("reports.title")}</h1>
        <p className="mt-1 text-sm text-secondary max-w-xl">{t("reports.intro")}</p>
      </div>

      {/* Date Stepper */}
      <div
        className="flex items-center justify-between gap-3 rounded-2xl bg-surface p-4 border border-border/80 shadow-card-modern"
        role="group"
        aria-label={t("reports.dateLabel")}
      >
        <Button
          variant="secondary"
          onClick={() => go(shiftDay(day, -1))}
          aria-label={t("reports.previousDay")}
          className="h-10 w-10 min-w-10 p-0 text-lg font-bold rounded-xl"
        >
          ‹
        </Button>
        <div className="flex flex-col items-center text-center">
          <p className="font-heading font-bold text-lg text-primary tracking-tight" data-testid="report-day">
            {dayLabel(day, i18n.language)}
          </p>
          {day !== today ? (
            <button
              type="button"
              onClick={() => go(today)}
              className="mt-0.5 min-h-11 text-xs font-bold uppercase tracking-wider text-action underline underline-offset-2 hover:text-action-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            >
              {t("reports.backToToday")}
            </button>
          ) : (
            <p className="mt-0.5 text-xs font-semibold uppercase tracking-wider text-secondary">{t("reports.today")}</p>
          )}
        </div>
        <Button
          variant="secondary"
          disabled={day >= today}
          onClick={() => go(shiftDay(day, 1))}
          aria-label={t("reports.nextDay")}
          className="h-10 w-10 min-w-10 p-0 text-lg font-bold rounded-xl"
        >
          ›
        </Button>
      </div>

      {report.isError ? <ErrorMessage error={report.error} /> : null}
      {report.isPending ? <p className="text-sm text-secondary">{t("common.loading")}</p> : null}
      {report.data ? <ReportBody report={report.data} /> : null}
      {generate.error ? <ErrorMessage error={generate.error} /> : null}

      {canGenerate && report.data ? (
        <div>
          <Button
            variant="secondary"
            disabled={generate.isPending}
            onClick={() => generate.mutate(day, { onSuccess: () => go(day) })}
          >
            {generate.isPending ? t("common.saving") : t("reports.regenerate")}
          </Button>
        </div>
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
      {report.is_partial || report.has_simulated_data ? (
        <div className="flex flex-wrap items-center gap-2">
          {report.is_partial ? (
            <p
              className="inline-flex items-center gap-1.5 rounded-control bg-info-subtle border border-info/30 px-3 py-1 text-sm font-medium text-info"
              data-testid="report-as-of"
            >
              <ClockIcon className="text-base shrink-0" />
              {t("reports.asOf", { time: asOf })}
            </p>
          ) : null}
          {report.has_simulated_data ? <SimulatedBadge /> : null}
        </div>
      ) : null}

      {!report.evidence_complete ? (
        <p
          role="status"
          className="flex items-center gap-2.5 rounded-panel bg-attention-subtle p-3.5 text-sm text-attention border border-attention/30 shadow-xs"
        >
          <AlertIcon className="text-lg shrink-0" />
          <span>{t("reports.evidenceUnavailable")}</span>
        </p>
      ) : null}

      {report.summary.empty ? (
        <EmptyState title={report.summary.text} description={t("reports.emptyHint")} />
      ) : (
        sections.map((section) => (
          <Card key={section.section} aria-labelledby={`report-section-${section.section}`} className="p-5 md:p-6 rounded-2xl shadow-card-modern border-border/80">
            <h2 id={`report-section-${section.section}`} className="text-lg font-heading font-bold text-primary pb-3 border-b border-border/60">
              {section.title}
            </h2>
            <ul className="divide-y divide-border/60">
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

  // Comparison bar calculation
  const barWidth = Math.min(100, Math.max(14, typeof metric.value === "number" ? Math.min(metric.value * 8, 100) : 25));
  const isDanger = metric.key.includes("error") || metric.key.includes("failed");
  const isAttention = metric.key.includes("pending");

  return (
    <li className="flex flex-col gap-2 py-4">
      <div className="flex min-h-12 items-center justify-between gap-4">
        <div className="flex flex-col">
          <span className="text-primary font-medium">{label}</span>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-3.5">
          {screen ? (
            <Link
              to={screen}
              className="rounded-control border border-border bg-surface px-3 py-1 text-xs font-semibold text-action hover:bg-surface-subtle hover:text-action-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus shadow-2xs transition-colors"
            >
              {t("reports.openScreen")}
            </Link>
          ) : null}
          {drill ? (
            <Link to={drill} className={LINK} aria-label={`${label}: ${shown}`}>
              {shown}
            </Link>
          ) : (
            <span className="type-metric font-semibold text-primary">{shown}</span>
          )}
        </div>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-subtle">
        <div
          className={`h-full rounded-full transition-all ${
            isDanger ? "bg-danger" : isAttention ? "bg-attention" : "bg-action"
          }`}
          style={{ width: `${barWidth}%` }}
        />
      </div>
    </li>
  );
}
