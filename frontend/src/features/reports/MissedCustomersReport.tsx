import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import type { MissedCustomerReport, MissedMetric } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { ErrorMessage } from "@/components/ErrorMessage";
import { ClockIcon } from "@/components/icons";
import { PageHeader } from "@/components/Layout";
import { useCurrentWorkspace } from "@/features/workspaces/context";
import { isLocalDay, shiftDay, todayIn } from "./dates";
import { formatValue } from "./format";
import { useMissedReport } from "./missedHooks";
import { mondayOf, weekLabel } from "./weeks";

const LINK =
  "inline-flex min-h-11 items-center text-xl tabular-nums font-semibold text-action underline underline-offset-4 hover:text-action-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";
const TEXT_LINK =
  "inline-flex min-h-11 items-center text-sm font-semibold text-action underline underline-offset-2 hover:text-action-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

/** The order of the numbers on the page; the server decides the values. */
const METRIC_ORDER = [
  "after_hours_dms",
  "after_hours_price_answers",
  "answered_questions",
  "unanswered_conversations",
  "first_reply_median_minutes",
] as const;

/**
 * The weekly missed-customer report (D-03): what the assistant did for customers who wrote
 * outside opening hours, in lira. Every lira figure is an estimate shown with its formula and
 * every input; with no verified hours or price only the counts are shown.
 */
export function MissedCustomersReport() {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const [params, setParams] = useSearchParams();
  const thisWeek = mondayOf(todayIn(workspace.timezone));
  const requested = params.get("week");
  // Nothing after this week: a later date falls back to it.
  const week = isLocalDay(requested) && mondayOf(requested) <= thisWeek ? mondayOf(requested) : thisWeek;
  const report = useMissedReport(workspace.id, week === thisWeek ? null : week);
  const go = (target: string) => setParams(target === thisWeek ? {} : { week: target }, { replace: true });

  return (
    <div className="flex flex-col gap-6 w-full">
      <PageHeader title={t("reports.missed.title")} description={t("reports.missed.intro")} />

      <div className="flex items-center justify-between gap-3 border-b border-border pb-3" role="group" aria-label={t("reports.missed.weekLabel")}>
        <Button variant="secondary" onClick={() => go(shiftDay(week, -7))} aria-label={t("reports.missed.previousWeek")} className="size-11 shrink-0 p-0 text-lg">
          ‹
        </Button>
        <div className="flex flex-col items-center text-center">
          <p className="font-heading font-bold text-lg text-primary tracking-tight" data-testid="missed-week">
            {weekLabel(week, i18n.language)}
          </p>
          {week !== thisWeek ? (
            <button
              type="button"
              onClick={() => go(thisWeek)}
              className="mt-0.5 min-h-11 text-xs font-bold uppercase tracking-wider text-action underline underline-offset-2 hover:text-action-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            >
              {t("reports.missed.backToThisWeek")}
            </button>
          ) : (
            <p className="mt-0.5 text-xs font-semibold uppercase tracking-wider text-secondary">{t("reports.missed.thisWeek")}</p>
          )}
        </div>
        <Button variant="secondary" disabled={week >= thisWeek} onClick={() => go(shiftDay(week, 7))} aria-label={t("reports.missed.nextWeek")} className="size-11 shrink-0 p-0 text-lg">
          ›
        </Button>
      </div>

      {report.isError ? <ErrorMessage error={report.error} /> : null}
      {report.isPending ? <p className="text-sm text-secondary">{t("common.loading")}</p> : null}
      {report.data ? <ReportBody report={report.data} /> : null}
      <p className="text-sm text-secondary">{t("reports.missed.simulatedNote")}</p>
    </div>
  );
}

function ReportBody({ report }: { report: MissedCustomerReport }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const asOf = new Date(report.period_end).toLocaleString(i18n.language, {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: workspace.timezone,
  });
  const byKey = new Map(report.metrics.map((metric) => [metric.key, metric]));
  const empty = report.metrics.every((metric) => !metric.value);

  return (
    <>
      {report.is_partial ? (
        <p
          className="inline-flex w-fit items-center gap-1.5 rounded-control bg-info-subtle border border-info/30 px-3 py-1 text-sm font-medium text-info"
          data-testid="missed-as-of"
        >
          <ClockIcon className="text-base shrink-0" />
          {t("reports.missed.inProgress", { time: asOf })}
        </p>
      ) : null}

      <EstimateCard report={report} />

      {empty ? (
        <EmptyState title={t("reports.missed.empty")} description={t("reports.missed.emptyHint")} />
      ) : null}

      <Card aria-labelledby="missed-numbers" className="min-w-0 p-5">
        <h2 id="missed-numbers" className="text-lg font-heading font-bold text-primary pb-3 border-b border-border/60">
          {t("reports.missed.numbersTitle")}
        </h2>
        <ul className="divide-y divide-border/60">
          {METRIC_ORDER.map((key) => {
            const metric = byKey.get(key);
            return metric ? <MetricRow key={key} metric={metric} hoursAvailable={report.hours_available} /> : null;
          })}
        </ul>
      </Card>
    </>
  );
}

