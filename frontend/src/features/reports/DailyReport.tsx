import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import type { ReportMetric } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { PageHeader } from "@/components/Layout";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ClockIcon, AlertIcon } from "@/components/icons";
import { SimulatedBadge } from "@/components/SimulatedBadge";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { dayLabel, isLocalDay, shiftDay, todayIn } from "./dates";
import { formatValue } from "./format";
import { useDailyReport, useGenerateReport } from "./hooks";

const LINK =
  "inline-flex min-h-11 items-center text-xl tabular-nums font-semibold text-action underline underline-offset-4 hover:text-action-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

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
    <div className="flex flex-col gap-6 w-full">
      <PageHeader
        title={t("reports.title")}
        description={t("reports.intro")}
        action={canGenerate && report.data ? (
          <Button variant="secondary" pending={generate.isPending} onClick={() => generate.mutate(day, { onSuccess: () => go(day) })}>
            {generate.isPending ? t("common.saving") : t("reports.regenerate")}
          </Button>
        ) : undefined}
      />

      {/* Date Stepper */}
      <div
        className="flex items-center justify-between gap-3 border-b border-border pb-3"
        role="group"
        aria-label={t("reports.dateLabel")}
      >
        <Button
          variant="secondary"
          onClick={() => go(shiftDay(day, -1))}
          aria-label={t("reports.previousDay")}
          className="size-11 shrink-0 p-0 text-lg"
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
          className="size-11 shrink-0 p-0 text-lg"
        >
          ›
        </Button>
      </div>

      {report.isError ? <ErrorMessage error={report.error} /> : null}
      {report.isPending ? <p className="text-sm text-secondary">{t("common.loading")}</p> : null}
      {report.data ? <ReportBody report={report.data} /> : null}
      {generate.error ? <ErrorMessage error={generate.error} /> : null}
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
  const guarantee = guaranteeMetrics(report.metrics);
  const shown = (metric: ReportMetric) => !guarantee || (metric.key !== "replies_sent" && metric.key !== "unverified_values_sent");
  const sections = report.summary.sections
    .map((section) => ({
      ...section,
      metrics: report.metrics.filter((metric) => metric.section === section.section && hasValue(metric) && shown(metric)),
    }))
    .filter((section) => !guarantee || section.metrics.length > 0);

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

      {guarantee ? <GuaranteeCard replies={guarantee.replies} unverified={guarantee.unverified} /> : null}

      {report.summary.empty ? (
        <EmptyState title={report.summary.text} description={t("reports.emptyHint")} />
      ) : (
        <div className="grid min-w-0 items-start gap-5 lg:grid-cols-2">{sections.map((section) => (
          <Card key={section.section} aria-labelledby={`report-section-${section.section}`} className="min-w-0 p-5">
            <h2 id={`report-section-${section.section}`} className="text-lg font-heading font-bold text-primary pb-3 border-b border-border/60">
              {section.title}
            </h2>
            <ul className="divide-y divide-border/60">
              {section.metrics.map((metric) => (
                <MetricRow key={metric.key} metric={metric as ReportMetric & { value: number }} />
              ))}
            </ul>
          </Card>
        ))}</div>
      )}
    </>
  );
}

/** The two numbers of the guarantee, or null for a report saved before the metric existed. */
function guaranteeMetrics(metrics: ReportMetric[]) {
  const replies = metrics.find((metric) => metric.key === "replies_sent");
  const unverified = metrics.find((metric) => metric.key === "unverified_values_sent");
  return replies && unverified ? { replies, unverified } : null;
}

/**
 * "Replies sent" and "unverified values sent" (D-01). Both are shown even at zero: a zero is the
 * point. The numbers come from the server (the claim validator's stored results), never from here;
 * above zero, the number links to the replies it counts.
 */
function GuaranteeCard({ replies, unverified }: { replies: ReportMetric; unverified: ReportMetric }) {
  const { t, i18n } = useTranslation();
  const sent = replies.value ?? 0;
  const bad = unverified.value ?? 0;
  const line = (metric: ReportMetric, value: number, label: string, tone: string) => {
    const number = formatValue(value, i18n.language);
    return (
      <li className="flex min-h-12 flex-wrap items-center justify-between gap-3 py-2" data-testid={`guarantee-${metric.key}`}>
        <span className="font-medium text-primary">{label}</span>
        {value > 0 && metric.link.route ? (
          <Link to={metric.link.route} className={`${LINK} ${tone}`} aria-label={`${label}: ${number}`}>
            {number}
          </Link>
        ) : (
          <span className={`type-metric font-semibold ${tone}`}>{number}</span>
        )}
      </li>
    );
  };
  return (
    <Card aria-labelledby="report-guarantee" className="min-w-0 p-5" data-testid="report-guarantee" data-unverified={bad}>
      <h2 id="report-guarantee" className="pb-1 text-lg font-heading font-bold text-primary">{t("reports.guarantee.title")}</h2>
      <p className="pb-3 text-body text-secondary border-b border-border/60">{t("reports.guarantee.hint")}</p>
      <ul className="divide-y divide-border/60">
        {line(replies, sent, t("reports.metrics.replies_sent"), "text-primary")}
        {line(unverified, bad, bad > 0 ? t("reports.guarantee.unverifiedSome") : t("reports.guarantee.unverified"), bad > 0 ? "text-danger" : "text-success")}
      </ul>
      {bad > 0 ? <p role="status" className="mt-2 text-body font-medium text-danger">{t("reports.guarantee.alert")}</p> : null}
    </Card>
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
    <li className="py-2">
      <div className="flex min-h-12 flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col">
          <span className="text-primary font-medium">{label}</span>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-3.5">
          {screen ? (
            <Link
              to={screen}
              className="inline-flex min-h-11 items-center rounded-control px-3 py-2 text-body font-semibold text-action hover:bg-surface-subtle hover:text-action-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus shadow-2xs transition-colors"
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
    </li>
  );
}