function MetricRow({ metric, hoursAvailable }: { metric: MissedMetric; hoursAvailable: boolean }) {
  const { t, i18n } = useTranslation();
  const label = t(`reports.missed.metrics.${metric.key}`);
  const isMinutes = metric.key === "first_reply_median_minutes";
  const show = (value: number) => {
    const number = formatValue(value, i18n.language);
    return isMinutes ? t("reports.minutes", { value: number }) : number;
  };
  const unknown = metric.value === null && !hoursAvailable;
  const drill = metric.value ? metric.link?.route : null;

  return (
    <li className="py-2" data-testid={`missed-${metric.key}`}>
      <div className="flex min-h-12 flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-col">
          <span className="text-primary font-medium">{label}</span>
          {metric.previous_value !== null && metric.previous_value !== undefined ? (
            <span className="text-xs text-secondary">{t("reports.missed.previous", { value: show(metric.previous_value) })}</span>
          ) : null}
        </div>
        {unknown ? (
          <span className="text-secondary" title={t("reports.missed.needsHours")}>
            {t("reports.missed.unknown")}
          </span>
        ) : metric.value === null ? (
          <span className="text-secondary">{t("reports.missed.noData")}</span>
        ) : drill ? (
          <Link to={drill} className={LINK} aria-label={`${label}: ${show(metric.value)}`}>
            {show(metric.value)}
          </Link>
        ) : (
          <span className="type-metric font-semibold text-primary">{show(metric.value)}</span>
        )}
      </div>
    </li>
  );
}

/** The lira estimate, never without its formula and inputs; counts only when it cannot be made. */
function EstimateCard({ report }: { report: MissedCustomerReport }) {
  const { t, i18n } = useTranslation();
  const { workspace } = useCurrentWorkspace();
  const base = `/w/${workspace.id}/more/knowledge`;
  const estimate = report.estimate;
  const money = (value: string) =>
    new Intl.NumberFormat(i18n.language, { style: "currency", currency: estimate.currency }).format(Number(value));
  const rate = new Intl.NumberFormat(i18n.language, { style: "percent", maximumFractionDigits: 1 }).format(Number(estimate.conversion_rate));

  return (
    <Card aria-labelledby="missed-estimate-title" className="min-w-0 p-5" data-testid="missed-estimate" data-status={estimate.status}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="missed-estimate-title" className="text-lg font-heading font-bold text-primary">
          {t("reports.missed.estimate.title")}
        </h2>
        <span className="rounded-control border border-border bg-surface-subtle px-2 py-0.5 text-xs font-semibold text-secondary">
          {t("reports.missed.estimate.badge")}
        </span>
      </div>

      {estimate.status === "ok" && estimate.amount !== null && estimate.median_price !== null ? (
        <>
          <p className="mt-3 text-3xl font-heading font-bold tabular-nums text-primary" data-testid="missed-amount">
            {money(estimate.amount)}
          </p>
          <div className="mt-3 rounded-control border border-border/70 bg-surface-subtle p-3">
            <p className="text-sm font-semibold text-primary">{t("reports.missed.estimate.formulaTitle")}</p>
            <p className="mt-1 text-body text-primary" data-testid="missed-formula">
              {t("reports.missed.estimate.formula", {
                questions: formatValue(estimate.price_questions ?? 0, i18n.language),
                rate,
                price: money(estimate.median_price),
                amount: money(estimate.amount),
              })}
            </p>
            <p className="mt-2 text-sm text-secondary">{t("reports.missed.estimate.rateNote", { rate })}</p>
          </div>
          <h3 className="mt-4 text-sm font-semibold text-primary">{t("reports.missed.estimate.inputsTitle")}</h3>
          <p className="text-sm text-secondary" data-testid="missed-price-count">
            {t("reports.missed.estimate.medianOf", { count: estimate.price_count })}
            {estimate.price_count > estimate.price_inputs.length
              ? ` ${t("reports.missed.estimate.showing", { shown: estimate.price_inputs.length, count: estimate.price_count })}`
              : ""}
          </p>
          <ul className="mt-1 divide-y divide-border/60" data-testid="missed-price-inputs">
            {estimate.price_inputs.map((price) => (
              <li key={price.key} className="flex flex-wrap items-center justify-between gap-2 py-1.5 text-body">
                <span className="text-primary">{price.label}</span>
                <span className="tabular-nums text-secondary">
                  {money(price.amount)}
                  {price.unit ? ` / ${t(`reports.missed.unit.${price.unit}`, { defaultValue: price.unit })}` : ""}
                </span>
              </li>
            ))}
          </ul>
          <Link to={`${base}/pricing`} className={`${TEXT_LINK} mt-1`}>
            {t("reports.missed.estimate.checkPrices")}
          </Link>
        </>
      ) : (
        <div className="mt-3 flex flex-col gap-1" data-testid="missed-counts-only">
          <p className="text-body text-primary">
            {estimate.status === "hours_missing" ? t("reports.missed.estimate.hoursMissing") : t("reports.missed.estimate.noPrice")}
          </p>
          <Link to={estimate.status === "hours_missing" ? `${base}/hours` : `${base}/pricing`} className={TEXT_LINK}>
            {estimate.status === "hours_missing" ? t("reports.missed.estimate.addHours") : t("reports.missed.estimate.addPrices")}
          </Link>
        </div>
      )}
    </Card>
  );
}
